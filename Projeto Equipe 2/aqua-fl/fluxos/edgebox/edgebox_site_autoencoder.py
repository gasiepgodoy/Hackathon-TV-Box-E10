import json
from pathlib import Path
from datetime import datetime

from config import EDGEBOX_DATA_DIR, WEB_DIR

INDEX_PATH = WEB_DIR / "legacy.html"
DASHBOARD_PATH = WEB_DIR / "dashboard.html"
AE_PATH = EDGEBOX_DATA_DIR / "edgebox_autoencoder_latest.json"

START = "<!-- AUTOENCODER_BLOCK_START -->"
END = "<!-- AUTOENCODER_BLOCK_END -->"


def read_autoencoder():
    if not AE_PATH.exists():
        return None

    try:
        return json.loads(AE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def status_class(status):
    status = status or ""

    if "CRÍTICA" in status:
        return "#7f1d1d"
    if "ANOMALIA" in status:
        return "#9a3412"
    if "ATENÇÃO" in status:
        return "#854d0e"

    return "#14532d"


def build_block():
    ae = read_autoencoder()

    if not ae:
        return f"""
{START}
<div class="section" style="border: 1px solid #334155;">
    <h2>Modelo avançado: Autoencoder</h2>
    <p>
        O Autoencoder ainda não possui inferência disponível.
        Rode <code>python3 -m fluxos.edgebox.edgebox_autoencoder train</code> e depois
        <code>python3 -m fluxos.edgebox.edgebox_autoencoder infer</code>.
    </p>
</div>
{END}
"""

    status = ae.get("status", "N/A")
    bg = status_class(status)

    err = float(ae.get("reconstruction_error", 0))
    threshold = float(ae.get("threshold", 0))
    score = float(ae.get("anomaly_score", 0))
    samples = ae.get("model_samples", 0)
    created_at = ae.get("created_at", "N/A")

    return f"""
{START}
<div class="section" style="border: 1px solid #334155;">
    <h2>Modelo avançado: Autoencoder</h2>

    <div style="
        background: {bg};
        padding: 18px;
        border-radius: 14px;
        text-align: center;
        font-size: 24px;
        font-weight: bold;
        margin-bottom: 18px;
    ">
        Status do Autoencoder: {status} | Score: {score:.2f}
    </div>

    <div class="grid">
        <div class="card">
            <h2>Erro de reconstrução</h2>
            <div class="value">{err:.6f}</div>
            <p class="small">Diferença entre entrada real e reconstrução do modelo</p>
        </div>

        <div class="card">
            <h2>Limite aprendido</h2>
            <div class="value">{threshold:.6f}</div>
            <p class="small">Acima desse limite, o comportamento pode ser anômalo</p>
        </div>

        <div class="card">
            <h2>Score de anomalia</h2>
            <div class="value">{score:.2f}</div>
            <p class="small">Score = erro / limite</p>
        </div>

        <div class="card">
            <h2>Amostras de treino</h2>
            <div class="value">{samples}</div>
            <p class="small">Histórico usado para aprender o padrão normal</p>
        </div>
    </div>

    <p>
        O Autoencoder aprende o padrão normal da TV Box usando CPU, RAM,
        temperatura, disco, latência e carga do sistema. Quando o erro de
        reconstrução aumenta, o sistema identifica uma possível anomalia operacional.
    </p>

    <p>
        Última inferência: <b>{created_at}</b>
    </p>

    <p>
        <a href="/autoencoder.html" style="color:#93c5fd;font-weight:bold;">
            Abrir painel detalhado do Autoencoder
        </a>
    </p>
</div>
{END}
"""


def remove_old_block(html):
    if START in html and END in html:
        before = html.split(START)[0]
        after = html.split(END)[1]
        return before + after

    return html


def main():
    if not INDEX_PATH.exists():
        print("index.html não encontrado.")
        return

    html = INDEX_PATH.read_text(encoding="utf-8")
    html = remove_old_block(html)

    block = build_block()

    if '<div class="footer">' in html:
        html = html.replace('<div class="footer">', block + '\n    <div class="footer">', 1)
    elif "</body>" in html:
        html = html.replace("</body>", block + "\n</body>", 1)
    else:
        html += block

    INDEX_PATH.write_text(html, encoding="utf-8")
    DASHBOARD_PATH.write_text(html, encoding="utf-8")

    print(f"Autoencoder inserido no painel principal em {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
