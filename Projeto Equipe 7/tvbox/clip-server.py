#!/usr/bin/env python3
# Serviço de clipes (porta 9997):
#   /cameras                        -> câmeras detectadas (JSON)
#   /clip?path=&start=&duration=    -> trecho em MP4 navegável (+faststart)
#
# O app pede trechos alinhados numa grade de tempo, então o mesmo minuto é
# sempre a mesma chave: o remux roda uma única vez e as próximas requisições
# são servidas direto do cache em disco.
import hashlib, os, subprocess, tempfile, threading, urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MEDIAMTX = "http://localhost:9996/get"
CAMERAS_JSON = "/opt/secbox/cameras.json"
CACHE_DIR = "/opt/secbox-clip/cache"
CACHE_MAX = 1024 * 1024 * 1024  # teto do cache em disco: 1 GB
SETTLE = 15  # só entra no cache o trecho que já terminou há esse tempo

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
        if u.path == "/cameras":
            try:
                data = open(CAMERAS_JSON, "rb").read()
            except Exception:
                data = b'{"cameras":[],"connected":0,"limit":0,"exceeded":false}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
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


ThreadingHTTPServer(("0.0.0.0", 9997), Handler).serve_forever()
