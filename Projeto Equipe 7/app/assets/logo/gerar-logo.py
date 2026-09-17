#!/usr/bin/env python3
# Gera o logo Guardian Co. a partir de geometria pura.
#
# Não existe arquivo-fonte do logo: o símbolo foi desenhado aqui com quatro
# formas — o arco da pálpebra, o G aberto à direita, a barra do G até o centro
# e o ponto (pupila). Este script é a fonte da verdade. Para ajustar o desenho,
# mexa nas proporções em marca() e rode de novo; ele reescreve tudo.
#
# Saídas (caminhos relativos à pasta app/):
#   assets/logo/marca.svg              símbolo vetorial, branco, fundo transparente
#   assets/marca.png                   símbolo 512px, branco, fundo transparente (login)
#   assets/guardian-co.png             lockup "Guardian Co." em navy (README)
#   android/.../mipmap-*/ic_launcher.png  ícone do launcher nas cinco densidades
#
# Uso:  python assets/logo/gerar-logo.py      (rodar de dentro de app/)
import math, os, sys
from PIL import Image, ImageDraw, ImageFont

NAVY = (11, 26, 60)        # #0B1A3C — a cor-semente do app usa o mesmo valor
WHITE = (255, 255, 255)
S = 4                      # supersampling: desenha em 4x e reduz com LANCZOS

# Proporções do símbolo, relativas ao raio r do G — exceto o traço, que é
# fração do lado da tela para reproduzir exatamente o que a 2.0.0 publicou.
G_ARCO = (0, 310)          # graus, a partir das 3h, sentido horário: gap no
                           # quadrante superior direito
PUPILA = 0.30
PALPEBRA_R = 2.4           # raio do arco da pálpebra
PALPEBRA_C = (0.2, 0.9)    # centro dela, deslocado do centro do G
PALPEBRA_ARCO = (196, 288)
TRACO = 0.052              # traço, fração do lado da tela (é o que a 2.0.0 usou)
TRACO_LOCKUP = 0.028


def marca(draw, cx, cy, r, cor, esp):
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=G_ARCO[0], end=G_ARCO[1],
             fill=cor, width=esp)
    draw.line([(cx, cy), (cx + r, cy)], fill=cor, width=esp)
    draw.ellipse([cx + r - esp / 2, cy - esp / 2, cx + r + esp / 2, cy + esp / 2],
                 fill=cor)
    pr = r * PUPILA
    draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=cor)
    R = r * PALPEBRA_R
    ex, ey = cx + r * PALPEBRA_C[0], cy + r * PALPEBRA_C[1]
    draw.arc([ex - R, ey - R, ex + R, ey + R], start=PALPEBRA_ARCO[0],
             end=PALPEBRA_ARCO[1], fill=cor, width=esp)


def render_marca(tam, cor, fundo, margem=0.16):
    W = tam * S
    im = Image.new("RGBA", (W, W), fundo)
    marca(ImageDraw.Draw(im), W * 0.55, W * 0.58, W * (0.5 - margem) * 0.62, cor, int(W * TRACO))
    return im.resize((tam, tam), Image.LANCZOS)


def render_lockup(largura, cor, fundo):
    W = largura * S
    H = int(W * 0.62)
    im = Image.new("RGBA", (W, H), fundo)
    d = ImageDraw.Draw(im)
    marca(d, W * 0.52, H * 0.40, W * 0.13, cor, int(W * TRACO_LOCKUP))
    for fonte in ("C:/Windows/Fonts/courbd.ttf", "/usr/share/fonts/truetype/msttcorefonts/courbd.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"):
        try:
            f = ImageFont.truetype(fonte, int(W * 0.115))
            break
        except OSError:
            f = None
    if f is None:
        f = ImageFont.load_default()
    txt = "Guardian Co."
    bb = d.textbbox((0, 0), txt, font=f)
    d.text(((W - (bb[2] - bb[0])) / 2, H * 0.72), txt, fill=cor, font=f)
    return im.resize((largura, H // S), Image.LANCZOS)


def svg_marca():
    """Mesma geometria, em SVG. Convenção de ângulo igual à do PIL: a partir
    das 3h, sentido horário, y para baixo — por isso os pontos saem de
    (cos, sin) direto e o sweep é 1."""
    W = 100.0
    cx, cy, r = W * 0.55, W * 0.58, W * (0.5 - 0.16) * 0.62
    esp = W * TRACO

    def pt(c, R, ang):
        a = math.radians(ang)
        return c[0] + R * math.cos(a), c[1] + R * math.sin(a)

    def arco(c, R, a1, a2):
        x1, y1 = pt(c, R, a1)
        x2, y2 = pt(c, R, a2)
        grande = 1 if (a2 - a1) % 360 > 180 else 0
        return "M %.2f %.2f A %.2f %.2f 0 %d 1 %.2f %.2f" % (x1, y1, R, R, grande, x2, y2)

    R = r * PALPEBRA_R
    ec = (cx + r * PALPEBRA_C[0], cy + r * PALPEBRA_C[1])
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <!-- Guardian Co. — gerado por gerar-logo.py; edite lá, não aqui -->
  <g fill="none" stroke="#fff" stroke-width="%.2f" stroke-linecap="round">
    <path d="%s"/>
    <path d="%s"/>
    <line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>
  </g>
  <circle cx="%.2f" cy="%.2f" r="%.2f" fill="#fff"/>
</svg>
""" % (esp, arco((cx, cy), r, *G_ARCO), arco(ec, R, *PALPEBRA_ARCO),
       cx, cy, cx + r, cy, cx, cy, r * PUPILA)


if __name__ == "__main__":
    app = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(app)
    res = "android/app/src/main/res"
    for pasta, tam in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
        render_marca(tam, WHITE, NAVY, margem=0.12).save("%s/mipmap-%s/ic_launcher.png" % (res, pasta))
    render_marca(512, WHITE, (0, 0, 0, 0)).save("assets/marca.png")
    render_lockup(1200, WHITE, NAVY).save("assets/guardian-co.png")
    with open("assets/logo/marca.svg", "w", encoding="utf-8") as f:
        f.write(svg_marca())
    print("logo regenerado em", app)
