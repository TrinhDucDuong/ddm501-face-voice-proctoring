"""Real local MLflow + SQL lifecycle; fixtures are synthetic, never human evidence."""
import json
from pathlib import Path

import mlflow
import pytest
from mlflow import MlflowClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_checks import checks_api  # noqa: F401

from pipeline.modality_training import register_policy


@pytest.mark.parametrize('code,message,missing', [
    ('RESOURCE_DOES_NOT_EXIST', 'Registered model missing', True),
    ('INVALID_PARAMETER_VALUE', 'Registered model alias champion not found.', True),
    ('INVALID_PARAMETER_VALUE', 'Invalid registered model name', False),
    ('INTERNAL_ERROR', 'Database unavailable', False),
])
def test_registry_bootstrap_only_handles_missing_alias(code, message, missing):
    from app.lifecycle_api import missing_champion
    from mlflow.exceptions import RestException
    assert missing_champion(RestException({'error_code': code, 'message': message})) is missing


def test_registry_shadow_canary_promotion_and_rollback(checks_api, tmp_path):  # noqa: F811
    from app.models import (
        ModalityDeployment,
        ModalityMonitorState,
        ModalityObservation,
        Person,
        VerificationEvent,
    )

    client, engine, _, _, main = checks_api
    tracking = (tmp_path / 'mlruns').as_uri()
    mlflow.set_tracking_uri(tracking)
    original_uri, original_config = main.settings.mlflow_tracking_uri, main.settings.lifecycle_config_path
    main.settings.mlflow_tracking_uri = tracking
    config = json.loads(Path(original_config).read_text())
    config['rollout'].update(min_samples=4, min_seconds=0, min_labels_per_class=2, stages=[5, 100])
    config['drift'].update(min_samples=10, min_labels_per_class=2)
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps(config))
    main.settings.lifecycle_config_path = str(config_path)
    headers = {'X-API-Key': 'checks-platform'}
    try:
        result = client.post('/v1/admin/lifecycle/bootstrap', headers=headers)
        assert result.status_code == 200, result.text
        registry = MlflowClient(tracking_uri=tracking)
        initial = result.json()
        assert set(initial) == {'face', 'voice'}
        from app.registry import RuntimeModel
        incumbent = main.registry.current
        main.registry.current = RuntimeModel(.45, .25, 'local-default')
        try:
            assert client.get('/ready').status_code == 200
            assert client.post('/v1/admin/lifecycle/bootstrap', headers=headers).json() == initial
        finally:
            main.registry.current = incumbent
        with Session(engine) as db:
            db.add(ModalityMonitorState(tenant_id='demo', modality='face', model_version=initial['face'],
                                       reference=[], report={'trigger_training': True, 'current_window': 'window-a'}))
            db.add(Person(id='test-person', tenant_id='demo', external_id='test-person', display_name='Fixture'))
            db.commit()
        claim = client.post('/v1/admin/lifecycle/face/claim', headers=headers, json={'window_id': 'window-a'})
        assert claim.status_code == 200, claim.text
        new = register_policy('face', .7,
            {k: 0. for k in ('far', 'frr', 'cv_far', 'cv_frr', 'holdout_far', 'holdout_frr')},
            {'positive': [.9] * 20, 'negative': [.1] * 20},
            {'modality': 'face', 'training_window': 'window-a', 'dataset_version': 'fixture',
             'model_family': 'cosine-threshold-policy'})
        candidate = client.post('/v1/admin/lifecycle/face/candidate', headers=headers,
                                 json={'version': new, 'window_id': 'window-a'})
        assert candidate.status_code == 200, candidate.text
        assert candidate.json()['state'] == 'SHADOW'
        duplicate = register_policy('face', .7, {}, {},
            {'training_window': 'window-a', 'dataset_version': 'fixture'})
        assert duplicate == new
        assert str(registry.get_model_version_by_alias('face-verification', 'champion').version) == initial['face']
        for expected in ('CANARY', 'CANARY', 'CHAMPION'):
            with Session(engine) as db:
                row = db.get(ModalityDeployment, 'face')
                for i in range(4):
                    event = VerificationEvent(person_id='test-person', session_id='test', accepted=True,
                        risk_score=0, reasons=[], latency_ms=1, model_version=initial['face'])
                    db.add(event)
                    db.flush()
                    db.add(ModalityObservation(event_id=event.id, tenant_id='demo', person_id='test-person',
                        modality='face', model_version=initial['face'], encoder='pinned', template_version='1',
                        template_age_days=10, score=.9 if i % 2 == 0 else .1, threshold=row.champion_threshold,
                        quality={'quality': .9}, media_sha256=str(i), truth=i % 2 == 0, random_audit=True,
                        deployment_id=row.deployment_id, stage=row.state, served_candidate=row.state == 'CANARY',
                        challenger_score=.9 if i % 2 == 0 else .1, challenger_threshold=.7,
                        challenger_version=new, challenger_latency_ms=.1))
                db.commit()
            tick = client.post('/v1/admin/lifecycle/tick', headers=headers)
            assert tick.status_code == 200, tick.text
            assert next(r for r in tick.json() if r['modality'] == 'face')['state'] == expected
        assert str(registry.get_model_version_by_alias('face-verification', 'champion').version) == new
        assert str(registry.get_model_version_by_alias('voice-verification', 'champion').version) == initial['voice']
        assert str(registry.get_model_version_by_alias('face-verification', 'previous_champion').version) == initial['face']
        rolled = client.post('/v1/admin/lifecycle/face/rollback', headers=headers)
        assert rolled.status_code == 200, rolled.text
        assert str(registry.get_model_version_by_alias('face-verification', 'champion').version) == initial['face']
        with Session(engine) as db:
            assert db.scalar(select(ModalityDeployment).where(ModalityDeployment.modality == 'face')).state == 'ROLLED_BACK'
        assert registry.get_model_version('face-verification', initial['face']).tags['lifecycle_status'] == 'CHAMPION'
        assert registry.get_model_version('face-verification', new).tags['lifecycle_status'] == 'ROLLED_BACK'
        reference_body = {'tenant_id': 'demo', 'reason': 'Reviewed baseline after retention renewal'}
        assert client.post('/v1/admin/lifecycle/face/reference', json=reference_body).status_code == 401
        missing_vectors = client.post('/v1/admin/lifecycle/face/reference', headers=headers, json=reference_body)
        assert missing_vectors.status_code == 409
        with Session(engine) as db:
            for observation in db.scalars(select(ModalityObservation)):
                observation.embedding = [1., 0.]
            db.commit()
        reset = client.post('/v1/admin/lifecycle/face/reference', headers=headers, json=reference_body)
        assert reset.status_code == 200, reset.text
        assert reset.json()['reference_samples'] == 10
        monitored = client.post('/v1/admin/lifecycle/monitor', headers=headers)
        assert monitored.status_code == 200, monitored.text
        assert monitored.json()['evidence'][0]['window_id'] == monitored.json()['modalities'][0]['current_window']
    finally:
        main.settings.mlflow_tracking_uri, main.settings.lifecycle_config_path = original_uri, original_config
        mlflow.set_tracking_uri(original_uri)
