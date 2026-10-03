from pathlib import Path
from types import SimpleNamespace

import requests
from streamlit.testing.v1 import AppTest


def test_platform_simulation_buttons_and_operator_isolation(monkeypatch):
    requests_seen = []
    state = {'isolated': True, 'current': None, 'history': [], 'alerts': []}

    def upstream(method, url, headers, **kwargs):
        requests_seen.append((method, url, kwargs.get('json')))
        if url.endswith('/v1/me'):
            data = {'tenant_id': 'demo', 'role': 'platform'}
        elif url.endswith('/v1/admin/tenants'):
            data = [{'id': 'demo', 'name': 'Demo', 'active': True}]
        elif url.endswith('/simulation/state'):
            data = state
        elif url.endswith('/simulation/runs'):
            state['current'] = {'id': 'test', 'modality': 'voice', 'status': 'QUEUED', 'phase': 'QUEUED'}
            data = state['current']
        elif url.endswith('/simulation/reset'):
            state['current']['status'] = 'RESET'
            data = state
        else:
            raise AssertionError(url)
        return SimpleNamespace(ok=True, status_code=200, json=lambda: data)

    monkeypatch.setattr(requests, 'request', upstream)
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'ui' / 'app.py'))
    app.session_state['auth_key'] = 'test-platform'
    app.session_state['auth_expires_at'] = 9999999999
    app.run()
    app.sidebar.radio[0].set_value('Simulation MLOps').run()
    assert not app.exception
    next(b for b in app.button if b.label.startswith('1.')).click().run()
    assert not app.exception
    assert any(body and body.get('scenario') == 'promotion' for _, _, body in requests_seen)
    assert next(b for b in app.button if b.label.startswith('2.')).disabled
    next(b for b in app.button if b.label.startswith('3.')).click().run()
    assert not app.exception
    assert not next(b for b in app.button if b.label.startswith('2.')).disabled
    next(b for b in app.button if b.label.startswith('2.')).click().run()
    assert any(body and body.get('scenario') == 'rollback' for _, _, body in requests_seen)
