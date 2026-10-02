import importlib
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_exam_selects_tenant_server_side_and_rejects_cross_tenant(monkeypatch, tmp_path):
    demo = importlib.import_module('legacy_demo.app')
    monkeypatch.delenv('EXAM_SERVICE_API_KEY', raising=False)
    monkeypatch.delenv('API_KEY', raising=False)
    primary = {'tenant_id': 'a', 'integration_key': 'key-a', 'webhook_secret': 'secret-a'}
    (tmp_path / 'local-saas.json').write_text(json.dumps(primary))
    (tmp_path / 'company-demo.json').write_text(json.dumps({'companies': [
        {'tenant_id': 'b', 'name': 'Company B', 'integration_key': 'key-b', 'webhook_secret': 'secret-b'}]}))
    monkeypatch.setattr(demo, 'CONFIG', tmp_path / 'local-saas.json')
    monkeypatch.setattr(demo, 'DATABASE', str(tmp_path / 'legacy.db'))
    calls = []

    def upstream(method, url, headers, **kwargs):
        calls.append((method, url, headers['X-API-Key']))
        if url.endswith('/v1/people'):
            key = headers['X-API-Key']
            return SimpleNamespace(ok=True, json=lambda: [{'id': 'person-' + key[-1],
                'display_name': 'Employee ' + key[-1], 'external_id': 'EMP-' + key[-1], 'ready': True}])
        return SimpleNamespace(ok=True, json=lambda: {'integrity_status': 'verified'})

    monkeypatch.setattr(demo.requests, 'request', upstream)
    with TestClient(demo.app) as browser:
        browser.get('/')
        companies = browser.get('/companies').json()
        assert [(item['id'], item['name']) for item in companies] == [('a', 'Demo nội bộ'), ('b', 'Company B')]
        assert browser.get('/candidates?company_id=b').json()[0]['id'] == 'person-b'
        media = {'face_file': ('face.jpg', b'face', 'image/jpeg'),
                 'voice_file': ('voice.wav', b'voice', 'audio/wav')}
        data = {'company_id': 'a', 'person_id': 'person-b', 'session_id': 'exam',
                'request_id': 'request-1', 'consent': 'true'}
        assert browser.post('/check', data=data, files=media).status_code == 404
        assert not any(url.endswith('/v1/checks') for _, url, _ in calls)
        data['company_id'] = 'b'
        assert browser.post('/check', data=data, files=media).json()['integrity_status'] == 'verified'
        assert calls[-1][2] == 'key-b'


def test_exam_queries_new_companies_and_people_without_employee_login(monkeypatch, tmp_path):
    demo = importlib.import_module('legacy_demo.app')
    monkeypatch.setenv('EXAM_SERVICE_API_KEY', 'service-secret')
    monkeypatch.setattr(demo, 'CONFIG', tmp_path / 'absent-config.json')
    monkeypatch.setattr(demo, 'DATABASE', str(tmp_path / 'legacy.db'))
    companies = [{'id': 'a', 'name': 'Company A'}]
    people = {'a': [], 'b': []}
    calls = []

    def upstream(method, url, headers, **kwargs):
        calls.append((method, url, dict(headers)))
        assert headers['X-API-Key'] == 'service-secret'
        if url.endswith('/v1/exam/companies'):
            data = list(companies)
        elif url.endswith('/v1/people'):
            data = people[headers['X-Tenant-ID']]
        elif url.endswith('/v1/company'):
            data = {'webhook_secret': 'secret-' + headers['X-Tenant-ID']}
        elif url.endswith('/v1/checks'):
            data = {'integrity_status': 'verified'}
        else:
            raise AssertionError(url)
        return SimpleNamespace(ok=True, json=lambda: data)

    monkeypatch.setattr(demo.requests, 'request', upstream)
    with TestClient(demo.app) as browser:
        assert browser.get('/').status_code == 200
        assert browser.get('/companies').json() == companies
        companies.append({'id': 'b', 'name': 'New Company B'})
        people['b'] = [{'id': f'b-{i}', 'display_name': f'Employee {i}',
                        'external_id': f'EMP-{i}', 'ready': True} for i in range(503)]
        response = browser.get('/companies')
        assert response.json() == companies
        assert 'service-secret' not in response.text
        assert len(browser.get('/candidates?company_id=b').json()) == 503
        assert browser.get('/candidates?company_id=a').json() == []
        media = {'face_file': ('face.jpg', b'face', 'image/jpeg'),
                 'voice_file': ('voice.wav', b'voice', 'audio/wav')}
        data = {'company_id': 'a', 'person_id': 'b-502', 'session_id': 'exam',
                'request_id': 'live-request', 'consent': 'true'}
        assert browser.post('/check', data=data, files=media).status_code == 404
        data['company_id'] = 'b'
        assert browser.post('/check', data=data, files=media).status_code == 200
        assert calls[-1][2] == {'X-API-Key': 'service-secret', 'X-Tenant-ID': 'b'}
        assert demo.customer_config('b')['webhook_secret'] == 'secret-b'
        companies.pop()
        assert browser.get('/candidates?company_id=b').status_code == 404
