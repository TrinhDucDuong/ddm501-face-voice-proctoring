"""Durable threshold-policy rollout; MLflow remains the model registry."""
import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import timezone

import numpy as np

from pipeline.drift_decision import DriftConfig, performance

from .models import LifecycleAudit, utcnow

ACTIVE_STATES = {'TRAINING', 'CANDIDATE', 'OFFLINE_EVALUATION', 'CHALLENGER', 'SHADOW', 'CANARY', 'PROMOTING'}


@dataclass(frozen=True)
class RolloutConfig:
    stages: tuple = (5, 10, 25, 50, 100)
    min_samples: int = 1000
    min_seconds: int = 3600
    min_labels_per_class: int = 30
    max_fmr: float = .01
    max_fnmr: float = .05
    max_security_regression: float = 0.
    max_fnmr_regression: float = .005
    max_policy_latency_ms: float = 10.
    max_disagreement: float = .1
    minimum_cohort_samples: int = 20

    def __post_init__(self):
        if (not self.stages or self.stages[-1] != 100 or any(not 0 < x <= 100 for x in self.stages)
                or list(self.stages) != sorted(set(self.stages)) or self.min_samples < 1
                or self.min_seconds < 0 or self.min_labels_per_class < 1):
            raise ValueError('Invalid rollout configuration')
        rates = (self.max_fmr, self.max_fnmr, self.max_security_regression,
                 self.max_fnmr_regression, self.max_disagreement)
        if (any(not math.isfinite(v) or not 0 <= v <= 1 for v in rates)
                or not 0 < self.max_fmr < 1 or self.minimum_cohort_samples < 1
                or not math.isfinite(self.max_policy_latency_ms) or self.max_policy_latency_ms <= 0):
            raise ValueError('Invalid rollout safety limits')


def audit_transition(db, row, state, evidence):
    row.state = state
    row.revision += 1
    row.updated_at = utcnow()
    row.evidence = {**(row.evidence or {}), **evidence}
    db.add(LifecycleAudit(modality=row.modality, deployment_id=row.deployment_id,
                          state=state, evidence=evidence))


def start_challenger(db, row, version, threshold, offline):
    if row.state in ACTIVE_STATES:
        raise ValueError('A modality lifecycle is already active')
    if not offline.get('passed') or not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise ValueError('Offline gate did not pass')
    if version == row.champion_version:
        raise ValueError('Challenger must differ from champion')
    row.deployment_id = str(uuid.uuid4())
    row.challenger_version, row.challenger_threshold = version, threshold
    row.stage_index, row.traffic_percent = 0, 0
    row.stage_started_at = utcnow()
    audit_transition(db, row, 'CHALLENGER', {'offline': offline})
    audit_transition(db, row, 'SHADOW', {'started_at': row.stage_started_at.isoformat()})


def route(row, cohort_key):
    bucket = int(hashlib.sha256(f'{row.modality}/{row.deployment_id}/{cohort_key}'.encode()).hexdigest()[:16], 16) / 2**64
    canary = row.state == 'CANARY' and bucket * 100 < row.traffic_percent
    return {'threshold': row.challenger_threshold if canary else row.champion_threshold,
            'version': row.challenger_version if canary else row.champion_version,
            'candidate': canary,
            'shadow': row.state in {'SHADOW', 'CANARY'}, 'stage': row.state}


def reject(db, row, metric, observed, threshold):
    failure = {'metric': metric, 'observed': observed, 'threshold': threshold,
               'timestamp': utcnow().isoformat(), 'stage': row.state,
               'traffic_percent': row.traffic_percent, 'model_version': row.challenger_version}
    state = 'FAILED_CANARY' if row.state == 'CANARY' else 'REJECTED'
    row.traffic_percent = 0
    audit_transition(db, row, state, {'failure': failure})


def advance(db, row, observations, config):
    if row.state not in {'SHADOW', 'CANARY'}:
        return
    complete = [o for o in observations if o.get('challenger_score') is not None]
    if not complete:
        return
    candidate = [{**o, 'score': o['challenger_score'], 'threshold': o['challenger_threshold']} for o in complete]
    limits = DriftConfig(min_labels_per_class=config.min_labels_per_class, target_far=config.max_fmr)
    champion_metrics, candidate_metrics = performance(complete, limits), performance(candidate, limits)
    latencies = [o['challenger_latency_ms'] for o in complete if o.get('challenger_latency_ms') is not None]
    p95 = float(np.quantile(latencies, .95)) if latencies else None
    disagreement = float(np.mean([(o['score'] >= o['threshold']) !=
                                 (o['challenger_score'] >= o['challenger_threshold']) for o in complete]))
    row.evidence = {**(row.evidence or {}), 'live': {
        'samples': len(complete), 'champion_metrics': champion_metrics, 'challenger_metrics': candidate_metrics,
        'disagreement': disagreement, 'policy_latency_p95_ms': p95,
        'score_delta_mean': float(np.mean([o['challenger_score'] - o['score'] for o in complete])),
        'policy_latency_delta_mean_ms': float(np.mean([
            o['challenger_latency_ms'] - o.get('policy_latency_ms', 0.) for o in complete
            if o.get('challenger_latency_ms') is not None])) if latencies else None}}
    if p95 is None or not math.isfinite(p95) or p95 > config.max_policy_latency_ms:
        reject(db, row, 'policy_latency_p95_ms', p95, config.max_policy_latency_ms)
        return
    if candidate_metrics['status'] == champion_metrics['status'] == 'READY':
        for metric, absolute, regression in [('fmr', config.max_fmr, config.max_security_regression),
                                              ('fnmr', config.max_fnmr, config.max_fnmr_regression)]:
            limit = min(absolute, champion_metrics[metric] + regression)
            if candidate_metrics[metric] > limit:
                reject(db, row, metric, candidate_metrics[metric], limit)
                return
    else:
        return
    # A pooled metric must not conceal a regression in an input-quality cohort.
    cohort_metrics = {}
    for name, lower, upper in [('low', 0., .4), ('medium', .4, .7), ('high', .7, 1.01)]:
        cohort = [o for o in complete if lower <= o.get('quality', {}).get('quality', .9) < upper]
        if len(cohort) < config.minimum_cohort_samples:
            continue
        baseline = performance(cohort, limits)
        compared = performance([{**o, 'score': o['challenger_score'], 'threshold': o['challenger_threshold']}
                                for o in cohort], limits)
        if baseline['status'] != 'READY' or compared['status'] != 'READY':
            return
        cohort_metrics[name] = compared
        for metric, delta in [('fmr', config.max_security_regression), ('fnmr', config.max_fnmr_regression)]:
            if compared[metric] > baseline[metric] + delta:
                reject(db, row, name + '_' + metric, compared[metric], baseline[metric] + delta)
                return
    if disagreement > config.max_disagreement:
        reject(db, row, 'disagreement', disagreement, config.max_disagreement)
        return
    started = row.stage_started_at.replace(tzinfo=timezone.utc) if row.stage_started_at.tzinfo is None else row.stage_started_at
    if len(complete) < config.min_samples or (utcnow() - started).total_seconds() < config.min_seconds:
        return
    evidence = {'samples': len(complete), 'champion_metrics': champion_metrics,
                'challenger_metrics': candidate_metrics, 'policy_latency_p95_ms': p95,
                'disagreement': disagreement, 'quality_cohorts': cohort_metrics}
    if row.state == 'SHADOW':
        row.stage_index = 0
    elif row.stage_index + 1 < len(config.stages):
        row.stage_index += 1
    else:
        # Durable intent first: external alias operations can safely be retried.
        audit_transition(db, row, 'PROMOTING', evidence)
        row.traffic_percent = 0
        return
    row.traffic_percent = config.stages[row.stage_index]
    row.stage_started_at = utcnow()
    audit_transition(db, row, 'CANARY', evidence)


def reconcile_registry(db, row, client):
    if row.state == 'PROMOTING':
        current = client.get_model_version_by_alias(row.registry_name, 'champion')
        if str(current.version) not in {row.champion_version, row.challenger_version}:
            raise ValueError('Registry champion changed outside this rollout')
        client.set_registered_model_alias(row.registry_name, 'previous_champion', row.champion_version)
        client.set_model_version_tag(row.registry_name, row.champion_version, 'lifecycle_status', 'archived')
        client.set_registered_model_alias(row.registry_name, 'champion', row.challenger_version)
        client.set_model_version_tag(row.registry_name, row.challenger_version, 'lifecycle_status', 'CHAMPION')
        row.previous_version, row.previous_threshold = row.champion_version, row.champion_threshold
        row.champion_version, row.champion_threshold = row.challenger_version, row.challenger_threshold
        row.traffic_percent = 0
        audit_transition(db, row, 'CHAMPION', {'previous_champion': row.previous_version})
    elif row.state in {'REJECTED', 'FAILED_CANARY', 'ROLLED_BACK'} and row.challenger_version:
        client.set_model_version_tag(row.registry_name, row.challenger_version, 'lifecycle_status', row.state)
        client.set_model_version_tag(row.registry_name, row.challenger_version, 'rejection_reason', str(row.evidence))


def rollback_champion(db, row, client):
    if row.state in {'SHADOW', 'CANARY', 'PROMOTING'}:
        client.set_registered_model_alias(row.registry_name, 'champion', row.champion_version)
        reject(db, row, 'operator_rollback', None, None)
        return
    if not row.previous_version:
        raise ValueError('No previous champion')
    displaced = row.champion_version
    client.set_registered_model_alias(row.registry_name, 'champion', row.previous_version)
    client.set_model_version_tag(row.registry_name, row.previous_version, 'lifecycle_status', 'CHAMPION')
    if displaced != row.previous_version:
        client.set_model_version_tag(row.registry_name, displaced, 'lifecycle_status', 'ROLLED_BACK')
    row.champion_version, row.champion_threshold = row.previous_version, row.previous_threshold
    row.traffic_percent = 0
    audit_transition(db, row, 'ROLLED_BACK', {'restored': row.previous_version})


def stop_active_rollouts(db, cause):
    from sqlalchemy import select

    from .models import ModalityDeployment

    for row in db.scalars(select(ModalityDeployment).where(
            ModalityDeployment.state.in_(['SHADOW', 'CANARY'])).with_for_update()):
        reject(db, row, 'serving_system_failure', cause, 'no system failures')
