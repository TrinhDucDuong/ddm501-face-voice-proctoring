# Company API / webhook integration

## Contract

Customer owns exam login, capture cadence, scoring and business decisions. Service owns employees/enrollment, identity/integrity signals, history/evidence and callbacks. Company portal exposes its tenant only; Grafana/Evidently/Telegram are platform administration.

1. POST /v1/registrations {name} creates simulated active company; operator_key returned once. Platform-admin tenant provisioning also remains available.
2. Operator creates people and POST /v1/people/{id}/enroll with face_files/voice_files. At least 2 different images and WAVs recommended. Raw enrollment defaults off; embeddings/metadata remain.
3. Operator POST /v1/company/keys issues integration key; GET lists key IDs, DELETE revokes only own keys. PATCH /v1/company sets webhook_url on approved host; GET provides signing secret to operator.
4. Customer backend POST /v1/checks with X-API-Key integration credential and multipart person_id, session_id, request_id, consent=true, face_file, voice_file. session_id belongs to customer; new request_id for each capture, stable request_id for retry. Consent assertion must originate from an actual consented process.
5. API returns check_id, employee code/name, checked_at, face_match/voice_match, scores, verified/suspicious/inconclusive, reason_codes/labels, capabilities, model_version and evidence_status.
6. GET /v1/checks supports person_id/session_id/start/end/limit/offset. GET /v1/checks/{id} fetches canonical immutable result. Company decides consequences; no automatic exam admission contract in checks.
7. Operator GET /v1/company/report[.csv|.pdf] exports same filtered history and employee/session first-last ranges. GET /v1/checks/{id}/evidence/face|voice streams protected evidence. No public S3 link/secret in report.

## Local service pages

- Employee demo: `http://localhost:18600/` remains open without login. The backend queries current active companies and all employees; use **Cap nhat danh sach** after registering a company or employee in another tab.
- Company and platform administration: `http://localhost:18501/?page=login`. Submit an operator or platform key once to enter `?page=portal`. The key field is removed during the session. Logout clears credentials and page state; expiry after one hour or a revoked key returns to login.
- Compose loads `API_KEY` for the demo backend and API from the same `ENV_FILE` (default `.env`). This credential stays on the server. Standalone demo deployments may set `EXAM_SERVICE_API_KEY` instead. The demo uses `GET /v1/exam/companies` and platform-only cross-company scope via `X-Tenant-ID`; company keys cannot select another tenant. Without either key environment variable, standalone legacy deployments retain the file-based configuration.
- `GET /v1/people` returns the complete tenant roster, including employees beyond the previous 500-record cutoff. Technical monitoring pages are unchanged.

## Example backend request

```python
import requests, uuid
with open('capture.jpg','rb') as face, open('capture.wav','rb') as voice:
    result = requests.post('http://localhost:18100/v1/checks',
        headers={'X-API-Key': integration_key},
        data={'person_id': employee_uuid, 'session_id': 'ANNUAL-2026-ATTEMPT-1',
              'request_id': str(uuid.uuid4()), 'consent': 'true'},
        files={'face_file': ('capture.jpg',face,'image/jpeg'),
               'voice_file': ('capture.wav',voice,'audio/wav')},timeout=180)
    result.raise_for_status()
```

Employee binding must come from customer backend's authenticated identity, not a browser-selected arbitrary person_id. Cadence is customer-owned; 30 seconds and audio 10 seconds are examples. WAV supports 0.8-30 seconds; short clips may not support speaker consistency. Cold models cost more latency; pilot must measure the complete checks path separately from legacy identity latency.

## Signed business webhook

Envelope: id (delivery ID), type=integrity.checked, data=same check result as API. Headers X-Webhook-Id/Timestamp/Signature. Verify hex HMAC-SHA256(secret, timestamp + '.' + raw_body), constant-time comparison, <=5 minutes skew. Persist unique delivery ID; return 2xx for known duplicates. Delivery is at-least-once, maximum 5 attempts with backoff; operator may retry failed delivery. GET canonical check if state needs reconciliation. No media/embedding/API keys in payload. Evidence requires operator authentication.

Receiver example is legacy_demo/app.py. It also accepts verification.completed from old hosted session endpoints. No customer Telegram. Platform alerts go to project Telegram only.

## Isolation and retention

Tenant comes from hashed authenticated credential. Matching employee codes in different companies are supported. Other tenant IDs/check IDs/evidence/filter IDs return 404. Disabled subscription blocks tenant credential use; historical data retained. Demo self-registration can be disabled with ENABLE_DEMO_REGISTRATION=false. No real billing or email verification. Webhook callback must be on an allowlisted host; private deployment requires HTTPS and egress policy.

## Detector interpretation

face/voice mismatch indicates identity mismatch. MiniFASNet PAD indicates print/screen suspicion; AASIST indicates synthetic/converted speech suspicion. ECAPA segment change and exact repeated capture are heuristic signals. Unavailable capability is not passed. Physical audio replay, overlapping voices and unseen deepfakes remain explicitly unvalidated. Identity embeddings do not themselves prove liveness.
