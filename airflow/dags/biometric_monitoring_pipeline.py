"""Batch monitoring and guarded continuous-training trigger."""
import json
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.models.dagrun import DagRun
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator


def branch_on_evidence(ti):
    summary = json.loads(Path('/opt/project/data/monitoring/latest.json').read_text(encoding='utf-8'))
    requested = [row for row in summary.get('modalities', []) if row['trigger_training']]
    if not requested:
        return 'no_training_needed'
    ti.xcom_push(key='training_requests', value=requested)
    return 'trigger_candidate_training'


def trigger_modalities(ti):
    from airflow.api.common.trigger_dag import trigger_dag

    for row in ti.xcom_pull(task_ids='decide_retraining', key='training_requests') or []:
        run_id = f"monitor__{row['modality']}__{row['current_window'][:32]}"
        if not DagRun.find(dag_id='biometric_model_pipeline', run_id=run_id):
            trigger_dag('biometric_model_pipeline', run_id=run_id,
                        conf={'modality': row['modality'], 'window_id': row['current_window']})


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
    trigger = PythonOperator(task_id='trigger_candidate_training', python_callable=trigger_modalities)
    no_training = EmptyOperator(task_id='no_training_needed')
    collect >> decide >> [trigger, no_training]
