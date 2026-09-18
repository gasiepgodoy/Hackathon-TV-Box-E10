"""Presentation adapter for an existing ForgeHub forge_kiosk.py installation.

Install beside the existing engine. Its network state detection, framebuffer
format and update loop remain in charge; only the panel renderer is replaced.
"""
import os
from pathlib import Path

import forge_kiosk as engine
from panel_renderer import render_panel


def render(mode, info, sx=0, sy=0):
    configured = dict(info)
    configured.update(engine.read_ap_config())
    candidates = [
        os.environ.get('FORGEOS_LOGO', ''),
        str(Path(__file__).resolve().parent.parent / 'web' / 'logo-sm.png'),
        str(Path(__file__).resolve().parent.parent / 'web' / 'logo.png'),
        '/opt/forgehub/web/logo-sm.png',
        '/opt/forgehub/web/logo.png',
        '/opt/multi-forge/ForgeOS/web/logo-sm.png',
        '/opt/multi-forge/ForgeOS/web/logo.png',
        '/opt/forgeos/web/logo-sm.png',
        '/opt/forgeos/web/logo.png',
    ]
    logo = next((p for p in candidates if p and Path(p).is_file()), None)
    return render_panel(mode, configured, sx, sy, logo)


engine.render = render

if __name__ == '__main__':
    engine.main()
