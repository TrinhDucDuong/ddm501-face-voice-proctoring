from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


def training_failure(context):
    import os

    import requests

    conf = context['dag_run'].conf
    if conf.get('modality') in ('face', 'voice'):
        response = requests.post(os.environ['API_URL'].rstrip('/') +
            f"/v1/admin/lifecycle/{conf['modality']}/training-failed",
            headers={'X-API-Key': os.environ['API_KEY']}, json={'window_id': conf.get('window_id', '')}, timeout=30)
        response.raise_for_status()

default_args = {
    "owner": "ml-platform", "retries": 1, "retry_delay": timedelta(minutes=2),
    "env": {"SNAPSHOT_PATH": "/opt/project/data/snapshots/snapshot-{{ ts_nodash }}-{{ dag_run.conf.get('modality', 'invalid') }}.json",
            "MODEL_MODALITY": "{{ dag_run.conf.get('modality', 'invalid') }}",
            "TRAINING_WINDOW_ID": "{{ dag_run.conf.get('window_id', '') }}"},
    "append_env": True,
    "on_failure_callback": training_failure,
}

with DAG(
    dag_id="biometric_model_pipeline",
    description="Ingest, validate, feature/calibrate, evaluate, register, promote and deploy",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    default_args=default_args,
    max_active_runs=2,
    tags=["ddm501", "biometrics", "mlflow"],
) as dag:
    ingest = BashOperator(
        task_id="ingest_versioned_snapshot",
        bash_command="python /opt/project/pipeline/snapshot_stats.py",
    )
    validate = BashOperator(
        task_id="validate_data_quality",
        bash_command="python /opt/project/pipeline/validate_data.py",
    )
    publish_dataset = BashOperator(
        task_id="publish_versioned_dataset",
        bash_command="cd /opt/project && python -m pipeline.dataset_ledger",
    )
    train = BashOperator(
        task_id="feature_engineer_train_register_candidate",
        bash_command="python /opt/project/pipeline/calibrate_and_register.py",
    )
    evaluate = BashOperator(
        task_id="evaluate_and_promote_candidate",
        bash_command="python /opt/project/pipeline/promotion_gate.py",
    )
    responsible_ai_audit = BashOperator(
        task_id="generate_responsible_ai_audit",
        bash_command="python /opt/project/pipeline/responsible_ai_report.py",
    )
    reload_champion = BashOperator(
        task_id="reload_current_champion",
        bash_command="cd /opt/project && python -m pipeline.model_rollout",
    )
    ingest >> validate >> publish_dataset >> train >> responsible_ai_audit >> evaluate >> reload_champion
