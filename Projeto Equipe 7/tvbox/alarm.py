#!/usr/bin/env python3
# Sirene do alarme: escuta devices/{id}/alarme/command e toca o WAV pelo ALSA.
#
# Modulo separado de proposito, no mesmo estilo de motion.py e leds.py: tocar
# som nao pode travar o loop MQTT do agente, e uma falha aqui (dispositivo de
# audio errado, arquivo faltando) nao pode derrubar quem entrega os comandos.
import json, os, signal, subprocess, threading, time
import paho.mqtt.client as mqtt

BASE = "/opt/secbox"
dev = json.load(open(f"{BASE}/device.json"))
cfg = json.load(open(f"{BASE}/config.json"))

DEVICE_ID  = dev["device_id"]
BASE_TOPIC = f"devices/{DEVICE_ID}"
CMD_TOPIC  = f"{BASE_TOPIC}/alarme/command"

# Estado armado/desarmado, em disco: sobrevive a reboot e nao depende de rede.
STATE_FILE   = f"{BASE}/alarm-state.json"
# Gatilho local do motion.py. NAO passa pelo broker de proposito: o MQTT sai
# pela internet, a rede desta box cai varias vezes por hora, e um alarme que
# nao toca com a rede fora bastaria ser desarmado cortando a internet.
TRIGGER_FILE = f"{BASE}/alarme-trigger"

WAV      = cfg.get("siren_file", f"{BASE}/sounds/sirene.wav")
ALSA_DEV = cfg.get("alsa_device", "default")
MAX_SEC  = int(cfg.get("siren_max_seconds", 300))

_proc = None
_deadline = 0.0
_lock = threading.Lock()


def ler_estado():
    try:
        e = json.load(open(STATE_FILE))
        return bool(e.get("armed")), int(e.get("seconds", 60))
    except Exception:
        return False, 60      # desarmado por omissao: tocar sem pedir e pior


def gravar_estado(armado, segundos):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"armed": bool(armado), "seconds": int(segundos)}, f, indent=2)
    os.replace(tmp, STATE_FILE)   # troca atomica: nunca deixa arquivo parcial

def publish(client, etype, extra=None):
    body = {"type": etype}
    if extra: body.update(extra)
    client.publish(f"{BASE_TOPIC}/alarme/event", json.dumps(body), qos=1)

def _spawn():
    # O laco fica no shell para o aplay reiniciar sozinho a cada repeticao, e o
    # "|| exit 1" impede que um dispositivo invalido vire laco a 100% de CPU --
    # esta box ja vive com a carga alta.
    return subprocess.Popen(
        ["sh", "-c", 'while :; do aplay -q -D "$1" "$2" || exit 1; done',
         "sirene", ALSA_DEV, WAV],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid)

def siren_start(client, seconds):
    global _proc, _deadline
    seconds = max(1, min(int(seconds), MAX_SEC))
    with _lock:
        if not os.path.exists(WAV):
            print("sirene: arquivo nao encontrado:", WAV, flush=True)
            publish(client, "sirene_falhou", {"erro": "arquivo_ausente"})
            return
        if _proc is None or _proc.poll() is not None:
            _proc = _spawn()
            print("sirene: ligada", seconds, "s em", ALSA_DEV, flush=True)
            publish(client, "sirene_ligada", {"seconds": seconds})
        # Rearmar o prazo com a sirene ja tocando e valido: um segundo alarme
        # durante o primeiro deve estender, nao ser ignorado.
        _deadline = time.time() + seconds

def siren_stop(client, motivo="comando"):
    global _proc, _deadline
    with _lock:
        _deadline = 0.0
        if _proc is not None and _proc.poll() is None:
            try:
                os.killpg(os.getpgid(_proc.pid), signal.SIGTERM)
            except Exception as e:
                print("sirene: erro ao parar:", e, flush=True)
            print("sirene: desligada (%s)" % motivo, flush=True)
            publish(client, "sirene_desligada", {"motivo": motivo})
        _proc = None

def watchdog(client):
    # Trava de seguranca: sirene presa tocando e pior que sirene que nao toca.
    # Vale tambem se o comando de parar se perder com a rede fora do ar.
    armado_antes = ler_estado()[0]
    while True:
        time.sleep(1)

        # O estado tambem muda por fora (o app escreve pelo clip-server), entao
        # e relido a cada volta. So a TRANSICAO para desarmado cala a sirene --
        # comparar o valor absoluto cancelaria um disparo manual feito com o
        # alarme desarmado, que e um uso legitimo.
        armado_agora = ler_estado()[0]
        if armado_antes and not armado_agora:
            siren_stop(client, "desarmado")
            publish(client, "desarmado")
        armado_antes = armado_agora

        # Gatilho do movimento. O arquivo e consumido (removido) mesmo com o
        # alarme desarmado -- senao um movimento de ontem dispararia no
        # instante em que alguem armasse.
        if os.path.exists(TRIGGER_FILE):
            try:
                os.unlink(TRIGGER_FILE)
            except OSError:
                pass
            armado, segundos = ler_estado()
            if armado:
                print("sirene: disparada por movimento", flush=True)
                publish(client, "disparo_movimento", {"seconds": segundos})
                siren_start(client, segundos)

        with _lock:
            expirou = _deadline and time.time() >= _deadline
            morreu  = _proc is not None and _proc.poll() is not None
        if expirou:
            siren_stop(client, "tempo")
        elif morreu:
            # aplay saiu sozinho antes do prazo: dispositivo ALSA invalido ou
            # arquivo ilegivel. Avisa, porque silencio aqui seria confundido
            # com "o alarme nao disparou".
            print("sirene: aplay terminou sozinho (dispositivo?)", flush=True)
            publish(client, "sirene_falhou", {"erro": "aplay_terminou"})
            siren_stop(client, "falha")

def handle(client, cmd):
    action = (cmd.get("action") or "").lower()
    if action in ("on", "start", "ligar"):
        siren_start(client, cmd.get("seconds", 30))
    elif action in ("off", "stop", "parar"):
        siren_stop(client)
    elif action == "test":
        siren_start(client, 3)
    elif action in ("arm", "armar"):
        segundos = int(cmd.get("seconds", ler_estado()[1]))
        gravar_estado(True, segundos)
        print("alarme: ARMADO (%ds por disparo)" % segundos, flush=True)
        publish(client, "armado", {"seconds": segundos})
    elif action in ("disarm", "desarmar"):
        gravar_estado(False, ler_estado()[1])
        # Desarmar tambem cala a sirene em curso: quem desarma quer silencio
        # agora, nao daqui a alguns minutos.
        siren_stop(client, "desarmado")
        print("alarme: DESARMADO", flush=True)
        publish(client, "desarmado")
    else:
        print("sirene: acao desconhecida:", action, flush=True)

def on_connect(client, userdata, flags, rc):
    print("sirene: conectado ao broker rc=", rc, flush=True)
    client.subscribe(CMD_TOPIC, qos=1)
    # Anuncia o estado ao (re)conectar: quem estava sem contato com a box
    # descobre se ela esta armada sem precisar perguntar.
    armado, segundos = ler_estado()
    publish(client, "armado" if armado else "desarmado", {"seconds": segundos})

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode() or "{}")
    except Exception:
        data = {}
    handle(client, data)

try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"alarm-{DEVICE_ID}")
except (AttributeError, TypeError):
    client = mqtt.Client(client_id=f"alarm-{DEVICE_ID}")

client.username_pw_set(cfg["broker_user"], cfg["broker_pass"])
client.on_connect = on_connect
client.on_message = on_message
client.connect_async(cfg["broker_host"], int(cfg["broker_port"]), keepalive=60)
threading.Thread(target=watchdog, args=(client,), daemon=True).start()
def _on_signal(*_):
    # Sirene tocando sem ninguem para desligar e o pior cenario. Mata o grupo
    # direto, sem o lock: se o sinal chegar com ele tomado, passar por
    # siren_stop travaria exatamente no desligamento.
    try:
        if _proc is not None:
            os.killpg(os.getpgid(_proc.pid), signal.SIGKILL)
    except Exception:
        pass
    os._exit(0)

for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, _on_signal)
client.loop_forever(retry_first_connection=True)
