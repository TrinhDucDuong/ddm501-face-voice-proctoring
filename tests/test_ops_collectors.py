import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient

from monitoring import ops_monitor as ops
from monitoring import telegram


def response(body, status=200):
    result = Mock(status_code=status, ok=status < 400)
    result.json.return_value = body
    return result


def connection(monkeypatch, results):
    conn = Mock()
    conn.execute.side_effect = results
    engine = Mock()
    engine.connect.return_value.__enter__ = Mock(return_value=conn)
    engine.connect.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(ops, 'create_engine', lambda *a, **k: engine)
    return engine, conn


def test_registry_aliases_keep_missing_metrics_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr(ops, 'REPORT_DIR', tmp_path)
    version = {'version':'8', 'run_id':'run8', 'tags':[{'key':'promotion_status','value':'passed'}]}
    run = {'run':{'data':{'params':[{'key':'face_threshold','value':'.4'},
                                  {'key':'evaluation_method','value':'identity-disjoint-max-template'}],
                          'metrics':[{'key':'face_holdout_far','value':.02}]}}}
    get = Mock(side_effect=[response({'model_version':version}), response(run),
                            response({},404), response({},404)])
    monkeypatch.setattr(ops.requests, 'get', get)
    ops.collect_registry()
    report = json.loads((tmp_path/'model-evaluation.json').read_text())
    assert list(report) == ['champion']
    assert report['champion']['metrics']['face_holdout_far'] == .02
    assert ops.MODEL_METRIC.labels(alias='champion',modality='face',metric='holdout_far')._value.get() == .02
    assert get.call_args_list[2].kwargs['params']['alias'] == 'candidate'
    assert get.call_args_list[3].kwargs['params']['alias'] == 'challenger'


def test_database_quality_and_fairness_are_not_confused(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://test/db')
    monkeypatch.setattr(ops, 'REPORT_DIR', tmp_path)
    engine, _ = connection(monkeypatch, [Mock(mappings=Mock(return_value=[])),
                                        Mock(scalar=Mock(return_value=1234)), Mock(scalar=Mock(return_value=3))])
    monkeypatch.setattr(ops, 'extract', lambda c: {'samples':[], 'dataset_version':'a'*64,'tenant_scope':'demo'})
    def invalid(_):
        raise ValueError(json.dumps({'counts':{'face':0,'voice':0},'identities':{},'dimensions':{},'failures':['no data']}))
    monkeypatch.setattr(ops, 'validate', invalid)
    ops.collect_database()
    assert ops.VALID._value.get() == 0
    assert ops.RAI_GATE.labels(status='insufficient_data')._value.get() == 1
    assert json.loads((tmp_path/'data-quality.json').read_text())['failures'] == ['no data']
    engine.dispose.assert_called_once()


def test_airflow_task_duration_and_empty_run(monkeypatch, tmp_path):
    monkeypatch.setenv('AIRFLOW_DATABASE_URL', 'postgresql://test/airflow')
    monkeypatch.setattr(ops, 'REPORT_DIR', tmp_path)
    start = datetime.now(timezone.utc)
    row = {'run_id':'run', 'state':'failed','start_date':start,'end_date':start+timedelta(seconds=12)}
    task = {'task_id':'promote','state':'failed','start_date':start,'end_date':row['end_date']}
    engine, _ = connection(monkeypatch, [Mock(mappings=Mock(return_value=Mock(first=Mock(return_value=row)))),
                                        Mock(mappings=Mock(return_value=[task]))])
    ops.collect_airflow()
    assert ops.TASK_STATE.labels(task='promote')._value.get() == 0
    assert ops.TASK_DURATION.labels(task='promote')._value.get() == 12
    engine.dispose.assert_called_once()
    connection(monkeypatch,[Mock(mappings=Mock(return_value=Mock(first=Mock(return_value=None))))])
    ops.collect_airflow()
    assert ops.DAG_STATE.labels(state='no_run')._value.get() == 1
    assert not list(ops.TASK_STATE.collect()[0].samples)


def test_monitoring_dag_state_is_reported_separately(monkeypatch):
    monkeypatch.setenv('AIRFLOW_DATABASE_URL', 'postgresql://test/airflow')
    row = {'run_id': 'monitor-run', 'state': 'success', 'start_date': datetime.now(timezone.utc)}
    connection(monkeypatch, [Mock(mappings=Mock(return_value=Mock(first=Mock(return_value=row))))])
    ops.collect_monitoring_dag()
    assert ops.MONITOR_DAG_STATE.labels(state='success')._value.get() == 1
    assert ops.MONITOR_DAG_TIME._value.get() > 0


def test_poll_isolates_collector_failure_and_probes_scheduler(monkeypatch, caplog):
    def fail():
        raise RuntimeError('credential-bearing message')
    monkeypatch.setattr(ops, 'collect_database', fail)
    monkeypatch.setattr(ops, 'collect_registry', lambda: None)
    monkeypatch.setattr(ops, 'collect_airflow', lambda: None)
    monkeypatch.setattr(ops, 'collect_containers', lambda: None)
    monkeypatch.setattr(ops, 'collect_monitoring', lambda: None)
    monkeypatch.setattr(ops, 'collect_monitoring_dag', lambda: None)
    monkeypatch.setattr(ops, 'PROBES', {'airflow':'http://airflow/health','api':'http://api/ready','legacy':'ignored'})
    monkeypatch.setenv('OPS_DISABLED_PROBES','legacy')
    monkeypatch.setattr(ops.requests, 'get', Mock(side_effect=[response({'scheduler':{'status':'unhealthy'}}),
                                                             requests.ConnectionError('down')]))
    ops.run_once()
    assert ops.COLLECTION.labels(component='database')._value.get() == 0
    assert ops.COLLECTION.labels(component='registry')._value.get() == 1
    assert ops.SERVICE.labels(service='airflow')._value.get() == 0
    assert ops.SERVICE.labels(service='api')._value.get() == 0
    assert 'credential-bearing message' not in caplog.text


def test_alert_endpoint_retries_failed_delivery_and_rejects_invalid(monkeypatch, tmp_path):
    monkeypatch.setattr(ops, 'REPORT_DIR', tmp_path)
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','private')
    monkeypatch.setenv('TELEGRAM_CHAT_ID','1')
    client = TestClient(ops.app)
    assert client.get('/health').status_code == 200
    assert client.post('/alerts',json=[]).status_code == 422
    assert client.post('/alerts',content=b'x'*262145).status_code == 413
    monkeypatch.setattr(ops, 'send_telegram', lambda _:False)
    assert client.post('/alerts',json={'alerts':[]}).status_code == 503
    monkeypatch.setattr(ops, 'send_telegram', lambda _:True)
    assert client.post('/alerts',json={'status':'resolved','alerts':[]}).json()['telegram_delivered']
    assert json.loads((tmp_path/'alerts.json').read_text())['status'] == 'resolved'


def test_telegram_tls_fallback_keeps_hostname_verification(monkeypatch):
    monkeypatch.setattr(telegram.requests, 'post', Mock(side_effect=requests.ConnectionError('reset')))
    monkeypatch.setattr(telegram.socket, 'gethostbyname', lambda _: '149.154.167.220')
    pool = Mock()
    pool.request.return_value = SimpleNamespace(status=200,data=b'{"ok":true}')
    constructor = Mock(return_value=pool)
    monkeypatch.setattr(telegram.urllib3,'HTTPSConnectionPool',constructor)
    assert telegram.request_telegram('private','sendMessage',{'text':'test'}) == (200,{'ok':True})
    assert constructor.call_args.kwargs['assert_hostname'] == 'api.telegram.org'
    assert constructor.call_args.kwargs['cert_reqs'] == 'CERT_REQUIRED'
    pool.close.assert_called_once()
    monkeypatch.setattr(telegram.requests,'post',Mock(side_effect=requests.exceptions.SSLError('bad certificate')))
    with pytest.raises(RuntimeError,match='redacted'):
        telegram.request_telegram('private','getMe')
    assert constructor.call_count == 1
    with pytest.raises(ValueError):
        telegram.request_telegram('private','arbitrary-method')


def test_docker_metrics_filter_project_and_reset_removed_containers(monkeypatch):
    monkeypatch.setenv('COMPOSE_PROJECT_NAME','test')
    container = {'Id':'a'*64, 'Labels':{'com.docker.compose.project':'test','com.docker.compose.service':'api'}}
    other = {'Id':'b'*64, 'Labels':{'com.docker.compose.project':'other'}}
    stats = {'cpu_stats':{'cpu_usage':{'total_usage':2500000000}},
             'memory_stats':{'usage':1000,'stats':{'inactive_file':200}},
             'networks':{'eth0':{'rx_bytes':10,'tx_bytes':20}},
             'blkio_stats':{'io_service_bytes_recursive':[{'op':'Read','value':30}]}}
    monkeypatch.setattr(ops.requests,'get',Mock(side_effect=[response([container,other]), response(stats), response([])]))
    ops.collect_containers()
    labels = {'project':'test','service':'api','container':'a'*12}
    assert ops.CONTAINER_CPU.labels(**labels)._value.get() == 2.5
    assert ops.CONTAINER_MEMORY.labels(**labels)._value.get() == 800
    assert ops.CONTAINER_NETWORK.labels(**labels,direction='tx')._value.get() == 20
    ops.collect_containers()
    assert not list(ops.CONTAINER_CPU.collect()[0].samples)
