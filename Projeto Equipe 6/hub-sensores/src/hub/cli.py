"""CLI de inspecao e manutencao do hub."""
from __future__ import annotations

import argparse
import sys

from .config import Config
from .db import conectar, inicializar, purgar


def _tabela(linhas, colunas) -> str:
    if not linhas:
        return "(vazio)"
    larg = [max(len(c), *(len(str(l[c])) for l in linhas)) for c in colunas]
    cab = "  ".join(c.ljust(w) for c, w in zip(colunas, larg))
    sep = "  ".join("-" * w for w in larg)
    corpo = "\n".join(
        "  ".join(str(l[c]).ljust(w) for c, w in zip(colunas, larg)) for l in linhas
    )
    return f"{cab}\n{sep}\n{corpo}"


def cmd_status(con, _args) -> int:
    q = lambda s: con.execute(s).fetchone()[0]
    print("=== Hub de sensores")
    print(f"sensores cadastrados : {q('SELECT COUNT(*) FROM sensores')}")
    print(f"leituras armazenadas : {q('SELECT COUNT(*) FROM leituras')}")
    print(f"agregados            : {q('SELECT COUNT(*) FROM agregados')}"
          f"  (pendentes: {q('SELECT COUNT(*) FROM agregados WHERE enviado=0')})")
    print(f"eventos              : {q('SELECT COUNT(*) FROM eventos')}"
          f"  (pendentes: {q('SELECT COUNT(*) FROM eventos WHERE enviado=0')})")
    ultima = con.execute(
        "SELECT datetime(MAX(ts),'unixepoch','localtime') FROM leituras").fetchone()[0]
    print(f"ultima leitura       : {ultima or '-'}")
    return 0


def cmd_leituras(con, args) -> int:
    linhas = con.execute(
        "SELECT * FROM v_ultimas_leituras LIMIT ?", (args.n,)).fetchall()
    print(_tabela(linhas, ["sensor", "quando", "temperatura", "umidade", "bateria"]))
    return 0


def cmd_pendentes(con, _args) -> int:
    ev = con.execute(
        "SELECT e.id, COALESCE(s.nome,'-') AS sensor, e.tipo, e.valor,"
        " datetime(e.ts,'unixepoch','localtime') AS quando, e.prioridade"
        " FROM eventos e LEFT JOIN sensores s ON s.id=e.sensor_id"
        " WHERE e.enviado=0 ORDER BY e.prioridade DESC, e.ts").fetchall()
    print("--- eventos pendentes")
    print(_tabela(ev, ["id", "sensor", "tipo", "valor", "quando", "prioridade"]))
    ag = con.execute(
        "SELECT a.id, COALESCE(s.nome,'-') AS sensor,"
        " datetime(a.inicio,'unixepoch','localtime') AS janela,"
        " ROUND(a.temp_min,1) AS tmin, ROUND(a.temp_max,1) AS tmax,"
        " ROUND(a.temp_media,1) AS tmed, a.amostras"
        " FROM agregados a JOIN sensores s ON s.id=a.sensor_id"
        " WHERE a.enviado=0 ORDER BY a.inicio").fetchall()
    print("\n--- agregados pendentes")
    print(_tabela(ag, ["id", "sensor", "janela", "tmin", "tmax", "tmed", "amostras"]))
    return 0


def cmd_nomear(con, args) -> int:
    cur = con.execute("UPDATE sensores SET nome=?, local=? WHERE ieee=?",
                      (args.nome, args.local, args.ieee))
    print("atualizado" if cur.rowcount else f"sensor {args.ieee} nao encontrado")
    return 0 if cur.rowcount else 1


def cmd_espiar(con, args) -> int:
    """Mostra tudo que passa no MQTT e se o coletor aceitaria ou nao — e por que."""
    import subprocess

    from .coletor import diagnosticar, parse_linha

    cfg = Config()
    cmd = ["mosquitto_sub", "-h", cfg.txt("mqtt", "host"), "-p", cfg.txt("mqtt", "port"),
           "-t", args.topico, "-F", "%j"]
    print(f"espiando '{args.topico}' em {cfg.txt('mqtt','host')} — Ctrl+C para sair\n")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, bufsize=1)
    except FileNotFoundError:
        print("mosquitto_sub nao encontrado: apt install mosquitto-clients")
        return 1
    vistos = 0
    try:
        assert proc.stdout is not None
        for linha in proc.stdout:
            msg = parse_linha(linha)
            if not msg:
                continue
            topico, payload = msg
            leitura, motivo = diagnosticar(topico, payload)
            marca = "ACEITA " if leitura else "ignorada"
            print(f"[{marca}] {topico}\n           {motivo}")
            if leitura:
                print(f"           -> sensor={leitura[0]} temp={leitura[2]} umid={leitura[3]}")
            vistos += 1
            if args.n and vistos >= args.n:
                break
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
    if vistos == 0:
        print("NENHUMA mensagem recebida — o Zigbee2MQTT esta publicando?"
              "\n  systemctl status zigbee2mqtt")
    return 0


def cmd_purgar(con, args) -> int:
    n = purgar(con, args.dias)
    con.execute("VACUUM")
    print(f"{n} leituras removidas (mais antigas que {args.dias} dias)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="hub", description="Hub de sensores")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="cria o banco").set_defaults(fn=lambda c, a: 0)
    sub.add_parser("status", help="visao geral").set_defaults(fn=cmd_status)

    p = sub.add_parser("leituras", help="ultimas leituras")
    p.add_argument("-n", type=int, default=20)
    p.set_defaults(fn=cmd_leituras)

    sub.add_parser("pendentes", help="fila aguardando o LoRa").set_defaults(fn=cmd_pendentes)

    p = sub.add_parser("nomear", help="da nome amigavel a um sensor")
    p.add_argument("ieee")
    p.add_argument("nome")
    p.add_argument("--local", default=None)
    p.set_defaults(fn=cmd_nomear)

    p = sub.add_parser("espiar", help="mostra o que passa no MQTT e se seria aceito")
    p.add_argument("--topico", default="zigbee2mqtt/#")
    p.add_argument("-n", type=int, default=0, help="para apos N mensagens (0 = infinito)")
    p.set_defaults(fn=cmd_espiar, sem_banco=True)

    p = sub.add_parser("purgar", help="remove leituras brutas antigas")
    p.add_argument("--dias", type=int, default=90)
    p.set_defaults(fn=cmd_purgar)

    args = ap.parse_args()
    # `espiar` so observa o MQTT: nao deve falhar se o banco estiver
    # inacessivel (usuario sem permissao, diretorio ainda inexistente).
    if getattr(args, "sem_banco", False):
        return args.fn(None, args)
    cfg = Config()
    con = conectar(cfg.txt("banco", "caminho"))
    inicializar(con)
    try:
        return args.fn(con, args)
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
