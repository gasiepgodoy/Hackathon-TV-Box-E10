#!/usr/bin/env python3
"""Liga a saida de audio analogica (jack AV) no device tree da TV box S905X2.

O codec ja vem descrito no DTB (amlogic,t9015 e amlogic,g12a-toacodec), porem
com status "disabled" e sem dai-link no no "sound" -- por isso o mixer so mostra
SPDIF e HDMI, e o aplay toca em silencio sem erro nenhum.

Este script edita o DTS decompilado e recompila. Nao instala nada sem --apply e,
antes de instalar, confere que o resultado ainda tem a correcao de 25 MHz do
SDIO (sem ela o Wi-Fi interno nao sobe) e que os nos novos ficaram coerentes.

  python3 enable-av-audio.py /boot/dtb-.../meson-g12a-u2xx-generic.dtb
  python3 enable-av-audio.py <dtb> --apply

Reverter: cp <dtb>.orig <dtb> && reboot   (ou o cartao num leitor, se nao bootar)
"""
import argparse, os, re, shutil, subprocess, sys, tempfile

T9015 = "amlogic,t9015"
TOACODEC = "amlogic,g12a-toacodec"
SOUNDCARD = "amlogic,axg-sound-card"
SDIO_25MHZ = "0x17d7840"        # a correcao que faz o Wi-Fi interno funcionar

# valores de include/dt-bindings/sound/meson-g12a-toacodec.h
TOACODEC_IN_B, TOACODEC_OUT = 1, 3


def sh(*cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("falhou: %s\n%s" % (" ".join(cmd), p.stderr.strip()))
    return p.stdout


def node_span(lines, idx):
    """Delimita o no que contem a linha idx, contando chaves."""
    start = idx
    while start >= 0 and not lines[start].rstrip().endswith("{"):
        start -= 1
    if start < 0:
        sys.exit("nao achei a abertura do no")
    depth = 0
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0 and i > start:
            return start, i
    sys.exit("no sem fechamento")


def find_by(lines, needle):
    for i, l in enumerate(lines):
        if needle in l:
            return i
    return -1


def indent_of(line):
    return line[:len(line) - len(line.lstrip())]


def get_prop(lines, a, b, name):
    pat = re.compile(r"\s*" + re.escape(name) + r"\s*=\s*(.*);\s*$")
    for i in range(a, b + 1):
        m = pat.match(lines[i])
        if m:
            return i, m.group(1)
    return -1, None


def set_prop(lines, a, b, name, value):
    """Troca a propriedade se existir; senao insere logo apos a abertura."""
    i, _ = get_prop(lines, a, b, name)
    if i >= 0:
        lines[i] = indent_of(lines[i]) + name + " = " + value + ";"
        return False
    lines.insert(a + 1, indent_of(lines[a]) + "\t" + name + " = " + value + ";")
    return True


def max_phandle(text):
    vals = [int(v, 16) for v in re.findall(r"phandle = <(0x[0-9a-fA-F]+)>", text)]
    return max(vals) if vals else 0


def ensure_phandle(lines, a, b, novo):
    """Devolve o phandle do no, criando um se ele nao tiver -- caso dos nos
    desabilitados: ninguem os referencia, entao o dtc nem gera phandle."""
    i, v = get_prop(lines, a, b, "phandle")
    if i >= 0:
        return int(v.strip("<> "), 16), False
    lines.insert(a + 1, indent_of(lines[a]) + "\tphandle = <" + hex(novo) + ">;")
    return novo, True


def patch_dts(text):
    """Aplica as cinco edicoes. Funcao pura: da para testar sem dtc."""
    lines = text.split("\n")
    livre = max_phandle(text) + 1
    notas = []

    # --- 1. acodec (t9015): phandle, AVDD-supply e okay ---------------------
    i = find_by(lines, T9015)
    if i < 0:
        sys.exit("nao achei o no " + T9015 + " -- este DTB nao descreve o codec")
    a, b = node_span(lines, i)
    ph_acodec, criou = ensure_phandle(lines, a, b, livre)
    if criou:
        livre += 1
    a, b = node_span(lines, find_by(lines, T9015))
    set_prop(lines, a, b, "status", '"okay"')
    notas.append("acodec: phandle " + hex(ph_acodec) + ", status okay")

    # Regulador de 1V8 para o AVDD. Sem ele o nucleo substitui por um dummy e
    # avisa no dmesg -- costuma funcionar, mas nao e a forma correta.
    reg = -1
    for pat in ('"VDDAO_1V8"', '"vddao_1v8"', '"VDDIO_AO18"'):
        reg = find_by(lines, "regulator-name = " + pat)
        if reg >= 0:
            break
    if reg >= 0:
        ra, rb = node_span(lines, reg)
        ph_reg, criou = ensure_phandle(lines, ra, rb, livre)
        if criou:
            livre += 1
        a, b = node_span(lines, find_by(lines, T9015))
        set_prop(lines, a, b, "AVDD-supply", "<" + hex(ph_reg) + ">")
        notas.append("AVDD-supply: regulador " + hex(ph_reg))
    else:
        notas.append("AVDD-supply: nenhum regulador 1V8 encontrado -- sobe com "
                     "dummy (aviso no dmesg, normalmente funciona)")

    # --- 2. toacodec: phandle e okay ---------------------------------------
    i = find_by(lines, TOACODEC)
    if i < 0:
        sys.exit("nao achei o no " + TOACODEC)
    a, b = node_span(lines, i)
    ph_toa, criou = ensure_phandle(lines, a, b, livre)
    if criou:
        livre += 1
    a, b = node_span(lines, find_by(lines, TOACODEC))
    set_prop(lines, a, b, "status", '"okay"')
    notas.append("toacodec: phandle " + hex(ph_toa) + ", status okay")

    # --- 3. no sound: widgets, rotas e codec-1 no dai-link do TDM_B --------
    i = find_by(lines, SOUNDCARD)
    if i < 0:
        sys.exit("nao achei o no sound (" + SOUNDCARD + ")")
    sa, sb = node_span(lines, i)

    ri, rv = get_prop(lines, sa, sb, "audio-routing")
    if ri < 0:
        sys.exit("no sound sem audio-routing")
    if "ACODEC LOLP" not in rv:
        # Direto do codec para a saida: o u200 passa por um amplificador na
        # placa ("10U2"), que TV box popular nao costuma ter.
        lines[ri] = (indent_of(lines[ri]) + "audio-routing = " + rv +
                     ', "Lineout", "ACODEC LOLP", "Lineout", "ACODEC LORP";')
        notas.append("audio-routing: + Lineout <- ACODEC LOLP/LORP")
    sa, sb = node_span(lines, find_by(lines, SOUNDCARD))
    set_prop(lines, sa, sb, "audio-widgets", '"Line", "Lineout"')
    notas.append("audio-widgets: Line/Lineout")

    sa, sb = node_span(lines, find_by(lines, SOUNDCARD))
    di = -1
    for k in range(sa, sb + 1):
        if re.match(r"\s*dai-link-3 \{", lines[k]):
            di = k
            break
    if di < 0:
        sys.exit("nao achei dai-link-3 (o TDM_B) dentro do no sound")
    da, db = node_span(lines, di)
    # O dai-link-4 do SPDIF ja nasce com codec-0/codec-1 no DTB de fabrica,
    # entao a guarda tem de olhar so o dai-link-3.
    if "codec-1" in "\n".join(lines[da:db + 1]):
        sys.exit("dai-link-3 ja tem codec-1 -- este DTB ja foi patcheado")

    # O analogico compartilha o TDM_B com o HDMI: o dai-link passa a ter dois
    # codecs, entao o "codec" que ja existe vira "codec-0".
    ck = -1
    for k in range(da, db + 1):
        if re.match(r"\s*codec \{", lines[k]):
            ck = k
            break
    if ck < 0:
        sys.exit("nao achei o codec dentro do dai-link-3")
    ca, cb = node_span(lines, ck)
    lines[ca] = lines[ca].replace("codec {", "codec-0 {")
    ind = indent_of(lines[ca])
    lines[cb + 1:cb + 1] = [
        "",
        ind + "codec-1 {",
        ind + "\tsound-dai = <" + hex(ph_toa) + " " + hex(TOACODEC_IN_B) + ">;",
        ind + "};",
    ]
    notas.append("dai-link-3: codec -> codec-0, mais codec-1 TOACODEC_IN_B")

    # --- 4. dai-link novo: TOACODEC_OUT -> acodec --------------------------
    sa, sb = node_span(lines, find_by(lines, SOUNDCARD))
    usados = []
    for k in range(sa, sb + 1):
        m = re.match(r"\s*dai-link-(\d+) \{", lines[k])
        if m:
            usados.append(int(m.group(1)))
    novo = max(usados) + 1 if usados else 0
    ind = indent_of(lines[sa]) + "\t"
    lines[sb:sb] = [
        "",
        ind + "dai-link-" + str(novo) + " {",
        ind + "\tsound-dai = <" + hex(ph_toa) + " " + hex(TOACODEC_OUT) + ">;",
        "",
        ind + "\tcodec {",
        ind + "\t\tsound-dai = <" + hex(ph_acodec) + ">;",
        ind + "\t};",
        ind + "};",
    ]
    notas.append("dai-link-" + str(novo) + ": TOACODEC_OUT -> acodec")

    return "\n".join(lines), notas


def verificar(antes, depois):
    """O patch so vale se nao quebrou nada do que ja funcionava."""
    p = []
    if SDIO_25MHZ not in depois:
        p.append("a correcao do SDIO (" + SDIO_25MHZ + ") sumiu -- o Wi-Fi "
                 "interno nao subiria")
    if "sd-uhs-sdr50" in depois:
        p.append("sd-uhs-sdr50 reapareceu -- o SDIO voltaria a falhar")
    for termo in (T9015, TOACODEC, "ACODEC LOLP", "TOACODEC_OUT".split("_")[0]):
        if termo not in depois:
            p.append("esperava encontrar " + termo + " no resultado")
    if depois.count('status = "disabled"') >= antes.count('status = "disabled"'):
        p.append("nenhum no saiu de disabled -- o patch nao pegou")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dtb")
    ap.add_argument("--apply", action="store_true",
                    help="instala de fato (sem isto, so mostra o que faria)")
    args = ap.parse_args()

    if not os.path.exists(args.dtb):
        sys.exit("nao existe: " + args.dtb)

    tmp = tempfile.mkdtemp(prefix="avaudio-")
    new_dts = os.path.join(tmp, "new.dts")
    new_dtb = os.path.join(tmp, "new.dtb")

    antes = sh("dtc", "-I", "dtb", "-O", "dts", args.dtb)
    saida, notas = patch_dts(antes)
    open(new_dts, "w").write(saida)
    sh("dtc", "-I", "dts", "-O", "dtb", "-o", new_dtb, new_dts)
    depois = sh("dtc", "-I", "dtb", "-O", "dts", new_dtb)

    print("== mudancas ==")
    for n in notas:
        print("  -", n)
    print("\n== verificacao ==")
    print("  DTB gerado: %d bytes (original: %d)"
          % (os.path.getsize(new_dtb), os.path.getsize(args.dtb)))
    problemas = verificar(antes, depois)
    if problemas:
        print("  REPROVADO:")
        for x in problemas:
            print("   !", x)
        sys.exit("\nnada foi instalado.")
    print("  passou: SDIO intacto, nos habilitados, rotas presentes")

    if not args.apply:
        print("\n(simulacao) para instalar de verdade:")
        print("  python3 %s %s --apply" % (sys.argv[0], args.dtb))
        return

    if not os.path.exists(args.dtb + ".orig"):
        shutil.copy2(args.dtb, args.dtb + ".orig")
        print("\nbackup: " + args.dtb + ".orig")
    else:
        print("\nbackup ja existia: " + args.dtb + ".orig (mantido)")
    shutil.copy2(args.dtb, args.dtb + ".pre-av")
    shutil.copy2(new_dtb, args.dtb)
    base = os.path.basename(args.dtb)
    print("instalado em " + args.dtb)
    print("\nreinicie e confira com:")
    print("  aplay -l")
    print("  amixer -c 0 scontrols | grep -i acodec")
    print("\nse nao bootar: cartao no leitor do PC, e")
    print("  cp " + base + ".orig " + base)


if __name__ == "__main__":
    main()
