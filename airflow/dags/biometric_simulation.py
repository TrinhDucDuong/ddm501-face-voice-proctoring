"""Classroom replay on isolated storage; never invokes production training DAGs."""
import os
import time
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator


def call(path, body):
    response = requests.post(os.environ['SIMULATION_SERVICE_URL'] + path,
        headers={'X-Simulation-Key': os.environ['SIMULATION_KEY']}, json=body, timeout=240)
    response.raise_for_status()
    return response.json()


def claim(run_id):
    if not os.getenv('SIMULATION_SERVICE_URL'):
        raise AirflowSkipException('Simulation service not configured')
    run = call('/internal/claim', {'airflow_run_id': run_id})['run_id']
    if not run:
        raise AirflowSkipException('No queued simulation')
    return run


def execute(step, ti):
    for _ in range(18):
        try:
            call('/internal/step', {'run_id': ti.xcom_pull(task_ids='claim_simulation'), 'step': step})
            return
        except requests.HTTPError as exc:
            if exc.response.status_code == 409 and 'inactive' in exc.response.text:
                raise AirflowSkipException('Simulation reset; stale task stopped') from exc
            if exc.response.status_code != 425:
                raise
            time.sleep(5)
    raise RuntimeError('Simulation alert was not delivered within 90 seconds')


def failed(context):
    ti = context['ti']
    run_id = ti.xcom_pull(task_ids='claim_simulation')
    if run_id:
        call('/internal/fail', {'run_id': run_id, 'task': ti.task_id})


with DAG('biometric_simulation', start_date=datetime(2026, 1, 1), schedule='* * * * *',
         catchup=False, max_active_runs=1, is_paused_upon_creation=False,
         default_args={'owner': 'simulation', 'retries': 1, 'retry_delay': timedelta(seconds=10),
                       'execution_timeout': timedelta(minutes=5), 'on_failure_callback': failed}, tags=['synthetic', 'isolated-demo']) as dag:
    previous = PythonOperator(task_id='claim_simulation', python_callable=claim)
    for phase in ('prepare', 'drift', 'train', 'offline', 'shadow', 'canary'):
        task = PythonOperator(task_id=phase, python_callable=execute, op_kwargs={'step': phase})
        previous >> task
        previous = task
