"""The legacy kiosk must advance to the portal QR after Wi-Fi association."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'display'))
import qr_screen


class PairingTransitionTest(unittest.TestCase):
    def detect(self, station_output):
        with tempfile.TemporaryDirectory() as state, \
                patch.object(qr_screen, 'STATE', state), \
                patch.object(qr_screen, 'get_wlan_ip', return_value='192.168.4.1'), \
                patch.object(qr_screen, 'get_eth_ip', return_value=None), \
                patch.object(qr_screen.subprocess, 'run', side_effect=[
                    SimpleNamespace(returncode=1, stdout=''),
                    SimpleNamespace(returncode=0, stdout=station_output)]):
            return qr_screen.get_device_state()[0]

    def test_phone_join_advances_to_portal(self):
        self.assertEqual(self.detect('Station aa:bb:cc:dd:ee:ff (on wlan0)\n'), 'peer')

    def test_no_phone_keeps_wifi_qr(self):
        self.assertEqual(self.detect(''), 'ap')


if __name__ == '__main__':
    unittest.main()
