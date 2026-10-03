"""Synthetic experiments use the real gates, never the production registry."""
import numpy as np
import pytest

from pipeline.drift_decision import evaluate
from pipeline.evaluation import identity_evaluation, policy_scores


def test_generated_vectors_drive_persistent_drift_and_real_calibration():
    from app.model_lifecycle import RolloutConfig

    from pipeline.modality_training import paired_gate
    from pipeline.simulation_data import dataset, window

    reference = window('baseline', 501, drift=False)
    assert evaluate(reference, window('healthy', 502, drift=False), 'voice', '1', 'healthy')['decision'] == 'HEALTHY'
    previous = None
    for index in range(3):
        current = window(f'drift-{index}', 503 + index)
        for row in current:
            assert row['score'] == pytest.approx(np.dot(row['embedding'], row['template']))
        previous = evaluate(reference, current, 'voice', '1', f'w{index}', previous)
    assert previous['decision'] == 'RETRAIN_REQUIRED'
    assert previous['quality']['drift'] is False
    samples = dataset(600)
    threshold, metrics, evidence = identity_evaluation(samples)
    holdout = [r for r in samples if r['person_id'] in evidence['holdout_identities']]
    positive, negative = policy_scores(holdout)
    gate = paired_gate(positive, negative, .8, threshold, metrics,
                       RolloutConfig(min_labels_per_class=20))
    assert gate['passed']
    assert gate['candidate']['fnmr'] < gate['champion']['fnmr']
    assert gate['candidate']['fmr'] == 0
    holdout_ids = set(evidence['holdout_identities'])
    assert all(not holdout_ids.intersection(f['train_identities']) for f in evidence['folds'])


def test_isolated_run_promotion_failure_reset_and_stale_requests(tmp_path):
    from pipeline.simulation_runner import SimulationRunner

    runner = SimulationRunner(tmp_path, stage_seconds=0)
    started = runner.start('promotion', 'voice', 501)
    run_id = started['id']
    with pytest.raises(ValueError, match='active'):
        runner.start('rollback', 'face', 501)
    with pytest.raises(ValueError, match='Expected'):
        runner.step(run_id, 'train')
    for step in runner.steps:
        runner.step(run_id, step)
    state = runner.status()
    assert state['current']['status'] == 'SUCCEEDED'
    assert state['current']['deployment']['state'] == 'CHAMPION'
    assert state['current']['deployment']['champion_version'] != state['current']['baseline_version']
    assert state['current']['other_modality']['champion_version'] == '1'
    stages = state['current']['stages']
    assert [s['traffic_percent'] for s in stages] == [0, 5, 10, 25, 50, 100]
    assert stages[0]['served_candidate'] == 0
    assert stages[-1]['served_candidate'] == stages[-1]['samples']
    assert all(s['response_mismatches'] == 0 for s in stages)
    assert runner.step(run_id, 'canary')['status'] == 'SUCCEEDED'
    reset = runner.reset()
    assert reset['current']['status'] == 'RESET'
    assert reset['current']['deployment']['champion_version'] == reset['current']['baseline_version']
    with pytest.raises(ValueError, match='inactive'):
        runner.step(run_id, 'train')
    second = runner.start('rollback', 'face', 502)['id']
    for step in runner.steps:
        runner.step(second, step)
    failed = runner.status()['current']
    assert failed['status'] == 'ROLLED_BACK'
    assert failed['deployment']['state'] == 'FAILED_CANARY'
    assert failed['deployment']['evidence']['failure']['metric'] == 'fmr'
    assert failed['rollback_probe']['served_candidate'] == 0
    assert failed['deployment']['champion_version'] == failed['baseline_version']
    runner.reset()
    assert len(runner.status()['history']) == 2
    third = runner.start('promotion', 'voice', 503)['id']
    runner.reset()
    with pytest.raises(ValueError, match='inactive'):
        runner.step(third, 'prepare')


def test_simulation_http_auth_alert_gate_and_reset(tmp_path):
    from app.simulation_server import create_app
    from fastapi.testclient import TestClient
    app = create_app(tmp_path, 'test-simulation-secret', stage_seconds=0)
    headers = {'X-Simulation-Key': 'test-simulation-secret'}
    with TestClient(app) as client:
        assert client.post('/runs', json={'scenario': 'promotion'}).status_code == 401
        started = client.post('/runs', headers=headers, json={'scenario': 'promotion', 'modality': 'voice'}).json()
        claim = {'airflow_run_id': 'test-airflow-run'}
        assert client.post('/internal/claim', headers=headers, json=claim).json()['run_id'] == started['id']
        assert client.post('/internal/claim', headers=headers, json=claim).json()['run_id'] == started['id']
        assert client.post('/internal/step', headers=headers, json={'run_id': started['id'], 'step': 'train'}).status_code == 425
        assert client.get('/evidence/../../other', headers=headers).status_code == 404
        assert client.post('/reset', headers=headers).json()['current']['status'] == 'RESET'
        assert client.post('/internal/step', headers=headers, json={'run_id': started['id'], 'step': 'prepare'}).status_code == 409
        assert client.get('/metrics').status_code == 200
        assert client.get('/state', headers=headers).json()['isolated']


def test_admin_proxy_requires_platform(checks_api):  # noqa: F811
    from test_checks import company
    client, _, _, _, _ = checks_api
    assert client.get('/v1/admin/simulation/state').status_code == 401
    owner = company(client, 'Simulation denied')
    assert client.get('/v1/admin/simulation/state', headers=owner['operator']).status_code == 403
    assert client.post('/v1/admin/simulation/reset', headers=owner['integration']).status_code == 403


def test_restart_requires_reset_and_old_run_cannot_mutate_new_run(tmp_path):
    from pipeline.simulation_runner import SimulationRunner
    runner = SimulationRunner(tmp_path, stage_seconds=0)
    run = runner.start('promotion', 'face', 501)
    runner.artifact(run, 'progress', {'phase': 'PREPARE'})
    runner.recover()
    assert runner.status()['current']['status'] == 'FAILED'
    runner.reset()
    current = runner.start('rollback', 'voice', 501)
    with pytest.raises(ValueError, match='inactive'):
        runner.step(run['id'], 'prepare')
    assert runner.status()['current']['id'] == current['id']


def test_reset_cancels_inflight_stage_and_preserves_evidence(tmp_path):
    import json
    import threading
    import time

    from pipeline.simulation_runner import SimulationRunner
    runner = SimulationRunner(tmp_path, stage_seconds=2)
    run = runner.start('promotion', 'voice', 501)
    for phase in ('prepare', 'drift', 'train', 'offline'):
        runner.step(run['id'], phase)
    errors = []

    def worker():
        try:
            runner.step(run['id'], 'shadow')
        except ValueError as exc:
            errors.append(str(exc))
    thread = threading.Thread(target=worker)
    thread.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if runner.status()['current']['phase'] == 'SHADOW':
            break
        time.sleep(.01)
    restored = runner.reset()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors and 'inactive' in errors[0]
    assert restored['current']['deployment']['state'] == 'CHAMPION'
    assert restored['current']['deployment']['champion_version'] == '1'
    snapshot = (tmp_path / run['id'] / 'result-before-reset.json').read_bytes()
    runner.reset()
    assert (tmp_path / run['id'] / 'result-before-reset.json').read_bytes() == snapshot
    assert json.loads(snapshot)['status'] == 'FAILED'


from test_checks import checks_api  # noqa: E402, F401
