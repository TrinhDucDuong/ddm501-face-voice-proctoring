"""Check Airflow evidence without requiring a running demo stack."""

import json
import sys
from types import SimpleNamespace

import pytest

from pipeline import verify_stack

TASK_IDS = [
    'ingest_versioned_snapshot',
    'validate_data_quality',
    'publish_versioned_dataset',
    'feature_engineer_train_register_candidate',
    'generate_responsible_ai_audit',
    'evaluate_and_promote_candidate',
    'reload_current_champion',
]


@pytest.mark.parametrize('scenario, expected_status', [
    ('complete', 'pass'),
    ('missing', 'fail'),
    ('duplicate', 'fail'),
    ('unexpected', 'fail'),
    ('empty', 'fail'),
    ('failed', 'fail'),
    ('running', 'fail'),
    ('skipped', 'fail'),
    ('unset', 'fail'),
])
def test_airflow_evidence_requires_all_expected_tasks(monkeypatch, tmp_path, scenario, expected_status):
    tasks = [{'task_id': task_id, 'state': 'success'} for task_id in TASK_IDS]
    if scenario == 'missing':
        tasks.pop(2)
    elif scenario == 'duplicate':
        tasks.append(tasks[0].copy())
    elif scenario == 'unexpected':
        tasks[-1]['task_id'] = 'unknown_task'
    elif scenario == 'empty':
        tasks = []
    elif scenario != 'complete':
        tasks[-1]['state'] = None if scenario == 'unset' else scenario

    def run(command, **kwargs):
        assert command == [
            'docker', 'compose', 'exec', '-T', 'airflow-scheduler', 'airflow', 'tasks',
            'states-for-dag-run', 'biometric_model_pipeline', 'regression-run', '-o', 'json',
        ]
        return SimpleNamespace(stdout=json.dumps(tasks))

    def offline_get(*args, **kwargs):
        raise RuntimeError('Other stack services are outside this regression test')

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['verify_stack.py', '--dag-run', 'regression-run'])
    monkeypatch.setattr(verify_stack.subprocess, 'run', run)
    monkeypatch.setattr(verify_stack.requests.Session, 'get', offline_get)
    with pytest.raises(SystemExit, match='1'):
        verify_stack.main()
    evidence = json.loads((tmp_path / 'reports/verification.json').read_text())
    assert evidence['checks']['airflow']['status'] == expected_status
    if expected_status == 'pass':
        assert evidence['checks']['airflow']['evidence'] == tasks
