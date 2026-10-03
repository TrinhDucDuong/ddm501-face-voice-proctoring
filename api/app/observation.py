"""Capture telemetry without exposing embeddings through response schemas."""
import hashlib
import math
import time
from datetime import timezone

from sqlalchemy import select

from .model_lifecycle import reject, route
from .models import (
    ActiveTemplate,
    ModalityDeployment,
    ModalityObservation,
    TemplateVersion,
    utcnow,
)


def templates(db, person, modality):
    active = db.get(ActiveTemplate, (person.id, modality))
    if active:
        version = db.get(TemplateVersion, active.version_id)
        return version.embeddings, version.id, version.created_at
    samples = [s for s in person.samples if s.modality == modality]
    digest = hashlib.sha256('/'.join(sorted(s.id for s in samples)).encode()).hexdigest()
    return [s.embedding for s in samples], digest, max((s.created_at for s in samples), default=utcnow())


def policy(db, modality, cohort_key, default_threshold, default_version, score):
    row = db.scalar(select(ModalityDeployment).where(ModalityDeployment.modality == modality))
    if row is None:
        return {'threshold': default_threshold, 'version': default_version,
                'champion_threshold': default_threshold, 'champion_version': default_version,
                'candidate': False, 'shadow': False, 'stage': 'CHAMPION', 'latency': 0.}
    started = time.perf_counter()
    if row.state in {'SHADOW', 'CANARY'} and (row.challenger_threshold is None or
            not math.isfinite(row.challenger_threshold) or not -1 <= row.challenger_threshold <= 1):
        reject(db, row, 'invalid_policy', None, 'finite threshold in [-1,1]')
    selected = route(row, cohort_key)
    _ = score >= selected['threshold']
    selected.update(champion_threshold=row.champion_threshold, champion_version=row.champion_version,
                    deployment_id=row.deployment_id, latency=(time.perf_counter() - started) * 1000)
    if selected['shadow']:
        started = time.perf_counter()
        _ = score >= row.challenger_threshold
        selected.update(challenger_version=row.challenger_version,
                        challenger_threshold=row.challenger_threshold,
                        challenger_latency=(time.perf_counter() - started) * 1000)
    return selected


def record(db, event, person, modality, result, score, media_hash, template, selected, retain):
    created = template[2]
    created = created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created
    db.add(ModalityObservation(event_id=event.id, tenant_id=person.tenant_id, person_id=person.id,
        modality=modality, model_version=selected['champion_version'], encoder=result.backend,
        template_version=template[1], template_age_days=max(0, (utcnow() - created).total_seconds() / 86400),
        score=score, threshold=selected['champion_threshold'], quality=result.quality_features or {'quality': result.quality},
        embedding=result.embedding.tolist() if retain else None, media_sha256=media_hash,
        deployment_id=selected.get('deployment_id'), stage=selected['stage'],
        served_candidate=selected['candidate'], challenger_score=score if selected['shadow'] else None,
        challenger_threshold=selected.get('challenger_threshold'),
        challenger_version=selected.get('challenger_version'), policy_latency_ms=selected['latency'],
        challenger_latency_ms=selected.get('challenger_latency')))
