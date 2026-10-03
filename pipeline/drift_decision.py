"""Modality-specific evidence; statistical drift alone never requests training."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass

import numpy as np

from pipeline.monitoring_etl import psi


@dataclass(frozen=True)
class DriftConfig:
    min_samples: int = 100
    min_labels_per_class: int = 20
    min_consecutive_windows: int = 3
    psi_threshold: float = .2
    embedding_threshold: float = .02
    embedding_max_samples: int = 512
    min_cohort_overlap: float = .8
    max_fmr: float = .01
    max_fnmr: float = .05
    degradation_absolute: float = .02
    degradation_relative: float = .25
    target_far: float = .01
    age_boundaries: tuple = (30, 90, 180, 365)

    def __post_init__(self):
        if (self.min_samples < 10 or self.min_labels_per_class < 1 or self.min_consecutive_windows < 1
                or self.embedding_max_samples < 10 or self.psi_threshold <= 0 or self.embedding_threshold <= 0
                or not 0 < self.min_cohort_overlap <= 1 or not 0 < self.target_far < 1
                or not self.age_boundaries or list(self.age_boundaries) != sorted(set(self.age_boundaries))):
            raise ValueError('Invalid drift configuration')
        rates = (self.max_fmr, self.max_fnmr, self.degradation_absolute)
        positive = (self.psi_threshold, self.embedding_threshold, self.degradation_relative, *self.age_boundaries)
        if (any(not math.isfinite(v) or not 0 <= v <= 1 for v in rates)
                or any(not math.isfinite(v) or v <= 0 for v in positive)):
            raise ValueError('Invalid drift safety limits')


def mmd(reference, current, max_samples=512):
    """Biased squared RBF MMD on unit embeddings; bounded quadratic memory."""
    left, right = np.asarray(reference, dtype=float), np.asarray(current, dtype=float)
    if (left.ndim != 2 or right.ndim != 2 or left.shape[1] != right.shape[1]
            or min(len(left), len(right)) < 1 or not np.isfinite(left).all()
            or not np.isfinite(right).all()):
        raise ValueError('Invalid or incompatible embedding samples')
    left = left[np.linspace(0, len(left) - 1, min(len(left), max_samples), dtype=int)]
    right = right[np.linspace(0, len(right) - 1, min(len(right), max_samples), dtype=int)]
    norms_left, norms_right = np.linalg.norm(left, axis=1), np.linalg.norm(right, axis=1)
    if min(norms_left.min(), norms_right.min()) <= 0:
        raise ValueError('Zero embedding norm')
    left, right = left / norms_left[:, None], right / norms_right[:, None]

    def kernel(a, b):
        # Fixed bandwidth on unit vectors keeps scores comparable between windows.
        return np.exp(-np.maximum(0, 2 - 2 * a @ b.T) / 2)

    return max(0., float(kernel(left, left).mean() + kernel(right, right).mean()
                         - 2 * kernel(left, right).mean()))


def performance(rows, config):
    audited = [row for row in rows if row.get('random_audit') and type(row.get('truth')) is bool
               and np.isfinite(row['score']) and np.isfinite(row['threshold'])]
    genuine = [row for row in audited if row['truth']]
    impostor = [row for row in audited if not row['truth']]
    result = {'genuine_count': len(genuine), 'impostor_count': len(impostor)}
    if min(len(genuine), len(impostor)) < config.min_labels_per_class:
        return {**result, 'status': 'INSUFFICIENT_LABELS'}
    positive = np.array([row['score'] for row in genuine])
    negative = np.array([row['score'] for row in impostor])
    thresholds = np.r_[-np.inf, np.unique(np.r_[positive, negative]), np.inf]
    far = 1 - np.searchsorted(np.sort(negative), thresholds, side='left') / len(negative)
    frr = np.searchsorted(np.sort(positive), thresholds, side='left') / len(positive)
    index = np.argmin(np.abs(far - frr))
    return {**result, 'status': 'READY',
            'fmr': float(np.mean([r['score'] >= r['threshold'] for r in impostor])),
            'fnmr': float(np.mean([r['score'] < r['threshold'] for r in genuine])),
            'eer': float((far[index] + frr[index]) / 2),
            'tar_at_far': float(np.max(1 - frr[far <= config.target_far])),
            'target_far': config.target_far}


def distribution(rows, truth=None):
    values = [row['score'] for row in rows if truth is None or
              row.get('random_audit') and row.get('truth') is truth]
    if not values:
        return {'count': 0}
    margins = [row['score'] - row['threshold'] for row in rows if truth is None or
               row.get('random_audit') and row.get('truth') is truth]
    return {'count': len(values), 'mean': float(np.mean(values)), 'std': float(np.std(values)),
            'quantiles': dict(zip(('p05', 'p50', 'p95'), np.quantile(values, [.05, .5, .95]).tolist(), strict=False)),
            'threshold_margin': float(np.mean(margins))}


def age_summary(rows, config):
    groups = [[] for _ in range(len(config.age_boundaries) + 1)]
    for row in rows:
        age = row.get('template_age_days')
        if age is not None and age >= 0:
            groups[int(np.searchsorted(config.age_boundaries, age, side='left'))].append(row)
    reports = []
    for index, group in enumerate(groups):
        genuine = [row for row in group if row.get('random_audit') and row.get('truth') is True]
        impostor = [row for row in group if row.get('random_audit') and row.get('truth') is False]
        reports.append({'bucket': index, 'sample_count': len(group), 'genuine_count': len(genuine),
                        'genuine_score_mean': float(np.mean([r['score'] for r in genuine])) if genuine else None,
                        'fnmr': float(np.mean([r['score'] < r['threshold'] for r in genuine]))
                        if len(genuine) >= config.min_labels_per_class else None,
                        'fmr': float(np.mean([r['score'] >= r['threshold'] for r in impostor]))
                        if len(impostor) >= config.min_labels_per_class else None,
                        'quality_mean': float(np.mean([r['quality']['quality'] for r in group]))
                        if group else None})
    return reports


def evaluate(reference, current, modality, model_version, window_id, previous=None, config=None):
    config = config or DriftConfig()
    if modality not in ('face', 'voice'):
        raise ValueError('Unknown modality')
    config_version = hashlib.sha256(json.dumps(asdict(config), sort_keys=True).encode()).hexdigest()
    if previous and previous.get('config_version') != config_version:
        previous = None
    if previous and (previous.get('modality'), previous.get('model_version')) != (modality, model_version):
        previous = None
    if previous and previous['current_window'] == window_id:
        return previous
    report = {'modality': modality, 'model_version': model_version, 'config_version': config_version,
              'reference_window': [r['id'] for r in reference], 'current_window': window_id,
              'sample_count': len(current), 'current_ids': [r['id'] for r in current], 'quality': {}, 'embedding': {},
              'verification_score': {}, 'performance': performance(current, config),
              'template_aging': {'detected': False}, 'persistence': {'consecutive_windows': 0},
              'decision': 'INSUFFICIENT_DATA', 'reason': []}
    if min(len(reference), len(current)) < config.min_samples:
        report['reason'] = ['insufficient window samples']
        return report
    encoders = {r.get('encoder') for r in reference + current}
    left_ids, right_ids = {r['person_id'] for r in reference}, {r['person_id'] for r in current}
    overlap = len(left_ids & right_ids) / max(1, len(left_ids | right_ids))
    if len(encoders) != 1 or None in encoders or overlap < config.min_cohort_overlap:
        report['reason'] = ['incompatible encoder or changed identity cohort']
        return report
    common = left_ids & right_ids
    left, right = [r for r in reference if r['person_id'] in common], [r for r in current if r['person_id'] in common]
    quality = {}
    features = set.intersection(*(set(row['quality']) for row in left + right))
    if 'quality' not in features or any(not np.isfinite(r['quality']['quality']) for r in left + right):
        report['reason'] = ['insufficient quality evidence']
        return report
    for feature in features:
        value = psi([r['quality'][feature] for r in left], [r['quality'][feature] for r in right])
        quality[feature] = float(value) if np.isfinite(value) else None
    q_score = max((v for v in quality.values() if v is not None), default=0.)
    report['quality'] = {'drift': q_score > config.psi_threshold, 'score': q_score, 'features': quality}
    embeddings_available = all(r.get('embedding') is not None for r in left + right)
    try:
        distance = mmd([r['embedding'] for r in left], [r['embedding'] for r in right],
                       config.embedding_max_samples) if embeddings_available else None
    except ValueError:
        report['reason'] = ['invalid embedding data']
        return report
    report['embedding'] = {'score': distance, 'threshold': config.embedding_threshold,
                           'drift': distance is not None and distance > config.embedding_threshold}
    scores = {}
    for label, truth in [('genuine', True), ('impostor', False)]:
        before, after = distribution(left, truth), distribution(right, truth)
        values_left = [r['score'] for r in left if r.get('random_audit') and r.get('truth') is truth]
        values_right = [r['score'] for r in right if r.get('random_audit') and r.get('truth') is truth]
        d = psi(values_left, values_right)
        scores[label] = {'reference': before, 'current': after,
                         'psi': float(d) if np.isfinite(d) else None,
                         'shift': after['mean'] - before['mean'] if before['count'] and after['count'] else None}
    score_drift = any(v['psi'] is not None and v['psi'] > config.psi_threshold for v in scores.values())
    report['verification_score'] = {'drift': score_drift, **scores}
    if all(scores[k]['current']['count'] for k in scores):
        report['verification_score']['separation'] = scores['genuine']['current']['mean'] - scores['impostor']['current']['mean']
    baseline, measured = performance(reference, config), report['performance']
    labelled = baseline['status'] == measured['status'] == 'READY'
    degraded = labelled and any(measured[key] - baseline[key] >= config.degradation_absolute and
                                (baseline[key] == 0 or measured[key] >= baseline[key] * (1 + config.degradation_relative))
                                for key in ('fmr', 'fnmr'))
    if labelled:
        measured.update(status='DEGRADED' if degraded else 'HEALTHY', reference=baseline)
    aging = age_summary(current, config)
    recent, older = aging[0], aging[-1]
    aging_only = (recent['fnmr'] is not None and older['fnmr'] is not None and
                  recent['fnmr'] <= config.max_fnmr and older['fnmr'] > config.max_fnmr + config.degradation_absolute)
    aging_only = aging_only and labelled and measured['fmr'] <= config.max_fmr
    cross_age = sum((r['fnmr'] is not None and r['fnmr'] > config.max_fnmr) or
                    (r['fmr'] is not None and r['fmr'] > config.max_fmr) for r in aging) >= 2
    report['template_aging'] = {'detected': aging_only, 'buckets': aging, 'boundaries_days': config.age_boundaries,
                                'cross_age_degradation': cross_age}
    persistent_evidence = report['embedding']['drift'] and score_drift and degraded and cross_age
    last_ids = (previous or {}).get('persistence', {}).get('last_counted_ids', [])
    new_window = not last_ids or len(set(report['current_ids']) - set(last_ids)) >= config.min_samples
    old_count = (previous or {}).get('persistence', {}).get('consecutive_windows', 0)
    count = old_count + int(new_window) if persistent_evidence else 0
    old_template_count = (previous or {}).get('persistence', {}).get('template_windows', 0)
    template_evidence = aging_only and degraded and embeddings_available and not report['quality']['drift']
    report['persistence']['template_windows'] = old_template_count + int(new_window) if template_evidence else 0
    report['persistence']['last_counted_ids'] = report['current_ids'] if new_window else last_ids
    report['persistence']['consecutive_windows'] = count
    if report['quality']['drift']:
        decision, reasons = 'INPUT_DRIFT', ['capture quality changed; investigate input before model changes']
        report['persistence']['consecutive_windows'] = 0
    elif not labelled or not embeddings_available:
        decision, reasons = 'INSUFFICIENT_DATA', ['insufficient trusted labels or retained embeddings']
    elif aging_only and degraded:
        decision, reasons = 'TEMPLATE_UPDATE_REQUIRED', ['old templates degrade while recent templates remain healthy']
    elif count >= config.min_consecutive_windows:
        decision, reasons = 'RETRAIN_REQUIRED', ['persistent embedding and score drift', 'verified cross-age performance degradation']
    elif score_drift:
        decision, reasons = 'SCORE_DRIFT', ['score distribution changed; awaiting sufficient causal evidence']
    elif report['embedding']['drift']:
        decision, reasons = 'EMBEDDING_DRIFT', ['embedding distribution changed without verified degradation']
    elif degraded:
        decision, reasons = 'MONITOR', ['performance changed but root cause is unresolved']
    else:
        decision, reasons = 'HEALTHY', ['measured evidence within configured boundaries']
    report.update(decision=decision, reason=reasons)
    return report
