#!/usr/bin/env python3
"""Testes unitários do ForgeOS Provisioner (rodar na box)."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

BASE = os.environ.get("FORGEOS_BASE", "/opt/forgeos" if os.path.exists("/opt/forgeos") else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class BuildClientConf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load("bcc", f"{BASE}/network/build_client_conf.py")

    def gen(self, data):
        with tempfile.TemporaryDirectory() as t:
            p, c = os.path.join(t, "p.json"), os.path.join(t, "c.conf")
            json.dump(data, open(p, "w"))
            sys.argv = ["x", p, c]
            self.m.main()
            return open(c).read()

    def test_psk_basico(self):
        s = self.gen({"mode": "psk", "ssid": "Casa", "password": "senha12345"})
        self.assertIn('ssid="Casa"', s)
        self.assertIn('psk="senha12345"', s)
        self.assertIn("key_mgmt=WPA-PSK", s)
        self.assertIn("scan_ssid=1", s)

    def test_psk_hex_64(self):
        hex64 = "a" * 64
        s = self.gen({"mode": "psk", "ssid": "H", "password": hex64})
        self.assertIn(f"psk={hex64}", s)  # sem aspas quando hex de 64

    def test_ssid_escape(self):
        s = self.gen({"mode": "psk", "ssid": 'A"B', "password": "12345678"})
        self.assertIn('ssid="A\\"B"', s)

    def test_eap_peap_mschapv2(self):
        s = self.gen({"mode": "eap", "ssid": "eduroam", "method": "PEAP",
                      "phase2": "MSCHAPV2", "identity": "u@x.br",
                      "password": "p", "anonymous_identity": "anon@x.br",
                      "domain": "x.br"})
        self.assertIn("key_mgmt=WPA-EAP", s)
        self.assertIn("eap=PEAP", s)
        self.assertIn('phase2="auth=MSCHAPV2"', s)
        self.assertIn('anonymous_identity="anon@x.br"', s)
        self.assertIn('altsubject_match="DNS:x.br;DNS:.x.br"', s)
        self.assertIn('phase1="peapver=0 peaplabel=0"', s)

    def test_eap_ttls_pap(self):
        s = self.gen({"mode": "eap", "ssid": "corp", "method": "TTLS",
                      "phase2": "PAP", "identity": "u", "password": "p"})
        self.assertIn("eap=TTLS", s)
        self.assertIn('phase2="auth=PAP"', s)


class ServerValidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # staticmethod evita que self.v vire método ligado (função como
        # atributo de classe é descritor no Python 3)
        cls.v = staticmethod(load("srv", f"{BASE}/web/server.py").validate)

    def test_psk_valido(self):
        self.assertIsNone(self.v({"mode": "psk", "ssid": "net", "password": "12345678"}))

    def test_psk_curto(self):
        self.assertIsNotNone(self.v({"mode": "psk", "ssid": "net", "password": "123"}))

    def test_ssid_vazio(self):
        self.assertIsNotNone(self.v({"mode": "psk", "ssid": "", "password": "12345678"}))

    def test_ssid_muito_longo(self):
        self.assertIsNotNone(self.v({"mode": "psk", "ssid": "x" * 40, "password": "12345678"}))

    def test_ssid_caracteres_invalidos(self):
        self.assertIsNotNone(self.v({"mode": "psk", "ssid": 'a"b', "password": "12345678"}))

    def test_eap_valido(self):
        self.assertIsNone(self.v({"mode": "eap", "ssid": "eduroam", "method": "PEAP",
                                  "phase2": "MSCHAPV2", "identity": "u@x.br",
                                  "password": "p"}))

    def test_eap_sem_identidade(self):
        self.assertIsNotNone(self.v({"mode": "eap", "ssid": "eduroam", "method": "PEAP",
                                     "phase2": "MSCHAPV2", "identity": "",
                                     "password": "p"}))

    def test_eap_metodo_invalido(self):
        self.assertIsNotNone(self.v({"mode": "eap", "ssid": "eduroam", "method": "TLSX",
                                     "phase2": "PAP", "identity": "u", "password": "p"}))

    def test_modo_invalido(self):
        self.assertIsNotNone(self.v({"mode": "wep", "ssid": "net", "password": "12345678"}))


class QRRender(unittest.TestCase):
    def test_render_1920x1080(self):
        from PIL import Image
        m = load("qr", f"{BASE}/display/qr_screen.py")
        png, fy = m.render()
        self.assertTrue(os.path.exists(png))
        im = Image.open(png)
        self.assertEqual(im.size, (1920, 1080))
        self.assertEqual(fy, 1010)

    def test_push_bandas(self):
        m = load("qr2", f"{BASE}/display/qr_screen.py")
        png, fy = m.render()
        variants = m.pulse_variants(png, fy)
        self.assertEqual(len(variants), 2)
        self.assertEqual(len(variants[0]), (1080 - fy) * m.LINE_LEN)


if __name__ == "__main__":
    unittest.main(verbosity=2)
