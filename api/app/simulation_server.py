"""Dedicated process: no production credentials, database or registry mounts."""
import hmac
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, FiniteFloat

from pipeline.simulation_runner import SimulationRunner


def create_app(root, key, stage_seconds=5, verify_url=None):
    if not key:
        raise ValueError('A simulation service key is required')
    runner = SimulationRunner(root, stage_seconds, verify_url, key)

    @asynccontextmanager
    async def lifespan(_):
        runner.recover()
        yield

    app = FastAPI(title='Isolated synthetic lifecycle lab', lifespan=lifespan)
    app.state.runner = runner

    def authorized(x_simulation_key: str = Header(default='')):
        if not hmac.compare_digest(x_simulation_key, key):
            raise HTTPException(401, 'Invalid simulation service key')

    @app.exception_handler(ValueError)
    async def invalid(_, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={'detail': str(exc)})

    @app.get('/health')
    def health():
        return {'status': 'healthy', 'synthetic': True, 'isolated': True}

    @app.get('/state', dependencies=[Depends(authorized)])
    def state():
        result = runner.status()
        with sqlite3.connect(Path(root) / 'alerts.sqlite') as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS alerts (body TEXT)')
            result['alerts'] = [json.loads(row[0]) for row in connection.execute('SELECT body FROM alerts ORDER BY rowid DESC LIMIT 20')]
        return result

    @app.post('/runs', dependencies=[Depends(authorized)], status_code=202)
    def start(body: Start):
        return runner.start(body.scenario, body.modality, body.seed)

    @app.post('/reset', dependencies=[Depends(authorized)])
    def reset():
        return runner.reset()

    @app.post('/internal/claim', dependencies=[Depends(authorized)])
    def claim(body: Claim):
        with runner.control(write=True) as connection:
            run = runner.read(connection)
            if run and run['status'] == 'RUNNING' and run.get('airflow_run_id') == body.airflow_run_id:
                return {'run_id': run['id']}
            if not run or run['status'] != 'QUEUED':
                return {'run_id': None}
            run.update(status='RUNNING', airflow_run_id=body.airflow_run_id)
            runner.save(connection, run)
        return {'run_id': run['id']}

    @app.post('/internal/step', dependencies=[Depends(authorized)])
    def step(body: Step):
        if body.step == 'train':
            with sqlite3.connect(Path(root) / 'alerts.sqlite') as connection:
                connection.execute('CREATE TABLE IF NOT EXISTS alerts (body TEXT)')
                received = any(json.loads(r[0]).get('run_id') == body.run_id and json.loads(r[0]).get('status') == 'firing'
                               for r in connection.execute('SELECT body FROM alerts'))
            if not received:
                raise HTTPException(425, 'Waiting for real Prometheus/Alertmanager delivery')
        return runner.step(body.run_id, body.step)

    @app.post('/internal/verify', dependencies=[Depends(authorized)])
    def verify(body: Probe):
        return runner.verify(body.model_dump())

    @app.post('/internal/fail', dependencies=[Depends(authorized)])
    def fail(body: ClaimFailure):
        with runner.control(write=True) as connection:
            run = runner.read(connection, body.run_id)
            if run and run['status'] in {'QUEUED', 'RUNNING'}:
                run.update(status='FAILED', error='Airflow task failed: ' + body.task)
                runner.save(connection, run)
        return {'recorded': True}

    @app.get('/evidence/{run_id}', dependencies=[Depends(authorized)])
    def evidence(run_id: str):
        with runner.control() as connection:
            run = runner.read(connection, run_id)
        if run is None:
            raise HTTPException(404, 'Unknown simulation')
        return {'run': run, 'artifacts': {p.name: json.loads(p.read_text(encoding='utf-8'))
                for p in runner.directory(run).glob('*.json') if p.name != 'progress.json'}}

    @app.post('/alerts')
    def alerts(body: dict):
        # This sink is intentionally separate from customer/Telegram notifications.
        accepted = []
        for alert in body.get('alerts', [])[:20]:
            labels = alert.get('labels', {})
            if labels.get('synthetic') == 'true' and labels.get('alertname') == 'SimulationRetrainRequired':
                with runner.control() as connection:
                    run = runner.read(connection, labels.get('run_id'))
                if not run or not run.get('alert_required') or run['modality'] != labels.get('modality'):
                    continue
                accepted.append({'status': alert.get('status'), 'modality': labels.get('modality'),
                                 'run_id': run['id'],
                                 'alertname': labels['alertname'], 'startsAt': alert.get('startsAt'),
                                 'received_at': datetime.now(timezone.utc).isoformat()})
        with sqlite3.connect(Path(root) / 'alerts.sqlite') as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS alerts (body TEXT)')
            connection.executemany('INSERT INTO alerts VALUES (?)', [(json.dumps(a),) for a in accepted])
            connection.execute('DELETE FROM alerts WHERE rowid NOT IN (SELECT rowid FROM alerts ORDER BY rowid DESC LIMIT 100)')
        return {'received': len(accepted)}

    @app.get('/metrics')
    def metrics():
        state = runner.status()['current'] or {}
        lines = []
        for modality in ('face', 'voice'):
            selected = state.get('modality') == modality
            value = int(selected and state.get('alert_required', False))
            run_id = state.get('id', 'none')
            lines.append(f'simulation_retrain_required{{modality="{modality}",synthetic="true",run_id="{run_id}"}} {value}')
            percent = state.get('deployment', {}).get('traffic_percent', 0) if selected else 0
            lines.append(f'simulation_canary_percent{{modality="{modality}",synthetic="true"}} {percent}')
        return Response('\n'.join(lines) + '\n', media_type='text/plain')

    return app


class Start(BaseModel):
    scenario: Literal['promotion', 'rollback']
    modality: Literal['face', 'voice'] = 'voice'
    seed: int = Field(default=501, ge=0, le=1000000)


class Claim(BaseModel):
    airflow_run_id: str = Field(max_length=250)


class Step(BaseModel):
    run_id: str = Field(max_length=36)
    step: Literal['prepare', 'drift', 'train', 'offline', 'shadow', 'canary']


class Probe(BaseModel):
    run_id: str = Field(max_length=36)
    cohort: str = Field(max_length=150)
    embedding: list[FiniteFloat] = Field(min_length=201, max_length=201)
    template: list[FiniteFloat] = Field(min_length=201, max_length=201)


class ClaimFailure(BaseModel):
    run_id: str = Field(max_length=36)
    task: str = Field(max_length=100)


def application():
    return create_app(os.environ['SIMULATION_ROOT'], os.environ['SIMULATION_KEY'],
                      int(os.getenv('SIMULATION_STAGE_SECONDS', '5')),
                      'http://127.0.0.1:8000/internal/verify')
