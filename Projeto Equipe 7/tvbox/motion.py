#!/usr/bin/env python3
# Detecção de movimento por câmera: lê o RTSP de cada uma em baixa resolução
# (cinza), compara quadros consecutivos e publica um evento quando a diferença
# passa do limiar. Sem OpenCV (Python puro).
#
# Cada câmera tem seu liga/desliga e sua sensibilidade em camera-settings.json;
# um supervisor acompanha cameras.json e sobe/derruba os detectores conforme as
# câmeras aparecem, somem ou mudam de configuração.
import json, os, time, subprocess, threading
from urllib.parse import quote
import paho.mqtt.client as mqtt

BASE = "/opt/secbox"
dev = json.load(open(f"{BASE}/device.json"))
cfg = json.load(open(f"{BASE}/config.json"))
DEVICE_ID = dev["device_id"]
TOPIC = f"devices/{DEVICE_ID}/alarme/event"
# Gatilho local da sirene. Escrito em disco, e nao publicado no broker, porque
# o MQTT sai pela internet: com a rede fora, o movimento seria detectado e a
# sirene nunca tocaria -- e cortar a internet viraria a forma de desarmar.
TRIGGER_FILE = f"{BASE}/alarme-trigger"
# Registro que o rec-prune.py le para decidir qual gravacao vale guardar.
# Duas coisas sao anotadas: o movimento ('m') e, de tempos em tempos, a marca
# de que a camera esta sendo vigiada ('v'). A segunda existe porque "nao ha
# movimento anotado" e "ninguem estava olhando" sao estados diferentes, e so
# o primeiro autoriza apagar gravacao.
MOTION_LOG = f"{BASE}/motion-log"
MARK = 300        # intervalo entre marcas de vigilancia (o podador conhece)
LOG_MAX = 1024 * 1024
LOG_KEEP = 20000  # ~34 dias de marcas com duas cameras
CAMERAS_JSON = f"{BASE}/cameras.json"
SETTINGS_JSON = f"{BASE}/camera-settings.json"
_MTX_PASS = (cfg.get("mtx_internal_pass") or "").strip()
_base = cfg.get("rtsp_base", "rtsp://localhost:8554")
# O MediaMTX exige credencial até de dentro da box: não há exceção por IP,
# porque o túnel faria todo tráfego externo parecer local.
RTSP_BASE = (_base.replace("://", "://box:%s@" % quote(_MTX_PASS, safe=""), 1)
             if _MTX_PASS else _base)
COOLDOWN = cfg.get("motion_cooldown", 30)
SENS = {"alta": 8, "media": 12, "baixa": 20}  # limiar: menor = mais sensível
W, H = 160, 90
FS = W * H

try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1,
                         client_id=f"motion-{DEVICE_ID}")
except (AttributeError, TypeError):
    client = mqtt.Client(client_id=f"motion-{DEVICE_ID}")
client.username_pw_set(cfg["broker_user"], cfg["broker_pass"])
client.connect_async(cfg["broker_host"], int(cfg["broker_port"]), keepalive=60)
client.loop_start()


def load_settings():
    try:
        s = json.load(open(SETTINGS_JSON))
    except Exception:
        s = {}
    if "cameras" not in s:  # formato antigo: o arquivo todo era o mapa
        s = {"cameras": s}
    s.setdefault("cameras", {})
    s.setdefault("notify", {})
    return s


_log_lock = threading.Lock()


def anotar(path, tipo, quando=None):
    """Acrescenta uma linha ao registro de movimento.

    Escritor unico (sempre sob este lock), o que torna seguro o corte por
    tamanho: nenhum append se perde entre a leitura e a troca do arquivo.
    O corte descarta as linhas mais antigas dos DOIS tipos junto, entao um
    periodo ou sobrevive inteiro ou some inteiro -- e um periodo que sumiu
    vira "nao vigiado", que preserva a gravacao em vez de apaga-la.
    """
    with _log_lock:
        try:
            with open(MOTION_LOG, "a") as f:
                f.write("%d %s %s\n" % (int(quando or time.time()), path, tipo))
            if os.path.getsize(MOTION_LOG) > LOG_MAX:
                linhas = open(MOTION_LOG).readlines()[-LOG_KEEP:]
                tmp = MOTION_LOG + ".tmp"
                with open(tmp, "w") as f:
                    f.writelines(linhas)
                os.replace(tmp, MOTION_LOG)
        except OSError as e:
            print("registro de movimento falhou:", e, flush=True)


def detect(path, name, thresh, stop):
    cmd = ["ffmpeg", "-loglevel", "quiet", "-rtsp_transport", "tcp",
           "-i", f"{RTSP_BASE}/{path}",
           "-vf", f"fps=3,scale={W}:{H},format=gray", "-f", "rawvideo", "pipe:1"]
    prev, last = None, 0.0
    while not stop.is_set():
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL)
        while not stop.is_set():
            buf = p.stdout.read(FS)
            if len(buf) < FS:  # fluxo caiu: sai e tenta de novo
                break
            if prev is not None:
                s = n = 0
                for i in range(0, FS, 7):  # amostra 1 de cada 7 pixels
                    d = buf[i] - prev[i]
                    s += d if d >= 0 else -d
                    n += 1
                score = s / n
                now = time.time()
                if score > thresh and now - last > COOLDOWN:
                    last = now
                    # O gatilho vem PRIMEIRO: publicar pode bloquear ou
                    # falhar com a rede caida, e a sirene nao pode depender
                    # disso. Quem decide se toca e o alarm.py, conforme o
                    # estado armado.
                    try:
                        open(TRIGGER_FILE, "w").write(str(int(time.time())))
                    except OSError as e:
                        print("gatilho falhou:", e, flush=True)
                    anotar(path, "m", now)
                    client.publish(TOPIC, json.dumps(
                        {"type": "movimento", "camera": path, "name": name,
                         "score": round(score, 1)}), qos=1)
                    print("Movimento em %s (score %.1f)" % (name, score),
                          flush=True)
            prev = buf
        try:
            p.terminate()
        except Exception:
            pass
        prev = None
        if not stop.is_set():
            time.sleep(2)


def wanted():
    # Quais detectores deveriam estar rodando agora: path -> (nome, limiar).
    st = load_settings()
    if not st["notify"].get("motion", True):
        return {}
    try:
        cams = json.load(open(CAMERAS_JSON)).get("cameras", [])
    except Exception:
        return {}
    out = {}
    for c in cams:
        cs = st["cameras"].get(c.get("id", ""), {})
        if not cs.get("motion", True):
            continue
        out[c["path"]] = (c.get("name", c["path"]),
                          SENS.get(cs.get("sensitivity", "media"), 12))
    return out


workers = {}  # path -> (stop_event, assinatura)
ultima_marca = time.time()  # a marca de estreia de cada detector e escrita
                            # ao cria-lo; a periodica so entra 5 min depois
print("Deteccao de movimento iniciada", flush=True)
while True:
    want = wanted()
    for path, (stop, sig) in list(workers.items()):
        if want.get(path) != sig:  # saiu, foi desligada ou mudou o limiar
            stop.set()
            del workers[path]
            print("Detector parado: %s" % path, flush=True)
    for path, sig in want.items():
        if path not in workers:
            stop = threading.Event()
            threading.Thread(target=detect, args=(path, sig[0], sig[1], stop),
                             daemon=True).start()
            workers[path] = (stop, sig)
            anotar(path, "v")  # a vigilancia comeca agora, nao na proxima marca
            print("Detector ativo: %s (limiar %d)" % (sig[0], sig[1]), flush=True)
    agora = time.time()
    if workers and agora - ultima_marca >= MARK:
        ultima_marca = agora
        for path in workers:
            anotar(path, "v", agora)
    time.sleep(10)
