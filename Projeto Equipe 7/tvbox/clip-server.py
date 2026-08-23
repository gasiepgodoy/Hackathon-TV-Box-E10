#!/usr/bin/env python3
# Serviço de clipes e configuração das câmeras (porta 9997):
#   /cameras                        -> câmeras detectadas (JSON)
#   /clip?path=&start=&duration=    -> trecho em MP4 navegável (+faststart)
#   /storage                        -> espaço, uso por câmera e autonomia estimada
#   /settings  (GET | POST)         -> qualidade e retenção de cada câmera
#   /health                         -> vivo? autenticação ligada? (sempre aberto)
#
# AUTENTICAÇÃO: se "api_token" existir no config.json, toda rota (menos /health)
# exige `Authorization: Bearer <token>` ou `?token=`. Sem token configurado o
# serviço fica aberto e avisa no log — era o comportamento do piloto atrás da
# Tailscale, e é inaceitável assim que a porta for publicada na internet, porque
# /settings ESCREVE a configuração das câmeras.
#
# O app pede trechos alinhados numa grade de tempo, então o mesmo minuto é
# sempre a mesma chave: o remux roda uma única vez e as próximas requisições
# são servidas direto do cache em disco.
import hashlib, hmac, json, os, subprocess, tempfile, threading, urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MEDIAMTX = "http://localhost:9996/get"
CONFIG_JSON = "/opt/secbox/config.json"
CAMERAS_JSON = "/opt/secbox/cameras.json"
SETTINGS_JSON = "/opt/secbox/camera-settings.json"
GEN_CAMERAS = "/opt/secbox/gen-cameras.py"
REC_DIR = "/opt/mediamtx/rec"
CACHE_DIR = "/opt/secbox-clip/cache"
CACHE_MAX = 1024 * 1024 * 1024  # teto do cache em disco: 1 GB
SETTLE = 15  # só entra no cache o trecho que já terminou há esse tempo
DISK_LIMIT = 0.85  # acima disso o sd-guard começa a apagar gravação

def _read_token():
    try:
        return (json.load(open(CONFIG_JSON)).get("api_token") or "").strip()
    except Exception:
        return ""


TOKEN = _read_token()

os.makedirs(CACHE_DIR, exist_ok=True)
_locks = {}
_locks_guard = threading.Lock()


def _lock_for(key):
    # Evita que duas requisições do mesmo trecho rodem o ffmpeg em paralelo.
    with _locks_guard:
        lk = _locks.get(key)
        if lk is None:
            lk = _locks[key] = threading.Lock()
        return lk


def _ok(p):
    try:
        return os.path.getsize(p) > 0
    except OSError:
        return False


def _evict():
    # Mantém o cache abaixo do teto, descartando os menos usados primeiro.
    try:
        files, total = [], 0
        for n in os.listdir(CACHE_DIR):
            p = os.path.join(CACHE_DIR, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            files.append((st.st_mtime, st.st_size, p))
            total += st.st_size
        if total <= CACHE_MAX:
            return
        files.sort()
        for _, size, p in files:
            if total <= CACHE_MAX:
                break
            try:
                os.unlink(p)
                total -= size
            except OSError:
                pass
    except OSError:
        pass


def _finished(start, dur):
    # Trecho ainda em gravação sai incompleto: serve, mas não cacheia.
    try:
        t = datetime.fromisoformat(start.replace("Z", "+00:00"))
    except ValueError:
        return False
    return t.timestamp() + dur < datetime.now(timezone.utc).timestamp() - SETTLE


def _dir_size(p):
    total = 0
    for root, _, files in os.walk(p):
        for n in files:
            try:
                total += os.path.getsize(os.path.join(root, n))
            except OSError:
                pass
    return total


def _storage():
    # Autonomia = quanto ainda cabe de gravação dividido pelo consumo somado.
    # O orçamento não é só o espaço livre: a gravação antiga é descartável, o
    # que não pode passar é o teto em que o sd-guard começa a apagar.
    st = os.statvfs("/")
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used = total - st.f_bfree * st.f_frsize
    per, rec = {}, 0
    try:
        for n in sorted(os.listdir(REC_DIR)):
            p = os.path.join(REC_DIR, n)
            if os.path.isdir(p):
                per[n] = _dir_size(p)
                rec += per[n]
    except OSError:
        pass
    budget = max(0, int(total * DISK_LIMIT) - (used - rec))
    kbps = 0
    try:
        kbps = sum(int(c.get("kbps", 0))
                   for c in json.load(open(CAMERAS_JSON)).get("cameras", []))
    except Exception:
        pass
    hours = budget * 8 / (kbps * 1000) / 3600 if kbps else 0
    # Sem codificador por hardware, a CPU é o recurso mais apertado: a carga
    # acima do número de núcleos significa captura atrasando e replay lento.
    try:
        load = os.getloadavg()[0]
    except OSError:
        load = 0.0
    return {"total": total, "free": free, "used": used, "rec_used": rec,
            "budget": budget, "per_camera": per, "kbps_total": kbps,
            "hours": round(hours, 1), "load": round(load, 2),
            "cpus": os.cpu_count() or 1}


def _load_settings():
    # {"cameras": {<id>: {...}}, "notify": {...}}; aceita o formato antigo, em
    # que o arquivo inteiro era o mapa de câmeras.
    try:
        s = json.load(open(SETTINGS_JSON))
    except Exception:
        s = {}
    if "cameras" not in s:
        s = {"cameras": s}
    s.setdefault("cameras", {})
    s.setdefault("notify", {})
    return s


def _apply_settings(new):
    # Grava as preferências e manda o gerador reescrever o mediamtx.yml.
    cur = _load_settings()
    try:
        meta = json.load(open(CAMERAS_JSON))
        valid = set(meta.get("presets", {}))
        sens = set(meta.get("sensitivities", []))
        fpss = set(meta.get("fps_options", []))
    except Exception:
        valid, sens, fpss = set(), set(), set()
    valid = valid or {"alta", "media", "baixa"}
    sens = sens or {"alta", "media", "baixa"}
    fpss = fpss or {3, 5, 10, 15}
    for k, v in (new.get("notify") or {}).items():
        if k in ("motion", "camera_offline"):
            cur["notify"][k] = bool(v)
    cams = new.get("cameras") if isinstance(new.get("cameras"), dict) else new
    for cid, cfg in (cams or {}).items():
        if cid == "notify" or not isinstance(cfg, dict):
            continue
        entry = cur["cameras"].get(cid, {})
        q = cfg.get("quality")
        if q in valid:
            entry["quality"] = q
        if cfg.get("sensitivity") in sens:
            entry["sensitivity"] = cfg["sensitivity"]
        if isinstance(cfg.get("motion"), bool):
            entry["motion"] = cfg["motion"]
        try:
            if int(cfg["fps"]) in fpss:
                entry["fps"] = int(cfg["fps"])
        except (KeyError, TypeError, ValueError):
            pass
        try:
            r = int(cfg.get("retention_h", entry.get("retention_h", 24)))
            entry["retention_h"] = max(1, min(r, 720))
        except (TypeError, ValueError):
            pass
        cur["cameras"][cid] = entry
    tmp = SETTINGS_JSON + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cur, f)
    os.replace(tmp, SETTINGS_JSON)
    subprocess.run(["python3", GEN_CAMERAS], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=60)
    return cur


def _build(src):
    # Remuxa o trecho para MP4 num arquivo temporário; None se falhar.
    fd, tmp = tempfile.mkstemp(suffix=".mp4", dir=CACHE_DIR)
    os.close(fd)
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-c", "copy",
             "-movflags", "+faststart", "-f", "mp4", tmp],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        if r.returncode != 0 or not _ok(tmp):
            os.unlink(tmp)
            return None
        return tmp
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return None


class Handler(BaseHTTPRequestHandler):
    def _autorizado(self):
        # Sem token configurado, mantém o comportamento antigo: o piloto roda
        # atrás da Tailscale e travar tudo num upgrade deixaria o app cego.
        if not TOKEN:
            return True
        cab = self.headers.get("Authorization", "")
        if cab.startswith("Bearer "):
            dado = cab[7:]
        else:
            # O player baixa o clipe pela URL; aceitar ?token= evita ter de
            # injetar cabeçalho em todo caminho de download do vídeo.
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            dado = q.get("token", [""])[0]
        # compare_digest: comparação de tempo constante, para o tempo de
        # resposta não revelar quantos caracteres do token estão certos.
        return hmac.compare_digest(dado, TOKEN)

    def _nega(self):
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "24")
        self.end_headers()
        self.wfile.write(b'{"error":"unauthorized"}')

    def _send_json(self, obj):
        data = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self._autorizado():
            self._nega()
            return
        if urllib.parse.urlparse(self.path).path != "/settings":
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
        except Exception:
            self.send_error(400)
            return
        try:
            cur = _apply_settings(body)
        except Exception:
            self.send_error(500)
            return
        self._send_json({"ok": True, "settings": cur, "storage": _storage()})

    def _send_file(self, p):
        try:
            size = os.path.getsize(p)
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with open(p, "rb") as f:
                while True:
                    b = f.read(65536)
                    if not b:
                        break
                    self.wfile.write(b)
        except Exception:
            pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        # /health fica aberto de propósito: é o que permite ao monitoramento
        # descobrir que o serviço subiu SEM token, que é o estado perigoso.
        if u.path == "/health":
            self._send_json({"ok": True, "auth": bool(TOKEN)})
            return
        if not self._autorizado():
            self._nega()
            return
        if u.path == "/cameras":
            try:
                data = open(CAMERAS_JSON, "rb").read()
            except Exception:
                data = b'{"cameras":[],"connected":0,"limit":0,"exceeded":false}'
            self._send_json(data)
            return
        if u.path == "/storage":
            self._send_json(_storage())
            return
        if u.path == "/settings":
            try:
                data = open(SETTINGS_JSON, "rb").read()
            except Exception:
                data = b"{}"
            self._send_json(data)
            return
        if u.path != "/clip":
            self.send_error(404)
            return
        q = urllib.parse.parse_qs(u.query)
        start = q.get("start", [""])[0]
        path = q.get("path", ["cam"])[0]
        try:
            dur = min(float(q.get("duration", ["30"])[0]), 1800.0)
        except ValueError:
            self.send_error(400)
            return
        if not start or not path.replace("_", "").isalnum():
            self.send_error(400)
            return

        key = hashlib.sha1(f"{path}|{start}|{dur}".encode()).hexdigest()
        dest = os.path.join(CACHE_DIR, key + ".mp4")
        cacheable = _finished(start, dur)
        if cacheable and _ok(dest):
            os.utime(dest, None)  # marca uso, para a eviction por idade
            self._send_file(dest)
            return

        serve, drop = None, None
        with _lock_for(key):
            if cacheable and _ok(dest):  # outra thread gerou enquanto esperava
                serve = dest
            else:
                src = MEDIAMTX + "?" + urllib.parse.urlencode(
                    {"path": path, "start": start, "duration": str(dur)})
                tmp = _build(src)
                if tmp is None:
                    self.send_error(500)
                    return
                if cacheable:
                    try:
                        os.replace(tmp, dest)
                        _evict()
                        serve = dest
                    except OSError:
                        serve, drop = tmp, tmp
                else:
                    serve, drop = tmp, tmp
        try:
            self._send_file(serve)
        finally:
            if drop:
                try:
                    os.unlink(drop)
                except OSError:
                    pass

    def log_message(self, *a):
        pass


if TOKEN:
    print("clip-server 9997: autenticacao LIGADA", flush=True)
else:
    print("clip-server 9997: SEM AUTENTICACAO — qualquer um que alcance esta "
          "porta le as cameras e ESCREVE a configuracao. Defina 'api_token' em "
          + CONFIG_JSON + " antes de publicar na internet.", flush=True)

ThreadingHTTPServer(("0.0.0.0", 9997), Handler).serve_forever()
