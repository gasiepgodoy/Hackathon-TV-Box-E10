#!/usr/bin/env python3
"""
AquaFL Web & Benchmark API Server
Servidor HTTP para telemetria em tempo real, artefatos estáticos e orquestração do benchmark.
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = int(os.environ.get("PORT", 3000))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE_DIR = os.path.join(BASE_DIR, "dados", "edgebox")
STATUS_FILE_PATH = os.path.join(STATUS_FILE_DIR, "benchmark_status.json")

# Estado global em memória do benchmark
benchmark_state = {
    "running": False,
    "current_model": None,
    "completed_models": [],
    "started_at": None,
    "pid": None
}

current_process = None

def save_benchmark_state_to_disk():
    try:
        os.makedirs(STATUS_FILE_DIR, exist_ok=True)
        with open(STATUS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(benchmark_state, f, indent=2)
    except Exception as e:
        print(f"[AquaFL Server] Erro ao salvar status em disco: {e}", file=sys.stderr)

def load_benchmark_state_from_disk():
    global benchmark_state
    if os.path.exists(STATUS_FILE_PATH):
        try:
            with open(STATUS_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    benchmark_state.update(data)
        except Exception as e:
            print(f"[AquaFL Server] Erro ao carregar status do disco: {e}", file=sys.stderr)

def check_process_status():
    global current_process, benchmark_state
    if current_process is not None:
        poll_res = current_process.poll()
        if poll_res is not None:
            # Processo terminou
            current_process = None
            benchmark_state["running"] = False
            benchmark_state["pid"] = None
            save_benchmark_state_to_disk()
    elif benchmark_state["running"]:
        # Se não há objeto de processo local, verifica se PID salvo ainda existe
        pid = benchmark_state.get("pid")
        if pid:
            try:
                # Checagem de processo no Linux / Windows
                if sys.platform != "win32":
                    os.kill(pid, 0)
                else:
                    # No Windows, verifica via tasklist ou ctypes
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(1, False, pid)
                    if handle == 0:
                        benchmark_state["running"] = False
                        benchmark_state["pid"] = None
                        save_benchmark_state_to_disk()
                    else:
                        kernel32.CloseHandle(handle)
            except OSError:
                benchmark_state["running"] = False
                benchmark_state["pid"] = None
                save_benchmark_state_to_disk()

class AquaFLRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def _send_json_response(self, data, status_code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        # Rota de status do benchmark
        if self.path.startswith("/api/benchmark/status"):
            check_process_status()
            self._send_json_response(benchmark_state)
            return

        # Servir arquivos estáticos padrão
        super().do_GET()

    def do_POST(self):
        global current_process, benchmark_state

        if self.path.startswith("/api/train"):
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length).decode("utf-8")
            
            try:
                payload = json.loads(post_data) if post_data else {}
            except Exception:
                payload = {}

            model_key = payload.get("model", "linear").lower()
            epochs = payload.get("epochs", 10)
            batch_size = payload.get("batch_size", 32)
            learning_rate = payload.get("learning_rate", 0.001)

            # Atualiza o modelo concluído anterior se estiver mudando
            prev_model = benchmark_state.get("current_model")
            if prev_model and prev_model != model_key and prev_model not in benchmark_state["completed_models"]:
                benchmark_state["completed_models"].append(prev_model)

            benchmark_state["running"] = True
            benchmark_state["current_model"] = model_key
            benchmark_state["started_at"] = datetime.utcnow().isoformat() + "Z"

            # Comando de treino
            cmd = f"python3 -m aquafl.models.train --model {model_key} --epochs {epochs} --batch_size {batch_size} --lr {learning_rate}"
            
            # Se houver script executável na TV Box, dispara subprocesso
            try:
                # Verifica se o script de treino real existe no path
                train_script = os.path.join(BASE_DIR, "train_model.py")
                if os.path.exists(train_script):
                    current_process = subprocess.Popen([sys.executable, train_script, "--model", model_key])
                    benchmark_state["pid"] = current_process.pid
                else:
                    # Simulação / fallback sem subprocesso bloqueante
                    current_process = None
                    benchmark_state["pid"] = os.getpid()
            except Exception as e:
                print(f"[AquaFL Server] Erro ao iniciar subprocesso de treino: {e}", file=sys.stderr)

            save_benchmark_state_to_disk()

            response_data = {
                "status": "training_started",
                "model": model_key,
                "command": cmd,
                "timestamp": benchmark_state["started_at"],
                "benchmark_state": benchmark_state
            }
            self._send_json_response(response_data, 200)
            return

        if self.path.startswith("/api/benchmark/reset"):
            benchmark_state["running"] = False
            benchmark_state["current_model"] = None
            benchmark_state["completed_models"] = []
            benchmark_state["started_at"] = None
            benchmark_state["pid"] = None
            save_benchmark_state_to_disk()
            self._send_json_response({"status": "reset", "benchmark_state": benchmark_state}, 200)
            return

        self._send_json_response({"error": "Endpoint não encontrado"}, 404)

def run(port=PORT):
    load_benchmark_state_from_disk()
    server_address = ("", port)
    httpd = HTTPServer(server_address, AquaFLRequestHandler)
    print(f"[AquaFL Server] Servidor ativo em http://0.0.0.0:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[AquaFL Server] Encerrando servidor.")
        httpd.server_close()

if __name__ == "__main__":
    run()
