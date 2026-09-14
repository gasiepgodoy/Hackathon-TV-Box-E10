"""Testes do hub. Rodar: python3 tests/test_hub.py"""
from __future__ import annotations

import base64
import io
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hub.agregador import agregar                                    # noqa: E402
from hub.coletor import diagnosticar, extrair, parse_linha     # noqa: E402
from hub.config import Config                                        # noqa: E402
from hub.db import (conectar, gravar_leituras, inicializar,     # noqa: E402
                    migrar, purgar)
from hub.enviador import (TransporteIndisponivel, TransporteLog,     # noqa: E402
                          empacotar_agregado, enviar_pendentes)
from hub.eventos import detectar                                     # noqa: E402
from hub.exportador import (_ha_quanto, csv_bytes, montar_zip,       # noqa: E402
                            pagina, resumo, servir, snapshot)

HORA = 3600


def _l(ieee, ts, temp, umid=50.0, bateria=90, lqi=100, **extra):
    """Atalho para montar o dict de uma leitura nos testes."""
    return {"ieee": ieee, "ts": ts, "temperatura": temp, "umidade": umid,
            "bateria": bateria, "linkquality": lqi, **extra}


class BaseHub(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = conectar(Path(self.tmp.name) / "t.db")
        inicializar(self.con)
        self.cfg = Config()

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()


class TestColetor(BaseHub):
    def test_extrai_leitura_valida(self):
        r = extrair("zigbee2mqtt/estufa", '{"temperature":21.5,"humidity":60,"battery":90,"linkquality":150}')
        self.assertIsNotNone(r)
        self.assertEqual(r["ieee"], "estufa")
        self.assertEqual(r["temperatura"], 21.5)
        self.assertEqual(r["transporte"], "zigbee")

    def test_ignora_topicos_da_bridge(self):
        self.assertIsNone(extrair("zigbee2mqtt/bridge/state", '{"state":"online"}'))
        self.assertIsNone(extrair("zigbee2mqtt/bridge/devices", "[]"))

    def test_ignora_payload_sem_grandeza(self):
        self.assertIsNone(extrair("zigbee2mqtt/x", '{"linkquality":10}'))
        self.assertIsNone(extrair("zigbee2mqtt/x", "nao-e-json"))

    def test_parse_de_topico_com_espaco(self):
        """Z2M aceita espaco no friendly_name; o parse nao pode partir o topico."""
        linha = ('{"tst":"2026-08-19T14:00:00Z","topic":"zigbee2mqtt/Sensor Temperatura",'
                 '"qos":0,"retain":0,"payloadlen":42,'
                 '"payload":"{\\"temperature\\":24.5,\\"humidity\\":60}"}')
        msg = parse_linha(linha)
        self.assertIsNotNone(msg)
        topico, payload = msg
        self.assertEqual(topico, "zigbee2mqtt/Sensor Temperatura")
        leitura = extrair(topico, payload)
        self.assertIsNotNone(leitura)
        self.assertEqual(leitura["ieee"], "Sensor Temperatura")
        self.assertEqual(leitura["temperatura"], 24.5)

    def test_parse_ignora_linha_invalida(self):
        self.assertIsNone(parse_linha(""))
        self.assertIsNone(parse_linha("nao é json"))

    def test_grava_em_lote_e_cadastra_sensor(self):
        ts = int(time.time())
        n = gravar_leituras(self.con, [_l("s1", ts, 20.0), _l("s2", ts, 21.0)])
        self.assertEqual(n, 2)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM sensores").fetchone()[0], 2)


class TestColetorLoRa(BaseHub):
    """Uplinks do ChirpStack — a segunda origem do hub."""

    TOPICO = "application/7f3a/device/62afdeb4e62c19e2/event/up"

    def _uplink(self, corpo: dict = None, data_b64: str = None, rssi=-97):
        m = {
            "deviceInfo": {"deviceName": "pomar_lora",
                           "devEui": "62afdeb4e62c19e2"},
            "devAddr": "00e8cdfb", "fCnt": 3, "fPort": 1,
            "rxInfo": [{"gatewayId": "3c71bfffff6b8270", "rssi": rssi, "snr": 9.0}],
        }
        if corpo is not None:
            m["object"] = corpo
        if data_b64 is not None:
            m["data"] = data_b64
        return json.dumps(m)

    def test_uplink_com_codec_configurado(self):
        r = extrair(self.TOPICO, self._uplink(
            corpo={"temperature": 23.4, "humidity": 61.0, "pressure": 1013.2}))
        self.assertIsNotNone(r)
        self.assertEqual(r["ieee"], "pomar_lora")
        self.assertEqual(r["temperatura"], 23.4)
        self.assertEqual(r["pressao"], 1013.2)
        self.assertEqual(r["transporte"], "lora")
        self.assertEqual(r["linkquality"], -97)      # RSSI no lugar do LQI

    def test_uplink_sem_codec_decodifica_base64(self):
        """Sem codec no ChirpStack, o payload chega em base64 — e o nó manda JSON."""
        bruto = base64.b64encode(
            b'{"temperature":19.8,"humidity":72,"pressure":1009.5}').decode()
        r = extrair(self.TOPICO, self._uplink(data_b64=bruto))
        self.assertIsNotNone(r)
        self.assertEqual(r["temperatura"], 19.8)
        self.assertEqual(r["pressao"], 1009.5)

    def test_payload_binario_pede_codec(self):
        bruto = base64.b64encode(bytes([0x01, 0x02, 0x03])).decode()
        leitura, motivo = diagnosticar(self.TOPICO, self._uplink(data_b64=bruto))
        self.assertIsNone(leitura)
        self.assertIn("codec", motivo)

    def test_ignora_eventos_que_nao_sao_uplink(self):
        topico = "application/7f3a/device/62afdeb4e62c19e2/event/join"
        self.assertIsNone(extrair(topico, "{}"))

    def test_grava_lora_e_zigbee_no_mesmo_banco(self):
        ts = int(time.time())
        gravar_leituras(self.con, [
            _l("estufa", ts, 20.0),
            _l("pomar_lora", ts, 21.0, pressao=1012.0, transporte="lora"),
        ])
        origens = dict(self.con.execute(
            "SELECT ieee, transporte FROM sensores").fetchall())
        self.assertEqual(origens["estufa"], "zigbee")
        self.assertEqual(origens["pomar_lora"], "lora")
        press = self.con.execute(
            "SELECT pressao FROM leituras WHERE pressao IS NOT NULL").fetchone()[0]
        self.assertEqual(press, 1012.0)


class TestMigracao(unittest.TestCase):
    def test_adiciona_colunas_em_banco_antigo(self):
        """Bancos ja em producao na box precisam ganhar as colunas novas."""
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "antigo.db"
            velho = sqlite3.connect(caminho)
            velho.executescript("""
                CREATE TABLE sensores (id INTEGER PRIMARY KEY, ieee TEXT UNIQUE);
                CREATE TABLE leituras (id INTEGER PRIMARY KEY, sensor_id INTEGER,
                                       ts INTEGER, temperatura REAL);
                CREATE TABLE agregados (id INTEGER PRIMARY KEY, sensor_id INTEGER,
                                        inicio INTEGER);
            """)
            velho.commit(); velho.close()

            con = conectar(caminho)
            aplicadas = migrar(con)
            self.assertIn("leituras.pressao", aplicadas)
            self.assertIn("sensores.transporte", aplicadas)
            self.assertIn("agregados.press_media", aplicadas)
            # rodar de novo nao deve mudar nada
            self.assertEqual(migrar(con), [])
            con.close()


class TestAgregador(BaseHub):
    def _povoar(self, base: int):
        # Uma geada curta no meio da hora: some na media, sobrevive no minimo.
        temps = [10.0] * 10 + [1.0] * 3 + [10.0] * 10
        linhas = [_l("s1", base + i * 60, t) for i, t in enumerate(temps)]
        gravar_leituras(self.con, linhas)

    def test_agrega_janela_fechada_preservando_min_max(self):
        base = (int(time.time()) // HORA) * HORA - 2 * HORA
        self._povoar(base)
        self.assertEqual(agregar(self.con, HORA), 1)
        r = self.con.execute("SELECT * FROM agregados").fetchone()
        self.assertEqual(r["temp_min"], 1.0)
        self.assertEqual(r["temp_max"], 10.0)
        self.assertGreater(r["temp_media"], 7.0)   # a media esconde a geada
        self.assertEqual(r["amostras"], 23)

    def test_nao_agrega_janela_em_aberto(self):
        agora = int(time.time())
        gravar_leituras(self.con, [_l("s1", agora, 20.0)])
        self.assertEqual(agregar(self.con, HORA), 0)

    def test_reprocessar_nao_reenfileira_o_que_ja_subiu(self):
        base = (int(time.time()) // HORA) * HORA - 2 * HORA
        self._povoar(base)
        agregar(self.con, HORA)
        enviar_pendentes(self.con, TransporteLog())
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM agregados WHERE enviado=0").fetchone()[0], 0)
        agregar(self.con, HORA)   # roda de novo
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM agregados WHERE enviado=0").fetchone()[0], 0)


class TestEventos(BaseHub):
    def test_detecta_geada(self):
        gravar_leituras(self.con, [_l("s1", int(time.time()), 1.0)])
        detectar(self.con, self.cfg)
        tipos = [r["tipo"] for r in self.con.execute("SELECT tipo FROM eventos")]
        self.assertIn("geada", tipos)

    def test_detecta_sensor_mudo(self):
        antigo = int(time.time()) - 4 * HORA
        gravar_leituras(self.con, [_l("s1", antigo, 20.0)])
        detectar(self.con, self.cfg)
        tipos = [r["tipo"] for r in self.con.execute("SELECT tipo FROM eventos")]
        self.assertIn("sensor_mudo", tipos)

    def test_nao_repete_evento_identico(self):
        gravar_leituras(self.con, [_l("s1", int(time.time()), 1.0)])
        detectar(self.con, self.cfg)
        detectar(self.con, self.cfg)
        n = self.con.execute("SELECT COUNT(*) FROM eventos WHERE tipo='geada'").fetchone()[0]
        self.assertEqual(n, 1)

    def test_bateria_baixa(self):
        gravar_leituras(self.con, [_l("s1", int(time.time()), 20.0, bateria=5)])
        detectar(self.con, self.cfg)
        tipos = [r["tipo"] for r in self.con.execute("SELECT tipo FROM eventos")]
        self.assertIn("bateria_baixa", tipos)


class TestEnviador(BaseHub):
    def _preparar(self, n_janelas=3):
        base = (int(time.time()) // HORA) * HORA - (n_janelas + 1) * HORA
        linhas = []
        for j in range(n_janelas):
            for i in range(5):
                linhas.append(_l("s1", base + j * HORA + i * 60, 20.0 + i))
        gravar_leituras(self.con, linhas)
        agregar(self.con, HORA)

    def test_agregado_cabe_em_14_bytes(self):
        """Tres agregados (42 B) cabem numa mensagem LoRa de 51 B."""
        self._preparar(1)
        r = self.con.execute("SELECT * FROM agregados").fetchone()
        self.assertEqual(len(empacotar_agregado(r)), 14)
        self.assertLessEqual(3 * 14, 51)

    def test_envio_marca_como_enviado(self):
        self._preparar()
        res = enviar_pendentes(self.con, TransporteLog())
        self.assertEqual(res["agregados"], 3)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM agregados WHERE enviado=0").fetchone()[0], 0)

    def test_enlace_fora_do_ar_preserva_a_fila(self):
        """O ponto central do projeto: sem comunicacao, nada se perde."""
        self._preparar()
        res = enviar_pendentes(self.con, TransporteIndisponivel())
        self.assertEqual(res["agregados"], 0)
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM agregados WHERE enviado=0").fetchone()[0], 3)
        # Enlace volta: a fila sobe inteira.
        res = enviar_pendentes(self.con, TransporteLog())
        self.assertEqual(res["agregados"], 3)

    def test_eventos_saem_antes_dos_agregados(self):
        self._preparar()
        gravar_leituras(self.con, [_l("s1", int(time.time()), 1.0)])
        detectar(self.con, self.cfg)

        ordem = []

        class Espiao(TransporteLog):
            def enviar(self, payload: bytes) -> bool:
                ordem.append(payload[0])   # 1 = evento, 2 = agregado
                return True

        enviar_pendentes(self.con, Espiao())
        self.assertEqual(ordem[0], 1)
        self.assertIn(2, ordem)

    def test_respeita_limite_de_payload(self):
        self._preparar(8)                  # 8 agregados x 15 bytes = 120 bytes
        tamanhos = []

        class Espiao(TransporteLog):
            def enviar(self, payload: bytes) -> bool:
                tamanhos.append(len(payload))
                return True

        enviar_pendentes(self.con, Espiao(), max_mensagens=100)
        self.assertTrue(all(t <= 51 for t in tamanhos), tamanhos)
        self.assertGreater(len(tamanhos), 1)   # teve de fatiar em varias mensagens


class TestRetencao(BaseHub):
    def test_purga_preserva_agregados(self):
        antigo = int(time.time()) - 100 * 86400
        gravar_leituras(self.con, [_l("s1", antigo, 20.0)])
        agregar(self.con, HORA)
        self.assertEqual(purgar(self.con, 90), 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM leituras").fetchone()[0], 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM agregados").fetchone()[0], 1)


class TestExportador(BaseHub):
    def _povoar(self):
        base = (int(time.time()) // HORA) * HORA - HORA
        gravar_leituras(self.con, [
            _l("s1", base + 60, 21.5, umid=73.4),
            _l("s1", base + 120, 1.0, umid=90.0),
            _l("s2", base + 60, 25.0, umid=55.0, pressao=1013.2),
        ])
        agregar(self.con, HORA)
        detectar(self.con, self.cfg)

    def _csv(self, nome: str) -> str:
        return b"".join(csv_bytes(self.con, nome)).decode("utf-8")

    def test_csv_no_dialeto_do_excel_ptbr(self):
        self._povoar()
        texto = self._csv("leituras")
        self.assertTrue(texto.startswith("﻿"), "falta o BOM: Excel estraga acento")
        cabecalho = texto.splitlines()[0].lstrip("﻿")
        self.assertIn(";", cabecalho)
        self.assertNotIn(",", cabecalho)          # virgula so aparece em decimal
        self.assertIn("21,5", texto)              # virgula decimal, nao ponto
        self.assertNotIn("21.5", texto)

    def test_csv_traz_tempo_legivel_e_epoch(self):
        self._povoar()
        colunas = self._csv("agregados").splitlines()[0].lstrip("﻿").split(";")
        self.assertIn("inicio_epoch", colunas)
        self.assertIn("inicio", colunas)
        self.assertIn("sensor", colunas)          # ieee, nao o id local
        self.assertIn("amostras", colunas)        # campo que o LoRa descartava

    def test_nulo_vira_celula_vazia(self):
        self._povoar()
        # s1 nao tem pressao; a celula deve ficar vazia, nao "None".
        self.assertNotIn("None", self._csv("leituras"))

    def test_exportar_nao_consome_a_fila_do_backhaul(self):
        self._povoar()
        antes = self.con.execute(
            "SELECT COUNT(*) FROM agregados WHERE enviado=0").fetchone()[0]
        self.assertGreater(antes, 0)
        b"".join(csv_bytes(self.con, "agregados"))
        with tempfile.TemporaryDirectory() as tmp:
            montar_zip(self.con, "tudo", Path(tmp) / "e.zip")
        depois = self.con.execute(
            "SELECT COUNT(*) FROM agregados WHERE enviado=0").fetchone()[0]
        self.assertEqual(antes, depois)

    def test_zip_tem_um_csv_por_tabela(self):
        self._povoar()
        with tempfile.TemporaryDirectory() as tmp:
            alvo = montar_zip(self.con, "tudo", Path(tmp) / "e.zip")
            with zipfile.ZipFile(alvo) as z:
                self.assertEqual(
                    {"leituras.csv", "agregados.csv", "eventos.csv",
                     "sensores.csv", "LEIA-ME.txt"}, set(z.namelist()))
                self.assertIn("EdgeVision", z.read("LEIA-ME.txt").decode("utf-8"))

    def test_escopo_agregados_nao_leva_serie_bruta(self):
        self._povoar()
        with tempfile.TemporaryDirectory() as tmp:
            alvo = montar_zip(self.con, "agregados", Path(tmp) / "e.zip")
            with zipfile.ZipFile(alvo) as z:
                self.assertNotIn("leituras.csv", z.namelist())

    def test_snapshot_pega_escrita_ainda_no_wal(self):
        """O -wal e o risco: copiar so o .db perderia as ultimas leituras."""
        self._povoar()
        n = self.con.execute("SELECT COUNT(*) FROM leituras").fetchone()[0]
        with tempfile.TemporaryDirectory() as tmp:
            alvo = snapshot(self.con, Path(tmp) / "copia.db")
            copia = sqlite3.connect(str(alvo))
            try:
                self.assertEqual(
                    copia.execute("SELECT COUNT(*) FROM leituras").fetchone()[0], n)
            finally:
                copia.close()

    def test_resumo_conta_e_datas(self):
        self._povoar()
        r = resumo(self.con)
        self.assertEqual(r["sensores"], 2)
        self.assertEqual(r["leituras"], 3)
        self.assertEqual(r["origens"], {"zigbee": 2})
        self.assertIsNotNone(r["ultima"])

    def test_pagina_e_autocontida(self):
        self._povoar()
        html = pagina(resumo(self.con))
        # Offline nao ha DNS: qualquer recurso externo trava o carregamento.
        for proibido in ("http://", "https://", "//cdn", "<script"):
            self.assertNotIn(proibido, html)
        self.assertIn("agregados.csv", html)
        self.assertIn("tudo.zip", html)

    def test_pagina_avisa_quando_banco_vazio(self):
        html = pagina(resumo(self.con))
        self.assertIn("Nenhuma leitura", html)
        self.assertNotIn("tudo.zip", html)     # nao oferece download inutil

    def test_ha_quanto_tempo(self):
        agora = 1_000_000
        self.assertEqual(_ha_quanto(None), "nunca")
        self.assertEqual(_ha_quanto(agora - 30, agora), "há 30 s")
        self.assertEqual(_ha_quanto(agora - 600, agora), "há 10 min")
        self.assertEqual(_ha_quanto(agora - 7200, agora), "há 2 h")


class TestExportadorHTTP(BaseHub):
    """Sobe o servidor de verdade e baixa por HTTP."""

    def setUp(self):
        super().setUp()
        # Janela fechada: o agregador so resume horas ja encerradas, entao uma
        # leitura de agora nao produziria nenhum agregado para baixar.
        base = (int(time.time()) // HORA) * HORA - HORA
        gravar_leituras(self.con, [_l("estufa_norte", base + 60, 21.5)])
        agregar(self.con, HORA)
        # Porta 0: o SO escolhe uma livre, entao o teste nao briga com um
        # exportador que ja esteja rodando na maquina.
        self.srv = servir("127.0.0.1", 0, str(Path(self.tmp.name) / "t.db"))
        self.porta = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def _get(self, rota: str):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.porta}{rota}", timeout=10) as r:
            return r.status, dict(r.headers), r.read()

    def test_pagina_inicial(self):
        status, cab, corpo = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", cab["Content-Type"])
        self.assertIn("EdgeVision", corpo.decode("utf-8"))

    def test_download_csv_vem_como_anexo(self):
        status, cab, corpo = self._get("/agregados.csv")
        self.assertEqual(status, 200)
        self.assertIn("attachment", cab["Content-Disposition"])
        self.assertIn(".csv", cab["Content-Disposition"])
        self.assertIn("estufa_norte", corpo.decode("utf-8"))

    def test_download_zip_abre(self):
        _, _, corpo = self._get("/tudo.zip")
        with zipfile.ZipFile(io.BytesIO(corpo)) as z:
            self.assertIsNone(z.testzip())
            self.assertIn("agregados.csv", z.namelist())

    def test_download_banco_e_sqlite_valido(self):
        _, _, corpo = self._get("/dados.db")
        self.assertTrue(corpo.startswith(b"SQLite format 3\x00"))
        destino = Path(self.tmp.name) / "baixado.db"
        destino.write_bytes(corpo)
        con = sqlite3.connect(str(destino))
        try:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM leituras").fetchone()[0], 1)
        finally:
            con.close()

    def test_rota_desconhecida_nao_serve_arquivo(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self._get("/etc/passwd")
        self.assertEqual(e.exception.code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
