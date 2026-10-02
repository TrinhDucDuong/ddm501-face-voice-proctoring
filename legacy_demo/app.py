"""Example customer-owned exam system. It never trusts browser verification results."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Legacy Exam Integration Demo")
CONFIG = Path(os.getenv("SAAS_CONFIG", "/config/local-saas.json"))
DATABASE = os.getenv("LEGACY_DATABASE", "/data/legacy.db")


@app.post('/check')
async def check_batch(request: Request, company_id: str = Form(...), person_id: str = Form(...), session_id: str = Form(...),
                      request_id: str = Form(...), consent: bool = Form(...),
                      face_file: UploadFile = File(...), voice_file: UploadFile = File(...)):
    browser_id(request)
    customer = customer_config(company_id)
    require_candidate(customer, person_id)
    files = {}
    for key, upload in [('face_file', face_file), ('voice_file', voice_file)]:
        payload = await upload.read(12*1024*1024+1)
        if len(payload) > 12*1024*1024:
            raise HTTPException(413, 'File exceeds demo limit')
        files[key] = (upload.filename, payload, upload.content_type)
    return api('POST', '/v1/checks', customer=customer, data={'person_id': person_id, 'session_id': session_id,
                                        'request_id': request_id, 'consent': str(consent).lower()}, files=files)


def service_key():
    return os.getenv('EXAM_SERVICE_API_KEY') or os.getenv('API_KEY')


def config():
    if key := service_key():
        return {'integration_key': key}
    if not CONFIG.exists():
        raise HTTPException(503, "Run pipeline/provision_local_saas.py first")
    return json.loads(CONFIG.read_text())


def customers():
    if service_key():
        return [{'tenant_id': row['id'], 'name': row['name'], **config()}
                for row in api('GET', '/v1/exam/companies')]
    primary = dict(config(), name='Demo nội bộ')
    extra_file = CONFIG.parent / 'company-demo.json'
    extra = json.loads(extra_file.read_text()).get('companies', []) if extra_file.exists() else []
    return [primary, *extra]


def customer_config(company_id):
    customer = next((item for item in customers() if item['tenant_id'] == company_id), None)
    if customer is None:
        raise HTTPException(404, 'Company is unavailable in this demo')
    if service_key():
        customer['webhook_secret'] = api('GET', '/v1/company', customer=customer)['webhook_secret']
    return customer


def require_candidate(customer, person_id):
    candidate = next((p for p in api('GET', '/v1/people', customer=customer) if p['id'] == person_id), None)
    if candidate is None:
        raise HTTPException(404, 'Employee does not belong to this company')
    return candidate


@app.post('/enrollment-info')
def enrollment_info(request: Request, token: str = Form(...)):
    browser_id(request)
    response = requests.post(os.getenv('API_URL', 'http://api:8000') + '/v1/public/enrollment-invitations/inspect',
                             data={'token': token}, timeout=15)
    if not response.ok:
        raise HTTPException(response.status_code, 'This enrollment link is invalid or expired')
    return response.json()


@app.post('/enroll')
async def enroll_employee(request: Request, token: str = Form(...), consent: bool = Form(...),
                          face_files: list[UploadFile] = File(...), voice_files: list[UploadFile] = File(...)):
    browser_id(request)
    if len(face_files) != 2 or len(voice_files) != 2:
        raise HTTPException(422, 'Provide two photos and two WAV recordings')
    files = []
    for field, uploads in (('face_files', face_files), ('voice_files', voice_files)):
        for upload in uploads:
            payload = await upload.read(12 * 1024 * 1024 + 1)
            if len(payload) > 12 * 1024 * 1024:
                raise HTTPException(413, 'File exceeds demo limit')
            files.append((field, (upload.filename, payload, upload.content_type)))
    response = requests.post(os.getenv('API_URL', 'http://api:8000') + '/v1/public/enroll',
                             data={'token': token, 'consent': str(consent).lower()}, files=files, timeout=180)
    if not response.ok:
        raise HTTPException(response.status_code, response.json().get('detail', 'Enrollment failed'))
    return response.json()


def connection():
    Path(DATABASE).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS attempts (browser TEXT PRIMARY KEY, session_id TEXT, person_id TEXT, exam_id TEXT, consumed INTEGER DEFAULT 0, company_id TEXT)")
    if 'company_id' not in {row[1] for row in db.execute('PRAGMA table_info(attempts)')}:
        db.execute('ALTER TABLE attempts ADD COLUMN company_id TEXT')
    db.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, session_id TEXT, received_at INTEGER)")
    return db


def api(method, path, customer=None, **kwargs):
    cfg = customer or config()
    headers = {"X-API-Key": cfg["integration_key"]}
    if service_key() and customer:
        headers['X-Tenant-ID'] = customer['tenant_id']
    response = requests.request(method, os.getenv("API_URL", "http://api:8000") + path,
                                headers=headers, timeout=180, **kwargs)
    if not response.ok:
        raise HTTPException(response.status_code, "Verification service rejected request")
    return response.json()


def browser_id(request: Request) -> str:
    token = request.cookies.get("exam_browser", "")
    pieces = token.split(".")
    if len(pieces) != 2:
        raise HTTPException(401, "Open the demo page first")
    expected = hmac.new(config()["integration_key"].encode(), pieces[0].encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, pieces[1]):
        raise HTTPException(401, "Invalid browser session")
    return pieces[0]


@app.get("/health")
def health():
    return {"status": "ok", "configured": bool(service_key()) or CONFIG.exists()}


@app.get("/", include_in_schema=False)
def index(request: Request):
    response = FileResponse(Path(__file__).parent / "index.html", headers={"Cache-Control": "no-store"})
    try:
        browser_id(request)
        return response
    except HTTPException:
        pass
    if service_key() or CONFIG.exists():
        token = secrets.token_urlsafe(24)
        signed = hmac.new(config()["integration_key"].encode(), token.encode(), hashlib.sha256).hexdigest()
        response.set_cookie("exam_browser", token + "." + signed, httponly=True, samesite="lax", max_age=3600)
    return response


@app.get("/candidates")
def candidates(request: Request, company_id: str):
    browser_id(request)
    return [{"id": p["id"], "name": p["display_name"], "code": p['external_id'], "ready": p['ready']}
            for p in api("GET", "/v1/people", customer=customer_config(company_id))]


@app.get('/companies')
def companies(request: Request):
    browser_id(request)
    return [{'id': item['tenant_id'], 'name': item['name']} for item in customers()]


class StartBody(BaseModel):
    company_id: str
    person_id: str


@app.post("/start")
def start(body: StartBody, request: Request):
    browser = browser_id(request)
    customer = customer_config(body.company_id)
    require_candidate(customer, body.person_id)
    result = api("POST", "/v1/sessions", customer=customer, json={"person_id": body.person_id, "exam_id": "ENGLISH-DEMO-501",
                                               "request_id": secrets.token_urlsafe(24)})
    with connection() as db:
        db.execute("INSERT INTO attempts (browser, session_id, person_id, exam_id, company_id) VALUES (?, ?, ?, ?, ?) "
                   "ON CONFLICT(browser) DO UPDATE SET session_id=excluded.session_id, person_id=excluded.person_id, exam_id=excluded.exam_id, company_id=excluded.company_id, consumed=0",
                   (browser, result["id"], body.person_id, result["exam_id"], body.company_id))
    return {"verify_url": result["verify_url"], "session_id": result["id"]}


def current_attempt(request):
    with connection() as db:
        row = db.execute("SELECT * FROM attempts WHERE browser=?", (browser_id(request),)).fetchone()
    if row is None:
        raise HTTPException(404, "Start a verification session first")
    customer = customer_config(row['company_id'] or config()['tenant_id'])
    result = api("GET", "/v1/sessions/" + row["session_id"], customer=customer)
    if (result["tenant_id"], result["person_id"], result["exam_id"]) != (customer["tenant_id"], row["person_id"], row["exam_id"]):
        raise HTTPException(403, "Verification binding mismatch")
    return row, result


@app.get("/status")
def status(request: Request):
    row, result = current_attempt(request)
    with connection() as db:
        count = db.execute("SELECT count(*) FROM receipts WHERE session_id=?", (row["session_id"],)).fetchone()[0]
    return {"status": result["status"], "session_id": row["session_id"], "webhooks_received": count,
            "consumed": bool(row["consumed"])}


@app.post("/enter")
def enter(request: Request):
    row, result = current_attempt(request)
    if result["status"] != "allow" or datetime.fromisoformat(result["expires_at"]) <= datetime.now(timezone.utc):
        raise HTTPException(403, "A current successful backend verification is required")
    with connection() as db:
        changed = db.execute("UPDATE attempts SET consumed=1 WHERE browser=? AND session_id=? AND consumed=0",
                             (row["browser"], row["session_id"]))
        if changed.rowcount != 1:
            raise HTTPException(409, "This attempt was already used")
    return {"allowed": True, "message": "Đã mở ca thi demo sau khi kiểm tra kết quả từ backend."}


@app.post("/webhooks/verification")
async def webhook(request: Request):
    body = await request.body()
    if len(body) > 16384:
        raise HTTPException(413, "Payload too large")
    try:
        payload = json.loads(body)
        tenant_id = payload['data']['tenant_id']
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, 'Invalid callback envelope') from exc
    try:
        customer = customer_config(tenant_id)
    except HTTPException as exc:
        raise HTTPException(403, 'Unknown demo customer') from exc
    timestamp = request.headers.get("X-Webhook-Timestamp", "")
    try:
        if abs(time.time() - int(timestamp)) > 300:
            raise ValueError()
    except ValueError as exc:
        raise HTTPException(401, "Expired webhook") from exc
    expected = hmac.new(customer["webhook_secret"].encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("X-Webhook-Signature", "")):
        raise HTTPException(401, "Invalid webhook signature")
    if payload["id"] != request.headers.get("X-Webhook-Id") or payload["data"]["tenant_id"] != customer["tenant_id"]:
        raise HTTPException(403, "Webhook tenant/event mismatch")
    with connection() as db:
        result_id = payload['data']['check_id'] if payload['type'] == 'integrity.checked' else payload['data']['id']
        inserted = db.execute("INSERT OR IGNORE INTO receipts VALUES (?, ?, ?)",
                               (payload["id"], result_id, int(time.time())))
    return JSONResponse({"received": True, "duplicate": inserted.rowcount == 0})
