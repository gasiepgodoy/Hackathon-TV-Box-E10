#!/usr/bin/env python3
# Faxineiro da gravação: nas câmeras configuradas para "gravar só com
# movimento", apaga os trechos em que nada aconteceu.
#
# A gravação NÃO é ligada e desligada conforme o movimento, e isso é
# deliberado. Parar e religar a captura custaria reescrever o mediamtx.yml e
# reiniciar o serviço — o que derruba junto o vídeo ao vivo — e, pior, perderia
# os segundos ANTERIORES ao movimento, justamente o trecho que mostra como a
# pessoa chegou. Gravando sempre e descartando depois, o pré-movimento sai de
# graça e nada reinicia.
#
# A regra de ouro é: só se apaga o que comprovadamente foi vigiado e estava
# vazio. "Não há movimento anotado" e "ninguém estava olhando" são estados
# diferentes, e confundi-los apagaria exatamente a gravação do período em que o
# detector esteve fora do ar — que é quando ela mais faria falta. Por isso o
# motion.py anota de tempos em tempos que está vigiando, e todo trecho sem essa
# cobertura é preservado.
import json, os, re, subprocess, time
from datetime import datetime

BASE = "/opt/secbox"
REC = "/opt/mediamtx/rec"
CAMERAS_JSON = BASE + "/cameras.json"
MOTION_LOG = BASE + "/motion-log"
STATS = BASE + "/rec-prune.json"

PRE = 30      # segundos guardados ANTES de cada movimento
POST = 60     # ... e depois. Tem de ser >= o cooldown do detector (30 s),
              # senão movimento contínuo abriria buracos no meio da cena.
GRACE = 180   # não encosta em arquivo mexido há menos que isso
# O motion.py marca vigilância a cada MARK segundos (300). Duas marcas mais
# distantes que isto significam que ele parou no meio — o período entre elas
# não foi vigiado, e a gravação correspondente fica.
GAP_MAX = 2 * 300 + 60

NOME = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})-\d+\.mp4$")


def inicio(nome):
    """Instante inicial do trecho, lido do nome do arquivo.

    O MediaMTX grava o nome em hora LOCAL (recordPath usa %Y-%m-%d_%H-%M-%S),
    e .timestamp() sobre um datetime ingênuo interpreta como local — as duas
    pontas combinam.
    """
    m = NOME.match(nome)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d_%H-%M-%S").timestamp()
    except ValueError:
        return None


def ler_registro():
    """{path: {"mov": [instantes], "marcas": [instantes]}} ou None.

    None significa que não há registro nenhum — instalação nova, ou o arquivo
    sumiu. Nesse caso não se apaga nada: a ausência de prova de movimento não
    é prova de ausência de movimento.
    """
    if not os.path.exists(MOTION_LOG):
        return None
    reg = {}
    try:
        with open(MOTION_LOG) as f:
            for linha in f:
                p = linha.split()
                if len(p) < 3:
                    continue
                try:
                    t = int(p[0])
                except ValueError:
                    continue
                e = reg.setdefault(p[1], {"mov": [], "marcas": []})
                # Um movimento também prova que havia alguém olhando.
                e["marcas"].append(t)
                if p[2] == "m":
                    e["mov"].append(t)
    except OSError:
        return None
    return reg


def unir(instantes, antes, depois, folga=0):
    """Instantes -> intervalos [ini, fim], fundindo os que se encostam."""
    ivs = []
    for t in sorted(instantes):
        ini, fim = t - antes, t + depois
        if ivs and ini - folga <= ivs[-1][1]:
            ivs[-1][1] = max(ivs[-1][1], fim)
        else:
            ivs.append([ini, fim])
    return ivs


def vigiado(marcas):
    """Períodos em que o detector estava comprovadamente de olho.

    O último intervalo termina na última marca, e não em "agora": os minutos
    desde então ainda não foram atestados por ninguém.
    """
    return unir(marcas, 0, 0, folga=GAP_MAX)


def dentro(a, b, ivs):
    # Exige o trecho INTEIRO dentro de um mesmo período vigiado. Um trecho que
    # começa dentro e termina fora contém tempo não vigiado, e fica.
    return any(iv[0] <= a and b <= iv[1] for iv in ivs)


def cruza(a, b, ivs):
    return any(a < iv[1] and iv[0] < b for iv in ivs)


def detector_ativo():
    try:
        r = subprocess.run(["systemctl", "is-active", "secbox-motion"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() == "active"
    except Exception:
        return False


def podar(path, reg, agora):
    """Apaga os trechos sem movimento de uma câmera. Devolve as estatísticas."""
    dirp = os.path.join(REC, path)
    arqs = []
    try:
        for nome in os.listdir(dirp):
            t = inicio(nome)
            if t is not None:
                arqs.append([t, os.path.join(dirp, nome)])
    except OSError:
        return None
    if not arqs:
        return None
    arqs.sort()

    janelas = unir(reg["mov"], PRE, POST)
    olhos = vigiado(reg["marcas"])
    st = {"guardado_s": 0.0, "vigiado_s": 0.0, "apagados": 0, "bytes": 0}

    for i, (ini, caminho) in enumerate(arqs):
        # O fim de um trecho é o começo do seguinte. O último ainda está sendo
        # escrito, então vai até agora — e nunca é candidato a sumir.
        fim = arqs[i + 1][0] if i + 1 < len(arqs) else agora
        dur = max(0.0, fim - ini)
        if not dentro(ini, fim, olhos):
            continue                      # não vigiado: não conta e não some
        st["vigiado_s"] += dur
        if cruza(ini, fim, janelas):
            st["guardado_s"] += dur
            continue
        if i == len(arqs) - 1:            # o que está sendo gravado agora
            st["guardado_s"] += dur
            continue
        try:
            if agora - os.path.getmtime(caminho) < GRACE:
                st["guardado_s"] += dur
                continue
            tam = os.path.getsize(caminho)
            os.remove(caminho)
            st["apagados"] += 1
            st["bytes"] += tam
        except OSError:
            st["guardado_s"] += dur
    return st


def main():
    agora = time.time()
    try:
        meta = json.load(open(CAMERAS_JSON))
    except Exception:
        return
    alvos = [c for c in meta.get("cameras", [])
             if c.get("record_mode") == "movimento"]
    if not alvos:
        return
    # Sem detector rodando não há como saber o que descartar. Apagar aqui seria
    # apagar às cegas o período inteiro em que ele esteve fora.
    if not detector_ativo():
        print("secbox-motion fora do ar: nada apagado", flush=True)
        return
    reg = ler_registro()
    if reg is None:
        print("sem registro de movimento: nada apagado", flush=True)
        return

    try:
        antes = json.load(open(STATS))
    except Exception:
        antes = {}
    acum = antes.get("acumulado", {})
    saida = {"ts": int(agora), "paths": {}, "acumulado": acum}

    for c in alvos:
        path = c.get("path")
        if not path or path not in reg:
            continue                     # câmera que o detector nunca observou
        st = podar(path, reg[path], agora)
        if st is None:
            continue
        a = acum.setdefault(path, {"apagados": 0, "bytes": 0})
        a["apagados"] += st["apagados"]
        a["bytes"] += st["bytes"]
        vig = st["vigiado_s"]
        saida["paths"][path] = {
            "vigiado_h": round(vig / 3600, 2),
            "guardado_h": round(st["guardado_s"] / 3600, 2),
            # A fração do tempo vigiado que sobrevive. É com ela que o app
            # estima espaço de verdade, em vez de fingir que gravação por
            # movimento ocupa o mesmo que gravação contínua.
            "razao": round(st["guardado_s"] / vig, 4) if vig > 0 else None,
            "liberado_bytes": a["bytes"],
            "liberado_trechos": a["apagados"],
        }
        if st["apagados"]:
            print("%s: %d trechos apagados (%.1f MB)"
                  % (path, st["apagados"], st["bytes"] / 1048576), flush=True)

    tmp = STATS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(saida, f, indent=2)
    os.replace(tmp, STATS)


if __name__ == "__main__":
    main()
