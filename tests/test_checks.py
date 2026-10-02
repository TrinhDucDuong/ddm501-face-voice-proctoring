import hashlib
import importlib
import io

import cv2
import numpy as np
import pytest
from app.biometrics import BiometricEngine
from app.config import get_settings
from app.db import get_db
from app.models import IntegrityCheck, VerificationFeedback, WebhookDelivery
from app.registry import RuntimeModel
from fastapi.testclient import TestClient
from scipy.io import wavfile
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


class MemoryEvidence:
    def __init__(self):
        self.objects = {}

    def put(self, *args):
        return None

    def put_evidence(self, tenant_id, event_id, modality, payload, content_type):
        key = f'{tenant_id}/{event_id}/{modality}'
        self.objects[key] = (payload, content_type)
        return key

    def get(self, key):
        return self.objects[key]


@pytest.fixture
def checks_api(monkeypatch, tmp_path):
    monkeypatch.setenv('API_KEY', 'checks-platform')
    monkeypatch.setenv('MODEL_BACKEND', 'demo')
    monkeypatch.setenv('STORE_RAW_BIOMETRICS', 'false')
    get_settings.cache_clear()
    main = importlib.import_module('app.main')
    engine = create_engine(f"sqlite:///{(tmp_path/'checks.db').as_posix()}", connect_args={'check_same_thread': False})
    monkeypatch.setattr(main, 'engine', engine)
    monkeypatch.setattr(main, 'settings', get_settings())
    monkeypatch.setattr(main, 'biometrics', BiometricEngine(get_settings()))
    monkeypatch.setattr(main.registry, 'current', RuntimeModel(.45, .25, 'check-test'))
    monkeypatch.setattr(main.registry, 'load', lambda: main.registry.current)
    store = MemoryEvidence()
    monkeypatch.setattr(main, 'object_store', store)
    monkeypatch.setattr(main.app.state, 'inspect_integrity', lambda *args: {
        'face_pad': {'status': 'passed'}, 'audio_spoof': {'status': 'passed'},
        'speaker_consistency': {'status': 'passed'},
    }, raising=False)

    def database():
        with Session(engine, expire_on_commit=False) as db:
            yield db
    main.app.dependency_overrides[get_db] = database
    image = np.zeros((160, 160, 3), dtype=np.uint8)
    image[::8, :] = 255
    image[:, ::8] = 255
    _, encoded = cv2.imencode('.png', image)
    stream = io.BytesIO()
    wavfile.write(stream, 16000, (np.sin(np.arange(160000)*2*np.pi*220/16000)*20000).astype(np.int16))
    media = {'face_file': ('face.png', encoded.tobytes(), 'image/png'),
             'voice_file': ('voice.wav', stream.getvalue(), 'audio/wav')}
    with TestClient(main.app) as client:
        yield client, engine, store, media, main
    main.app.dependency_overrides.clear()
    engine.dispose()
    get_settings.cache_clear()


def company(client, name):
    row = client.post('/v1/admin/tenants', headers={'X-API-Key': 'checks-platform'}, json={
        'name': name, 'webhook_url': 'http://legacy-demo:8000/webhooks/verification',
    }).json()
    for role in ('operator', 'integration'):
        row[role] = {'X-API-Key': client.post(f"/v1/admin/tenants/{row['id']}/keys",
                    headers={'X-API-Key': 'checks-platform'}, json={'role': role}).json()['api_key']}
    return row


def employee(client, owner, media):
    row = client.post('/v1/people', headers=owner['operator'], json={
        'external_id': 'EMP-001', 'display_name': 'Nguyễn Văn An',
    }).json()
    r = client.post(f"/v1/people/{row['id']}/enroll", headers=owner['operator'],
                    files=[('face_files', media['face_file']), ('voice_files', media['voice_file'])])
    assert r.status_code == 200, r.text
    return row


def send(client, owner, person, media, request_id='capture-1', session_id='ANNUAL-2026'):
    return client.post('/v1/checks', headers=owner['integration'], files=media,
                       data={'person_id': person['id'], 'session_id': session_id,
                             'request_id': request_id, 'consent': 'true'})


def test_company_review_is_tenant_scoped_and_separates_identity_from_cheating(checks_api):
    client, engine, _, media, _ = checks_api
    owner, other = company(client, 'Review owner'), company(client, 'Other reviewer')
    person = employee(client, owner, media)
    check_id = send(client, owner, person, media).json()['check_id']
    payload = {'identity_truth': 'genuine', 'cheating_judgement': 'confirmed',
               'selection_reason': 'manual', 'notes': 'Independent review'}
    path = f'/v1/checks/{check_id}/review'
    assert client.put(path, headers=other['operator'], json=payload).status_code == 404
    assert client.put(path, headers=owner['integration'], json=payload).status_code == 403
    response = client.put(path, headers=owner['operator'], json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['identity_truth'] == 'genuine'
    assert response.json()['cheating_judgement'] == 'confirmed'
    assert response.json()['source'] == 'human'
    assert client.get(path, headers=other['operator']).status_code == 404
    expected_reason = ('random_audit' if
                       int(hashlib.sha256(check_id.encode()).hexdigest()[:8], 16) % 10 == 0
                       else 'manual')
    assert client.get(path, headers=owner['operator']).json()['selection_reason'] == expected_reason
    with Session(engine) as db:
        feedback = db.scalars(select(VerificationFeedback)).one()
        assert feedback.is_genuine is True
        assert feedback.reviewer.startswith('operator:')
    payload['identity_truth'] = 'unknown'
    payload['cheating_judgement'] = 'dismissed'
    assert client.put(path, headers=owner['operator'], json=payload).status_code == 200
    with Session(engine) as db:
        assert db.scalars(select(VerificationFeedback)).all() == []


def test_review_queue_samples_verified_checks_independently_of_model_decision(checks_api):
    client, _, _, media, _ = checks_api
    owner, other = company(client, 'Audit queue owner'), company(client, 'Audit queue other')
    person = employee(client, owner, media)
    check_ids = [send(client, owner, person, media, request_id=f'audit-{i}',
                      session_id=f'exam-{i}').json()['check_id'] for i in range(12)]
    queue = client.get('/v1/reviews/queue', headers=owner['operator'])
    assert queue.status_code == 200, queue.text
    expected = {check_id for check_id in check_ids
                if int(hashlib.sha256(check_id.encode()).hexdigest()[:8], 16) % 10 == 0}
    selected = {row['check_id'] for row in queue.json()['items']
                if row['selection_reason'] == 'random_audit'}
    assert selected == expected
    with Session(checks_api[1]) as db:
        changed = db.get(IntegrityCheck, check_ids[0])
        changed.integrity_status = 'suspicious'
        db.commit()
    rerun = client.get('/v1/reviews/queue', headers=owner['operator']).json()['items']
    assert {row['check_id'] for row in rerun if row['selection_reason'] == 'random_audit'} == expected
    unselected = next(check_id for check_id in check_ids if check_id not in expected)
    forged = {'identity_truth': 'genuine', 'cheating_judgement': 'dismissed',
              'selection_reason': 'random_audit'}
    assert client.put(f'/v1/checks/{unselected}/review', headers=owner['operator'],
                      json=forged).status_code == 422
    assert client.get('/v1/reviews/queue', headers=other['operator']).json()['items'] == []
    assert client.get('/v1/reviews/queue', headers=owner['integration']).status_code == 403


def test_selected_audit_provenance_cannot_be_changed_by_reviewer(checks_api, monkeypatch):
    from app import checks

    client, _, _, media, _ = checks_api
    owner = company(client, 'Audit provenance')
    person = employee(client, owner, media)
    check_id = send(client, owner, person, media).json()['check_id']
    monkeypatch.setattr(checks, 'selected_for_random_audit', lambda _: True)
    response = client.put(f'/v1/checks/{check_id}/review', headers=owner['operator'],
                          json={'identity_truth': 'genuine', 'cheating_judgement': 'dismissed',
                                'selection_reason': 'manual'})
    assert response.status_code == 200
    assert response.json()['selection_reason'] == 'random_audit'


def test_legacy_feedback_cannot_spoof_reviewer_or_overwrite_check_review(checks_api):
    client, _, _, media, _ = checks_api
    owner = company(client, 'Feedback provenance')
    person = employee(client, owner, media)
    result = send(client, owner, person, media).json()
    check_id, event_id = result['check_id'], result['event_id']
    path = f'/v1/events/{event_id}/feedback'
    forged = {'is_genuine': True, 'reviewer': 'independent-human'}
    response = client.put(path, headers=owner['operator'], json=forged)
    assert response.status_code == 201
    assert response.json()['reviewer'].startswith('operator:')
    assert response.json()['reviewer'] != forged['reviewer']
    review = {'identity_truth': 'impostor', 'cheating_judgement': 'confirmed',
              'selection_reason': 'suspicious'}
    assert client.put(f'/v1/checks/{check_id}/review', headers=owner['operator'], json=review).status_code == 200
    assert client.put(path, headers=owner['operator'], json=forged).status_code == 409


def test_batch_check_integration_idempotency_and_webhook(checks_api):
    client, engine, store, media, _ = checks_api
    owner = company(client, 'First company')
    person = employee(client, owner, media)
    r = send(client, owner, person, media)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result['integrity_status'] == 'verified'
    assert result['face_match'] and result['voice_match']
    assert result['employee_name'] == 'Nguyễn Văn An'
    assert send(client, owner, person, media).json()['check_id'] == result['check_id']
    assert send(client, owner, person, media, session_id='DIFFERENT').status_code == 409
    assert store.objects == {}
    delivery = client.get('/v1/webhooks', headers=owner['operator']).json()[0]
    assert delivery['event_type'] == 'integrity.checked'
    assert delivery['check_id'] == result['check_id']
    with Session(engine) as db:
        rows = db.scalars(select(WebhookDelivery)).all()
        assert len(rows) == 1
        assert rows[0].payload['type'] == 'integrity.checked'
        assert rows[0].payload['data'] == result


def test_suspicious_only_evidence_and_full_tenant_isolation(checks_api, monkeypatch):
    client, _, store, media, main = checks_api
    first, second = company(client, 'First'), company(client, 'Second')
    p1, p2 = employee(client, first, media), employee(client, second, media)
    monkeypatch.setattr(main.app.state, 'inspect_integrity', lambda *args: {
        'face_pad': {'status': 'failed', 'score': .95},
        'audio_spoof': {'status': 'passed'}, 'speaker_consistency': {'status': 'passed'},
    })
    r = send(client, first, p1, media)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result['integrity_status'] == 'suspicious'
    assert 'face_spoof_suspected' in result['reason_codes']
    assert result['evidence_status'] == 'stored' and len(store.objects) == 2
    assert all(k.startswith(first['id']+'/') for k in store.objects)
    check_id = result['check_id']
    assert client.get(f'/v1/checks/{check_id}', headers=second['operator']).status_code == 404
    assert send(client, second, p1, media).status_code == 404
    assert client.get('/v1/checks', headers=second['operator']).json()['items'] == []
    assert client.get(f'/v1/checks/{check_id}/evidence/face', headers=second['operator']).status_code == 404
    assert client.get(f'/v1/checks/{check_id}/evidence/face').status_code == 401
    image = client.get(f'/v1/checks/{check_id}/evidence/face', headers=first['operator'])
    assert image.content == media['face_file'][1] and image.headers['content-type'] == 'image/png'
    assert p1['external_id'] == p2['external_id']


def test_missing_detector_is_inconclusive_without_evidence(checks_api, monkeypatch):
    client, _, store, media, main = checks_api
    owner = company(client, 'Missing detector')
    p = employee(client, owner, media)
    monkeypatch.setattr(main.app.state, 'inspect_integrity', lambda *args: {
        'face_pad': {'status': 'unavailable'}, 'audio_spoof': {'status': 'passed'},
        'speaker_consistency': {'status': 'passed'},
    })
    r = send(client, owner, p, media)
    assert r.status_code == 200, r.text
    assert r.json()['integrity_status'] == 'inconclusive'
    assert store.objects == {}


def test_reports_include_ranges_unicode_and_isolate_filters(checks_api):
    client, _, _, media, _ = checks_api
    first, second = company(client, 'Report owner'), company(client, 'Other reports')
    p1 = employee(client, first, media)
    employee(client, second, media)
    assert send(client, first, p1, media).status_code == 200
    report = client.get('/v1/company/report', headers=first['operator']).json()
    assert report['employees'][0]['first_check_at'] and report['employees'][0]['last_check_at']
    assert report['employees'][0]['checks'] == 1
    assert client.get('/v1/company/report', headers=second['operator']).json()['checks'] == []
    assert client.get('/v1/company/report?person_id='+p1['id'], headers=second['operator']).status_code == 404
    csv = client.get('/v1/company/report.csv', headers=first['operator'])
    assert csv.status_code == 200 and 'Nguyễn Văn An' in csv.content.decode('utf-8-sig')
    pdf = client.get('/v1/company/report.pdf', headers=first['operator'])
    assert pdf.status_code == 200 and pdf.content.startswith(b'%PDF')
    assert client.get('/v1/company/report.csv').status_code == 401


def test_registration_and_company_key_configuration(checks_api):
    client, _, _, _, _ = checks_api
    r = client.post('/v1/registrations', json={'name': 'Registered company'})
    assert r.status_code == 201, r.text
    headers = {'X-API-Key': r.json()['operator_key']}
    assert client.get('/v1/company', headers=headers).json()['name'] == 'Registered company'
    assert client.patch('/v1/company', headers=headers, json={'webhook_url': 'http://localhost:18600/webhooks/verification'}).status_code == 200
    assert client.patch('/v1/company', headers=headers, json={'webhook_url': 'http://169.254.169.254/'}).status_code == 422
    key = client.post('/v1/company/keys', headers=headers).json()
    assert client.get('/v1/me', headers={'X-API-Key': key['api_key']}).json()['role'] == 'integration'
    assert client.delete('/v1/company/keys/'+key['id'], headers=headers).status_code == 200
    assert client.get('/v1/me', headers={'X-API-Key': key['api_key']}).status_code == 401


def test_reused_capture_is_logged_but_retry_is_not_new_capture(checks_api):
    client, _, _, media, _ = checks_api
    owner = company(client, 'Reuse signals')
    p = employee(client, owner, media)
    first = send(client, owner, p, media).json()
    assert first['integrity_status'] == 'verified'
    assert send(client, owner, p, media).json() == first
    second = send(client, owner, p, media, request_id='new-capture').json()
    assert 'capture_reused' in second['reason_codes']
    assert second['evidence_status'] == 'stored'
    assert client.get('/v1/checks', headers=owner['operator']).json()['total'] == 2


def test_evidence_failure_keeps_business_result_and_outbox(checks_api, monkeypatch):
    client, engine, store, media, main = checks_api
    owner = company(client, 'Storage failure')
    p = employee(client, owner, media)
    monkeypatch.setattr(main.app.state, 'inspect_integrity', lambda *args: {
        'face_pad': {'status': 'failed'}, 'audio_spoof': {'status': 'passed'},
        'speaker_consistency': {'status': 'passed'}})
    def unavailable(*args):
        raise OSError('Object storage is unavailable')
    monkeypatch.setattr(store, 'put_evidence', unavailable)
    r = send(client, owner, p, media)
    assert r.status_code == 200
    assert r.json()['integrity_status'] == 'suspicious' and r.json()['evidence_status'] == 'unavailable'
    with Session(engine) as db:
        assert db.scalar(select(WebhookDelivery)).payload['data'] == r.json()


def test_capture_validation_filters_and_subscription_disable(checks_api):
    client, _, _, media, _ = checks_api
    owner = company(client, 'Subscription')
    p = employee(client, owner, media)
    data = {'person_id': p['id'], 'session_id': 'x', 'request_id': 'x', 'consent': 'false'}
    assert client.post('/v1/checks', headers=owner['integration'], data=data, files=media).status_code == 422
    assert client.get('/v1/company/report?start=2026-09-30&end=2026-09-01', headers=owner['operator']).status_code == 422
    assert send(client, owner, p, media).status_code == 200
    assert client.get('/v1/checks?session_id=other', headers=owner['operator']).json()['total'] == 0
    assert client.get('/v1/checks?limit=1&offset=1', headers=owner['operator']).json()['items'] == []
    r = client.patch('/v1/admin/tenants/'+owner['id']+'/subscription',
                     headers={'X-API-Key': 'checks-platform'}, json={'active': False})
    assert r.status_code == 200 and r.json()['data_retained']
    assert client.get('/v1/checks', headers=owner['operator']).status_code == 401


def test_csv_formula_values_are_neutralized():
    from app.company_reports import csv_cell
    assert csv_cell('=HYPERLINK("malicious")').startswith("'")
    assert csv_cell('  @SUM(A1)') == "'  @SUM(A1)"
    assert csv_cell('EMP-001') == 'EMP-001'
