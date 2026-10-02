"""Tenant administration and hosted, expiring verification sessions."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import Principal, audit, authenticate, digest, get_person, operator, platform
from .config import get_settings
from .db import get_db
from .models import (
    AuditLog,
    Tenant,
    TenantKey,
    VerificationEvent,
    VerifySession,
    WebhookDelivery,
    utcnow,
)

router = APIRouter()


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def derived_secret(purpose: str, value: str) -> str:
    settings = get_settings()
    root = (settings.webhook_master_key if purpose == "webhook" else settings.session_signing_key) or settings.api_key
    return hmac.new(root.encode(), f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def validate_destination(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    settings = get_settings()
    allowed = {host.strip().lower() for host in settings.webhook_allowed_hosts.split(",")}
    schemes = {"https", "http"} if settings.allow_insecure_webhooks else {"https"}
    if parsed.scheme not in schemes or parsed.hostname not in allowed or parsed.username or parsed.password or parsed.fragment:
        raise HTTPException(422, "Destination must use an approved host and scheme, without credentials/fragments")
    return value


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    webhook_url: str | None = Field(default=None, max_length=2048)
    return_url: str | None = Field(default=None, max_length=2048)


class KeyCreate(BaseModel):
    role: Literal["operator", "integration"]


class SessionCreate(BaseModel):
    person_id: str
    exam_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=100)
    ttl_seconds: int = Field(default=900, ge=60, le=1800)


class ReviewDecision(BaseModel):
    approved: bool
    notes: str = Field(min_length=5, max_length=1000)


@router.get("/v1/me")
def me(principal: Principal = Depends(authenticate)):
    return {"tenant_id": principal.tenant_id, "role": principal.role}


@router.get("/v1/admin/tenants", dependencies=[Depends(platform)])
def tenants(db: Session = Depends(get_db)):
    return [{"id": row.id, "name": row.name, "active": row.active,
             "webhook_url": row.webhook_url, "return_url": row.return_url} for row in db.scalars(select(Tenant))]


@router.get('/v1/exam/companies')
def exam_companies(db: Session = Depends(get_db), principal: Principal = Depends(authenticate)):
    query = select(Tenant).where(Tenant.active.is_(True)).order_by(Tenant.name, Tenant.id)
    if principal.role != 'platform':
        query = query.where(Tenant.id == principal.tenant_id)
    return [{'id': row.id, 'name': row.name} for row in db.scalars(query)]


@router.post("/v1/admin/tenants", status_code=201)
def create_tenant(body: TenantCreate, db: Session = Depends(get_db), principal: Principal = Depends(platform)):
    tenant = Tenant(name=body.name, webhook_url=validate_destination(body.webhook_url),
                    return_url=validate_destination(body.return_url))
    db.add(tenant)
    try:
        db.flush()
        audit(db, principal, "tenant.created", tenant.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Tenant name already exists") from exc
    return {"id": tenant.id, "name": tenant.name, "webhook_secret": derived_secret("webhook", tenant.id)}


@router.post("/v1/admin/tenants/{tenant_id}/keys", status_code=201)
def create_key(tenant_id: str, body: KeyCreate, db: Session = Depends(get_db), principal: Principal = Depends(platform)):
    if db.get(Tenant, tenant_id) is None:
        raise HTTPException(404, "Tenant not found")
    token = "fv_" + secrets.token_urlsafe(32)
    key = TenantKey(tenant_id=tenant_id, role=body.role, digest=digest(token))
    db.add(key)
    db.flush()
    audit(db, principal, "key.created", key.id)
    db.commit()
    return {"id": key.id, "role": key.role, "api_key": token}


@router.get("/v1/admin/tenants/{tenant_id}/keys", dependencies=[Depends(platform)])
def list_keys(tenant_id: str, db: Session = Depends(get_db)):
    return [{"id": key.id, "role": key.role, "active": key.active} for key in db.scalars(
        select(TenantKey).where(TenantKey.tenant_id == tenant_id))]


@router.delete("/v1/admin/keys/{key_id}")
def revoke_key(key_id: str, db: Session = Depends(get_db), principal: Principal = Depends(platform)):
    key = db.get(TenantKey, key_id)
    if key is None:
        raise HTTPException(404, "Key not found")
    key.active = False
    audit(db, principal, "key.revoked", key.id)
    db.commit()
    return {"revoked": key_id}


def session_result(row: VerifySession, db: Session) -> dict:
    status = "expired" if row.status == "pending" and aware(row.expires_at) <= utcnow() else row.status
    event = db.get(VerificationEvent, row.event_id) if row.event_id else None
    return {"id": row.id, "tenant_id": row.tenant_id, "person_id": row.person_id,
            "exam_id": row.exam_id, "request_id": row.request_id, "status": status, "sequence": row.sequence,
            "expires_at": aware(row.expires_at).isoformat(), "event_id": row.event_id,
            "model_version": event.model_version if event else None}


def scoped_session(db: Session, session_id: str, principal: Principal) -> VerifySession:
    row = db.scalar(select(VerifySession).where(VerifySession.id == session_id, VerifySession.tenant_id == principal.tenant_id))
    if row is None:
        raise HTTPException(404, "Session not found")
    return row


@router.post("/v1/sessions", status_code=201)
def create_session(body: SessionCreate, db: Session = Depends(get_db), principal: Principal = Depends(authenticate)):
    person = get_person(db, body.person_id, principal)
    for modality, minimum in (("face", get_settings().min_face_samples), ("voice", get_settings().min_voice_samples)):
        if sum(sample.modality == modality for sample in person.samples) < minimum:
            raise HTTPException(409, "Person needs enrollment before verification")
    row = db.scalar(select(VerifySession).where(VerifySession.tenant_id == principal.tenant_id,
                                              VerifySession.request_id == body.request_id))
    if row and (row.person_id != body.person_id or row.exam_id != body.exam_id):
        raise HTTPException(409, "request_id already used for a different request")
    if row is None:
        count = db.scalar(select(func.count()).select_from(VerifySession).where(
            VerifySession.tenant_id == principal.tenant_id, VerifySession.created_at > utcnow() - timedelta(days=1)))
        if count >= 1000:
            raise HTTPException(429, "Demo daily session quota reached")
        row = VerifySession(tenant_id=principal.tenant_id, person_id=body.person_id,
                            exam_id=body.exam_id, request_id=body.request_id,
                            expires_at=utcnow() + timedelta(seconds=body.ttl_seconds))
        db.add(row)
        try:
            db.flush()
            audit(db, principal, "session.created", row.id)
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "Concurrent duplicate request; retry with same request_id") from exc
    output = session_result(row, db)
    if output["status"] == "pending":
        output["verify_url"] = f"{get_settings().public_api_url.rstrip('/')}/verify#session={row.id}&token={derived_secret('session', row.id)}"
    return output


@router.get("/v1/sessions")
def sessions(db: Session = Depends(get_db), principal: Principal = Depends(authenticate)):
    return [session_result(row, db) for row in db.scalars(select(VerifySession)
            .where(VerifySession.tenant_id == principal.tenant_id).order_by(VerifySession.created_at.desc()).limit(200))]


@router.get("/v1/sessions/{session_id}")
def result(session_id: str, db: Session = Depends(get_db), principal: Principal = Depends(authenticate)):
    return session_result(scoped_session(db, session_id, principal), db)


def bearer_session(session_id: str, db: Session, authorization: str | None) -> VerifySession:
    supplied = (authorization or "").removeprefix("Bearer ")
    if not hmac.compare_digest(supplied, derived_secret("session", session_id)):
        raise HTTPException(401, "Invalid session token")
    row = db.get(VerifySession, session_id)
    if row is None or not db.get(Tenant, row.tenant_id).active:
        raise HTTPException(404, "Session not found")
    if aware(row.expires_at) <= utcnow():
        raise HTTPException(410, "Session expired; request a new session")
    return row


@router.get("/v1/public/sessions/{session_id}")
def public_session(session_id: str, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    row = bearer_session(session_id, db, authorization)
    tenant = db.get(Tenant, row.tenant_id)
    return {"exam_id": row.exam_id, "status": row.status, "expires_at": aware(row.expires_at).isoformat(),
            "return_url": tenant.return_url, "organization": tenant.name}


def queue_result(row: VerifySession, db: Session) -> None:
    tenant = db.get(Tenant, row.tenant_id)
    if tenant.webhook_url:
        db.add(WebhookDelivery(tenant_id=row.tenant_id, session_id=row.id,
                               payload={"type": "verification.completed", "data": session_result(row, db)}))


@router.post("/v1/public/sessions/{session_id}/verify")
async def submit_session(session_id: str, request: Request, consent: bool = Form(...),
                         face_file: UploadFile = File(...), voice_file: UploadFile = File(...),
                         authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    row = bearer_session(session_id, db, authorization)
    if not consent:
        raise HTTPException(422, "Consent required")
    claimed = db.execute(update(VerifySession).where(VerifySession.id == row.id, VerifySession.status == "pending")
                         .values(status="processing").execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        raise HTTPException(409, "Session already submitted")
    principal = Principal(row.tenant_id, "session", row.id)
    outcome = await request.app.state.perform_verification(row.person_id, row.id, face_file, voice_file, db, principal)
    row.status, row.event_id, row.consent_at, row.sequence = outcome.decision, outcome.event_id, utcnow(), 1
    db.flush()
    queue_result(row, db)
    audit(db, principal, "session.verified", row.id)
    db.commit()
    return {"status": row.status, "message": "Verified" if outcome.accepted else "Waiting for human review"}


@router.post("/v1/sessions/{session_id}/review")
def review(session_id: str, body: ReviewDecision, db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    row = scoped_session(db, session_id, principal)
    changed = db.execute(update(VerifySession).where(VerifySession.id == row.id, VerifySession.status == "review")
                         .values(status="allow" if body.approved else "reject", sequence=2))
    if changed.rowcount != 1:
        raise HTTPException(409, "Only sessions awaiting review can be decided")
    db.refresh(row)
    # Do not rewrite the original model prediction. Manual decision is separately audited.
    audit(db, principal, "session.approved" if body.approved else "session.rejected", row.id, body.notes)
    queue_result(row, db)
    db.commit()
    return session_result(row, db)


@router.get("/v1/webhooks")
def deliveries(db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    return [{"id": row.id, "session_id": row.session_id, "status": row.status,
             "event_type": row.payload.get('type'),
             "check_id": row.payload.get('data', {}).get('check_id'),
             "attempts": row.attempts, "last_status_code": row.last_status_code}
            for row in db.scalars(select(WebhookDelivery).where(WebhookDelivery.tenant_id == principal.tenant_id)
                                   .order_by(WebhookDelivery.created_at.desc()).limit(100))]


@router.post("/v1/webhooks/{delivery_id}/retry")
def retry_delivery(delivery_id: str, db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    row = db.scalar(select(WebhookDelivery).where(WebhookDelivery.id == delivery_id,
                                                 WebhookDelivery.tenant_id == principal.tenant_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Delivery not found")
    if row.status != "failed":
        raise HTTPException(409, "Only failed deliveries can be retried")
    row.status, row.attempts, row.next_attempt_at = "pending", 0, utcnow()
    audit(db, principal, "webhook.retried", row.id)
    db.commit()
    return {"status": "pending"}


@router.get("/v1/audit")
def audit_events(db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    return [{"action": row.action, "target": row.target, "actor": row.actor, "details": row.details, "created_at": row.created_at.isoformat()}
            for row in db.scalars(select(AuditLog).where(AuditLog.tenant_id == principal.tenant_id)
                                   .order_by(AuditLog.created_at.desc()).limit(200))]


@router.get("/verify", include_in_schema=False)
def hosted_page():
    return FileResponse(Path(__file__).parent / "static" / "verify.html", headers={
        "Referrer-Policy": "no-referrer", "Cache-Control": "no-store", "X-Frame-Options": "DENY",
    })


@router.get("/v1/admin/reports/{name}", dependencies=[Depends(platform)])
def report(name: Literal["data-drift", "model-performance"]):
    path = Path("/reports") / (name + ".html")
    if not path.exists():
        raise HTTPException(404, "Report not generated yet")
    return FileResponse(path, headers={"Cache-Control": "no-store"})
