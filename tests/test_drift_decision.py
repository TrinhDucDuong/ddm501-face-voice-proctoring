from dataclasses import replace

import numpy as np
import pytest

from pipeline.drift_decision import DriftConfig, evaluate, mmd, performance


def observations(shift=0., quality=.9, labelled=True, old_only=False):
    rows = []
    for i in range(120):
        genuine = i % 2 == 0
        age = 400 if i % 4 < 2 else 10
        score = .85 if genuine else .15
        if genuine and (not old_only or age > 365):
            score -= shift
        rows.append({'id': str(i), 'person_id': str(i % 20), 'encoder': 'pinned',
                     'score': score, 'threshold': .7, 'quality': {'quality': quality},
                     'embedding': [1., shift, (i % 3) * .01], 'template_age_days': age,
                     'truth': genuine if labelled else None, 'random_audit': True})
    return rows


def test_multivariate_distance_detects_joint_change_and_rejects_invalid_vectors():
    reference = np.random.default_rng(42).normal(size=(80, 6))
    assert mmd(reference, reference) == pytest.approx(0)
    assert mmd(reference, reference + 4) > .1
    with pytest.raises(ValueError):
        mmd([[float('nan'), 1]], [[1, 2]])


def test_missing_labels_never_become_healthy_or_trigger_retraining():
    result = evaluate(observations(), observations(.3, labelled=False), 'face', '1', 'w1')
    assert result['performance']['status'] == 'INSUFFICIENT_LABELS'
    assert result['decision'] == 'INSUFFICIENT_DATA'


def test_quality_degradation_does_not_trigger_retraining():
    result = evaluate(observations(), observations(.3, quality=.2), 'voice', '1', 'w1')
    assert result['decision'] == 'INPUT_DRIFT'


def test_old_template_only_degradation_routes_to_template_workflow():
    result = evaluate(observations(), observations(.3, old_only=True), 'face', '1', 'w1')
    assert result['decision'] == 'TEMPLATE_UPDATE_REQUIRED'


def test_persistent_labelled_degradation_and_duplicate_window_handling():
    config = replace(DriftConfig(), embedding_threshold=.001)
    prior = None
    for window in ('w1', 'w2', 'w3'):
        current = [{**r, 'id': window + r['id']} for r in observations(.3)]
        prior = evaluate(observations(), current, 'voice', '1', window, prior, config)
    assert prior['decision'] == 'RETRAIN_REQUIRED'
    assert prior['persistence']['consecutive_windows'] == 3
    duplicate = evaluate(observations(), observations(.3), 'voice', '1', 'w3', prior, config)
    assert duplicate['persistence']['consecutive_windows'] == 3
    healthy = evaluate(observations(), observations(), 'voice', '1', 'w4', prior, config)
    assert healthy['persistence']['consecutive_windows'] == 0
    assert healthy['decision'] == 'HEALTHY'


def test_changed_identity_cohort_cannot_be_classified_as_encoder_degradation():
    current = observations(.3)
    for row in current:
        row['person_id'] = 'new-' + row['person_id']
    result = evaluate(observations(), current, 'face', '1', 'w1')
    assert result['decision'] == 'INSUFFICIENT_DATA'


def test_performance_uses_modality_score_not_combined_decision():
    rows = observations()
    for row in rows:
        row['accepted'] = False
    result = performance(rows, DriftConfig())
    assert result['fmr'] == result['fnmr'] == result['eer'] == 0
    assert result['tar_at_far'] == 1


def test_missing_quality_cannot_authorize_retraining():
    before, after = observations(), observations(.3)
    for row in before + after:
        row['quality'] = {}
    result = evaluate(before, after, 'face', '1', 'missing-quality')
    assert result['decision'] == 'INSUFFICIENT_DATA'
    assert result['reason'] == ['insufficient quality evidence']


def test_input_issue_windows_do_not_count_toward_template_update():
    prior = None
    for index in range(3):
        current = [{**r, 'id': f'{index}-{r["id"]}'} for r in observations(.3, quality=.2, old_only=True)]
        prior = evaluate(observations(), current, 'face', '1', str(index), prior)
    clean = [{**r, 'id': 'clean-' + r['id']} for r in observations(.3, old_only=True)]
    result = evaluate(observations(), clean, 'face', '1', 'clean', prior)
    assert result['decision'] == 'TEMPLATE_UPDATE_REQUIRED'
    assert result['persistence']['template_windows'] == 1
