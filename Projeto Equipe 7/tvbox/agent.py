#!/usr/bin/env python3
# Agente da borda: cliente MQTT + modo pareamento (lê QR pela câmera,
# conecta Wi-Fi e reivindica o aparelho). Lê /opt/secbox/{device,config}.json.
#
# Também executa o "esquecer a box" (sistema/esquecer): apaga o estado local,
# o Wi-Fi e a marca de pareada, e volta a ler QR — o mesmo caminho de uma box
# recém-saída da caixa.
import glob, json, re, shutil, time, subprocess, threading, os
from urllib.parse import quote
import paho.mqtt.client as mqtt

BASE = "/opt/secbox"
dev = json.load(open(f"{BASE}/device.json"))
cfg = json.load(open(f"{BASE}/config.json"))

_MTX_PASS = (cfg.get("mtx_internal_pass") or "").strip()
# Mesma razão do motion.py: sem exceção por IP, todo consumidor se autentica.
RTSP_URL = (cfg["rtsp_url"].replace("://", "://box:%s@" % quote(_MTX_PASS, safe=""), 1)
            if _MTX_PASS else cfg["rtsp_url"])

DEVICE_ID    = dev["device_id"]
SECRET       = dev.get("secret","")
BASE_TOPIC   = f"devices/{DEVICE_ID}"
CMD_TOPIC    = f"{BASE_TOPIC}/+/command"
STATUS_TOPIC = f"{BASE_TOPIC}/status"
RESULT_TOPIC = f"{BASE_TOPIC}/provisioning/result"
CLAIM_TOPIC  = "provisioning/claim"
CLAIMED_FLAG = f"{BASE}/claimed"
# O wifi-guard vigia um perfil com este nome nesta interface. O pareamento
# precisa criar o perfil exatamente assim — "nmcli device wifi connect" o
# batizaria com o SSID, e o vigia passaria a tentar subir um perfil que não
# existe, escalando até reiniciar a box em laço.
WIFI_IFACE = cfg.get("wifi_iface", "wlan1")
WIFI_PERFIL = cfg.get("wifi_profile", "wifi-interna")
REC_DIR = "/opt/mediamtx/rec"
CACHE_DIR = "/opt/secbox-clip/cache"
GEN_CAMERAS = f"{BASE}/gen-cameras.py"
# Estado local que "esquecer" apaga. device.json e config.json ficam: são a
# identidade e os segredos de fábrica da box, não do dono.
ESTADO_DO_DONO = ["camera-settings.json", "camera-paths.json", "alarm-state.json"]
ESTADO_DA_GRAVACAO = ["motion-log", "rec-prune.json"]

def publish_event(client, module, etype, extra=None):
    body = {"type": etype}
    if extra: body.update(extra)
    client.publish(f"{BASE_TOPIC}/{module}/event", json.dumps(body), qos=1)

def take_snapshot(path="/tmp/snap.jpg"):
    subprocess.run(["ffmpeg","-y","-i",RTSP_URL,"-frames:v","1",path],
                   timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return path

def scan_qr():
    subprocess.run(["ffmpeg","-y","-i",RTSP_URL,"-frames:v","1","/tmp/scan.jpg"],
                   timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        out = subprocess.run(["zbarimg","-q","--raw","-Sdisable","-Sqrcode.enable",
                              "/tmp/scan.jpg"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None

def _nmcli(*args, timeout=30):
    try:
        return subprocess.run(["nmcli", *args], capture_output=True, text=True,
                              timeout=timeout)
    except Exception as e:
        print("nmcli falhou:", e, flush=True)
        return None


def perfis_wifi():
    """UUIDs de todos os perfis Wi-Fi salvos."""
    r = _nmcli("-g", "UUID,TYPE", "connection", "show")
    if r is None:
        return []
    return [l.split(":")[0] for l in r.stdout.splitlines()
            if l.endswith(":802-11-wireless")]


def esquecer_wifi(exceto=None):
    # TODOS os perfis, não só o principal: havia dois "wifi-interna-alt" para a
    # mesma rede com conexão automática, e apagar só um deixaria o
    # NetworkManager reconectar sozinho pelo outro.
    for u in perfis_wifi():
        if u != exceto:
            _nmcli("connection", "delete", "uuid", u)


def connect_wifi(ssid, password):
    # Não imprime a senha: o log vai para o journal.
    print("Conectando ao Wi-Fi:", ssid, flush=True)
    novo = WIFI_PERFIL + "-novo"
    _nmcli("connection", "delete", "id", novo)  # sobra de tentativa anterior
    cmd = ["connection", "add", "type", "wifi", "ifname", WIFI_IFACE,
           "con-name", novo, "ssid", ssid, "connection.autoconnect", "yes"]
    if password:
        cmd += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password]
    r = _nmcli(*cmd)
    if r is None or r.returncode != 0:
        print("não consegui criar o perfil:", r and r.stderr.strip(), flush=True)
        return False
    r = _nmcli("connection", "up", "id", novo, timeout=60)
    if r is None or r.returncode != 0:
        # Senha ou rede erradas. O perfil novo sai e os antigos, se houver,
        # ficam: um QR errado não pode derrubar um Wi-Fi que funcionava.
        print("não conectou:", r and r.stderr.strip(), flush=True)
        _nmcli("connection", "delete", "id", novo)
        return False
    uuid = _nmcli("-g", "connection.uuid", "connection", "show", "id", novo)
    esquecer_wifi(exceto=uuid.stdout.strip() if uuid else None)
    _nmcli("connection", "modify", "id", novo, "connection.id", WIFI_PERFIL)
    print("Wi-Fi conectado, perfil", WIFI_PERFIL, flush=True)
    return True

_pareando = threading.Event()


def iniciar_pareamento(client):
    # Uma thread só: o boot e o "esquecer" podem pedir ao mesmo tempo.
    if _pareando.is_set():
        return
    _pareando.set()
    threading.Thread(target=provisioning_loop, args=(client,), daemon=True).start()


def provisioning_loop(client):
    print("Modo pareamento: escaneando QR...", flush=True)
    try:
        _ler_qr_ate_parear(client)
    finally:
        _pareando.clear()


def _interpretar_qr(data):
    """Devolve (token, ssid, senha) ou None se o QR não for o do app."""
    try:
        info = json.loads(data)
    except Exception:
        info = {"token": data}
    # Um código de barras qualquer vira número ou lista: não é o nosso QR.
    if not isinstance(info, dict) or not info.get("token"):
        return None
    return str(info["token"]), info.get("ssid") or "", info.get("pass") or ""


def _ler_qr_ate_parear(client):
    ultimo = None          # último QR já processado: o celular continua mostrando
    ultimo_claim = 0.0     # o mesmo QR por minutos, e cada releitura derrubava o Wi-Fi
    while not os.path.exists(CLAIMED_FLAG):
        try:
            data = scan_qr()
            qr = _interpretar_qr(data) if data else None
            if qr and qr != ultimo:
                token, ssid, senha = qr
                # Nunca o conteúdo cru: ele carrega a senha do Wi-Fi.
                print("QR lido: token=%s wifi=%s" % (bool(token), ssid or "-"), flush=True)
                if ssid:
                    connect_wifi(ssid, senha)
                    for _ in range(30):
                        if client.is_connected(): break
                        time.sleep(1)
                client.publish(CLAIM_TOPIC, json.dumps(
                    {"deviceId": DEVICE_ID, "secret": SECRET, "token": token}), qos=1)
                print("Claim enviado, token:", token, flush=True)
                ultimo, ultimo_claim = qr, time.time()
            elif qr and time.time() - ultimo_claim > 60:
                # Mesmo QR, mas sem confirmação há um minuto: reenvia só o claim,
                # sem mexer no Wi-Fi (o publish fica na fila até o broker voltar).
                client.publish(CLAIM_TOPIC, json.dumps(
                    {"deviceId": DEVICE_ID, "secret": SECRET, "token": ultimo[0]}), qos=1)
                print("Claim reenviado", flush=True)
                ultimo_claim = time.time()
        except Exception as e:
            # A thread não pode morrer: sem ela a box fica sem Wi-Fi e sem leitor.
            print("pareamento: erro ignorado:", repr(e), flush=True)
        time.sleep(2)
    print("Pareado, saindo do modo pareamento.", flush=True)


def esquecer_box(client, apagar_gravacoes):
    """Volta a box ao estado de fábrica do ponto de vista do dono.

    A ordem importa: tudo que é local vem antes, enquanto o MQTT ainda está de
    pé; o Wi-Fi sai por último, porque a partir dali a box está fora da rede e
    só volta pelo QR.
    """
    print("Esquecendo a box (apagar gravações: %s)" % apagar_gravacoes, flush=True)
    publish_event(client, "sistema", "esquecendo",
                  {"apagar_gravacoes": apagar_gravacoes})
    subprocess.run(["systemctl", "stop", "mediamtx"], timeout=60)
    if apagar_gravacoes:
        # Só pastas com o formato que o gen-cameras cria. REC_DIR é o ponto de
        # montagem do cartão e não pode sair.
        for d in glob.glob(os.path.join(REC_DIR, "*")):
            if re.fullmatch(r"cam[0-9]{0,2}", os.path.basename(d)):
                shutil.rmtree(d, ignore_errors=True)
        for nome in ESTADO_DA_GRAVACAO:
            try: os.remove(os.path.join(BASE, nome))
            except OSError: pass
        for f in glob.glob(os.path.join(CACHE_DIR, "*")):
            try: os.remove(f)
            except OSError: pass
    for nome in ESTADO_DO_DONO:
        try: os.remove(os.path.join(BASE, nome))
        except OSError: pass
    # Sem registro de câmeras, a primeira plugada volta a ser "cam" — é o path
    # que o leitor de QR usa.
    subprocess.run(["python3", GEN_CAMERAS], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120)
    subprocess.run(["systemctl", "start", "mediamtx"], timeout=60)
    try: os.remove(CLAIMED_FLAG)
    except OSError: pass
    time.sleep(3)   # dá tempo do evento acima sair antes de a rede cair
    esquecer_wifi()
    print("Box esquecida: Wi-Fi apagado, aguardando QR.", flush=True)
    iniciar_pareamento(client)

def handle_command(client, module, cmd):
    action = cmd.get("action")
    print("Comando:", module, action)
    if module == "camera":
        if action == "snapshot":
            take_snapshot(); publish_event(client,"camera","snapshot_taken")
        elif action == "clear_recordings":
            subprocess.run(["/opt/mediamtx/clear-rec.sh"])
            publish_event(client,"camera","recordings_cleared")
    elif module == "sistema" and action == "esquecer":
        # Fora da thread do MQTT: parar o MediaMTX e redetectar câmeras leva
        # dezenas de segundos, e bloquear aqui derrubaria o keepalive.
        threading.Thread(target=esquecer_box,
                         args=(client, cmd.get("apagar_gravacoes") is not False),
                         daemon=True).start()

def on_connect(client, userdata, flags, rc):
    print("Conectado ao broker rc=", rc)
    client.subscribe(CMD_TOPIC, qos=1)
    client.subscribe(RESULT_TOPIC, qos=1)
    client.publish(STATUS_TOPIC,
        json.dumps({"online": True, "device_id": DEVICE_ID}), qos=1, retain=True)

def on_message(client, userdata, msg):
    topic = msg.topic
    try: data = json.loads(msg.payload.decode() or "{}")
    except Exception: data = {}
    if topic == RESULT_TOPIC:
        if data.get("result") == "ok":
            open(CLAIMED_FLAG, "w").write("ok")
            print("Pareamento confirmado pelo servidor.")
        return
    parts = topic.split("/")
    module = parts[2] if len(parts) > 2 else "?"
    handle_command(client, module, data)

def heartbeat(client):
    while True:
        client.publish(f"{BASE_TOPIC}/heartbeat",
                       json.dumps({"ts": int(time.time())}), qos=0)
        time.sleep(30)

def camera_watch(client):
    # Avisa quando uma câmera some ou volta. A referência é o cameras.json, que
    # o gen-cameras.py reescreve a cada 30s com o que está de fato conectado.
    # Começa com known=None para não alarmar na primeira leitura (boot).
    known = None
    while True:
        try:
            cams = json.load(open(f"{BASE}/cameras.json")).get("cameras", [])
            cur = {c.get("id") or c["path"]: c.get("name", "Câmera") for c in cams}
        except Exception:
            time.sleep(15)
            continue
        # Publica sempre. Quem quer ou nao quer ser avisado e escolha de cada
        # celular, e mora no servidor (push_tokens.notify) -- aqui nao ha como
        # saber de quem e o telefone. O evento tambem alimenta o historico, que
        # deve ser completo independentemente de quem pediu push.
        if known is not None and cur != known:
            for cid, name in known.items():
                if cid not in cur:
                    publish_event(client, "camera", "camera_offline",
                                  {"camera": cid, "name": name})
                    print("Camera offline:", name, flush=True)
            for cid, name in cur.items():
                if cid not in known:
                    publish_event(client, "camera", "camera_online",
                                  {"camera": cid, "name": name})
                    print("Camera online:", name, flush=True)
        known = cur
        time.sleep(15)

try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"agent-{DEVICE_ID}")
except (AttributeError, TypeError):
    client = mqtt.Client(client_id=f"agent-{DEVICE_ID}")

client.username_pw_set(cfg["broker_user"], cfg["broker_pass"])
client.will_set(STATUS_TOPIC,
    json.dumps({"online": False, "device_id": DEVICE_ID}), qos=1, retain=True)
client.on_connect = on_connect
client.on_message = on_message
client.reconnect_delay_set(min_delay=1, max_delay=5)  # padrão ia até 120 s
client.connect_async(cfg["broker_host"], int(cfg["broker_port"]), keepalive=60)
threading.Thread(target=heartbeat, args=(client,), daemon=True).start()
threading.Thread(target=camera_watch, args=(client,), daemon=True).start()
if not os.path.exists(CLAIMED_FLAG):
    iniciar_pareamento(client)
client.loop_forever(retry_first_connection=True)
