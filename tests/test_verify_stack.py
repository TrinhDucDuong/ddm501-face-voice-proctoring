"""Check Airflow evidence without requiring a running demo stack."""

import json
import sys
from types import SimpleNamespace

import pytest

from pipeline import verify_stack
from pipeline.build_dashboard import build

TASK_IDS = [
    'ingest_versioned_snapshot',
    'validate_data_quality',
    'publish_versioned_dataset',
    'feature_engineer_train_register_candidate',
    'generate_responsible_ai_audit',
    'evaluate_and_promote_candidate',
    'reload_current_champion',
]


def test_grafana_verification_accepts_compact_dashboard_and_rejects_stale_queries():
    dashboard = build()
    assert len(verify_stack.validate_grafana_dashboard(dashboard)) == 10
    dashboard['panels'][0]['targets'][0]['expr'] = 'up'
    with pytest.raises(AssertionError, match='dashboard'):
        verify_stack.validate_grafana_dashboard(dashboard)


def test_grafana_verification_rejects_missing_panel():
    dashboard = build()
    dashboard['panels'].pop()
    with pytest.raises(AssertionError, match='dashboard'):
        verify_stack.validate_grafana_dashboard(dashboard)


def test_inference_version_validation_accepts_only_routed_canary_versions():
    health = {'model_version': 'face:1|voice:3', 'modality_champions': {'face': '1', 'voice': '3'}}
    states = [{'modality': 'face', 'state': 'CANARY', 'champion_version': '1', 'challenger_version': '2'},
              {'modality': 'voice', 'state': 'SHADOW', 'champion_version': '3', 'challenger_version': '4'}]
    verify_stack.validate_served_versions({'model_versions': {'face': '2', 'voice': '3'}}, health, states)
    with pytest.raises(AssertionError):
        verify_stack.validate_served_versions({'model_versions': {'face': '2', 'voice': '4'}}, health, states)


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
