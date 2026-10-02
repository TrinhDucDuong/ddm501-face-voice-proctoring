"""Customer-scheduled immutable integrity checks, independent of exam admission."""
import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from prometheus_client import Counter
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from .auth import Principal, audit, authenticate, get_person, operator
from .db import get_db
from .models import (
    CheckEvidence,
    CheckReview,
    IntegrityCheck,
    Tenant,
    VerificationFeedback,
    WebhookDelivery,
)
from .storage import sha256

router = APIRouter()
CHECKS = Counter('biometric_integrity_checks_total', 'Customer batch check results', ['status'])
EVIDENCE = Counter('biometric_evidence_writes_total', 'Suspicious evidence storage outcomes', ['outcome'])
LABELS = {
    'face_mismatch': 'Khuôn mặt không khớp', 'voice_mismatch': 'Giọng nói không khớp',
    'multiple_faces': 'Phát hiện nhiều khuôn mặt', 'no_face': 'Không thấy khuôn mặt',
    'face_spoof_suspected': 'Nghi vấn ảnh phát lại / giả mạo',
    'audio_spoof_suspected': 'Nghi vấn giọng tổng hợp / chuyển đổi',
    'multiple_speakers_suspected': 'Nghi vấn nhiều người nói',
    'capture_reused': 'Media trùng một lượt kiểm tra trước',
    'missing_face': 'Thiếu ảnh', 'missing_voice': 'Thiếu audio',
    'low_face_quality': 'Ảnh chất lượng thấp', 'low_voice_quality': 'Audio chất lượng thấp',
    'invalid_face': 'Ảnh không xử lý được', 'invalid_voice': 'Audio không xử lý được',
}


def scoped_check(db, check_id, principal):
    row = db.scalar(select(IntegrityCheck).where(IntegrityCheck.id == check_id,
                                                IntegrityCheck.tenant_id == principal.tenant_id))
    if row is None:
        raise HTTPException(404, 'Check not found')
    return row


class ReviewInput(BaseModel):
    identity_truth: Literal['genuine', 'impostor', 'unknown']
    cheating_judgement: Literal['confirmed', 'dismissed', 'undetermined']
    selection_reason: Literal['suspicious', 'random_audit', 'near_threshold', 'manual']
    notes: str | None = Field(default=None, max_length=1000)


def review_output(row):
    return {'check_id': row.check_id, 'identity_truth': row.identity_truth,
            'cheating_judgement': row.cheating_judgement,
            'selection_reason': row.selection_reason, 'notes': row.notes,
            'reviewer': row.reviewer, 'source': 'human',
            'created_at': row.created_at.isoformat(), 'updated_at': row.updated_at.isoformat()}


def selected_for_random_audit(check_id: str) -> bool:
    """Stable 10% cohort, selected without consulting the model's decision."""
    return int(hashlib.sha256(check_id.encode()).hexdigest()[:8], 16) % 10 == 0


@router.get('/v1/reviews/queue')
def review_queue(db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    """Include every concern and the same model-independent audit cohort."""
    recent = list(db.scalars(select(IntegrityCheck).where(IntegrityCheck.tenant_id == principal.tenant_id)
                             .order_by(IntegrityCheck.created_at.desc(), IntegrityCheck.id.desc()).limit(200)))
    reviewed = set(db.scalars(select(CheckReview.check_id).where(CheckReview.tenant_id == principal.tenant_id)))
    pending = [check for check in recent if check.id not in reviewed]
    items = []
    for check in pending:
        reason = ('random_audit' if selected_for_random_audit(check.id) else
                  'suspicious' if check.integrity_status == 'suspicious' else
                  'manual' if check.integrity_status == 'inconclusive' else
                  None)
        if reason:
            result = check.result or {}
            items.append({'check_id': check.id, 'employee_code': result.get('employee_code'),
                          'employee_name': result.get('employee_name'), 'checked_at': result.get('checked_at'),
                          'integrity_status': check.integrity_status, 'selection_reason': reason})
    return {'items': items, 'audit_policy': 'stable 10% hash cohort across all check outcomes'}


@router.get('/v1/checks/{check_id}/review')
def get_review(check_id: str, db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    scoped_check(db, check_id, principal)
    row = db.get(CheckReview, check_id)
    return {'check_id': check_id, 'status': 'pending'} if row is None else review_output(row)


@router.put('/v1/checks/{check_id}/review')
def put_review(check_id: str, body: ReviewInput, db: Session = Depends(get_db),
               principal: Principal = Depends(operator)):
    check = scoped_check(db, check_id, principal)
    sampled = selected_for_random_audit(check_id)
    if body.selection_reason == 'random_audit' and not sampled:
        raise HTTPException(422, 'Check was not selected for random audit')
    row = db.get(CheckReview, check_id)
    if row is None:
        row = CheckReview(check_id=check_id, tenant_id=principal.tenant_id)
        db.add(row)
    row.identity_truth = body.identity_truth
    row.cheating_judgement = body.cheating_judgement
    row.selection_reason = 'random_audit' if sampled else body.selection_reason
    row.notes = body.notes
    row.reviewer = 'operator:' + principal.key_id
    row.updated_at = datetime.now(timezone.utc)
    feedback = db.scalar(select(VerificationFeedback).where(VerificationFeedback.event_id == check.event_id))
    if body.identity_truth == 'unknown':
        if feedback is not None:
            db.delete(feedback)
    elif feedback is None:
        db.add(VerificationFeedback(event_id=check.event_id, is_genuine=body.identity_truth == 'genuine',
                                    reviewer=row.reviewer, notes=body.notes))
    else:
        feedback.is_genuine = body.identity_truth == 'genuine'
        feedback.reviewer = row.reviewer
        feedback.notes = body.notes
    audit(db, principal, 'integrity.reviewed', check_id,
          details=f'{body.identity_truth}/{body.cheating_judgement}/{row.selection_reason}')
    db.commit()
    db.refresh(row)
    return review_output(row)


def check_query(principal, person_id=None, session_id=None, start=None, end=None):
    query = select(IntegrityCheck).where(IntegrityCheck.tenant_id == principal.tenant_id)
    if person_id:
        query = query.where(IntegrityCheck.person_id == person_id)
    if session_id:
        query = query.where(IntegrityCheck.session_id == session_id)
    if start:
        query = query.where(IntegrityCheck.created_at >= start)
    if end:
        query = query.where(IntegrityCheck.created_at <= end)
    return query


@router.post('/v1/checks')
async def submit_check(request: Request, person_id: str = Form(...),
                       session_id: str = Form(..., min_length=1, max_length=100),
                       request_id: str = Form(..., min_length=1, max_length=100), consent: bool = Form(...),
                       face_file: UploadFile = File(...), voice_file: UploadFile = File(...),
                       principal: Principal = Depends(authenticate), db: Session = Depends(get_db)):
    from . import main
    person = get_person(db, person_id, principal)
    if not consent:
        raise HTTPException(422, 'Consent required')
    for modality in ('face', 'voice'):
        if not any(sample.modality == modality for sample in person.samples):
            raise HTTPException(409, 'Employee needs face and voice enrollment')
    face = await main.read_upload(face_file, {'image/jpeg', 'image/png', 'image/webp'})
    voice = await main.read_upload(voice_file, {'audio/wav', 'audio/x-wav', 'audio/wave'})
    hashes = (sha256(face), sha256(voice))
    fingerprint = hashlib.sha256(json.dumps([person_id, session_id, *hashes]).encode()).hexdigest()
    previous = db.scalar(select(IntegrityCheck).where(IntegrityCheck.tenant_id == principal.tenant_id,
                                                     IntegrityCheck.request_id == request_id))
    if previous:
        if previous.fingerprint != fingerprint:
            raise HTTPException(409, 'request_id already used with different employee/session/media')
        return previous.result
    row = IntegrityCheck(tenant_id=principal.tenant_id, person_id=person_id, session_id=session_id,
                         request_id=request_id, fingerprint=fingerprint, face_sha256=hashes[0], voice_sha256=hashes[1])
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Concurrent request; retry with the same request_id') from exc
    uploads = [UploadFile(file=io.BytesIO(data), headers=Headers({'content-type': item.content_type}))
               for data, item in ((face, face_file), (voice, voice_file))]
    outcome = await main.perform_verification(person_id, session_id, *uploads, db, principal, capture_errors=True)
    capabilities = await run_in_threadpool(request.app.state.inspect_integrity, face, voice)
    codes = list(dict.fromkeys(outcome.reasons))
    for capability, reason in (('face_pad', 'face_spoof_suspected'), ('audio_spoof', 'audio_spoof_suspected'),
                               ('speaker_consistency', 'multiple_speakers_suspected')):
        if capabilities.get(capability, {}).get('status') == 'failed':
            codes.append(reason)
    reused = db.scalar(select(IntegrityCheck.id).where(
        IntegrityCheck.tenant_id == principal.tenant_id, IntegrityCheck.person_id == person_id,
        IntegrityCheck.session_id == session_id, IntegrityCheck.id != row.id,
        IntegrityCheck.face_sha256 == hashes[0], IntegrityCheck.voice_sha256 == hashes[1]))
    if reused:
        codes.append('capture_reused')
    suspicious_codes = {'face_mismatch', 'voice_mismatch', 'multiple_faces', 'face_spoof_suspected',
                        'audio_spoof_suspected', 'multiple_speakers_suspected', 'capture_reused'}
    complete = all(capabilities.get(key, {}).get('status') in {'passed', 'failed'}
                   for key in ('face_pad', 'audio_spoof', 'speaker_consistency'))
    status = 'suspicious' if suspicious_codes.intersection(codes) else 'inconclusive' if codes or not complete else 'verified'
    row.event_id, row.integrity_status = outcome.event_id, status
    evidence_status = 'not_retained'
    if status == 'suspicious':
        saved = 0
        for modality, payload, upload in (('face', face, face_file), ('voice', voice, voice_file)):
            try:
                key = await run_in_threadpool(main.object_store.put_evidence, principal.tenant_id, row.id,
                                              modality, payload, upload.content_type)
                db.add(CheckEvidence(check_id=row.id, modality=modality, object_key=key,
                                     content_type=upload.content_type, sha256=sha256(payload), size_bytes=len(payload)))
                saved += 1
                EVIDENCE.labels(outcome='success').inc()
            except Exception:
                EVIDENCE.labels(outcome='failure').inc()
                logging.getLogger(__name__).warning('Evidence storage unavailable check=%s modality=%s', row.id, modality)
        evidence_status = 'stored' if saved == 2 else 'partial' if saved else 'unavailable'
    result = {
        'check_id': row.id, 'tenant_id': principal.tenant_id, 'event_id': outcome.event_id, 'employee_id': person.id,
        'employee_code': person.external_ref or person.external_id, 'employee_name': person.display_name,
        'session_id': session_id, 'request_id': request_id, 'checked_at': row.created_at.isoformat(),
        'integrity_status': status, 'status_label': {'verified': 'Danh tính khớp, chưa phát hiện dấu hiệu nghi vấn',
            'suspicious': 'Phát hiện dấu hiệu nghi vấn', 'inconclusive': 'Chưa đủ thông tin để kết luận'}[status],
        'face_match': outcome.face_score is not None and outcome.face_score >= outcome.thresholds['face'],
        'voice_match': outcome.voice_score is not None and outcome.voice_score >= outcome.thresholds['voice'],
        'face_score': outcome.face_score, 'voice_score': outcome.voice_score,
        'reason_codes': codes, 'reason_labels': [LABELS.get(code, code) for code in codes],
        'capabilities': capabilities, 'model_version': outcome.model_version,
        'latency_ms': outcome.latency_ms, 'evidence_status': evidence_status,
    }
    row.result = result
    tenant = db.get(Tenant, principal.tenant_id)
    if tenant.webhook_url:
        db.add(WebhookDelivery(tenant_id=principal.tenant_id, payload={'type': 'integrity.checked', 'data': result}))
    audit(db, principal, 'integrity.checked', row.id)
    db.commit()
    CHECKS.labels(status=status).inc()
    return result


@router.get('/v1/checks')
def list_checks(person_id: str | None = None, session_id: str | None = None,
                start: datetime | None = None, end: datetime | None = None, limit: int = 100, offset: int = 0,
                db: Session = Depends(get_db), principal: Principal = Depends(authenticate)):
    if person_id:
        get_person(db, person_id, principal)
    query = check_query(principal, person_id, session_id, start, end)
    count = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(IntegrityCheck.created_at.desc(), IntegrityCheck.id)
                      .offset(max(0, offset)).limit(max(1, min(500, limit))))
    return {'total': count, 'items': [row.result for row in rows]}


@router.get('/v1/checks/{check_id}')
def check_result(check_id: str, db: Session = Depends(get_db), principal: Principal = Depends(authenticate)):
    return scoped_check(db, check_id, principal).result


@router.get('/v1/checks/{check_id}/evidence/{modality}')
def evidence(check_id: str, modality: str, db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    from . import main
    scoped_check(db, check_id, principal)
    item = db.scalar(select(CheckEvidence).where(CheckEvidence.check_id == check_id, CheckEvidence.modality == modality))
    if item is None:
        raise HTTPException(404, 'Evidence not retained')
    try:
        payload, _ = main.object_store.get(item.object_key)
    except Exception as exc:
        raise HTTPException(503, 'Evidence temporarily unavailable') from exc
    if sha256(payload) != item.sha256:
        raise HTTPException(503, 'Evidence checksum mismatch')
    audit(db, principal, 'evidence.read', check_id)
    db.commit()
    return Response(payload, media_type=item.content_type, headers={'Cache-Control': 'no-store',
                    'X-Content-Type-Options': 'nosniff'})
