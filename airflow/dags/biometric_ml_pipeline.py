from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {"owner": "ml-platform", "retries": 1, "retry_delay": timedelta(minutes=2)}

with DAG(
    dag_id="biometric_model_pipeline",
    description="Snapshot, calibrate, register and hot-reload face/voice decision thresholds",
    start_date=datetime(2026, 1, 1),
    schedule="0 2 * * 0",
    catchup=False,
    default_args=default_args,
    max_active_runs=1,
    tags=["ddm501", "biometrics", "mlflow"],
) as dag:
    snapshot = BashOperator(
        task_id="snapshot_dataset_stats",
        bash_command="python /opt/project/pipeline/snapshot_stats.py",
    )
    calibrate = BashOperator(
        task_id="calibrate_and_register_candidate",
        bash_command="python /opt/project/pipeline/calibrate_and_register.py",
    )
    reload_champion = BashOperator(
        task_id="reload_current_champion",
        bash_command="python -c \"import os,requests; r=requests.post(os.environ['API_URL']+'/v1/admin/reload-model',headers={'X-API-Key':os.environ['API_KEY']},timeout=60); r.raise_for_status(); print(r.json())\"",
    )
    snapshot >> calibrate >> reload_champion

