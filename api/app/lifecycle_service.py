"""Existing Airflow jobs call this service to use the serving DB's lifecycle state."""
import hashlib
import json
from datetime import timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, func, select, update

from pipeline.drift_decision import DriftConfig, evaluate

from .model_lifecycle import (
    ACTIVE_STATES,
    RolloutConfig,
    advance,
    audit_transition,
    reconcile_registry,
)
from .models import (
    ModalityDeployment,
    ModalityMonitorState,
    ModalityObservation,
    Person,
    utcnow,
)
from .template_lifecycle import TemplateConfig, update_template


def configuration(path):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    return config, DriftConfig(**config['drift']), RolloutConfig(**config['rollout']), TemplateConfig(**config['template'])


def observation_dict(row):
    return {**{column.name: getattr(row, column.name) for column in ModalityObservation.__table__.columns
               if column.name != 'created_at'}, 'observed_at': row.created_at.isoformat()}


def run_monitoring(db, settings):
    config, drift, _, template_config = configuration(settings.lifecycle_config_path)
    now = utcnow()
    # Bound retention of query vectors independently from audit metadata.
    db.execute(update(ModalityObservation).where(
        ModalityObservation.created_at < now - timedelta(days=settings.monitoring_embedding_retention_days)
    ).values(embedding=None))
    db.execute(delete(ModalityObservation).where(
        ModalityObservation.created_at < now - timedelta(days=config['observation_retention_days'])))
    for stored in db.scalars(select(ModalityMonitorState)):
        retained = {r.id: r for r in db.scalars(select(ModalityObservation).where(
            ModalityObservation.id.in_([r['id'] for r in stored.reference])))}
        stored.reference = [{**r, 'embedding': retained[r['id']].embedding if r['id'] in retained else None}
                            for r in stored.reference]
    groups = db.execute(select(ModalityObservation.tenant_id, ModalityObservation.modality,
                                ModalityObservation.model_version).distinct()).all()
    reports = []
    for tenant_id, modality, version in groups:
        rows = list(db.scalars(select(ModalityObservation).where(
            ModalityObservation.tenant_id == tenant_id, ModalityObservation.modality == modality,
            ModalityObservation.model_version == version).order_by(
                ModalityObservation.created_at.desc(), ModalityObservation.id.desc()).limit(2 * drift.min_samples)))
        rows = [observation_dict(r) for r in reversed(rows)]
        current = rows[-drift.min_samples:]
        state = db.get(ModalityMonitorState, (tenant_id, modality, version))
        if state is None:
            state = ModalityMonitorState(tenant_id=tenant_id, modality=modality, model_version=version,
                                         reference=[], report={})
            db.add(state)
        if not state.reference and len(rows) >= 2 * drift.min_samples:
            state.reference = rows[:-drift.min_samples]
        reference_end = max((r.get('observed_at', '') for r in state.reference), default='')
        if reference_end:
            current = [r for r in rows if r['observed_at'] > reference_end][-drift.min_samples:]
        if state.reference:
            labels = {r.id: r for r in db.scalars(select(ModalityObservation).where(
                ModalityObservation.id.in_([r['id'] for r in state.reference])))}
            state.reference = [{**r, 'truth': labels[r['id']].truth,
                                'embedding': labels[r['id']].embedding,
                                'random_audit': labels[r['id']].random_audit}
                               if r['id'] in labels else {**r, 'embedding': None} for r in state.reference]
        # Labels changing alone cannot manufacture a new feature window.
        window_id = hashlib.sha256('/'.join(r['id'] for r in current).encode()).hexdigest()
        previous = state.report
        if previous and previous['current_window'] == window_id:
            previous = {**previous, 'current_window': ''}
        report = evaluate(state.reference, current, modality, version, window_id, previous, drift)
        report = {**report, 'tenant_id': tenant_id, 'calculated_at': now.isoformat(), 'trigger_training': False}
        deployment = db.get(ModalityDeployment, modality)
        latest_version = deployment.champion_version if deployment else None
        if (deployment is not None and version == latest_version and deployment.state not in ACTIVE_STATES
                and report['decision'] == 'TEMPLATE_UPDATE_REQUIRED'
                and report['persistence'].get('template_windows', 0) >= drift.min_consecutive_windows):
            outcomes = []
            for person_id in sorted({r['person_id'] for r in current if r['template_age_days'] > drift.age_boundaries[-1]}):
                employee_rows = [observation_dict(r) for r in db.scalars(select(ModalityObservation).where(
                    ModalityObservation.person_id == person_id, ModalityObservation.modality == modality,
                    ModalityObservation.model_version == version, ModalityObservation.truth.is_not(None)
                ).order_by(ModalityObservation.created_at.desc()).limit(500))]
                if employee_rows:
                    outcomes.append(update_template(db, person_id, modality, employee_rows,
                                                      employee_rows[0]['threshold'], template_config))
            report['template_actions'] = outcomes
        last = state.last_action_at
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        eligible = (tenant_id == 'demo' and settings.continuous_training_enabled and deployment is not None
                    and version == latest_version and deployment.state not in ACTIVE_STATES
                    and report['decision'] == 'RETRAIN_REQUIRED'
                    and (last is None or now - last >= timedelta(hours=config['cooldown_hours'])))
        if eligible:
            new_labels = db.scalar(select(func.count()).select_from(ModalityObservation).where(
                ModalityObservation.tenant_id == tenant_id, ModalityObservation.modality == modality,
                ModalityObservation.random_audit.is_(True), ModalityObservation.truth.is_not(None),
                ModalityObservation.created_at > (last or now - timedelta(days=config['observation_retention_days']))))
            identities = db.scalar(select(func.count()).select_from(Person).where(Person.tenant_id == 'demo', Person.active.is_(True)))
            report['trigger_training'] = new_labels >= config['minimum_new_reviewed_samples'] and identities >= 10
        state.report, state.updated_at = report, now
        reports.append(report)
    return {'calculated_at': now.isoformat(), 'modalities': reports,
            'tenants': [], 'trigger_training': any(r['trigger_training'] for r in reports)}


def tick_rollouts(db, settings, client):
    config, _, rollout, _ = configuration(settings.lifecycle_config_path)
    result = []
    for row in db.scalars(select(ModalityDeployment).with_for_update()):
        if row.state in {'SHADOW', 'CANARY'}:
            query = select(ModalityObservation).where(
                ModalityObservation.deployment_id == row.deployment_id,
                ModalityObservation.modality == row.modality,
                ModalityObservation.created_at >= row.stage_started_at,
                ModalityObservation.stage == row.state)
            if row.state == 'CANARY':
                query = query.where(ModalityObservation.served_candidate.is_(True))
            observations = [observation_dict(o) for o in db.scalars(query.order_by(
                ModalityObservation.created_at.desc()).limit(config['max_observations_per_rollout']))]
            advance(db, row, observations, rollout)
    db.commit()
    # Persist PROMOTING before touching the external registry. Serving remains pinned
    # to the previous policy until aliases are reconciled and this transaction commits.
    for row in db.scalars(select(ModalityDeployment).with_for_update()):
        reconcile_registry(db, row, client)
        result.append({'modality': row.modality, 'state': row.state, 'stage': row.traffic_percent,
                       'champion': row.champion_version, 'challenger': row.challenger_version})
    return result


def claim_training(db, modality, window_id):
    row = db.scalar(select(ModalityDeployment).where(ModalityDeployment.modality == modality).with_for_update())
    if row is None:
        raise ValueError('Initialize modality registry before requesting training')
    if row.state == 'TRAINING' and row.evidence.get('training_window') == window_id:
        return row
    if row.evidence.get('training_window') == window_id:
        raise ValueError('This training window was already attempted; wait for fresh evidence')
    state = db.get(ModalityMonitorState, ('demo', modality, row.champion_version))
    if row.state in ACTIVE_STATES or state is None or not state.report.get('trigger_training') or state.report['current_window'] != window_id:
        raise ValueError('No eligible, current retraining decision for this modality')
    audit_transition(db, row, 'TRAINING', {'training_window': window_id})
    state.last_action_at = utcnow()
    return row
