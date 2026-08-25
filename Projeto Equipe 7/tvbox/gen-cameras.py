#!/usr/bin/env python3
# Detecta as câmeras conectadas e regenera o mediamtx.yml conforme a preferência
# de cada uma (qualidade e retenção), que o app grava em camera-settings.json.
# O mediamtx só é reiniciado quando o arquivo realmente muda.
import os, glob, json, re, subprocess

MAX = 2  # câmeras suportadas simultaneamente (limite de banda USB)
BYID = "/dev/v4l/by-id"
MTX_YML = "/opt/mediamtx/mediamtx.yml"
CONFIG_JSON = "/opt/secbox/config.json"
CAMERAS_JSON = "/opt/secbox/cameras.json"
SETTINGS_JSON = "/opt/secbox/camera-settings.json"

# Presets de qualidade. O bitrate determina o consumo de disco; a resolução e o
# fps determinam o consumo de CPU, que neste equipamento é o recurso mais
# apertado — não há codificador por hardware, tudo passa pelo libx264.
PRESETS = {
    "alta": {"size": "1280x720", "fps": 15, "kbps": 2000},
    "media": {"size": "1280x720", "fps": 10, "kbps": 1000},
    "baixa": {"size": "640x480", "fps": 10, "kbps": 500},
}
FPS_OPTIONS = [3, 5, 10, 15]
# Custo de codificação medido neste equipamento: 1280x720 a 15 fps ocupou ~115%
# de um núcleo, ou seja ~8,3% de CPU por megapixel por segundo. Serve para o app
# estimar o consumo antes de aplicar uma mudança.
CPU_PER_MPPS = 8.3
DEFAULT = {"quality": "media", "retention_h": 24,
           "motion": True, "sensitivity": "media", "fps": None}
# Sensibilidade do detector: limiar menor = dispara com menos movimento.
SENSITIVITIES = {"alta": 8, "media": 12, "baixa": 20}


def cam_id(link):
    # Identidade estável da câmera física: as preferências seguem o aparelho,
    # não a ordem em que ele foi detectado.
    return re.sub(r"-video-index\d+$", "", os.path.basename(link))


def label(link):
    n = re.sub(r"^usb-", "", cam_id(link))
    n = re.sub(r"^[0-9a-fA-F]{4}_", "", n)  # remove o id do fabricante
    return n.replace("_", " ").strip() or "Câmera"


def list_cameras():
    cams = []
    for link in sorted(glob.glob(BYID + "/*-video-index0")):
        dev = os.path.realpath(link)
        try:
            out = subprocess.run(["v4l2-ctl", "-d", dev, "--list-formats-ext"],
                                 capture_output=True, text=True, timeout=8).stdout
        except Exception:
            continue
        if "[0]" not in out:  # não é um dispositivo de captura utilizável
            continue
        sizes = sorted({s for s in re.findall(r"Discrete\s+(\d+x\d+)", out)},
                       key=lambda s: -(int(s.split("x")[0]) * int(s.split("x")[1])))
        cams.append((link, sizes))
    return cams


def load_settings():
    # {"cameras": {<id>: {...}}, "notify": {...}}. Aceita também o formato
    # antigo, em que o arquivo inteiro era o mapa de câmeras.
    try:
        s = json.load(open(SETTINGS_JSON))
    except Exception:
        s = {}
    if "cameras" not in s:
        s = {"cameras": s}
    s.setdefault("cameras", {})
    s.setdefault("notify", {})
    return s


def api_token():
    try:
        return (json.load(open(CONFIG_JSON)).get("api_token") or "").strip()
    except Exception:
        return ""


def auth_block(token):
    """Autenticação do MediaMTX. Sem ela, quem alcançar a porta 8889 recebe o
    vídeo ao vivo, e a 9996 entrega as gravações — inaceitável assim que a box
    for publicada na internet.

    O usuário 'any' restrito a localhost é o que mantém a casa funcionando: é
    dali que o ffmpeg do runOnInit publica e que o clip-server lê o playback.
    Sem essa exceção, a própria box perderia acesso a si mesma.

    Sem token configurado não escreve bloco nenhum — mesmo critério do
    clip-server, para um upgrade não deixar o piloto cego."""
    if not token:
        return []
    return [
        "authInternalUsers:",
        "  - user: any",
        "    pass:",
        "    ips: ['127.0.0.1', '::1']",
        "    permissions:",
        "      - action: publish",
        "      - action: read",
        "      - action: playback",
        "      - action: api",
        "      - action: metrics",
        "  - user: app",
        "    pass: %s" % token,
        "    permissions:",
        "      - action: read",
        "      - action: playback",
    ]


def build(cams, settings):
    lines = ["playback: yes"] + auth_block(api_token()) + ["paths:"]
    meta = []
    for i, (byid, sizes) in enumerate(cams[:MAX]):
        path = "cam" if i == 0 else "cam%d" % (i + 1)
        cfg = dict(DEFAULT, **settings["cameras"].get(cam_id(byid), {}))
        p = PRESETS.get(cfg["quality"], PRESETS["media"])
        # cai para a maior resolução suportada se o preset não existir na câmera
        size = p["size"] if (not sizes or p["size"] in sizes) else sizes[0]
        ret = max(1, int(cfg["retention_h"]))
        # fps é escolha independente da qualidade (é o que mais pesa na CPU);
        # sem escolha, vale o do preset
        fps = cfg["fps"] if cfg["fps"] in FPS_OPTIONS else p["fps"]
        run = ("ffmpeg -f v4l2 -input_format mjpeg -video_size %s -framerate %d "
               "-i %s -c:v libx264 -preset ultrafast -tune zerolatency "
               "-pix_fmt yuv420p -b:v %dk -g %d -f rtsp "
               "rtsp://localhost:$RTSP_PORT/$MTX_PATH"
               % (size, fps, byid, p["kbps"], fps * 2))
        lines += ["  %s:" % path,
                  "    runOnInit: %s" % run,
                  "    runOnInitRestart: yes",
                  "    record: yes",
                  "    recordPath: /opt/mediamtx/rec/%path/%Y-%m-%d_%H-%M-%S-%f",
                  "    recordFormat: fmp4",
                  "    recordSegmentDuration: 600s",
                  "    recordDeleteAfter: %dh" % ret]
        meta.append({"name": "Câmera %d" % (i + 1), "path": path,
                     "id": cam_id(byid), "label": label(byid),
                     "quality": cfg["quality"], "retention_h": ret,
                     "kbps": p["kbps"], "size": size, "sizes": sizes,
                     "fps": fps, "motion": bool(cfg["motion"]),
                     "sensitivity": cfg["sensitivity"]})
    return "\n".join(lines) + "\n", meta


settings = load_settings()
cams = list_cameras()
yml, meta = build(cams, settings)
json.dump({"cameras": meta, "connected": len(cams), "limit": MAX,
           "exceeded": len(cams) > MAX, "presets": PRESETS,
           "fps_options": FPS_OPTIONS, "cpu_per_mpps": CPU_PER_MPPS,
           "sensitivities": sorted(SENSITIVITIES),
           "notify": dict({"motion": True, "camera_offline": True},
                          **settings["notify"])},
          open(CAMERAS_JSON, "w"))
old = open(MTX_YML).read() if os.path.exists(MTX_YML) else ""
if old != yml:
    open(MTX_YML, "w").write(yml)
    subprocess.run(["systemctl", "restart", "mediamtx"])
    print("mediamtx atualizado (%d cameras)" % min(len(cams), MAX))
else:
    print("sem mudanca (%d cameras)" % min(len(cams), MAX))
