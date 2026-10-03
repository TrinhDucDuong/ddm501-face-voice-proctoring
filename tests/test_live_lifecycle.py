from datetime import timedelta

import pytest
from app.db import Base
from app.model_lifecycle import RolloutConfig, advance, route, start_challenger
from app.models import LifecycleAudit, ModalityDeployment, utcnow
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture
def lifecycle():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        row = ModalityDeployment(modality='face', registry_name='face-verification',
                                 champion_version='1', champion_threshold=.7)
        db.add(row)
        db.commit()
        yield db, row
    engine.dispose()


def evidence(n=100, candidate_threshold=.7):
    return [{'score': .9 if i % 2 == 0 else .2, 'threshold': .7,
             'challenger_score': .9 if i % 2 == 0 else .2,
             'challenger_threshold': candidate_threshold, 'truth': i % 2 == 0,
             'random_audit': True, 'challenger_latency_ms': .1, 'policy_latency_ms': .1}
            for i in range(n)]


def test_shadow_never_changes_live_response_and_canary_is_sticky(lifecycle):
    db, row = lifecycle
    start_challenger(db, row, '2', .8, {'passed': True})
    assert row.state == 'SHADOW'
    assert route(row, 'tenant/person/session')['threshold'] == .7
    row.state, row.traffic_percent = 'CANARY', 50
    first = route(row, 'tenant/person/session')
    assert route(row, 'tenant/person/session') == first
    assert first['version'] in ('1', '2')


def test_no_skip_from_candidate_to_champion(lifecycle):
    db, row = lifecycle
    with pytest.raises(ValueError):
        start_challenger(db, row, '2', .8, {'passed': False})
    assert row.champion_version == '1'


def test_shadow_and_each_canary_require_fresh_samples_and_time(lifecycle):
    db, row = lifecycle
    config = RolloutConfig(min_samples=100, min_seconds=60, stages=(5, 100))
    start_challenger(db, row, '2', .7, {'passed': True})
    advance(db, row, evidence(), config)
    assert row.state == 'SHADOW'
    for expected in (5, 100):
        row.stage_started_at = utcnow() - timedelta(seconds=61)
        advance(db, row, evidence(), config)
        assert row.state == 'CANARY' and row.traffic_percent == expected
    row.stage_started_at = utcnow() - timedelta(seconds=61)
    advance(db, row, [], config)
    assert row.state == 'CANARY'
    advance(db, row, evidence(), config)
    assert row.state == 'PROMOTING' and row.champion_version == '1'


def test_security_regression_rolls_back_without_waiting_for_duration(lifecycle):
    db, row = lifecycle
    start_challenger(db, row, '2', .1, {'passed': True})
    row.state, row.traffic_percent = 'CANARY', 5
    advance(db, row, evidence(candidate_threshold=.1), RolloutConfig())
    assert row.state == 'FAILED_CANARY' and row.traffic_percent == 0
    assert route(row, 'any')['version'] == '1'
    assert row.evidence['failure']['metric'] == 'fmr'
    assert list(db.scalars(select(LifecycleAudit)))


def test_missing_labels_hold_rollout_and_concurrent_training_is_rejected(lifecycle):
    db, row = lifecycle
    start_challenger(db, row, '2', .7, {'passed': True})
    with pytest.raises(ValueError):
        start_challenger(db, row, '3', .7, {'passed': True})
    rows = evidence()
    for item in rows:
        item['truth'] = None
    row.stage_started_at = utcnow() - timedelta(days=2)
    advance(db, row, rows, RolloutConfig(min_seconds=0))
    assert row.state == 'SHADOW'


@pytest.mark.parametrize('field', ['max_fmr', 'max_fnmr', 'max_policy_latency_ms', 'max_disagreement'])
def test_nonfinite_safety_limits_are_rejected(field):
    with pytest.raises(ValueError):
        RolloutConfig(**{field: float('nan')})
