"""Exportador: serve os dados da box para qualquer computador do AP.

Em campo nao existe servidor central nem internet. Quem quiser os dados conecta
no AP `hub-campo` e abre http://192.168.4.1:8000 no navegador — sem instalar
nada, sem SSH, sem pen drive.

Tres decisoes que parecem detalhe e nao sao:

1. A pagina nao referencia NENHUM recurso externo (fonte, CSS, icone de CDN).
   Offline, um `<link>` para fora nao deixa a pagina feia: deixa a pagina
   pendurada esperando um DNS que nao responde.

2. Exportar e leitura pura — nao mexe nas flags `enviado`. Elas sao a fila do
   backhaul (ver enviador.py). Se baixar um CSV marcasse registros como
   enviados, a primeira pessoa a clicar esvaziaria a fila.

3. O CSV sai no dialeto que o Excel em portugues espera: separador ';', virgula
   decimal e BOM. Ver comentario em `_fmt`.
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
import shutil
import sqlite3
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from .config import Config
from .db import conectar

log = logging.getLogger("hub.exportador")

# Excel em pt-BR usa ';' como separador de campo, porque ',' ja e o separador
# decimal. Um CSV com virgula abre com todas as colunas empilhadas na primeira
# — o sintoma classico de "o arquivo veio quebrado".
CSV_SEP = ";"

# Sem o BOM, o Excel assume a codificacao do sistema e "Análise" vira "AnÃ¡lise".
BOM = "﻿".encode("utf-8")

NEON = "#7BEC5A"
FUNDO = "#23282B"


@dataclass(frozen=True)
class Consulta:
    titulo: str
    sql: str


# As flags `enviado`/`enviado_em` ficam de fora de proposito: sao escrituracao
# interna da fila de saida, nao medicao. Quem abre o CSV quer dado de sensor.
CONSULTAS: dict[str, Consulta] = {
    "agregados": Consulta(
        "Resumos por janela (mín, máx, média)",
        """
        SELECT a.id,
               s.ieee                        AS sensor,
               COALESCE(s.nome, s.ieee)      AS nome,
               s.transporte                  AS origem,
               a.inicio                      AS inicio_epoch,
               datetime(a.inicio,'unixepoch','localtime') AS inicio,
               a.temp_min, a.temp_max, a.temp_media,
               a.umid_min, a.umid_max, a.umid_media,
               a.press_media, a.bateria, a.amostras
          FROM agregados a
          JOIN sensores s ON s.id = a.sensor_id
         ORDER BY a.inicio, s.ieee
        """,
    ),
    "leituras": Consulta(
        "Série temporal bruta",
        """
        SELECT l.id,
               s.ieee                        AS sensor,
               COALESCE(s.nome, s.ieee)      AS nome,
               s.transporte                  AS origem,
               l.ts                          AS ts_epoch,
               datetime(l.ts,'unixepoch','localtime') AS quando,
               l.temperatura, l.umidade, l.pressao, l.bateria, l.linkquality
          FROM leituras l
          JOIN sensores s ON s.id = l.sensor_id
         ORDER BY l.ts, s.ieee
        """,
    ),
    "eventos": Consulta(
        "Eventos detectados na borda",
        # LEFT JOIN: eventos.sensor_id e anulavel (evento pode nao ter sensor).
        """
        SELECT e.id,
               COALESCE(s.ieee, '-')         AS sensor,
               COALESCE(s.nome, s.ieee, '-') AS nome,
               e.ts                          AS ts_epoch,
               datetime(e.ts,'unixepoch','localtime') AS quando,
               e.tipo, e.valor, e.detalhe, e.prioridade
          FROM eventos e
          LEFT JOIN sensores s ON s.id = e.sensor_id
         ORDER BY e.ts
        """,
    ),
    "sensores": Consulta(
        "Cadastro dos sensores",
        """
        SELECT id, ieee, nome, modelo, local, transporte,
               datetime(criado_em,'unixepoch','localtime') AS criado_em
          FROM sensores
         ORDER BY id
        """,
    ),
}

ESCOPOS = {
    "agregados": ["agregados", "sensores"],
    "tudo": ["leituras", "agregados", "eventos", "sensores"],
}


def _fmt(v) -> str:
    """Valor do SQLite -> texto de celula, no dialeto pt-BR.

    O arredondamento em 3 casas evita que uma media vire
    '21,333333333333332' na planilha. NULL vira celula vazia, nao 'None'.
    """
    if v is None:
        return ""
    if isinstance(v, float):
        return str(round(v, 3)).replace(".", ",")
    return str(v)


def csv_bytes(con: sqlite3.Connection, nome: str, lote: int = 500) -> Iterator[bytes]:
    """Gera o CSV em pedacos.

    Gerador, e nao string: as leituras brutas podem passar de dezenas de
    milhares de linhas, e montar tudo em memoria numa TV Box e desperdicio —
    iterar o cursor custa o mesmo e o download comeca na hora.
    """
    cur = con.execute(CONSULTAS[nome].sql)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=CSV_SEP, lineterminator="\r\n")

    w.writerow([d[0] for d in cur.description])
    yield BOM + buf.getvalue().encode("utf-8")
    buf.seek(0), buf.truncate()

    for n, linha in enumerate(cur, 1):
        w.writerow([_fmt(v) for v in linha])
        if n % lote == 0:
            yield buf.getvalue().encode("utf-8")
            buf.seek(0), buf.truncate()
    if buf.tell():
        yield buf.getvalue().encode("utf-8")


def montar_zip(con: sqlite3.Connection, escopo: str, destino: Path) -> Path:
    """Um CSV por tabela dentro de um .zip — CSV nao comporta varias tabelas."""
    agora = time.localtime()[:6]
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for nome in ESCOPOS[escopo]:
            # Sem o ZipInfo explicito o zipfile data os membros em 1980 — o que
            # quem extrai le como arquivo corrompido, nao como detalhe.
            info = zipfile.ZipInfo(f"{nome}.csv", date_time=agora)
            info.compress_type = zipfile.ZIP_DEFLATED
            with z.open(info, "w") as f:
                for pedaco in csv_bytes(con, nome):
                    f.write(pedaco)
        z.writestr(zipfile.ZipInfo("LEIA-ME.txt", date_time=agora),
                   _leiame(con, escopo))
    return destino


def snapshot(con: sqlite3.Connection, destino: Path) -> Path:
    """Copia consistente do banco, com o coletor rodando.

    Nao da para servir /var/lib/hub/dados.db direto: o schema liga
    `journal_mode = WAL`, entao as transacoes mais recentes vivem no arquivo
    -wal, fora do .db. Copiar o .db sozinho entrega um banco sem as ultimas
    leituras — justamente as que interessam numa demonstracao.

    `Connection.backup` e a API de backup online do SQLite: le um snapshot
    coerente sem parar quem escreve. O VACUUM no destino so compacta, para o
    download ficar menor no Wi-Fi.
    """
    alvo = sqlite3.connect(str(destino))
    try:
        con.backup(alvo)
        alvo.execute("VACUUM")
    finally:
        alvo.close()
    return destino


def resumo(con: sqlite3.Connection) -> dict:
    """Numeros do cabecalho da pagina."""
    um = lambda s: con.execute(s).fetchone()[0]
    r = {
        "sensores": um("SELECT COUNT(*) FROM sensores"),
        "leituras": um("SELECT COUNT(*) FROM leituras"),
        "agregados": um("SELECT COUNT(*) FROM agregados"),
        "eventos": um("SELECT COUNT(*) FROM eventos"),
        "primeira": um("SELECT datetime(MIN(ts),'unixepoch','localtime') FROM leituras"),
        "ultima": um("SELECT datetime(MAX(ts),'unixepoch','localtime') FROM leituras"),
        "ultima_epoch": um("SELECT MAX(ts) FROM leituras"),
    }
    r["origens"] = {
        linha["transporte"]: linha["n"]
        for linha in con.execute(
            "SELECT transporte, COUNT(*) AS n FROM sensores GROUP BY transporte")
    }
    return r


def _ha_quanto(epoch: int | None, agora: int | None = None) -> str:
    """'ha 3 min'. Serve para ver de relance se a box parou de coletar."""
    if not epoch:
        return "nunca"
    seg = max(0, (agora if agora is not None else int(time.time())) - epoch)
    if seg < 90:
        return f"há {seg} s"
    if seg < 5400:
        return f"há {seg // 60} min"
    if seg < 172800:
        return f"há {seg // 3600} h"
    return f"há {seg // 86400} dias"


def _leiame(con: sqlite3.Connection, escopo: str) -> str:
    r = resumo(con)
    tabelas = "\n".join(
        f"  {n}.csv  — {CONSULTAS[n].titulo}" for n in ESCOPOS[escopo])
    return (
        "EdgeVision — exportação de dados\n"
        f"Gerado em {time.strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        f"{tabelas}\n\n"
        f"Sensores: {r['sensores']} | Leituras: {r['leituras']} | "
        f"Agregados: {r['agregados']} | Eventos: {r['eventos']}\n"
        f"Período coberto: {r['primeira'] or '-'} a {r['ultima'] or '-'}\n\n"
        "Formato: UTF-8 com BOM, separador ';', vírgula decimal — abre direto\n"
        "no Excel/LibreOffice em português. Cada tabela traz o tempo em duas\n"
        "colunas: o epoch (para processar) e a data local (para ler).\n"
    )


# --------------------------------------------------------------------------
# Pagina
# --------------------------------------------------------------------------

_CSS = f"""
* {{ box-sizing: border-box; }}
body {{ margin:0; padding:32px 20px; background:{FUNDO}; color:#E6EDE4;
        font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width:720px; margin:0 auto; }}
header {{ display:flex; align-items:center; gap:14px; margin-bottom:6px; }}
h1 {{ font-size:27px; margin:0; letter-spacing:-0.5px; color:{NEON}; font-weight:700; }}
.sub {{ color:#6FA55E; font-size:12px; letter-spacing:1.4px; text-transform:uppercase; }}
.painel {{ background:#2B3134; border:1px solid #3A4245; border-radius:12px;
           padding:18px 20px; margin:26px 0; }}
.grade {{ display:flex; flex-wrap:wrap; gap:26px; }}
.n {{ font-size:25px; font-weight:700; color:{NEON}; line-height:1.1; }}
.r {{ font-size:11px; color:#9BAA9C; text-transform:uppercase; letter-spacing:0.8px; }}
.periodo {{ margin-top:16px; padding-top:14px; border-top:1px solid #3A4245;
            font-size:13px; color:#9BAA9C; line-height:1.7; }}
.periodo b {{ color:#E6EDE4; font-weight:600; }}
h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:1.2px;
      color:#9BAA9C; margin:30px 0 12px; font-weight:600; }}
a.botao {{ display:block; text-decoration:none; background:#2B3134;
           border:1px solid #3A4245; border-left:3px solid {NEON};
           border-radius:10px; padding:15px 18px; margin-bottom:10px; color:inherit; }}
a.botao:hover {{ background:#333A3D; border-color:{NEON}; }}
a.botao .t {{ font-weight:600; font-size:15px; color:{NEON}; }}
a.botao .d {{ font-size:13px; color:#9BAA9C; margin-top:3px; line-height:1.5; }}
.extras {{ font-size:13px; color:#9BAA9C; line-height:2; }}
.extras a {{ color:{NEON}; }}
footer {{ margin-top:32px; padding-top:16px; border-top:1px solid #3A4245;
          font-size:12px; color:#78857A; line-height:1.8; }}
.aviso {{ background:#3A3527; border-color:#6B5D2E; border-left-color:#D9B84A; }}
.aviso .t {{ color:#D9B84A; }}
"""

_LOGO = (
    # Hexagono simplificado: a arte de linha fina da logo nao sobrevive a 38 px.
    f'<svg viewBox="0 0 400 400" width="40" height="40" aria-hidden="true">'
    f'<path d="M200,32 L345.5,116 L345.5,284 L200,368 L54.5,284 L54.5,116 Z" '
    f'fill="none" stroke="{NEON}" stroke-width="26" stroke-linejoin="round"/>'
    f'<circle cx="200" cy="200" r="52" fill="{NEON}"/></svg>'
)


def _botao(href: str, titulo: str, desc: str, classe: str = "") -> str:
    return (f'<a class="botao {classe}" href="{href}">'
            f'<div class="t">{titulo}</div><div class="d">{desc}</div></a>')


def pagina(r: dict, agora: int | None = None) -> str:
    hoje = time.strftime("%Y-%m-%d")
    origens = ", ".join(f"{k} {v}" for k, v in sorted(r["origens"].items())) or "nenhuma"

    if r["leituras"] == 0:
        destaque = _botao("#", "Nenhuma leitura no banco",
                          "A box ainda não gravou nada. Verifique o coletor: "
                          "<code>systemctl status hub-coletor</code>", "aviso")
    else:
        destaque = (
            _botao(f"/agregados.csv?d={hoje}", "Somente agregados (CSV)",
                   f"{r['agregados']} linhas — mín, máx e média por janela. "
                   "Abre direto no Excel. É o que quase todo mundo quer.")
            + _botao(f"/tudo.zip?d={hoje}", "Todos os dados (ZIP)",
                     f"{r['leituras']} leituras brutas + agregados + eventos + "
                     "cadastro, um CSV por tabela.")
            + _botao(f"/dados.db?d={hoje}", "Banco completo (SQLite)",
                     "Cópia consistente do banco, para abrir no DB Browser e "
                     "consultar com SQL.")
        )

    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EdgeVision — exportar dados</title>
<style>{_CSS}</style>
</head><body><main>

<header>{_LOGO}<div>
  <h1>EdgeVision</h1>
  <div class="sub">Exportar dados</div>
</div></header>

<div class="painel">
  <div class="grade">
    <div><div class="n">{r['sensores']}</div><div class="r">Sensores</div></div>
    <div><div class="n">{r['leituras']}</div><div class="r">Leituras</div></div>
    <div><div class="n">{r['agregados']}</div><div class="r">Agregados</div></div>
    <div><div class="n">{r['eventos']}</div><div class="r">Eventos</div></div>
  </div>
  <div class="periodo">
    Origens: <b>{origens}</b><br>
    Período coberto: <b>{r['primeira'] or '-'}</b> até <b>{r['ultima'] or '-'}</b><br>
    Última leitura: <b>{_ha_quanto(r['ultima_epoch'], agora)}</b>
  </div>
</div>

<h2>Baixar</h2>
{destaque}

<h2>Tabelas avulsas</h2>
<div class="extras">
  <a href="/leituras.csv?d={hoje}">leituras.csv</a> &nbsp;·&nbsp;
  <a href="/eventos.csv?d={hoje}">eventos.csv</a> &nbsp;·&nbsp;
  <a href="/sensores.csv?d={hoje}">sensores.csv</a> &nbsp;·&nbsp;
  <a href="/">atualizar</a>
</div>

<footer>
  Os CSV saem em UTF-8 com BOM, separador <b>;</b> e vírgula decimal — o dialeto
  que o Excel em português abre sem perguntar nada.<br>
  Cada tabela traz o tempo duas vezes: o epoch, para processar, e a data local,
  para ler.
</footer>

</main></body></html>
"""


# --------------------------------------------------------------------------
# Servidor
# --------------------------------------------------------------------------

class Manipulador(BaseHTTPRequestHandler):
    server_version = "EdgeVision"
    caminho_banco = ""          # preenchido por `servir`

    def log_message(self, formato, *args):      # noqa: A003 - assinatura da stdlib
        log.info("%s %s", self.address_string(), formato % args)

    # -- utilitarios de resposta ------------------------------------------
    def _cabecalho(self, tipo: str, anexo: str | None = None,
                   tamanho: int | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        if anexo:
            self.send_header("Content-Disposition", f'attachment; filename="{anexo}"')
        if tamanho is not None:
            self.send_header("Content-Length", str(tamanho))
        # O banco muda a cada minuto; navegador nao pode servir copia velha.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _erro(self, codigo: int, texto: str) -> None:
        corpo = texto.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _abrir(self) -> sqlite3.Connection | None:
        """Conexao propria por requisicao — conexao SQLite nao cruza threads.

        Se o banco nao existir, responde erro em vez de deixar o sqlite criar um
        vazio: um CSV com zero linhas parece coleta falhada, e o verdadeiro
        problema (caminho errado no hub.ini) ficaria invisivel.
        """
        if not Path(self.caminho_banco).is_file():
            self._erro(503, f"banco não encontrado em {self.caminho_banco}\n"
                            "verifique [banco] caminho no hub.ini")
            return None
        return conectar(self.caminho_banco)

    # -- rotas -------------------------------------------------------------
    def do_GET(self) -> None:                   # noqa: N802 - assinatura da stdlib
        rota = self.path.split("?")[0]
        if rota == "/favicon.ico":
            self._erro(404, "sem favicon")
            return

        con = self._abrir()
        if con is None:
            return
        try:
            if rota == "/":
                self._pagina(con)
            elif rota == "/dados.db":
                self._banco(con)
            elif rota in ("/tudo.zip", "/agregados.zip"):
                self._zip(con, "tudo" if rota == "/tudo.zip" else "agregados")
            elif rota.endswith(".csv") and rota[1:-4] in CONSULTAS:
                self._csv(con, rota[1:-4])
            else:
                self._erro(404, "rota desconhecida; use /")
        except BrokenPipeError:
            # Download cancelado no navegador. Normal, nao e falha.
            log.info("download interrompido pelo cliente")
        finally:
            con.close()

    def _pagina(self, con) -> None:
        corpo = pagina(resumo(con)).encode("utf-8")
        self._cabecalho("text/html; charset=utf-8", tamanho=len(corpo))
        self.wfile.write(corpo)

    def _csv(self, con, nome: str) -> None:
        self._cabecalho("text/csv; charset=utf-8", _nome_arquivo(f"{nome}.csv"))
        for pedaco in csv_bytes(con, nome):
            self.wfile.write(pedaco)

    def _zip(self, con, escopo: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            alvo = montar_zip(con, escopo, Path(tmp) / "e.zip")
            self._enviar_arquivo(alvo, "application/zip",
                                 _nome_arquivo(f"{escopo}.zip"))

    def _banco(self, con) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            alvo = snapshot(con, Path(tmp) / "dados.db")
            self._enviar_arquivo(alvo, "application/vnd.sqlite3",
                                 _nome_arquivo("dados.db"))

    def _enviar_arquivo(self, caminho: Path, tipo: str, anexo: str) -> None:
        self._cabecalho(tipo, anexo, caminho.stat().st_size)
        with caminho.open("rb") as f:
            shutil.copyfileobj(f, self.wfile)


def _nome_arquivo(sufixo: str) -> str:
    return f"edgevision-{time.strftime('%Y%m%d-%H%M')}-{sufixo}"


def servir(endereco: str, porta: int, caminho_banco: str) -> ThreadingHTTPServer:
    """Sobe o servidor. Nao bloqueia — quem chama decide.

    ThreadingHTTPServer porque o download do banco inteiro pode levar segundos e
    nao pode deixar a pagina sem resposta nesse meio tempo.
    """
    Manipulador.caminho_banco = caminho_banco
    return ThreadingHTTPServer((endereco, porta), Manipulador)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Serve os dados da box para download pelo AP")
    ap.add_argument("--endereco", default=None,
                    help="interface de escuta (padrao: [exportador] endereco)")
    ap.add_argument("--porta", type=int, default=None)
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = Config()
    endereco = args.endereco or cfg.txt("exportador", "endereco")
    porta = args.porta or cfg.num("exportador", "porta")
    banco = cfg.txt("banco", "caminho")

    if endereco in ("", "0.0.0.0", "::"):
        # Nao e paranoia: a box tem IP publico da universidade. Escutar em todas
        # as interfaces publica o banco inteiro, sem autenticacao, na internet —
        # e funciona identico no AP, entao o teste passa e ninguem percebe.
        log.warning("escutando em TODAS as interfaces (%s): o banco fica exposto "
                    "em qualquer rede alcancavel, nao so no AP", endereco or "0.0.0.0")

    srv = servir(endereco, porta, banco)
    log.info("exportador em http://%s:%d/  (banco: %s)", endereco, porta, banco)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
