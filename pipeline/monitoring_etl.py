"""Reproducible unlabeled drift and human-audited performance decisions."""
from __future__ import annotations

import math

import numpy as np

FEATURES = ('face_score', 'voice_score', 'face_quality', 'voice_quality', 'risk_score')


def psi(reference: list[float], current: list[float], bins: int = 10) -> float:
    left, right = np.asarray(reference, dtype=float), np.asarray(current, dtype=float)
    left, right = left[np.isfinite(left)], right[np.isfinite(right)]
    if min(len(left), len(right)) < bins:
        return math.nan
    edges = np.unique(np.quantile(left, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        spread = max(abs(float(left[0])) * .01, .001)
        edges = np.linspace(float(left[0]) - spread, float(left[0]) + spread, bins + 1)
    edges[0], edges[-1] = -np.inf, np.inf
    expected = np.clip(np.histogram(left, bins=edges)[0] / len(left), 1e-6, None)
    actual = np.clip(np.histogram(right, bins=edges)[0] / len(right), 1e-6, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def performance_on_random_audit(labels: list[dict], min_per_class: int = 5) -> dict:
    audited = [row for row in labels if row['selection_reason'] == 'random_audit'
               and row.get('is_genuine') is not None]
    impostors = [row for row in audited if not row['is_genuine']]
    genuine = [row for row in audited if row['is_genuine']]
    if min(len(impostors), len(genuine)) < min_per_class:
        return {'status': 'insufficient_random_audits', 'sample_count': len(audited),
                'genuine_count': len(genuine), 'impostor_count': len(impostors)}
    return {'status': 'ready', 'sample_count': len(audited),
            'genuine_count': len(genuine), 'impostor_count': len(impostors),
            'far': sum(bool(row['accepted']) for row in impostors) / len(impostors),
            'frr': sum(not bool(row['accepted']) for row in genuine) / len(genuine),
            'accuracy': sum(bool(row['accepted']) == bool(row['is_genuine']) for row in audited) / len(audited)}


def assess_window(reference: list[dict], current: list[dict], labels: list[dict], *,
                  previous_drift: bool, min_samples: int = 30, psi_threshold: float = .2,
                  training_eligible: bool = False) -> dict:
    performance = performance_on_random_audit(labels)
    if min(len(reference), len(current)) < min_samples:
        return {'status': 'insufficient_data', 'reference_count': len(reference),
                'current_count': len(current), 'performance': performance, 'psi': {},
                'trigger_training': False, 'recommendation': 'collect_more_data'}
    calculated = {feature: psi([row[feature] for row in reference], [row[feature] for row in current])
                  for feature in FEATURES}
    drifted = [feature for feature, value in calculated.items()
               if math.isfinite(value) and value > psi_threshold]
    values = {feature: value if math.isfinite(value) else None
              for feature, value in calculated.items()}
    degraded = performance['status'] == 'ready' and max(performance['far'], performance['frr']) > .2
    trigger = training_eligible and (bool(drifted) and previous_drift or degraded)
    return {'status': 'drift_detected' if drifted else 'performance_degraded' if degraded else 'stable',
            'reference_count': len(reference), 'current_count': len(current), 'psi': values,
            'drifted_features': drifted, 'performance': performance,
            'training_eligible': training_eligible, 'trigger_training': trigger,
            'recommendation': 'train_candidate' if trigger else 'investigate_drift' if drifted
                              else 'review_performance' if degraded else 'none'}
