from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "ml-platform", "retries": 1, "retry_delay": timedelta(minutes=2),
    "env": {"SNAPSHOT_PATH": "/opt/project/data/snapshots/snapshot-{{ ts_nodash }}.json"},
    "append_env": True,
}

with DAG(
    dag_id="biometric_model_pipeline",
    description="Ingest, validate, feature/calibrate, evaluate, register, promote and deploy",
    start_date=datetime(2026, 1, 1),
    schedule="0 2 * * 0",
    catchup=False,
    default_args=default_args,
    max_active_runs=1,
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
