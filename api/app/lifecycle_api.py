"""Platform-only orchestration endpoints consumed by the existing Airflow DAGs."""
import json
import math
from pathlib import Path
from typing import Literal

import mlflow
from fastapi import APIRouter, Depends, HTTPException
from mlflow import MlflowClient
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from pipeline.drift_decision import performance
from pipeline.modality_training import paired_gate, register_policy

from .auth import Principal, platform
from .db import get_db
from .lifecycle_service import (
    claim_training,
    configuration,
    observation_dict,
    run_monitoring,
    tick_rollouts,
)
from .model_lifecycle import audit_transition, rollback_champion, start_challenger
from .models import (
    LifecycleAudit,
    ModalityDeployment,
    ModalityMonitorState,
    ModalityObservation,
)
from .template_lifecycle import rollback_template

router = APIRouter(prefix='/v1/admin/lifecycle', dependencies=[Depends(platform)])
Modality = Literal['face', 'voice']


@router.get('/monitoring-evidence')
def monitoring_evidence(db: Session = Depends(get_db)):
    """Export bounded scalar/label snapshots; query vectors remain retention-controlled in DB."""
    result = []
    for state in db.scalars(select(ModalityMonitorState)):
        ids = state.report.get('current_ids', [])
        observations = list(db.scalars(select(ModalityObservation).where(ModalityObservation.id.in_(ids))))
        result.append({'tenant_id': state.tenant_id, 'modality': state.modality,
                       'model_version': state.model_version, 'window_id': state.report.get('current_window'),
                       'reference': [{k: v for k, v in r.items() if k not in {'embedding', 'truth', 'random_audit'}}
                                     for r in state.reference],
                       'inputs': [{'id': r.id, 'encoder': r.encoder, 'score': r.score,
                                   'threshold': r.threshold, 'quality': r.quality,
                                   'template_version': r.template_version, 'template_age_days': r.template_age_days}
                                  for r in observations],
                       'labels': [{'id': r.id, 'truth': r.truth, 'random_audit': r.random_audit}
                                  for r in observations if r.truth is not None]})
    return result


@router.get('/state')
def deployment_state(db: Session = Depends(get_db)):
    from sqlalchemy import func
    result = []
    for row in db.scalars(select(ModalityDeployment)):
        samples = db.scalar(select(func.count()).select_from(ModalityObservation).where(
            ModalityObservation.deployment_id == row.deployment_id,
            ModalityObservation.created_at >= row.stage_started_at))
        rollbacks = db.scalar(select(func.count()).select_from(LifecycleAudit).where(
            LifecycleAudit.modality == row.modality, LifecycleAudit.state.in_(['FAILED_CANARY', 'ROLLED_BACK'])))
        result.append({'modality': row.modality, 'state': row.state, 'traffic_percent': row.traffic_percent,
                       'samples': samples, 'rollback_count': rollbacks,
                       'evidence': row.evidence,
                       'champion_version': row.champion_version, 'challenger_version': row.challenger_version})
    return result


def context():
    from .main import settings
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    return settings, MlflowClient(tracking_uri=settings.mlflow_tracking_uri)


def lock(db):
    if db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(5012030)'))


def missing_champion(exc):
    code = getattr(exc, 'error_code', None)
    # MLflow SQL/REST and file stores use different codes for an absent alias.
    return code == 'RESOURCE_DOES_NOT_EXIST' or (
        code == 'INVALID_PARAMETER_VALUE' and 'Registered model alias champion not found.' in str(exc))


@router.post('/bootstrap')
def bootstrap(db: Session = Depends(get_db)):
    from .main import registry
    settings, client = context()
    lock(db)
    result = {}
    for modality in ('face', 'voice'):
        row = db.get(ModalityDeployment, modality)
        if row is None:
            if registry.current.version == 'local-default':
                raise HTTPException(409, 'A registered incumbent is required for migration')
            threshold = getattr(registry.current, modality + '_threshold')
            name = modality + '-verification'
            try:
                incumbent = client.get_model_version_by_alias(name, 'champion')
            except Exception as exc:
                if not missing_champion(exc):
                    raise
                version = register_policy(modality, threshold, {}, {}, {
                    'migration_from': settings.mlflow_model_name + ':' + registry.current.version,
                    'model_family': 'cosine-threshold-policy'})
                client.set_registered_model_alias(name, 'champion', version)
            else:
                version = str(incumbent.version)
                threshold = float(client.get_run(incumbent.run_id).data.params['threshold'])
            row = ModalityDeployment(modality=modality, registry_name=name,
                                      champion_version=version, champion_threshold=threshold)
            db.add(row)
            db.flush()
        result[modality] = row.champion_version
    db.commit()
    return result


@router.post('/monitor')
def monitor(db: Session = Depends(get_db)):
    from .main import settings
    lock(db)
    report = run_monitoring(db, settings)
    report['evidence'] = monitoring_evidence(db)
    db.commit()
    return report


class ReferenceRequest(BaseModel):
    tenant_id: str
    reason: str = Field(min_length=10, max_length=500)


@router.post('/{modality}/reference')
def establish_reference(modality: Modality, body: ReferenceRequest, db: Session = Depends(get_db),
                        principal: Principal = Depends(platform)):
    from .model_lifecycle import ACTIVE_STATES
    from .models import utcnow

    settings, _ = context()
    lock(db)
    deployment = db.scalar(select(ModalityDeployment).where(ModalityDeployment.modality == modality).with_for_update())
    if deployment is None or deployment.state in ACTIVE_STATES:
        raise HTTPException(409, 'A stable champion is required to establish a reference')
    _, config, _, _ = configuration(settings.lifecycle_config_path)
    rows = list(db.scalars(select(ModalityObservation).where(
        ModalityObservation.tenant_id == body.tenant_id, ModalityObservation.modality == modality,
        ModalityObservation.model_version == deployment.champion_version
    ).order_by(ModalityObservation.created_at.desc(), ModalityObservation.id.desc()).limit(config.min_samples)))
    reference = [observation_dict(r) for r in reversed(rows)]
    metrics = performance(reference, config)
    if (len(reference) < config.min_samples or any(r['embedding'] is None for r in reference)
            or len({r['encoder'] for r in reference}) != 1 or metrics['status'] != 'READY'
            or metrics['fmr'] > config.max_fmr or metrics['fnmr'] > config.max_fnmr):
        raise HTTPException(409, 'A complete retained, independently labelled healthy reference is required')
    key = (body.tenant_id, modality, deployment.champion_version)
    state = db.get(ModalityMonitorState, key)
    if state is None:
        state = ModalityMonitorState(tenant_id=key[0], modality=key[1], model_version=key[2])
        db.add(state)
    state.reference, state.report, state.updated_at = reference, {}, utcnow()
    db.add(LifecycleAudit(modality=modality, deployment_id=deployment.deployment_id, state='REFERENCE_RESET',
        evidence={'tenant_id': body.tenant_id, 'reason': body.reason, 'actor': principal.key_id,
                  'reference_ids': [r['id'] for r in reference], 'metrics': metrics}))
    db.commit()
    return {'modality': modality, 'reference_samples': len(reference)}


@router.post('/tick')
def tick(db: Session = Depends(get_db)):
    settings, client = context()
    lock(db)
    result = tick_rollouts(db, settings, client)
    db.commit()
    return result


class TrainingRequest(BaseModel):
    window_id: str


@router.post('/{modality}/claim')
def claim(modality: Modality, body: TrainingRequest, db: Session = Depends(get_db)):
    try:
        row = claim_training(db, modality, body.window_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return {'modality': row.modality, 'state': row.state}


class CandidateRequest(TrainingRequest):
    version: str


@router.post('/{modality}/candidate')
def candidate(modality: Modality, body: CandidateRequest, db: Session = Depends(get_db)):
    settings, client = context()
    row = db.scalar(select(ModalityDeployment).where(ModalityDeployment.modality == modality).with_for_update())
    if (row is not None and row.challenger_version == body.version and
            row.evidence.get('training_window') == body.window_id and row.state != 'TRAINING'):
        return {'state': row.state, 'offline': row.evidence.get('offline', {})}
    if row is None or row.state != 'TRAINING' or row.evidence.get('training_window') != body.window_id:
        raise HTTPException(409, 'No matching training intent')
    version = client.get_model_version(row.registry_name, body.version)
    run = client.get_run(version.run_id)
    if run.data.params.get('training_window') != body.window_id or run.data.params.get('modality') != modality:
        raise HTTPException(409, 'Candidate provenance does not match the training intent')
    threshold = float(run.data.params['threshold'])
    if not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise HTTPException(422, 'Invalid policy threshold')
    policy_path = client.download_artifacts(version.run_id, 'policy/artifacts/policy.json')
    policy = json.loads(Path(policy_path).read_text(encoding='utf-8'))
    if policy.get('threshold') != threshold or policy.get('modality') != modality:
        raise HTTPException(409, 'Registered artifact disagrees with policy metadata')
    audit_transition(db, row, 'CANDIDATE', {'candidate_version': body.version})
    audit_transition(db, row, 'OFFLINE_EVALUATION', {'candidate_version': body.version})
    path = client.download_artifacts(version.run_id, 'evaluation/paired-scores.json')
    scores = json.loads(Path(path).read_text(encoding='utf-8'))
    _, _, limits, _ = configuration(settings.lifecycle_config_path)
    result = paired_gate(scores['positive'], scores['negative'], row.champion_threshold,
                         threshold, run.data.metrics, limits)
    result['dataset_version'] = run.data.params['dataset_version']
    passed = result['passed']
    if passed:
        client.set_registered_model_alias(row.registry_name, 'challenger', body.version)
        row.state = 'CHAMPION'
        start_challenger(db, row, body.version, threshold, result)
    else:
        row.challenger_version, row.challenger_threshold = body.version, threshold
        audit_transition(db, row, 'REJECTED', {'offline': result})
    client.set_model_version_tag(row.registry_name, body.version, 'lifecycle_status', row.state)
    db.commit()
    return {'state': row.state, 'offline': result}


@router.post('/{modality}/training-failed')
def training_failed(modality: Modality, body: TrainingRequest, db: Session = Depends(get_db)):
    row = db.scalar(select(ModalityDeployment).where(ModalityDeployment.modality == modality).with_for_update())
    if row is not None and row.state == 'TRAINING' and row.evidence.get('training_window') == body.window_id:
        audit_transition(db, row, 'REJECTED', {'failure': {'metric': 'training_task_failed', 'window': body.window_id}})
        db.commit()
    return {'state': row.state if row else 'uninitialized'}


@router.post('/{modality}/rollback')
def rollback(modality: Modality, db: Session = Depends(get_db)):
    _, client = context()
    row = db.scalar(select(ModalityDeployment).where(ModalityDeployment.modality == modality).with_for_update())
    if row is None:
        raise HTTPException(404, 'Lifecycle not initialized')
    try:
        rollback_champion(db, row, client)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return {'state': row.state, 'champion': row.champion_version}


@router.post('/templates/{person_id}/{modality}/rollback')
def template_rollback(person_id: str, modality: Modality, db: Session = Depends(get_db)):
    try:
        result = rollback_template(db, person_id, modality)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.commit()
    return result
