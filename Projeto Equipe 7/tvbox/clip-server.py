#!/usr/bin/env python3
# Serviço de clipes e configuração das câmeras (porta 9997):
#   /cameras                        -> câmeras detectadas (JSON)
#   /clip?path=&start=&duration=    -> trecho em MP4 navegável (+faststart)
#   /list?path=                     -> trechos gravados (repassa do MediaMTX)
#   /storage                        -> espaço, uso por câmera e autonomia estimada
#   /settings  (GET | POST)         -> qualidade, retenção e modo de gravação
#   /alarm     (GET | POST)         -> armar/desarmar o disparo por movimento
#   /forget    (POST)               -> esquecer uma câmera (config, vaga e gravações)
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
import base64, fcntl, hashlib, hmac, json, os, re, shutil, subprocess, tempfile, threading
import urllib.parse, urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MEDIAMTX = "http://localhost:9996/get"
MEDIAMTX_LIST = "http://localhost:9996/list"
MTX_USER = "box"  # usuário interno do MediaMTX (não é o do celular)
CONFIG_JSON = "/opt/secbox/config.json"
CAMERAS_JSON = "/opt/secbox/cameras.json"
SETTINGS_JSON = "/opt/secbox/camera-settings.json"
ALARM_STATE = "/opt/secbox/alarm-state.json"
PRUNE_STATS = "/opt/secbox/rec-prune.json"
REGISTRO = "/opt/secbox/camera-paths.json"   # câmera -> path (gen-cameras.py)
CAMERAS_LOCK = "/opt/secbox/cameras.lock"    # a mesma trava do gen-cameras.py
GEN_CAMERAS = "/opt/secbox/gen-cameras.py"
REC_DIR = "/opt/mediamtx/rec"
CACHE_DIR = "/opt/secbox-clip/cache"
CACHE_MAX = 1024 * 1024 * 1024  # teto do cache em disco: 1 GB
SETTLE = 15  # só entra no cache o trecho que já terminou há esse tempo
DISK_LIMIT = 0.85  # acima disso o sd-guard começa a apagar gravação

def _read_cfg(chave):
    try:
        return (json.load(open(CONFIG_JSON)).get(chave) or "").strip()
    except Exception:
        return ""


TOKEN = _read_cfg("api_token")          # o que o app apresenta a ESTE serviço
MTX_PASS = _read_cfg("mtx_internal_pass")  # o que ESTE serviço apresenta ao MediaMTX


# O MediaMTX exige autenticação e NÃO tem exceção para localhost: o cloudflared
# entrega o tráfego do túnel em http://localhost, então qualquer regra por IP de
# origem daria permissão total a quem viesse da internet. Logo, este serviço
# autentica como qualquer outro cliente — com o usuário interno, que tem senha
# diferente da que o celular recebe.
def _mtx_req(url):
    req = urllib.request.Request(url)
    if MTX_PASS:
        cred = base64.b64encode(("%s:%s" % (MTX_USER, MTX_PASS)).encode()).decode()
        req.add_header("Authorization", "Basic " + cred)
    return req


def _mtx_url(url):
    # Para o ffmpeg, que recebe a URL pronta e não aceita cabeçalho.
    if not MTX_PASS:
        return url
    esquema, resto = url.split("://", 1)
    return "%s://%s:%s@%s" % (esquema, MTX_USER,
                              urllib.parse.quote(MTX_PASS, safe=""), resto)

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


def _prune_stats():
    """O que o faxineiro de gravação mediu por câmera.

    Interessa ao app sobretudo a "razao": a fração do tempo vigiado que
    sobrevive ao descarte. Sem ela o app só saberia estimar espaço supondo
    gravação contínua, e mostraria números muito maiores que a realidade para
    quem escolheu gravar só com movimento.
    """
    try:
        return json.load(open(PRUNE_STATS)).get("paths", {})
    except Exception:
        return {}


def _storage():
    # Autonomia = quanto ainda cabe de gravação dividido pelo consumo somado.
    # O orçamento não é só o espaço livre: a gravação antiga é descartável, o
    # que não pode passar é o teto em que o sd-guard começa a apagar.
    #
    # Mede o disco DA GRAVAÇÃO, não o "/": desde que o sistema passou para a
    # eMMC e o cartão virou disco de dados, são dois sistemas de arquivos
    # diferentes, e medir o "/" reportaria os 5 GB da eMMC no lugar dos 29 GB
    # do cartão.
    st = os.statvfs(REC_DIR)
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
    # Cartão fora do ar: a montagem falha (nofail) e REC_DIR volta a ser um
    # diretório na eMMC. Mesmo st_dev que a raiz denuncia isso -- sem esta
    # checagem, o app mostraria o espaço da eMMC como se fosse o do cartão e
    # ninguém perceberia que parou de gravar.
    try:
        rec_montado = os.stat(REC_DIR).st_dev != os.stat("/").st_dev
    except OSError:
        rec_montado = False
    return {"rec_mounted": rec_montado,
            "total": total, "free": free, "used": used, "rec_used": rec,
            "budget": budget, "per_camera": per, "kbps_total": kbps,
            "hours": round(hours, 1), "load": round(load, 2),
            "cpus": os.cpu_count() or 1, "prune": _prune_stats()}


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
    meta = {}   # sem isto, um cameras.json ilegivel deixaria "meta" sem valor
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
    modos = set(meta.get("record_modes", [])) if isinstance(meta, dict) else set()
    modos = modos or {"continuo", "movimento"}
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
        if cfg.get("record_mode") in modos:
            entry["record_mode"] = cfg["record_mode"]
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


def _ler_json(caminho, padrao):
    try:
        with open(caminho) as f:
            return json.load(f)
    except Exception:
        return padrao


def _gravar_json(caminho, dado):
    tmp = caminho + ".tmp"
    with open(tmp, "w") as f:
        json.dump(dado, f)
    os.replace(tmp, caminho)


# Id é o nome by-id da câmera sem o sufixo, ex. usb-046d_HD_Pro_Webcam_C920.
ID_VALIDO = re.compile(r"[A-Za-z0-9_.:\-]{1,120}")
# O path vira nome de pasta dentro de REC_DIR e é apagado com rmtree. Só passa
# o formato que o gen-cameras.py gera: com "" aqui, o rmtree levaria TODAS as
# gravações de todas as câmeras.
PATH_VALIDO = re.compile(r"cam[0-9]{0,2}")


def _esquecer(cid):
    """Esquece uma câmera: configuração, vaga no registro e gravações.

    Devolve (status_http, corpo). A câmera pode estar plugada ou não. Se
    estiver, o gen-cameras.py a detecta de novo na mesma hora e ela volta como
    câmera nova, com os padrões — o que é o "zerar" que a demonstração pede.
    Para ela sumir de vez, desconecta-se o cabo antes.
    """
    if not ID_VALIDO.fullmatch(cid or ""):
        return 400, {"error": "id_invalido"}

    with open(CAMERAS_LOCK, "w") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX)
        settings = _load_settings()
        registro = _ler_json(REGISTRO, {})
        if cid not in settings["cameras"] and cid not in registro:
            return 404, {"error": "desconhecida"}
        path = registro.pop(cid, None)
        settings["cameras"].pop(cid, None)
        _gravar_json(SETTINGS_JSON, settings)
        _gravar_json(REGISTRO, registro)

    apagado = 0
    if path is not None:
        if not PATH_VALIDO.fullmatch(path):
            # Registro corrompido. A configuração já saiu; a pasta fica, porque
            # apagar algo com nome inesperado é o erro que não tem volta.
            return 500, {"error": "path_invalido", "path": path}
        pasta = os.path.join(REC_DIR, path)
        # Para o MediaMTX antes: ele escreve nessa pasta, e apagar com o
        # arquivo aberto deixaria o segmento atual gravando num inode órfão.
        subprocess.run(["systemctl", "stop", "mediamtx"], timeout=60)
        apagado = _dir_size(pasta)
        shutil.rmtree(pasta, ignore_errors=True)
        # O contador de espaço liberado era desta câmera; a próxima que
        # herdar o path começa do zero.
        stats = _ler_json(PRUNE_STATS, None)
        if isinstance(stats, dict):
            for chave in ("paths", "acumulado"):
                if isinstance(stats.get(chave), dict):
                    stats[chave].pop(path, None)
            _gravar_json(PRUNE_STATS, stats)
        # O cache é indexado por path+horário. Não dá para separar por câmera,
        # e ele é descartável: sai inteiro, para nenhum clipe velho ser
        # servido como se fosse da câmera que herdar a vaga.
        try:
            for nome in os.listdir(CACHE_DIR):
                try:
                    os.remove(os.path.join(CACHE_DIR, nome))
                except OSError:
                    pass
        except OSError:
            pass

    # Regenera tudo (inclusive readmite a câmera, se ainda estiver plugada) e
    # garante o MediaMTX de pé mesmo que o yml não tenha mudado.
    subprocess.run(["python3", GEN_CAMERAS], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120)
    subprocess.run(["systemctl", "start", "mediamtx"], timeout=60)
    return 200, {"ok": True, "path": path, "apagado_bytes": apagado}


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
        caminho = urllib.parse.urlparse(self.path).path
        if caminho == "/alarm":
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                armado = bool(body.get("armed"))
                segundos = max(1, min(int(body.get("seconds", 60)), 600))
            except Exception:
                self.send_error(400)
                return
            # Escrita atomica: o alarm.py le este arquivo a cada segundo, e um
            # arquivo pela metade seria lido como "desarmado".
            tmp = ALARM_STATE + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"armed": armado, "seconds": segundos}, f, indent=2)
            os.replace(tmp, ALARM_STATE)
            self._send_json({"armed": armado, "seconds": segundos})
            return
        if caminho == "/forget":
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                cid = str(body.get("id", ""))
            except Exception:
                self.send_error(400)
                return
            status, corpo = _esquecer(cid)
            if status != 200:
                data = json.dumps(corpo).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._send_json(corpo)
            return
        if caminho != "/settings":
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
        if u.path == "/alarm":
            try:
                data = open(ALARM_STATE, "rb").read()
            except Exception:
                data = b'{"armed": false, "seconds": 60}'
            self._send_json(data)
            return
        if u.path == "/settings":
            try:
                data = open(SETTINGS_JSON, "rb").read()
            except Exception:
                data = b"{}"
            self._send_json(data)
            return
        if u.path == "/list":
            # Repassa a listagem do MediaMTX. Existe para a porta 9996 não
            # precisar ser publicada: ela não tem autenticação, e aqui a
            # listagem passa a herdar o token desta porta.
            q = urllib.parse.parse_qs(u.query)
            path = q.get("path", ["cam"])[0]
            if not path.replace("_", "").isalnum():
                self.send_error(400)
                return
            try:
                with urllib.request.urlopen(_mtx_req(
                        MEDIAMTX_LIST + "?path=" + urllib.parse.quote(path)),
                        timeout=15) as r:
                    data = r.read()
            except Exception:
                data = b"[]"
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
                src = _mtx_url(MEDIAMTX) + "?" + urllib.parse.urlencode(
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


if __name__ != "__main__":
    pass  # importado (teste): não sobe servidor
elif TOKEN:
    print("clip-server 9997: autenticacao LIGADA", flush=True)
else:
    print("clip-server 9997: SEM AUTENTICACAO — qualquer um que alcance esta "
          "porta le as cameras e ESCREVE a configuracao. Defina 'api_token' em "
          + CONFIG_JSON + " antes de publicar na internet.", flush=True)

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9997), Handler).serve_forever()
