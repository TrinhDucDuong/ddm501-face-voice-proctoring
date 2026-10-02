import json
from types import SimpleNamespace

import numpy as np
import pytest
from botocore.exceptions import ClientError

from pipeline.data_snapshot import training_scope
from pipeline.dataset_ledger import (
    identity_split,
    manifest_for_snapshot,
    publish_snapshot,
)
from pipeline.monitoring_etl import assess_window, performance_on_random_audit
from pipeline.monitoring_job import (
    blind_review_sets,
    build_report,
    report_artifact,
    training_run_id,
)
from pipeline.promotion_gate import (
    compare_paired_holdout,
    compare_reviewed_shadow,
    promote,
)


def test_identity_split_is_deterministic_and_holdout_never_enters_training():
    rows = [{'id': f'{person}-{sample}', 'person_id': str(person)}
            for person in range(15) for sample in range(2)]
    first = identity_split(rows)
    assert first == identity_split(list(reversed(rows)))
    assert set(first['calibration_identities']).isdisjoint(first['holdout_identities'])
    assert set(first['calibration_identities']) | set(first['holdout_identities']) == {str(i) for i in range(15)}
    manifest = manifest_for_snapshot({'dataset_version': 'abc', 'tenant_scope': 'demo', 'samples': rows})
    assert manifest['dataset_version'] == 'abc'
    assert manifest['tenant_scope'] == 'demo'
    assert manifest['split'] == first


def test_same_training_data_can_be_republished_without_changing_immutable_object():
    class MemoryS3:
        def __init__(self):
            self.objects = {}

        def head_object(self, *, Bucket, Key):
            if Key not in self.objects:
                raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')
            return {'Metadata': self.objects[Key]['Metadata']}

        def put_object(self, *, Bucket, Key, Body, ContentType, Metadata):
            self.objects[Key] = {'Body': Body, 'Metadata': Metadata}

    rows = [{'id': f'{i}', 'person_id': f'{i}'} for i in range(12)]
    first = {'dataset_version': 'fixed', 'tenant_scope': 'demo', 'samples': rows,
             'created_at': '2026-10-01T00:00:00Z'}
    store = MemoryS3()
    published = publish_snapshot(first, client=store)
    second = {**first, 'created_at': '2026-10-02T00:00:00Z'}
    again = publish_snapshot(second, client=store)
    assert published['manifest']['snapshot_sha256'] == again['manifest']['snapshot_sha256']
    assert len(store.objects) == 2


def test_customer_embeddings_cannot_be_enabled_for_training_by_env_only(monkeypatch):
    monkeypatch.setenv('TRAINING_TENANT_ID', 'customer-1')
    with pytest.raises(ValueError, match='consent'):
        training_scope()
    monkeypatch.setenv('TRAINING_TENANT_ID', 'demo')
    assert training_scope() == 'demo'


def test_monitoring_does_not_infer_accuracy_from_unlabelled_or_selected_cases():
    labels = [{'accepted': False, 'is_genuine': False, 'selection_reason': 'suspicious'} for _ in range(30)]
    assert performance_on_random_audit(labels)['status'] == 'insufficient_random_audits'
    reference = [{'face_score': .8 + i/10000, 'voice_score': .8, 'face_quality': .9,
                  'voice_quality': .9, 'risk_score': .1} for i in range(40)]
    stable = assess_window(reference, list(reference), labels, previous_drift=False, min_samples=30)
    assert stable['status'] == 'stable'
    assert stable['performance']['status'] == 'insufficient_random_audits'
    assert stable['trigger_training'] is False


def test_missing_feature_is_reported_as_unknown_in_json():
    rows = [{'face_score': .8, 'voice_score': .8, 'face_quality': None,
             'voice_quality': .9, 'risk_score': .1} for _ in range(40)]
    report = assess_window(rows, rows, [], previous_drift=False, min_samples=30)
    assert report['psi']['face_quality'] is None
    json.dumps(report, allow_nan=False)


def test_sustained_drift_requires_second_window_and_training_eligibility():
    reference = [{'face_score': .8 + i/10000, 'voice_score': .8, 'face_quality': .9,
                  'voice_quality': .9, 'risk_score': .1} for i in range(40)]
    changed = [{**row, 'face_score': .2 + i/10000} for i, row in enumerate(reference)]
    first = assess_window(reference, changed, [], previous_drift=False, min_samples=30,
                          training_eligible=True)
    assert first['status'] == 'drift_detected'
    assert first['trigger_training'] is False
    second = assess_window(reference, changed, [], previous_drift=True, min_samples=30,
                           training_eligible=True)
    assert second['trigger_training'] is True
    ineligible = assess_window(reference, changed, [], previous_drift=True, min_samples=30,
                               training_eligible=False)
    assert ineligible['trigger_training'] is False


def test_random_audit_performance_needs_both_truth_classes():
    labels = [{'accepted': prediction, 'is_genuine': truth, 'selection_reason': 'random_audit'}
              for truth in (False, True) for prediction in (False, True) for _ in range(6)]
    result = performance_on_random_audit(labels, min_per_class=5)
    assert result['status'] == 'ready'
    assert result['far'] == .5 and result['frr'] == .5
    assert result['sample_count'] == 24


def test_monitoring_reference_is_frozen_and_same_window_cannot_retrigger():
    rows = [{'id': str(i), 'face_score': .8 if i < 40 else .2, 'voice_score': .8,
             'face_quality': .9, 'voice_quality': .9, 'risk_score': .1,
             'accepted': True, 'is_genuine': None, 'selection_reason': None} for i in range(80)]
    first, reference = build_report(rows, tenant_id='demo', model_version='v1',
                                    window_size=40, training_eligible=True)
    assert first['status'] == 'drift_detected' and not first['trigger_training']
    again, unchanged_reference = build_report(rows, tenant_id='demo', model_version='v1',
                                               window_size=40, reference=reference,
                                               previous_report=first, training_eligible=True)
    assert again['unchanged'] is True and not again['trigger_training']
    assert unchanged_reference == reference
    new_rows = rows + [{**rows[-1], 'id': str(i)} for i in range(80, 120)]
    second, _ = build_report(new_rows, tenant_id='demo', model_version='v1', window_size=40,
                             reference=reference, previous_report=first, training_eligible=True)
    assert second['trigger_training'] is True
    same, _ = build_report(new_rows, tenant_id='demo', model_version='v1', window_size=40,
                           reference=reference, previous_report=second, training_eligible=True)
    assert same['unchanged'] is True
    assert same['trigger_training'] is True
    assert training_run_id(same) == training_run_id(second)


def test_review_update_does_not_count_same_feature_window_as_second_drift_window():
    rows = [{'id': str(i), 'face_score': .8 if i < 40 else .2, 'voice_score': .8,
             'face_quality': .9, 'voice_quality': .9, 'risk_score': .1,
             'accepted': True, 'is_genuine': None, 'selection_reason': None} for i in range(80)]
    first, reference = build_report(rows, tenant_id='demo', model_version='v1',
                                    window_size=40, training_eligible=True)
    reviewed = [dict(row) for row in rows]
    reviewed[-1].update(is_genuine=True, selection_reason='random_audit',
                        reviewed_at='2026-10-02T00:00:00Z')
    updated, _ = build_report(reviewed, tenant_id='demo', model_version='v1',
                              window_size=40, reference=reference,
                              previous_report=first, training_eligible=True)
    assert updated['window_id'] != first['window_id']
    assert updated['feature_window_id'] == first['feature_window_id']
    assert updated['trigger_training'] is False


def test_blind_review_sets_keep_truth_out_of_prediction_input():
    rows = [{'id': 'check-1', 'face_score': .8, 'voice_score': .9, 'face_quality': .8,
             'voice_quality': .9, 'risk_score': .1, 'accepted': True,
             'is_genuine': False, 'selection_reason': 'random_audit'}]
    inputs, labels = blind_review_sets(rows)
    assert 'is_genuine' not in inputs[0]
    assert labels == [{'check_id': 'check-1', 'is_genuine': False,
                       'selection_reason': 'random_audit'}]


def test_monitoring_report_retry_has_same_immutable_artifact():
    report = {'window_id': 'abc', 'status': 'drift_detected', 'psi': {'face_score': .7},
              'calculated_at': '2026-10-02T00:00:00Z', 'last_trigger_at': '2026-10-02T00:00:00Z'}
    first_key, first_payload = report_artifact(report)
    retry_key, retry_payload = report_artifact({**report,
        'calculated_at': '2026-10-02T00:01:00Z', 'last_trigger_at': '2026-10-02T00:01:00Z'})
    assert first_key == retry_key
    assert first_payload == retry_payload


def test_challenger_must_improve_same_locked_holdout_without_regressing_a_modality():
    scores = {'face': ([.8] * 10, [.4] * 10),
              'voice': ([.8] * 10, [.4] * 10)}
    champion = {'face_threshold': .5, 'voice_threshold': .5}
    tied = compare_paired_holdout(scores, champion, dict(champion))
    assert not tied['promote'] and tied['reason'] == 'no_measured_gain'
    weak = compare_paired_holdout(scores, champion, {'face_threshold': .9, 'voice_threshold': .5})
    assert not weak['promote'] and weak['reason'] == 'holdout_regression'
    incumbent = {'face_threshold': .3, 'voice_threshold': .3}
    improved = compare_paired_holdout(scores, incumbent, champion)
    assert improved['promote'] is True
    assert improved['champion']['face']['far'] == 1.0
    assert improved['challenger']['face']['far'] == 0.0
    arrays = {key: (np.asarray(p), np.asarray(n)) for key, (p, n) in scores.items()}
    assert json.loads(json.dumps(compare_paired_holdout(arrays, incumbent, champion)))['promote'] is True


def test_reviewed_shadow_requires_random_audits_and_blocks_regression():
    rows = [{'face_score': .8 if truth else .4, 'voice_score': .8 if truth else .4,
             'is_genuine': truth, 'selection_reason': 'random_audit'}
            for truth in (False, True) for _ in range(6)]
    incumbent = {'face_threshold': .5, 'voice_threshold': .5}
    worse = {'face_threshold': .3, 'voice_threshold': .3}
    assert compare_reviewed_shadow(rows, incumbent, worse)['status'] == 'regression'
    assert compare_reviewed_shadow(rows[:4], incumbent, worse)['status'] == 'insufficient_data'


def test_registry_promotion_requires_actual_gain_and_reviewed_shadow(monkeypatch):
    from pipeline import data_snapshot, promotion_gate

    class Registry:
        def __init__(self):
            self.alias_updates = []
            self.tags = []
            self.candidate = SimpleNamespace(version='11', run_id='new')
            self.champion = SimpleNamespace(version='10', run_id='old')
            metrics = {f'{modality}_{metric}': 0.05 for modality in ('face', 'voice')
                       for metric in ('far', 'frr', 'cv_far', 'cv_frr', 'holdout_far', 'holdout_frr')}
            metrics.update({f'{modality}_{metric}': 10 for modality in ('face', 'voice')
                            for metric in ('positive_pairs', 'negative_pairs',
                                           'holdout_positive_pairs', 'holdout_negative_pairs')})
            self.runs = {'new': SimpleNamespace(data=SimpleNamespace(metrics=metrics,
                         params={'face_threshold': '.5', 'voice_threshold': '.5'})),
                         'old': SimpleNamespace(data=SimpleNamespace(metrics=metrics,
                         params={'face_threshold': '.3', 'voice_threshold': '.3'}))}

        def get_run(self, run_id):
            return self.runs[run_id]

        def get_model_version_by_alias(self, name, alias):
            assert alias == 'champion'
            return self.champion

        def set_model_version_tag(self, name, version, key, value):
            self.tags.append((key, value))

        def set_registered_model_alias(self, name, alias, version):
            self.alias_updates.append((alias, version))

    scores = {'face': ([.8] * 10, [.4] * 10), 'voice': ([.8] * 10, [.4] * 10)}
    rows = [{'face_score': .8 if truth else .4, 'voice_score': .8 if truth else .4,
             'is_genuine': truth, 'selection_reason': 'random_audit'}
            for truth in (True, False) for _ in range(6)]
    monkeypatch.setenv('SNAPSHOT_PATH', 'locked.json')
    monkeypatch.setenv('REQUIRE_REVIEWED_SHADOW', 'true')
    monkeypatch.setenv('DATABASE_URL', 'test://')
    monkeypatch.setattr(data_snapshot, 'read_snapshot', lambda _: {'tenant_scope': 'demo', 'samples': []})
    monkeypatch.setattr(promotion_gate, 'paired_scores_from_snapshot', lambda _: scores)
    monkeypatch.setattr(promotion_gate, 'load_reviewed_shadow', lambda *_: rows)
    client = Registry()
    result = promote(client, 'bundle', client.candidate)
    assert result['paired_holdout']['promote'] is True
    assert result['reviewed_shadow']['status'] == 'pass'
    assert client.alias_updates == [('champion', '11')]
    assert ('rollback_version', '10') in client.tags

    client = Registry()
    client.runs['old'].data.params.update(face_threshold='.5', voice_threshold='.5')
    result = promote(client, 'bundle', client.candidate)
    assert 'no_measured_gain' in result['failures']
    assert client.alias_updates == []
