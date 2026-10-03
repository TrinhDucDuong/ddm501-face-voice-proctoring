from datetime import timedelta

import pytest
from app.config import Settings
from app.db import Base
from app.lifecycle_service import claim_training, run_monitoring
from app.models import (
    ModalityDeployment,
    ModalityObservation,
    Person,
    VerificationEvent,
    utcnow,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


def test_persisted_monitoring_only_claims_independent_labelled_drift_once(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    settings = Settings(lifecycle_config_path='pipeline/lifecycle_config.json')
    with Session(engine, expire_on_commit=False) as db:
        for i in range(20):
            db.add(Person(id=str(i), external_id=str(i), display_name='Fixture', tenant_id='demo'))
        db.add(ModalityDeployment(modality='face', registry_name='face-verification', champion_version='1', champion_threshold=.7))
        db.commit()
        now = utcnow() - timedelta(days=1)

        def add_window(window, shift):
            for i in range(100):
                event = VerificationEvent(person_id=str(i % 20), session_id='fixture', accepted=True,
                                           risk_score=0, reasons=[], model_version='1', latency_ms=1)
                db.add(event)
                db.flush()
                db.add(ModalityObservation(id=f'{window}-{i:03}', event_id=event.id,
                    tenant_id='demo', person_id=str(i % 20), modality='face', model_version='1', encoder='pinned',
                    template_version='1', template_age_days=400 if i % 4 < 2 else 10,
                    score=(.85 - shift) if i % 2 == 0 else .15, threshold=.7,
                    quality={'quality': .9}, embedding=[1., shift, .001 * (i % 3)],
                    media_sha256=f'{window}-{i}', truth=i % 2 == 0, random_audit=True,
                    created_at=now + timedelta(seconds=window * 100 + i)))
            db.commit()

        add_window(0, 0)
        add_window(1, .3)
        first = run_monitoring(db, settings)
        db.commit()
        assert first['modalities'][0]['persistence']['consecutive_windows'] == 1
        assert not first['trigger_training']
        for window in (2, 3):
            add_window(window, .3)
            result = run_monitoring(db, settings)
            db.commit()
        assert result['trigger_training']
        report = result['modalities'][0]
        assert report['decision'] == 'RETRAIN_REQUIRED'
        duplicate = run_monitoring(db, settings)['modalities'][0]
        assert duplicate['persistence']['consecutive_windows'] == 3
        claim_training(db, 'face', report['current_window'])
        db.commit()
        assert claim_training(db, 'face', report['current_window']).state == 'TRAINING'
        with pytest.raises(ValueError, match='eligible'):
            claim_training(db, 'face', 'different-window')
        db.get(ModalityDeployment, 'face').state = 'REJECTED'
        db.flush()
        with pytest.raises(ValueError, match='already attempted'):
            claim_training(db, 'face', report['current_window'])
        db.get(ModalityDeployment, 'face').state = 'TRAINING'
        assert db.get(ModalityDeployment, 'face').state == 'TRAINING'
        assert not run_monitoring(db, settings)['trigger_training']
        assert db.get(ModalityDeployment, 'voice') is None
        # Expired vectors and observations are removed, including frozen references.
        for row in db.scalars(select(ModalityObservation)):
            row.created_at = utcnow() - timedelta(days=31)
        db.commit()
        expired = run_monitoring(db, settings)
        db.commit()
        assert expired['modalities'][0]['decision'] == 'INSUFFICIENT_DATA'
        assert all(r.embedding is None for r in db.scalars(select(ModalityObservation)))
        # Template gates must not mutate enrollment during a rollout or using retired-policy evidence.
        from app.models import ModalityMonitorState
        db.get(ModalityMonitorState, ('demo', 'face', '1')).reference = []
        add_window(4, .3)
        monkeypatch.setattr('app.lifecycle_service.evaluate', lambda *args: {
            **report, 'decision': 'TEMPLATE_UPDATE_REQUIRED',
            'persistence': {'template_windows': 3}})
        monkeypatch.setattr('app.lifecycle_service.update_template',
                            lambda *args: pytest.fail('Unsafe template update'))
        run_monitoring(db, settings)
        deployment = db.get(ModalityDeployment, 'face')
        deployment.state, deployment.champion_version = 'CHAMPION', 'new-policy'
        run_monitoring(db, settings)
    engine.dispose()


def test_monitoring_does_not_call_unlabelled_observations_healthy():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert run_monitoring(db, Settings(lifecycle_config_path='pipeline/lifecycle_config.json'))['modalities'] == []
    engine.dispose()
