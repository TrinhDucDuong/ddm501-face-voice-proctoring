from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from streamlit.testing.v1 import AppTest


def test_platform_monitoring_links_distinguish_production_and_simulation(monkeypatch):
    def upstream(method, url, **kwargs):
        if url.endswith('/v1/me'):
            data = {'tenant_id': 'demo', 'role': 'platform'}
        elif url.endswith('/v1/admin/tenants'):
            data = [{'id': 'demo', 'name': 'Demo', 'active': True}]
        else:
            raise AssertionError(url)
        return SimpleNamespace(ok=True, status_code=200, json=lambda: data)

    monkeypatch.setattr(requests, 'request', upstream)
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'ui' / 'app.py'))
    app.session_state['auth_key'] = 'test-platform'
    app.session_state['auth_expires_at'] = 9999999999
    app.run()
    app.sidebar.radio[0].set_value('Vận hành MLOps').run()
    assert not app.exception
    links = {button.proto.label: button.proto.url for button in app.get('link_button')}
    assert links['Grafana System Overview'] == 'http://localhost:13000/d/biometric-overview'
    assert links['MLflow production'] == 'http://localhost:15030'
    assert links['MLflow simulation'] == 'http://localhost:15031'
    assert links['Airflow monitoring'] == 'http://localhost:18081/dags/biometric_monitoring_pipeline/grid'
    assert links['CI/CD'] == 'https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring/actions'


@pytest.mark.parametrize('role', ['operator', 'platform'])
def test_portal_login_removes_key_widget_and_logout_clears_session(monkeypatch, role):
    def upstream(method, url, headers, **kwargs):
        if url.endswith('/v1/me'):
            if headers.get('X-API-Key') != 'test-login-secret':
                return SimpleNamespace(ok=False, status_code=401, json=lambda: {'detail': 'Invalid key'})
            data = {'tenant_id': 'company-a', 'role': role}
        elif url.endswith('/v1/admin/tenants'):
            data = [{'id': 'company-a', 'name': 'Company A', 'active': True}]
        elif url.endswith('/v1/people'):
            data = []
        elif url.endswith('/v1/checks'):
            data = {'items': [], 'total': 0}
        elif url.endswith('/v1/company'):
            data = {'name': 'Company A'}
        else:
            raise AssertionError(f'Unexpected request: {method} {url}')
        return SimpleNamespace(ok=True, status_code=200, json=lambda: data)

    monkeypatch.setattr(requests, 'request', upstream)
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'ui' / 'app.py')).run()
    assert not app.exception
    assert app.query_params['page'] == ['login']
    app.text_input(key='login_key').set_value('test-login-secret')
    next(b for b in app.button if b.label == 'Đăng nhập').click().run()
    assert app.sidebar.radio
    app.session_state['auth_expires_at'] = 0
    app.run()
    assert app.query_params['page'] == ['login']
    assert 'auth_key' not in app.session_state.filtered_state
    app.text_input(key='login_key').set_value('test-login-secret')
    next(b for b in app.button if b.label == 'Đăng nhập').click().run()
    monkeypatch.setattr(requests, 'request', lambda *args, **kwargs: SimpleNamespace(
        ok=False, status_code=401, json=lambda: {'detail': 'Revoked key'}))
    app.run()
    assert app.query_params['page'] == ['login']
    assert 'auth_key' not in app.session_state.filtered_state
    assert not app.sidebar.radio
    monkeypatch.setattr(requests, 'request', upstream)
    app.text_input(key='login_key').set_value('wrong-key')
    next(b for b in app.button if b.label == 'Đăng nhập').click().run()
    assert app.error
    assert not app.sidebar.radio
    app.text_input(key='login_key').set_value('test-login-secret')
    next(b for b in app.button if b.label == 'Đăng nhập').click().run()
    assert not app.exception
    assert app.query_params['page'] == ['portal']
    assert not any(w.proto.type == 'password' for w in app.text_input)
    assert 'login_key' not in app.session_state.filtered_state
    app.session_state['enrollment_link'] = 'private-invitation'
    next(b for b in app.button if b.label == 'Đăng xuất').click().run()
    assert app.query_params['page'] == ['login']
    assert app.text_input(key='login_key').value == ''
    assert 'auth_key' not in app.session_state.filtered_state
    assert 'enrollment_link' not in app.session_state.filtered_state
    app.query_params['page'] = 'portal'
    app.run()
    assert not app.sidebar.radio
    assert app.query_params['page'] == ['login']
