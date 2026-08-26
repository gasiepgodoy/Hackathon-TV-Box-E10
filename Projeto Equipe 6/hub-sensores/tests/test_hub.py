"""Testes do hub. Rodar: python3 tests/test_hub.py"""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hub.agregador import agregar                                    # noqa: E402
from hub.coletor import extrair, parse_linha                   # noqa: E402
from hub.config import Config                                        # noqa: E402
from hub.db import conectar, gravar_leituras, inicializar, purgar    # noqa: E402
from hub.enviador import (TransporteIndisponivel, TransporteLog,     # noqa: E402
                          empacotar_agregado, enviar_pendentes)
from hub.eventos import detectar                                     # noqa: E402

HORA = 3600


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
        self.assertEqual(r[0], "estufa")
        self.assertEqual(r[2], 21.5)

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
        self.assertEqual(leitura[0], "Sensor Temperatura")
        self.assertEqual(leitura[2], 24.5)

    def test_parse_ignora_linha_invalida(self):
        self.assertIsNone(parse_linha(""))
        self.assertIsNone(parse_linha("nao é json"))

    def test_grava_em_lote_e_cadastra_sensor(self):
        ts = int(time.time())
        n = gravar_leituras(self.con, [("s1", ts, 20.0, 50.0, 90, 100),
                                       ("s2", ts, 21.0, 55.0, 80, 120)])
        self.assertEqual(n, 2)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM sensores").fetchone()[0], 2)


class TestAgregador(BaseHub):
    def _povoar(self, base: int):
        # Uma geada curta no meio da hora: some na media, sobrevive no minimo.
        temps = [10.0] * 10 + [1.0] * 3 + [10.0] * 10
        linhas = [("s1", base + i * 60, t, 50.0, 90, 100) for i, t in enumerate(temps)]
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
        gravar_leituras(self.con, [("s1", agora, 20.0, 50.0, 90, 100)])
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
        gravar_leituras(self.con, [("s1", int(time.time()), 1.0, 50.0, 90, 100)])
        detectar(self.con, self.cfg)
        tipos = [r["tipo"] for r in self.con.execute("SELECT tipo FROM eventos")]
        self.assertIn("geada", tipos)

    def test_detecta_sensor_mudo(self):
        antigo = int(time.time()) - 4 * HORA
        gravar_leituras(self.con, [("s1", antigo, 20.0, 50.0, 90, 100)])
        detectar(self.con, self.cfg)
        tipos = [r["tipo"] for r in self.con.execute("SELECT tipo FROM eventos")]
        self.assertIn("sensor_mudo", tipos)

    def test_nao_repete_evento_identico(self):
        gravar_leituras(self.con, [("s1", int(time.time()), 1.0, 50.0, 90, 100)])
        detectar(self.con, self.cfg)
        detectar(self.con, self.cfg)
        n = self.con.execute("SELECT COUNT(*) FROM eventos WHERE tipo='geada'").fetchone()[0]
        self.assertEqual(n, 1)

    def test_bateria_baixa(self):
        gravar_leituras(self.con, [("s1", int(time.time()), 20.0, 50.0, 5, 100)])
        detectar(self.con, self.cfg)
        tipos = [r["tipo"] for r in self.con.execute("SELECT tipo FROM eventos")]
        self.assertIn("bateria_baixa", tipos)


class TestEnviador(BaseHub):
    def _preparar(self, n_janelas=3):
        base = (int(time.time()) // HORA) * HORA - (n_janelas + 1) * HORA
        linhas = []
        for j in range(n_janelas):
            for i in range(5):
                linhas.append(("s1", base + j * HORA + i * 60, 20.0 + i, 50.0, 90, 100))
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
        gravar_leituras(self.con, [("s1", int(time.time()), 1.0, 50.0, 90, 100)])
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
        gravar_leituras(self.con, [("s1", antigo, 20.0, 50.0, 90, 100)])
        agregar(self.con, HORA)
        self.assertEqual(purgar(self.con, 90), 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM leituras").fetchone()[0], 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM agregados").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
