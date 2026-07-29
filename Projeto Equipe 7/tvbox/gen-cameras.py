#!/usr/bin/env python3
# Detecta as câmeras conectadas e regenera o mediamtx.yml conforme a preferência
# de cada uma (qualidade e retenção), que o app grava em camera-settings.json.
# O mediamtx só é reiniciado quando o arquivo realmente muda.
import os, glob, json, re, subprocess

MAX = 2  # câmeras suportadas simultaneamente (limite de banda USB)
BYID = "/dev/v4l/by-id"
MTX_YML = "/opt/mediamtx/mediamtx.yml"
CAMERAS_JSON = "/opt/secbox/cameras.json"
SETTINGS_JSON = "/opt/secbox/camera-settings.json"

# Presets de qualidade (o bitrate é o que determina o consumo de disco).
PRESETS = {
    "alta": {"size": "1280x720", "fps": 15, "kbps": 2000},
    "media": {"size": "1280x720", "fps": 15, "kbps": 1000},
    "baixa": {"size": "640x480", "fps": 15, "kbps": 500},
}
DEFAULT = {"quality": "media", "retention_h": 24,
           "motion": True, "sensitivity": "media"}
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


def build(cams, settings):
    lines = ["playback: yes", "paths:"]
    meta = []
    for i, (byid, sizes) in enumerate(cams[:MAX]):
        path = "cam" if i == 0 else "cam%d" % (i + 1)
        cfg = dict(DEFAULT, **settings["cameras"].get(cam_id(byid), {}))
        p = PRESETS.get(cfg["quality"], PRESETS["media"])
        # cai para a maior resolução suportada se o preset não existir na câmera
        size = p["size"] if (not sizes or p["size"] in sizes) else sizes[0]
        ret = max(1, int(cfg["retention_h"]))
        run = ("ffmpeg -f v4l2 -input_format mjpeg -video_size %s -framerate %d "
               "-i %s -c:v libx264 -preset ultrafast -tune zerolatency "
               "-pix_fmt yuv420p -b:v %dk -g 30 -f rtsp "
               "rtsp://localhost:$RTSP_PORT/$MTX_PATH"
               % (size, p["fps"], byid, p["kbps"]))
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
                     "motion": bool(cfg["motion"]),
                     "sensitivity": cfg["sensitivity"]})
    return "\n".join(lines) + "\n", meta


settings = load_settings()
cams = list_cameras()
yml, meta = build(cams, settings)
json.dump({"cameras": meta, "connected": len(cams), "limit": MAX,
           "exceeded": len(cams) > MAX, "presets": PRESETS,
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
