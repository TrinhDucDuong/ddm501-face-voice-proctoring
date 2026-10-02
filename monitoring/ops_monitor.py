"""Aggregate operational telemetry and deliver Alertmanager notifications to Telegram."""
import asyncio
import json
import logging
import math
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from html import escape
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Request
from prometheus_client import Counter, Gauge, make_asgi_app
from sqlalchemy import create_engine, text

from pipeline.data_snapshot import extract
from pipeline.responsible_ai_report import QUERY, build_report
from pipeline.validate_data import validate

from .telegram import request_telegram

LOGGER = logging.getLogger('ops-monitor')
COLLECTION = Gauge('biometric_ops_collection_success', 'Latest component collection result', ['component'])
LAST = Gauge('biometric_ops_last_success_unixtime', 'Latest successful collection', ['component'])
SERVICE = Gauge('biometric_service_health', 'HTTP readiness of platform service', ['service'])
PROBE_LATENCY = Gauge('biometric_service_probe_seconds', 'Service health probe duration', ['service'])
TRAINING = Gauge('biometric_training_samples', 'Training samples in the selected tenant', ['modality'])
IDENTITIES = Gauge('biometric_training_identities', 'Training identities', ['modality'])
DIMENSION = Gauge('biometric_embedding_dimension', 'Validated embedding dimension', ['modality'])
VALID = Gauge('biometric_training_data_valid', 'Training data quality gate')
REGISTRY_INFO = Gauge('biometric_registry_model_info', 'Current Registry alias', ['alias', 'version', 'evaluation'])
MODEL_METRIC = Gauge('biometric_registry_evaluation', 'Offline model evaluation, not live accuracy', ['alias', 'modality', 'metric'])
THRESHOLD = Gauge('biometric_registry_threshold', 'Registered decision thresholds', ['alias', 'modality'])
PROMOTION = Gauge('biometric_candidate_gate_passed', 'Candidate gate: 1 passed, 0 rejected, NaN unevaluated')
MONITOR_PSI = Gauge('biometric_monitor_tenant_psi', 'Versioned tenant monitoring PSI',
                    ['tenant', 'model_version', 'feature'])
MONITOR_SAMPLES = Gauge('biometric_monitor_tenant_samples', 'Versioned tenant monitoring rows',
                        ['tenant', 'model_version', 'window'])
RETRAIN_RECOMMENDED = Gauge('biometric_retrain_recommended', 'Monitoring ETL recommends candidate training',
                           ['tenant', 'model_version', 'status'])
MONITOR_ETL_TIME = Gauge('biometric_monitoring_etl_unixtime', 'Latest batch monitoring ETL timestamp')
DAG_STATE = Gauge('biometric_airflow_latest_run_state', 'Latest DAG run state', ['state'])
DAG_TIME = Gauge('biometric_airflow_latest_run_unixtime', 'Latest DAG start time')
MONITOR_DAG_STATE = Gauge('biometric_monitoring_dag_state', 'Latest batch monitoring DAG run state', ['state'])
MONITOR_DAG_TIME = Gauge('biometric_monitoring_dag_unixtime', 'Latest batch monitoring DAG start time')
TASK_STATE = Gauge('biometric_airflow_task_success', 'Latest DAG task success', ['task'])
TASK_DURATION = Gauge('biometric_airflow_task_seconds', 'Latest task duration', ['task'])
RAI_METRIC = Gauge('biometric_fairness_slice', 'Quality fairness slices; human and synthetic separated', ['source', 'slice', 'metric'])
RAI_GATE = Gauge('biometric_fairness_status', 'Human quality fairness assessment', ['status'])
RAI_GAP = Gauge('biometric_fairness_accuracy_gap', 'Human quality-slice accuracy gap')
DB_SIZE = Gauge('biometric_database_bytes', 'Application database size')
DB_CONNECTIONS = Gauge('biometric_database_connections', 'Active PostgreSQL connections')
CONTAINER_CPU = Gauge('biometric_container_cpu_seconds_total', 'Cumulative Docker container CPU seconds', ['project', 'service', 'container'])
CONTAINER_MEMORY = Gauge('biometric_container_memory_bytes', 'Docker memory usage excluding reclaimable cache', ['project', 'service', 'container'])
CONTAINER_NETWORK = Gauge('biometric_container_network_bytes_total', 'Cumulative Docker network bytes', ['project', 'service', 'container', 'direction'])
CONTAINER_IO = Gauge('biometric_container_io_bytes_total', 'Cumulative Docker block IO bytes', ['project', 'service', 'container', 'operation'])
NOTIFICATIONS = Counter('biometric_alert_notifications_total', 'Notification deliveries', ['outcome'])
TELEGRAM = Gauge('biometric_telegram_configured', 'Telegram token and chat destination available')
REPORT_DIR = Path(os.getenv('REPORT_DIR', '/reports'))
PROBES = {'api': 'http://api:8000/ready', 'mlflow': 'http://mlflow:5000/health',
          'minio': 'http://minio:9000/minio/health/ready', 'airflow': 'http://airflow-webserver:8080/health',
          'portal': 'http://ui:8501/_stcore/health', 'legacy': 'http://legacy-demo:8000/health',
          'grafana': 'http://grafana:3000/api/health', 'prometheus': 'http://prometheus:9090/-/ready',
          'alertmanager': 'http://alertmanager:9093/-/ready', 'loki': 'http://loki:3100/ready'}


def write_report(name, report):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    content = json.dumps(report, indent=2, allow_nan=False, default=str)
    target = REPORT_DIR / (name + '.json')
    target.write_text(content, encoding='utf-8')
    (REPORT_DIR / (name + '.html')).write_text(
        '<!doctype html><html><head><meta charset="utf-8"><title>' + escape(name)
        + '</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto}pre{white-space:pre-wrap}</style>'
        + '</head><body><h1>' + escape(name) + '</h1><pre>' + escape(content) + '</pre></body></html>', encoding='utf-8')


def collect_monitoring():
    path = Path(os.getenv('MONITORING_SUMMARY_PATH', '/data/monitoring/latest.json'))
    report = json.loads(path.read_text(encoding='utf-8'))
    MONITOR_PSI.clear()
    MONITOR_SAMPLES.clear()
    RETRAIN_RECOMMENDED.clear()
    for row in report['tenants']:
        tenant, version = row['tenant_id'], row['model_version']
        for feature, value in row.get('psi', {}).items():
            if value is not None and math.isfinite(value):
                MONITOR_PSI.labels(tenant=tenant, model_version=version, feature=feature).set(value)
        for window in ('reference', 'current'):
            MONITOR_SAMPLES.labels(tenant=tenant, model_version=version, window=window).set(
                row[window + '_count'])
        RETRAIN_RECOMMENDED.labels(tenant=tenant, model_version=version,
                                   status=row['status']).set(int(row['trigger_training']))
    MONITOR_ETL_TIME.set(datetime.fromisoformat(report['calculated_at']).timestamp())
    return report


def format_alert(alert, monitor_summary=None):
    labels, annotations = alert.get('labels', {}), alert.get('annotations', {})
    name = labels.get('alertname', 'Alert')
    if name == 'BiometricTenantDataDrift':
        tenant = labels.get('tenant', 'unknown')
        row = next((item for item in (monitor_summary or {}).get('tenants', [])
                    if item['tenant_id'] == tenant), None)
        company = row['tenant_name'] if row else tenant
        sizes = f"{row['reference_count']}/{row['current_count']}" if row else 'chưa rõ'
        action = 'xem xét drift và nguồn dữ liệu'
        if row and row.get('recommendation') == 'train_candidate':
            action = 'đã yêu cầu train challenger; theo dõi gate trước khi đổi champion'
        return (f"⚠️ Drift dữ liệu · {company}\n"
                f"Model {labels.get('model_version', '?')} · feature {labels.get('feature', '?')}\n"
                f"Mẫu tham chiếu/hiện tại: {sizes}\nHành động: {action}")
    return f"{labels.get('severity', 'info')} · {name}: {annotations.get('summary', '')}"


def collect_database():
    db_engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
    try:
        with db_engine.connect() as connection:
            snapshot = extract(connection)
            try:
                quality = validate(snapshot['samples'])
                VALID.set(1)
            except ValueError as exc:
                quality = json.loads(str(exc))
                VALID.set(0)
            for modality in ('face', 'voice'):
                TRAINING.labels(modality=modality).set(quality['counts'].get(modality, 0))
                IDENTITIES.labels(modality=modality).set(quality['identities'].get(modality, 0))
                dims = quality['dimensions'].get(modality, [])
                DIMENSION.labels(modality=modality).set(dims[0] if len(dims) == 1 else math.nan)
            write_report('data-quality', {**quality, 'dataset_version': snapshot['dataset_version'],
                                          'tenant_scope': snapshot['tenant_scope'], 'checked_at': time.time()})
            rai = build_report([dict(row) for row in connection.execute(text(QUERY)).mappings()])
            RAI_METRIC.clear()
            for row in rai['slices']:
                for metric in ('reviewed', 'accuracy', 'false_accept_rate', 'false_reject_rate', 'genuine_count', 'impostor_count'):
                    value = row.get(metric)
                    RAI_METRIC.labels(source=row['label_source'], slice=row['quality_slice'], metric=metric).set(math.nan if value is None else value)
            for state in ('pass', 'review', 'insufficient_data'):
                RAI_GATE.labels(status=state).set(int(rai['gate'] == state))
            RAI_GAP.set(rai['max_accuracy_gap'] if rai['max_accuracy_gap'] is not None else math.nan)
            write_report('responsible-ai', rai)
            DB_SIZE.set(connection.execute(text('SELECT pg_database_size(current_database())')).scalar())
            DB_CONNECTIONS.set(connection.execute(text('SELECT count(*) FROM pg_stat_activity')).scalar())
    finally:
        db_engine.dispose()


def collect_registry():
    base = os.getenv('MLFLOW_TRACKING_URI', 'http://mlflow:5000').rstrip('/')
    model = os.getenv('MLFLOW_MODEL_NAME', 'face-voice-risk-bundle')
    output = {}
    REGISTRY_INFO.clear()
    MODEL_METRIC.clear()
    THRESHOLD.clear()
    PROMOTION.set(math.nan)
    for alias in ('champion', 'candidate', 'challenger'):
        response = requests.get(base + '/api/2.0/mlflow/registered-models/alias',
                                params={'name': model, 'alias': alias}, timeout=10)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        version = response.json()['model_version']
        response = requests.get(base + '/api/2.0/mlflow/runs/get', params={'run_id': version['run_id']}, timeout=10)
        response.raise_for_status()
        run = response.json()['run']['data']
        params = {p['key']: p['value'] for p in run['params']}
        REGISTRY_INFO.labels(alias=alias, version=version['version'], evaluation=params.get('evaluation_method', 'legacy-pair-cv')).set(1)
        metrics = {p['key']: p['value'] for p in run['metrics']}
        for modality in ('face', 'voice'):
            for metric in ('far', 'frr', 'cv_far', 'cv_frr', 'holdout_far', 'holdout_frr'):
                MODEL_METRIC.labels(alias=alias, modality=modality, metric=metric).set(metrics.get(modality + '_' + metric, math.nan))
            THRESHOLD.labels(alias=alias, modality=modality).set(float(params.get(modality + '_threshold', 'nan')))
        tags = {t['key']:t['value'] for t in version.get('tags', [])}
        if alias == 'candidate' and tags.get('promotion_status') in {'passed', 'rejected'}:
            PROMOTION.set(int(tags['promotion_status'] == 'passed'))
        output[alias] = {'version': version['version'], 'params': params, 'metrics': metrics, 'promotion_status': tags.get('promotion_status', 'not_evaluated')}
    write_report('model-evaluation', output)


def collect_airflow():
    db_engine = create_engine(os.environ['AIRFLOW_DATABASE_URL'], pool_pre_ping=True)
    try:
        with db_engine.connect() as connection:
            row = connection.execute(text("SELECT run_id, state, start_date, end_date FROM dag_run WHERE dag_id='biometric_model_pipeline' ORDER BY execution_date DESC LIMIT 1")).mappings().first()
            TASK_STATE.clear()
            TASK_DURATION.clear()
            DAG_TIME.set(math.nan)
            for state in ('success', 'failed', 'running', 'queued', 'no_run'):
                DAG_STATE.labels(state=state).set(int((row['state'] if row else 'no_run') == state))
            if row is None:
                return
            if row['start_date']:
                DAG_TIME.set(row['start_date'].timestamp())
            tasks = [dict(t) for t in connection.execute(text("SELECT task_id, state, start_date, end_date FROM task_instance WHERE dag_id='biometric_model_pipeline' AND run_id=:run"), {'run':row['run_id']}).mappings()]
            for task in tasks:
                TASK_STATE.labels(task=task['task_id']).set(int(task['state'] == 'success'))
                duration = (task['end_date'] - task['start_date']).total_seconds() if task['end_date'] and task['start_date'] else math.nan
                TASK_DURATION.labels(task=task['task_id']).set(duration)
            write_report('pipeline-status', {'run':dict(row), 'tasks':tasks})
    finally:
        db_engine.dispose()


def collect_monitoring_dag():
    db_engine = create_engine(os.environ['AIRFLOW_DATABASE_URL'], pool_pre_ping=True)
    try:
        with db_engine.connect() as connection:
            row = connection.execute(text("""
                SELECT run_id, state, start_date FROM dag_run
                WHERE dag_id='biometric_monitoring_pipeline'
                ORDER BY execution_date DESC LIMIT 1
            """)).mappings().first()
            for state in ('success', 'failed', 'running', 'queued', 'no_run'):
                MONITOR_DAG_STATE.labels(state=state).set(int((row['state'] if row else 'no_run') == state))
            MONITOR_DAG_TIME.set(row['start_date'].timestamp() if row and row['start_date'] else math.nan)
    finally:
        db_engine.dispose()


def collect_containers():
    base = os.getenv('DOCKER_API_URL', 'http://docker-observer:2375').rstrip('/')
    project = os.getenv('COMPOSE_PROJECT_NAME', 'ddm501-biometric-demo')
    response = requests.get(base + '/containers/json',
                            params={'filters':json.dumps({'label':['com.docker.compose.project=' + project]})}, timeout=10)
    response.raise_for_status()
    containers = response.json()
    readings = []
    for container in containers:
        labels = container['Labels']
        if labels.get('com.docker.compose.project') != project:
            continue
        response = requests.get(base + '/containers/' + container['Id'] + '/stats',
                                params={'stream':'false', 'one-shot':'true'}, timeout=10)
        response.raise_for_status()
        readings.append((container, response.json()))
    # Publish a complete cycle, so disappearing containers do not leave stale series.
    for metric in (CONTAINER_CPU, CONTAINER_MEMORY, CONTAINER_NETWORK, CONTAINER_IO):
        metric.clear()
    for container, stats in readings:
        labels = {'project':project,'service':container['Labels']['com.docker.compose.service'],
                  'container':container['Id'][:12]}
        CONTAINER_CPU.labels(**labels).set(stats['cpu_stats']['cpu_usage']['total_usage'] / 1e9)
        memory = stats.get('memory_stats', {})
        cache = memory.get('stats', {}).get('inactive_file', memory.get('stats', {}).get('total_inactive_file', 0))
        CONTAINER_MEMORY.labels(**labels).set(max(0, memory.get('usage', 0) - cache))
        for direction in ('rx', 'tx'):
            CONTAINER_NETWORK.labels(**labels,direction=direction).set(
                sum(n.get(direction + '_bytes', 0) for n in stats.get('networks', {}).values()))
        for operation in ('Read','Write'):
            CONTAINER_IO.labels(**labels,operation=operation.lower()).set(sum(
                r['value'] for r in stats.get('blkio_stats', {}).get('io_service_bytes_recursive', []) or []
                if r['op'].lower() == operation.lower()))


def send_telegram(payload):
    token, chat = os.getenv('TELEGRAM_BOT_TOKEN', ''), os.getenv('TELEGRAM_CHAT_ID', '')
    TELEGRAM.set(int(bool(token and chat)))
    if not token or not chat:
        NOTIFICATIONS.labels(outcome='not_configured').inc()
        return False
    lines = ['DDM501 Face Voice Proctoring — ' + str(payload.get('status', 'unknown'))]
    try:
        monitoring = json.loads(Path(os.getenv('MONITORING_SUMMARY_PATH', '/data/monitoring/latest.json'))
                                .read_text(encoding='utf-8'))
    except (OSError, ValueError):
        monitoring = None
    for alert in payload.get('alerts', [])[:15]:
        lines.append(format_alert(alert, monitoring))
    lines.append(os.getenv('PUBLIC_GRAFANA_URL', 'http://localhost:13000/d/biometric-overview'))
    try:
        status, result = request_telegram(token, 'sendMessage', {'chat_id': chat, 'text': '\n'.join(lines)[:4000]})
        successful = 200 <= status < 300 and result.get('ok', False)
    except (RuntimeError, ValueError):
        # Never log exceptions containing the request URL, because it includes the token.
        successful = False
    NOTIFICATIONS.labels(outcome='success' if successful else 'failure').inc()
    return successful


def run_once():
    for component, function in [('database', collect_database), ('registry', collect_registry),
                                ('airflow', collect_airflow), ('monitoring_dag', collect_monitoring_dag),
                                ('docker', collect_containers),
                                ('monitoring', collect_monitoring)]:
        COLLECTION.labels(component=component).set(0)
        try:
            function()
            COLLECTION.labels(component=component).set(1)
            LAST.labels(component=component).set_to_current_time()
        except Exception as exc:
            LOGGER.warning('Collection failed component=%s type=%s', component, type(exc).__name__)
    disabled = set(os.getenv('OPS_DISABLED_PROBES', '').split(','))
    for name, url in PROBES.items():
        if name in disabled:
            continue
        started = time.monotonic()
        try:
            response = requests.get(url, timeout=3)
            healthy = response.ok
            if name == 'airflow' and healthy:
                healthy = response.json()['scheduler']['status'] == 'healthy'
        except (requests.RequestException, ValueError, KeyError):
            healthy = False
        SERVICE.labels(service=name).set(int(healthy))
        PROBE_LATENCY.labels(service=name).set(time.monotonic() - started)
    TELEGRAM.set(int(bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID'))))


async def poll():
    while True:
        await asyncio.to_thread(run_once)
        await asyncio.sleep(int(os.getenv('OPS_INTERVAL_SECONDS', '30')))


@asynccontextmanager
async def lifespan(_):
    task = asyncio.create_task(poll())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title='DDM501 Operations', lifespan=lifespan)
app.mount('/metrics', make_asgi_app())


@app.get('/health')
def health():
    return {'status':'healthy'}


@app.post('/alerts')
async def alerts(request: Request):
    body = await request.body()
    if len(body) > 262144:
        raise HTTPException(413, 'Alert payload too large')
    try:
        payload = json.loads(body)
        if not isinstance(payload.get('alerts'), list):
            raise ValueError()
    except (ValueError, AttributeError) as exc:
        raise HTTPException(422, 'Invalid Alertmanager payload') from exc
    sent = await asyncio.to_thread(send_telegram, payload)
    if os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID') and not sent:
        raise HTTPException(503, 'Telegram unavailable; Alertmanager will retry')
    write_report('alerts', {'received_at':time.time(), 'status':payload.get('status'),
                            'alerts':payload['alerts'], 'telegram_delivered':sent})
    return {'received':True, 'telegram_delivered':sent}
