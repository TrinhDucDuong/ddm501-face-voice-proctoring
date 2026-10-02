"""Live employee self-enrollment across two configured demo companies; no secret output."""
import io
import json
import uuid
from pathlib import Path

import numpy as np
import requests
from scipy.io import wavfile

ROOT = Path(__file__).resolve().parents[1]
API = 'http://localhost:18100'


def main():
    companies = json.loads((ROOT / 'data/company-demo.json').read_text(encoding='utf-8'))['companies']
    assert len(companies) >= 2
    session = requests.Session()
    session.trust_env = False
    exam = requests.Session()
    exam.trust_env = False
    assert exam.get('http://localhost:18600/', timeout=15).status_code == 200
    listed = exam.get('http://localhost:18600/companies', timeout=15).json()
    assert {c['id'] for c in listed} >= {c['tenant_id'] for c in companies[:2]}
    evidence = []

    def call(method, path, expected=200, key=None, **kwargs):
        response = session.request(method, API + path, headers={'X-API-Key': key} if key else {},
                                   timeout=180, **kwargs)
        if response.status_code != expected:
            raise RuntimeError(f'{method} {path}: HTTP {response.status_code}, expected {expected}')
        return response

    for index, company in enumerate(companies[:2]):
        owner = company['operator_key']
        code = 'SELF-' + uuid.uuid4().hex[:8]
        person = call('POST', '/v1/people', 201, owner,
                      json={'external_id': code, 'display_name': f'Nhân viên tự ghi danh {index + 1}'}).json()
        invitation = call('POST', f"/v1/people/{person['id']}/enrollment-invitations", 201, owner).json()
        token = invitation['token']
        info = exam.post('http://localhost:18600/enrollment-info', data={'token': token}, timeout=15).json()
        assert info['display_name'] == person['display_name']
        folder = ROOT / 'data/bootstrap/DEMO-001'
        faces = sorted(folder.glob('face-*.jpg'))[:2]
        voices = sorted(folder.glob('voice-*.wav'))[:2]
        assert len(faces) == len(voices) == 2
        files = [('face_files', (p.name, p.read_bytes(), 'image/jpeg')) for p in faces]
        files += [('voice_files', (p.name, p.read_bytes(), 'audio/wav')) for p in voices]
        enrollment_response = exam.post('http://localhost:18600/enroll',
                                        data={'token': token, 'consent': 'true'}, files=files, timeout=180)
        assert enrollment_response.status_code == 200, enrollment_response.status_code
        enrollment = enrollment_response.json()
        assert enrollment['ready'] and enrollment['face_added'] == enrollment['voice_added'] == 2
        assert exam.post('http://localhost:18600/enroll', data={'token': token, 'consent': 'true'},
                         files=files, timeout=180).status_code == 404
        people = call('GET', '/v1/people', key=owner).json()
        assert next(p for p in people if p['id'] == person['id'])['ready']
        visible = exam.get('http://localhost:18600/candidates',
                           params={'company_id': company['tenant_id']}, timeout=15).json()
        assert next(p for p in visible if p['id'] == person['id'])['ready']
        rate, wave = wavfile.read(voices[0])
        wave = np.tile(wave, int(np.ceil(10 * rate / len(wave))))[:10 * rate]
        audio = io.BytesIO()
        wavfile.write(audio, rate, wave)
        media = {'face_file': ('fresh.jpg', faces[0].read_bytes(), 'image/jpeg'),
                 'voice_file': ('fresh.wav', audio.getvalue(), 'audio/wav')}
        check_response = exam.post('http://localhost:18600/check', data={
            'company_id': company['tenant_id'], 'person_id': person['id'], 'session_id': 'EMPLOYEE-DEMO-2026',
            'request_id': str(uuid.uuid4()), 'consent': 'true'}, files=media, timeout=180)
        assert check_response.status_code == 200, check_response.status_code
        result = check_response.json()
        assert result['integrity_status'] in {'verified', 'suspicious', 'inconclusive'}
        evidence.append({'company': company['name'], 'employee': code, 'ready': True,
                         'single_submission': True, 'replay_rejected': True,
                         'exam_check_status': result['integrity_status']})

    first, second = companies[:2]
    call('POST', f"/v1/people/{person['id']}/enrollment-invitations", 404, first['operator_key'])
    assert exam.post('http://localhost:18600/check', data={
        'company_id': first['tenant_id'], 'person_id': person['id'], 'session_id': 'CROSS-TENANT',
        'request_id': str(uuid.uuid4()), 'consent': 'true'}, files=media, timeout=30).status_code == 404
    output = {'status': 'pass', 'scenarios': evidence, 'tenant_isolation': 'pass',
              'note': 'Bootstrap media exercises transport and enrollment; it is not a human biometric accuracy benchmark.'}
    (ROOT / 'reports').mkdir(exist_ok=True)
    (ROOT / 'reports/employee-demo-verification.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
