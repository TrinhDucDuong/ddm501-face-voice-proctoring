"""Exercise actual customer checks/storage/export isolation; never manufacture human labels."""
import io
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    client = requests.Session()
    client.trust_env = False
    config_file = ROOT/'data/company-demo.json'
    config = json.loads(config_file.read_text()) if config_file.exists() else {'companies': []}
    results = {}
    def call(method, path, key=None, expected=200, **kwargs):
        r = client.request(method, 'http://localhost:18100'+path,
                           headers={'X-API-Key': key} if key else {}, timeout=180, **kwargs)
        if r.status_code != expected:
            raise RuntimeError(f'{method} {path}: HTTP {r.status_code}, expected {expected}')
        return r
    if not config['companies']:
        for label in ('A', 'B'):
            row = call('POST', '/v1/registrations', expected=201,
                       json={'name': f'DDM501 Annual Assessment {label} - {uuid.uuid4().hex[:6]}'}).json()
            owner = {'tenant_id': row['tenant_id'], 'name': row['name'], 'operator_key': row['operator_key']}
            owner['integration_key'] = call('POST', '/v1/company/keys', owner['operator_key'], expected=201).json()['api_key']
            owner['webhook_secret'] = call('GET', '/v1/company', owner['operator_key']).json()['webhook_secret']
            config['companies'].append(owner)
        config_file.write_text(json.dumps(config, indent=2), encoding='utf-8')
    for company in config['companies']:
        key = company['operator_key']
        call('PATCH', '/v1/company', key, json={'webhook_url': 'http://legacy-demo:8000/webhooks/verification'})
        people = call('GET', '/v1/people', key).json()
        employee = next((p for p in people if p['external_id'] == 'EMP-001'), None)
        if employee is None:
            employee = call('POST', '/v1/people', key, expected=201,
                            json={'external_id': 'EMP-001', 'display_name': 'Nhân viên demo '+company['name']}).json()
        company['employee_id'] = employee['id']
        if not employee['ready']:
            folder = ROOT/'data/bootstrap/DEMO-001'
            files = [('face_files', (p.name, p.read_bytes(), 'image/jpeg')) for p in sorted(folder.glob('face-*.jpg'))]
            files += [('voice_files', (p.name, p.read_bytes(), 'audio/wav')) for p in sorted(folder.glob('voice-*.wav'))]
            r = call('POST', f"/v1/people/{employee['id']}/enroll", key, files=files).json()
            assert r['ready'], r
    config_file.write_text(json.dumps(config, indent=2), encoding='utf-8')
    a, b = config['companies']
    session = 'ANNUAL-'+uuid.uuid4().hex[:8]
    outputs = []
    previous_deliveries = {r['id'] for r in call('GET', '/v1/webhooks', a['operator_key']).json()}
    for name, folder in [('same_identity', 'DEMO-001'), ('other_identity', 'DEMO-002')]:
        path = ROOT/'data/bootstrap'/folder
        rate, wave = wavfile.read(path/'voice-1.wav')
        # Synthetic duration extension to exercise the transport/windowing; not a claim of genuine live capture.
        wave = np.tile(wave, int(np.ceil(10*rate/len(wave))))[:10*rate]
        output = io.BytesIO()
        wavfile.write(output, rate, wave)
        media = {'face_file': ('face.jpg', (path/'face-1.jpg').read_bytes(), 'image/jpeg'),
                 'voice_file': ('voice.wav', output.getvalue(), 'audio/wav')}
        data = {'person_id': a['employee_id'], 'session_id': session, 'request_id': str(uuid.uuid4()), 'consent': 'true'}
        r = call('POST', '/v1/checks', a['integration_key'], data=data, files=media).json()
        outputs.append({'scenario': name, 'result': r})
        retry = call('POST', '/v1/checks', a['integration_key'], data=data, files=media).json()
        assert retry == r
        call('POST', '/v1/checks', a['integration_key'], expected=409,
             data={**data, 'session_id': 'DIFFERENT'}, files=media)
        call('GET', '/v1/checks/'+r['check_id'], b['operator_key'], expected=404)
        if name == 'other_identity':
            assert r['integrity_status'] == 'suspicious'
            assert r['evidence_status'] == 'stored'
            for modality in ('face', 'voice'):
                route = '/v1/checks/'+r['check_id']+'/evidence/'+modality
                call('GET', route, b['operator_key'], expected=404)
                call('GET', route, expected=401)
                assert len(call('GET', route, a['operator_key']).content) > 100
    results['batch_identity_and_idempotency'] = 'pass'
    results['suspicious_minio_evidence'] = 'pass'
    results['check_and_evidence_isolation'] = 'pass'
    filters = {'person_id': a['employee_id'], 'session_id': session}
    report = call('GET', '/v1/company/report', a['operator_key'], params=filters).json()
    assert len(report['checks']) == 2 and report['employees'][0]['checks'] == 2
    call('GET', '/v1/company/report', b['operator_key'], expected=404, params=filters)
    for extension in ('csv', 'pdf'):
        r = call('GET', '/v1/company/report.'+extension, a['operator_key'], params=filters)
        call('GET', '/v1/company/report.'+extension, b['operator_key'], expected=404, params=filters)
        (ROOT/'reports'/('company-demo.'+extension)).write_bytes(r.content)
    results['company_exports_and_ranges'] = 'pass'
    deadline = time.monotonic() + 60
    while True:
        deliveries = [r for r in call('GET', '/v1/webhooks', a['operator_key']).json()
                      if r['id'] not in previous_deliveries]
        if len(deliveries) == len(outputs) and all(r['status'] == 'delivered' and r['last_status_code'] == 200 for r in deliveries):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('Customer callback did not acknowledge every check within 60 seconds')
        time.sleep(2)
    results['signed_customer_callbacks'] = 'pass'
    print(json.dumps({'checks': results, 'scenarios': [{'scenario': o['scenario'], 'status': o['result']['integrity_status'],
                                                      'capabilities': o['result']['capabilities']} for o in outputs]}, ensure_ascii=True))
    (ROOT/'reports/company-verification.json').write_text(json.dumps({
        'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'pass', 'checks': results,
        'scenarios': outputs, 'deliveries': deliveries,
        'note': 'Bootstrap/tiled media checks transport/inference, not real-user anti-spoof accuracy.'}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
