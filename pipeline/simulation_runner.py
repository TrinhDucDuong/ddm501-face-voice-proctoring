"""Isolated synthetic experiments reusing real training, drift and rollout gates."""
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

import mlflow
from app.db import Base
from app.model_lifecycle import (
    RolloutConfig,
    advance,
    audit_transition,
    reconcile_registry,
    route,
    start_challenger,
)
from app.models import LifecycleAudit, ModalityDeployment, utcnow
from mlflow import MlflowClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from pipeline.drift_decision import evaluate
from pipeline.evaluation import identity_evaluation, policy_scores
from pipeline.modality_training import paired_gate, register_policy
from pipeline.simulation_data import BASELINE_THRESHOLD, dataset, window

ACTIVE = {'QUEUED', 'RUNNING'}


class SimulationRunner:
    steps = ('prepare', 'drift', 'train', 'offline', 'shadow', 'canary')

    def __init__(self, root, stage_seconds=5, verify_url=None, token=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.tracking = (self.root / 'mlruns').as_uri()
        self.verify_url, self.token = verify_url, token
        self.limits = RolloutConfig(min_samples=200, min_seconds=stage_seconds,
                                   min_labels_per_class=20, max_disagreement=.6)
        with self.control() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, body TEXT NOT NULL)')

    @contextmanager
    def control(self, write=False):
        connection = sqlite3.connect(self.root / 'control.sqlite', timeout=180)
        connection.execute('PRAGMA journal_mode=WAL')
        try:
            if write:
                connection.execute('BEGIN IMMEDIATE')
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def read(self, connection, run_id=None):
        row = connection.execute('SELECT body FROM runs WHERE id=?', (run_id,)).fetchone() if run_id else \
            connection.execute('SELECT body FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()
        return json.loads(row[0]) if row else None

    def save(self, connection, run):
        run['updated_at'] = utcnow().isoformat()
        connection.execute('INSERT OR REPLACE INTO runs VALUES (?, ?)', (run['id'], json.dumps(run)))

    def directory(self, run):
        return self.root / run['id']

    def artifact(self, run, name, value):
        path = self.directory(run) / (name + '.json')
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')
        temporary.replace(path)

    def engine(self, run):
        return create_engine('sqlite:///' + (self.directory(run) / 'lifecycle.sqlite').as_posix())

    def start(self, scenario, modality, seed):
        if scenario not in {'promotion', 'rollback'} or modality not in {'face', 'voice'}:
            raise ValueError('Invalid simulation scenario or modality')
        if not isinstance(seed, int) or not 0 <= seed <= 1000000:
            raise ValueError('Invalid seed')
        with self.control(write=True) as connection:
            previous = self.read(connection)
            if previous and previous['status'] in ACTIVE:
                raise ValueError('A simulation is already active')
            if previous and previous['status'] != 'RESET':
                raise ValueError('Restore baseline before another simulation')
            run = {'id': str(uuid.uuid4()), 'scenario': scenario, 'modality': modality, 'seed': seed,
                   'status': 'QUEUED', 'phase': 'QUEUED', 'completed': [], 'stages': [],
                   'synthetic': True, 'started_at': utcnow().isoformat(), 'limits': asdict(self.limits),
                   'baseline_threshold': BASELINE_THRESHOLD, 'alert_required': False}
            self.directory(run).mkdir()
            self.save(connection, run)
            return run

    def pending(self):
        with self.control() as connection:
            current = self.read(connection)
            return current['id'] if current and current['status'] == 'QUEUED' else None

    def status(self):
        with self.control() as connection:
            current = self.read(connection)
            history = [json.loads(r[0]) for r in connection.execute('SELECT body FROM runs ORDER BY rowid DESC LIMIT 20')]
        if current and current['status'] in ACTIVE:
            progress = self.directory(current) / 'progress.json'
            if progress.exists():
                current.update(json.loads(progress.read_text(encoding='utf-8')))
        if current and (self.directory(current) / 'lifecycle.sqlite').exists():
            engine = self.engine(current)
            with Session(engine) as db:
                for key, modality in [('deployment', current['modality']),
                                      ('other_modality', 'voice' if current['modality'] == 'face' else 'face')]:
                    row = db.get(ModalityDeployment, modality)
                    if row:
                        current[key] = {k: getattr(row, k) for k in ('state', 'champion_version', 'champion_threshold',
                            'challenger_version', 'traffic_percent', 'registry_name', 'evidence')}
                current['audit'] = [{'state': r.state, 'at': r.created_at.isoformat(), 'evidence': r.evidence}
                                   for r in db.scalars(select(LifecycleAudit).order_by(LifecycleAudit.created_at))]
            engine.dispose()
        return {'isolated': True, 'synthetic': True, 'current': current,
                'history': [{k: r.get(k) for k in ('id', 'scenario', 'modality', 'status', 'started_at')} for r in history]}

    def step(self, run_id, step):
        with self.control(write=True) as connection:
            run = self.read(connection, run_id)
            current = self.read(connection)
            if not run or not current or current['id'] != run_id or run['status'] in {'RESET', 'FAILED'}:
                raise ValueError('Simulation inactive; stale task rejected')
            if (self.directory(run) / 'cancel').exists():
                raise ValueError('Simulation inactive; reset requested')
            if step in run['completed']:
                return run
            expected = self.steps[len(run['completed'])] if len(run['completed']) < len(self.steps) else None
            if step != expected:
                raise ValueError(f'Expected {expected}, received {step}')
            run.update(status='RUNNING', phase=step.upper())
            self.artifact(run, 'progress', {'phase': run['phase'], 'stages': run['stages']})
            mlflow.set_tracking_uri(self.tracking)
            try:
                getattr(self, '_' + step)(run)
                run['completed'].append(step)
            except Exception as exc:
                run.update(status='FAILED', error=str(exc)[:1000])
                self.save(connection, run)
                # Keep error state durable so reset can recover a partially completed step.
                connection.commit()
                raise
            self.save(connection, run)
        return run

    def _prepare(self, run):
        engine = self.engine(run)
        Base.metadata.create_all(engine)
        client = MlflowClient(tracking_uri=self.tracking)
        run['baseline_versions'] = {}
        with Session(engine) as db:
            for modality in ('face', 'voice'):
                name = f"simulation-{run['id']}-{modality}"
                version = register_policy(modality, BASELINE_THRESHOLD, {}, {},
                    {'source': 'synthetic', 'simulation_id': run['id'], 'dataset_version': 'baseline',
                     'training_window': run['id'] + '-baseline-' + modality}, registry_name=name)
                client.set_registered_model_alias(name, 'champion', version)
                client.set_model_version_tag(name, version, 'lifecycle_status', 'CHAMPION')
                run['baseline_versions'][modality] = version
                db.add(ModalityDeployment(modality=modality, registry_name=name,
                    champion_version=version, champion_threshold=BASELINE_THRESHOLD))
                if modality == run['modality']:
                    run['baseline_version'] = version
            db.commit()
        engine.dispose()
        self.artifact(run, 'reference', window('baseline', run['seed'], drift=False))

    def _drift(self, run):
        reference = json.loads((self.directory(run) / 'reference.json').read_text())
        reports, previous = [], None
        for index in range(3):
            rows = window(f'{run["id"]}-drift-{index}', run['seed'] + index + 1)
            previous = evaluate(reference, rows, run['modality'], run['baseline_version'],
                                f'{run["id"]}-w{index}', previous)
            self.artifact(run, f'drift-input-{index}', rows)
            reports.append(previous)
        self.artifact(run, 'drift-reports', reports)
        run['drift'] = {k: previous[k] for k in ('decision', 'quality', 'embedding', 'performance', 'persistence', 'reason')}
        if previous['decision'] != 'RETRAIN_REQUIRED':
            raise ValueError('Real decision engine did not request retraining')
        run['alert_required'] = True

    def _train(self, run):
        if run['drift']['decision'] != 'RETRAIN_REQUIRED':
            raise ValueError('Retraining requires persistent drift evidence')
        rows = dataset(run['seed'] + 100)
        self.artifact(run, 'training-dataset', rows)
        digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        threshold, metrics, evaluation = identity_evaluation(rows)
        holdout = set(evaluation['holdout_identities'])
        positive, negative = policy_scores([r for r in rows if r['person_id'] in holdout])
        evidence = {'positive': positive.tolist(), 'negative': negative.tolist(), 'evaluation': evaluation}
        self.artifact(run, 'evaluation', evidence)
        engine = self.engine(run)
        with Session(engine) as db:
            row = db.get(ModalityDeployment, run['modality'])
            audit_transition(db, row, 'TRAINING', {'dataset_version': digest, 'synthetic': True})
            db.commit()
            version = register_policy(run['modality'], threshold, metrics, evidence,
                {'source': 'synthetic', 'simulation_id': run['id'], 'dataset_version': digest,
                 'training_window': run['id'], 'model_family': 'cosine-threshold-policy'}, row.registry_name)
            run.update(candidate_version=version, candidate_threshold=threshold, metrics=metrics, dataset_version=digest)
            audit_transition(db, row, 'CANDIDATE', {'candidate_version': version})
            db.commit()
        engine.dispose()

    def _offline(self, run):
        scores = json.loads((self.directory(run) / 'evaluation.json').read_text())
        result = paired_gate(scores['positive'], scores['negative'], BASELINE_THRESHOLD,
                             run['candidate_threshold'], run['metrics'], self.limits)
        run['offline'] = result
        engine = self.engine(run)
        with Session(engine) as db:
            row = db.get(ModalityDeployment, run['modality'])
            audit_transition(db, row, 'OFFLINE_EVALUATION', result)
            if not result['passed']:
                audit_transition(db, row, 'REJECTED', {'offline': result})
                db.commit()
                raise ValueError('Offline gate rejected candidate')
            client = MlflowClient(tracking_uri=self.tracking)
            client.set_registered_model_alias(row.registry_name, 'challenger', run['candidate_version'])
            row.state = 'CHAMPION'
            start_challenger(db, row, run['candidate_version'], run['candidate_threshold'], result)
            db.commit()
        engine.dispose()

    def _traffic(self, run, row, failure=False):
        import requests
        rows = window(f'{run["id"]}-{row.state}-{row.traffic_percent}', run['seed'] + 200,
                      count=self.limits.min_samples, security_failure=failure)
        with requests.Session() as transport:
            for index, observation in enumerate(rows):
                if (self.directory(run) / 'cancel').exists():
                    raise ValueError('Simulation inactive; reset requested')
                body = {'run_id': run['id'], 'cohort': f'{run["id"]}/{index}',
                        'embedding': observation['embedding'], 'template': observation['template']}
                if self.verify_url:
                    response = transport.post(self.verify_url, json=body, headers={'X-Simulation-Key': self.token}, timeout=15)
                    response.raise_for_status()
                    result = response.json()
                else:
                    result = self.policy_response(row, body)
                observation.update(result)
        return rows

    @staticmethod
    def policy_response(row, body):
        from app.biometrics import cosine
        score = cosine(body['embedding'], body['template'])
        started = time.perf_counter()
        selected = route(row, body['cohort'])
        decision = score >= selected['threshold']
        policy_ms = (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        candidate = score >= (row.challenger_threshold if row.challenger_threshold is not None else row.champion_threshold)
        return {'score': score, 'threshold': row.champion_threshold, 'served_candidate': selected['candidate'],
                'served_version': selected['version'], 'served_threshold': selected['threshold'], 'served_decision': decision,
                'challenger_score': score, 'challenger_threshold': row.challenger_threshold,
                'challenger_decision': candidate, 'policy_latency_ms': policy_ms,
                'challenger_latency_ms': (time.perf_counter() - started) * 1000}

    def verify(self, body):
        with self.control() as connection:
            run = self.read(connection, body['run_id'])
            current = self.read(connection)
        if not run or current['id'] != run['id'] or run['status'] in {'RESET', 'FAILED'} or (self.directory(run) / 'cancel').exists():
            raise ValueError('Simulation inactive')
        engine = self.engine(run)
        with Session(engine) as db:
            row = db.get(ModalityDeployment, run['modality'])
            if row is None:
                raise ValueError('Baseline not initialized')
            result = self.policy_response(row, body)
        engine.dispose()
        return result

    def _stage(self, run, db, row):
        failure = run['scenario'] == 'rollback' and row.state == 'CANARY' and row.traffic_percent >= 25
        observations = self._traffic(run, row, failure)
        summary = {'stage': row.state, 'traffic_percent': row.traffic_percent, 'samples': len(observations),
                   'served_candidate': sum(o['served_candidate'] for o in observations),
                   'response_mismatches': sum(o['served_decision'] != (o['score'] >= o['served_threshold']) for o in observations),
                   'fault_injected': failure, 'at': utcnow().isoformat()}
        self.artifact(run, f"traffic-{row.state}-{int(row.traffic_percent)}", observations)
        deadline = time.monotonic() + self.limits.min_seconds
        while time.monotonic() < deadline:
            if (self.directory(run) / 'cancel').exists():
                raise ValueError('Simulation inactive; reset requested')
            time.sleep(.1)
        advance(db, row, observations, self.limits)
        reconcile_registry(db, row, MlflowClient(tracking_uri=self.tracking))
        summary['evaluation'] = row.evidence.get('live', {})
        run['stages'].append(summary)
        db.commit()
        self.artifact(run, 'progress', {'phase': 'CANARY' if row.state == 'CANARY' else row.state, 'stages': run['stages']})

    def _shadow(self, run):
        engine = self.engine(run)
        with Session(engine) as db:
            row = db.get(ModalityDeployment, run['modality'])
            self._stage(run, db, row)
            if row.state != 'CANARY':
                raise ValueError('Shadow did not pass')
        engine.dispose()

    def _canary(self, run):
        engine = self.engine(run)
        with Session(engine) as db:
            row = db.get(ModalityDeployment, run['modality'])
            for _ in self.limits.stages:
                if row.state != 'CANARY':
                    break
                self._stage(run, db, row)
            if row.state == 'FAILED_CANARY':
                probe = self._traffic(run, row)
                run['rollback_probe'] = {'samples': len(probe), 'served_candidate': sum(o['served_candidate'] for o in probe),
                                         'versions': sorted({o['served_version'] for o in probe})}
                self.artifact(run, 'rollback-probe', probe)
                run['status'] = 'ROLLED_BACK'
            elif row.state == 'CHAMPION':
                probe = self._traffic(run, row)
                run['champion_probe'] = {'versions': sorted({o['served_version'] for o in probe}), 'samples': len(probe)}
                self.artifact(run, 'champion-probe', probe)
                run['status'] = 'SUCCEEDED'
            else:
                raise ValueError(f'Canary incomplete: {row.state}')
            run['phase'] = row.state
        engine.dispose()

    def reset(self):
        # Signal first, then wait for the in-flight step to release its transaction.
        with self.control() as connection:
            run = self.read(connection)
        if not run:
            return self.status()
        (self.directory(run) / 'cancel').touch()
        with self.control(write=True) as connection:
            run = self.read(connection, run['id'])
            if run['status'] != 'RESET':
                self.artifact(run, 'result-before-reset', run)
            if run['status'] != 'RESET' and (self.directory(run) / 'lifecycle.sqlite').exists():
                client = MlflowClient(tracking_uri=self.tracking)
                engine = self.engine(run)
                with Session(engine) as db:
                    for row in db.scalars(select(ModalityDeployment)):
                        baseline = run.get('baseline_versions', {}).get(row.modality, '1')
                        client.set_registered_model_alias(row.registry_name, 'champion', baseline)
                        client.set_model_version_tag(row.registry_name, baseline, 'lifecycle_status', 'CHAMPION')
                        if row.champion_version != baseline:
                            client.set_model_version_tag(row.registry_name, row.champion_version, 'lifecycle_status', 'RESET_TO_BASELINE')
                        for alias in ('challenger', 'candidate', 'previous_champion'):
                            version = client.get_registered_model(row.registry_name)
                            if alias in version.aliases:
                                client.delete_registered_model_alias(row.registry_name, alias)
                        row.champion_version, row.champion_threshold = baseline, BASELINE_THRESHOLD
                        row.challenger_version = row.challenger_threshold = None
                        row.previous_version = row.previous_threshold = None
                        row.traffic_percent, row.stage_index = 0, 0
                        row.evidence = {}
                        audit_transition(db, row, 'CHAMPION', {'baseline_restored': True, 'synthetic': True})
                    db.commit()
                engine.dispose()
            run.update(status='RESET', phase='BASELINE', alert_required=False)
            self.save(connection, run)
        return self.status()

    def recover(self):
        with self.control(write=True) as connection:
            run = self.read(connection)
            if run and run['status'] in ACTIVE and (self.directory(run) / 'progress.json').exists():
                run.update(status='FAILED', error='Simulation service restarted during a step; restore baseline before retrying')
                self.save(connection, run)
