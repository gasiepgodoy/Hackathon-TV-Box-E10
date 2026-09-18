"""Verify the actual Python asset handler without touching network configuration."""
import importlib.util
import os
from pathlib import Path
import tempfile
import threading
from urllib.request import urlopen

base = Path(__file__).resolve().parents[1]
os.environ['FORGEOS_BASE'] = str(base)
# The legacy server creates STATE on import; use an isolated temporary base.
with tempfile.TemporaryDirectory() as temporary:
    os.environ['FORGEOS_BASE'] = temporary
    spec = importlib.util.spec_from_file_location('portal_server', base / 'web/server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.WEB = str(base / 'web')
    server = module.ThreadingHTTPServer(('127.0.0.1', 0), module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for route, content_type, marker in [
            ('/', 'text/html', 'welcome-card'),
            ('/static/css/portal.css', 'text/css', '.pf-card'),
            ('/static/css/design.css', 'text/css', 'prefers-reduced-motion'),
            ('/static/js/portal.js', 'javascript', 'tickRealtime'),
            ('/static/js/accessibility.js', 'javascript', 'ArrowDown'),
        ]:
            with urlopen(f'http://127.0.0.1:{server.server_port}{route}') as response:
                assert response.status == 200
                assert content_type in response.headers['Content-Type']
                assert marker in response.read().decode('utf-8')
                print(f'PASS {route}')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
