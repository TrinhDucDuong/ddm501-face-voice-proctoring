"""Batch monitoring and guarded continuous-training trigger."""
import json
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.models.dagrun import DagRun

from pipeline.monitoring_job import training_run_id


def branch_on_evidence(ti):
    summary = json.loads(Path('/opt/project/data/monitoring/latest.json').read_text(encoding='utf-8'))
    requested = next((row for row in summary['tenants'] if row['trigger_training']), None)
    if requested is None:
        return 'no_training_needed'
    run_id = training_run_id(requested)
    if DagRun.find(dag_id='biometric_model_pipeline', run_id=run_id):
        return 'no_training_needed'
    ti.xcom_push(key='target_run_id', value=run_id)
    return 'trigger_candidate_training'


with DAG(
    dag_id='biometric_monitoring_pipeline',
    description='Snapshot tenant telemetry, evaluate drift and reviewed quality, request candidate training',
    start_date=datetime(2026, 1, 1), schedule='0 * * * *', catchup=False,
    max_active_runs=1, default_args={'owner': 'ml-platform', 'retries': 1,
                                     'retry_delay': timedelta(minutes=2)},
    tags=['ddm501', 'monitoring', 'drift'],
) as dag:
    collect = BashOperator(task_id='collect_versioned_monitoring_windows',
                           bash_command='cd /opt/project && python -m pipeline.monitoring_job')
    decide = BranchPythonOperator(task_id='decide_retraining', python_callable=branch_on_evidence)
    trigger = TriggerDagRunOperator(task_id='trigger_candidate_training',
                                    trigger_dag_id='biometric_model_pipeline',
                                    trigger_run_id='{{ ti.xcom_pull(task_ids="decide_retraining", key="target_run_id") }}',
                                    wait_for_completion=False)
    no_training = EmptyOperator(task_id='no_training_needed')
    collect >> decide >> [trigger, no_training]
