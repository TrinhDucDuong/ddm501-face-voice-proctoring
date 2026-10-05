"""Check actual Grafana queries, protected reports and Alertmanager delivery."""
import argparse
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

if __package__:
    from .verify_stack import validate_grafana_dashboard
else:
    from verify_stack import validate_grafana_dashboard


def verify(send_alert=False):
    session = requests.Session()
    session.trust_env = False
    session.auth = ('admin', 'admin')
    base = 'http://127.0.0.1:13000'
    report = {'checked_at':datetime.now(timezone.utc).isoformat(),'checks':{}}

    def get(path, **kwargs):
        response = session.get(base + path, timeout=30, **kwargs)
        response.raise_for_status()
        return response.json()

    def check(name, function):
        try:
            evidence = function()
            report['checks'][name] = {'status':'pass','evidence':evidence}
            print('PASS', name, flush=True)
        except Exception as exc:
            report['checks'][name] = {'status':'fail','error':str(exc)}
            print('FAIL', name, type(exc).__name__, flush=True)

    dashboard = get('/api/dashboards/uid/biometric-overview')['dashboard']

    def queries():
        # Select all actual tenant IDs for the same SQL used by Grafana.
        def sql(query, fmt='table'):
            response = session.post(base + '/api/ds/query', timeout=30, json={
                'from':str(int((time.time()-86400)*1000)),'to':str(int(time.time()*1000)),
                'queries':[{'refId':'A','datasource':{'type':'postgres','uid':'biometric-postgres'},
                            'rawSql':query,'format':fmt,'intervalMs':15000,'maxDataPoints':1000}]})
            response.raise_for_status()
            result = response.json()['results']['A']
            assert not result.get('error'), result.get('error')
            return result.get('frames', [])
        frames = sql('SELECT id FROM tenants ORDER BY id')
        tenants = frames[0]['data']['values'][0]
        tenant_sql = ','.join("'" + t.replace("'","''") + "'" for t in tenants)
        evidence = []
        for panel in dashboard['panels']:
            for target in panel.get('targets', []):
                uid = target.get('datasource',panel['datasource'])['uid']
                query = target.get('rawSql',target.get('expr',''))
                query = query.replace('${tenant:sqlstring}',tenant_sql).replace('$project','ddm501-biometric-demo').replace('$service','.*')
                if uid == 'biometric-postgres':
                    query = re.sub(r'\$__timeFilter\(([^)]+)\)',r"\1 >= now()-interval '24 hours'",query)
                    result = sql(query,target.get('format','table'))
                    count = sum(len((f.get('data',{}).get('values') or [[]])[0]) for f in result)
                elif uid == 'prometheus':
                    result = get('/api/datasources/proxy/uid/prometheus/api/v1/query',params={'query':query})
                    assert result['status'] == 'success', result
                    count = len(result['data']['result'])
                elif uid == 'loki':
                    result = get('/api/datasources/proxy/uid/loki/loki/api/v1/query_range',
                                 params={'query':query,'limit':10,'start':str(int((time.time()-3600)*1e9)),'end':str(time.time_ns())})
                    assert result['status'] == 'success', result
                    count = len(result['data']['result'])
                    if panel['title'].startswith('Logs tập trung'):
                        assert count > 0, 'No Docker logs ingested'
                else:
                    raise AssertionError('Unexpected datasource ' + uid)
                evidence.append({'panel':panel['title'],'datasource':uid,'result_count':count})
        return evidence

    def collectors():
        result = get('/api/datasources/proxy/uid/prometheus/api/v1/query',params={'query':'biometric_ops_collection_success'})['data']['result']
        assert {r['metric']['component'] for r in result} == {
            'database', 'registry', 'airflow', 'docker', 'monitoring', 'monitoring_dag', 'lifecycle'}
        assert all(r['value'][1] == '1' for r in result), result
        age = get('/api/datasources/proxy/uid/prometheus/api/v1/query',params={'query':'time()-biometric_ops_last_success_unixtime'})['data']['result']
        assert all(float(r['value'][1]) < 180 for r in age), age
        memory = get('/api/datasources/proxy/uid/prometheus/api/v1/query',params={'query':'biometric_container_memory_bytes'})['data']['result']
        assert len(memory) >= 10 and any(float(r['value'][1]) > 0 for r in memory)
        return {'components':result,'container_series':len(memory),'freshness':age}

    def reports():
        evidence = {}
        for name in ['data-drift','model-performance','synthetic-performance','data-quality','model-evaluation','pipeline-status','responsible-ai','alerts']:
            path = '/reports/' + name + '.html'
            anon = requests.get(base + path, timeout=10)
            assert anon.status_code in (401,403), (name,anon.status_code)
            authorized = session.get(base + path,timeout=10)
            assert authorized.status_code == 200, (name,authorized.status_code)
            evidence[name] = {'anonymous':anon.status_code,'authenticated':authorized.status_code}
        human, synthetic = get('/reports/model-performance.json'), get('/reports/synthetic-performance.json')
        assert human['label_source'] == 'human' and synthetic['label_source'] == 'synthetic'
        evidence['human_status'] = human['status']
        evidence['fairness_gate'] = get('/reports/responsible-ai.json')['gate']
        return evidence

    def delivery():
        verification_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        payload = [{'labels':{'alertname':'DDM501MonitoringDeliveryTest','severity':'info','verification_id':verification_id},
                    'annotations':{'summary':'Kiểm tra Grafana → Alertmanager → Telegram; cảnh báo thử nghiệm.'},
                    'startsAt':now.isoformat(),'endsAt':(now+timedelta(minutes=2)).isoformat()}]
        response = requests.post('http://127.0.0.1:19093/api/v2/alerts',json=payload,timeout=10)
        response.raise_for_status()
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            received = get('/reports/alerts.json')
            if received['telegram_delivered'] and any(a['labels'].get('verification_id') == verification_id for a in received['alerts']):
                return {'route':'Alertmanager → ops-monitor → Telegram','telegram_delivered':True,'verification_id':verification_id}
            time.sleep(2)
        raise AssertionError('Alertmanager test notification not delivered within 100 seconds')

    check('provisioned_dashboard_revision', lambda: validate_grafana_dashboard(dashboard))
    check('all_dashboard_queries', queries)
    check('collector_and_container_freshness', collectors)
    check('protected_reports_and_sources', reports)
    if send_alert:
        check('telegram_alertmanager_delivery', delivery)
    report['status'] = 'pass' if all(c['status']=='pass' for c in report['checks'].values()) else 'fail'
    Path('reports').mkdir(exist_ok=True)
    Path('reports/monitoring-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report['status'] == 'pass'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--send-alert',action='store_true')
    args = parser.parse_args()
    raise SystemExit(0 if verify(args.send_alert) else 1)
