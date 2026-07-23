#!/usr/bin/env python3
# Serviço de remux de clipes: recebe start+duration, puxa o trecho do playback
# do MediaMTX (fMP4) e remuxa para MP4 navegável (moov na frente / +faststart),
# resolvendo a linha do tempo com seek no app. Porta 9997.
import subprocess, tempfile, os, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MEDIAMTX = "http://localhost:9996/get"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path != "/clip":
            self.send_error(404); return
        q = urllib.parse.parse_qs(u.query)
        start = q.get("start", [""])[0]
        try:
            dur = min(float(q.get("duration", ["30"])[0]), 1800.0)
        except ValueError:
            self.send_error(400); return
        if not start:
            self.send_error(400); return
        src = MEDIAMTX + "?" + urllib.parse.urlencode(
            {"path": "cam", "start": start, "duration": str(dur)})
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp.close()
        try:
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", src, "-c", "copy",
                 "-movflags", "+faststart", "-f", "mp4", tmp.name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            if r.returncode != 0 or os.path.getsize(tmp.name) == 0:
                self.send_error(500); return
            size = os.path.getsize(tmp.name)
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with open(tmp.name, "rb") as f:
                while True:
                    b = f.read(65536)
                    if not b: break
                    self.wfile.write(b)
        except Exception:
            pass
        finally:
            try: os.unlink(tmp.name)
            except Exception: pass
    def log_message(self, *a):
        pass

ThreadingHTTPServer(("0.0.0.0", 9997), Handler).serve_forever()
