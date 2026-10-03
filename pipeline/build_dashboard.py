"""Generate the provisioned Grafana monitoring centre from reviewed queries."""
import json
from pathlib import Path


def build():
    panels, next_id, y = [], 1, 0

    def row(title):
        nonlocal next_id, y
        y = max((p['gridPos']['y'] + p['gridPos']['h'] for p in panels), default=0)
        panels.append({'type':'row', 'id':next_id, 'title':title, 'collapsed':False,
                       'gridPos':{'x':0,'y':y,'w':24,'h':1}, 'panels':[]})
        next_id += 1
        y += 1

    def panel(title, queries, kind='timeseries', source='prometheus', unit=None, description='', width=12):
        nonlocal next_id, y
        targets = []
        for index, query in enumerate(queries if isinstance(queries, list) else [queries]):
            target = {'refId':chr(65+index)}
            if source == 'biometric-postgres':
                target.update(rawSql=query, format='table' if kind=='table' else 'time_series', rawQuery=True)
            else:
                target.update(expr=query, legendFormat='{{service}}{{task}}{{source}} {{window}} {{metric}} {{modality}} {{alias}}{{state}}{{feature}}{{outcome}}{{container_label_com_docker_compose_service}}')
                if kind in ('stat','table'):
                    target.update(instant=True, range=False)
            targets.append(target)
        ds_type = 'postgres' if source == 'biometric-postgres' else source
        x = 0
        if width == 12 and panels and panels[-1]['type'] != 'row' and panels[-1]['gridPos']['w'] == 12 and panels[-1]['gridPos']['x'] == 0:
            x, y = 12, panels[-1]['gridPos']['y']
        else:
            if panels and panels[-1]['type'] != 'row':
                y = panels[-1]['gridPos']['y'] + panels[-1]['gridPos']['h']
        field = {'defaults':{'unit':unit or 'short'}, 'overrides':[]}
        if unit == 'percentunit':
            field['defaults'].update(min=0,max=1)
        panel_data = {'id':next_id, 'type':kind, 'title':title, 'description':description,
                      'datasource':{'type':ds_type,'uid':source}, 'targets':targets,
                      'gridPos':{'x':x,'y':y,'w':width,'h':8}, 'fieldConfig':field,
                      'options':{'legend':{'displayMode':'table','placement':'bottom'}, 'tooltip':{'mode':'multi'}}}
        if kind == 'stat':
            panel_data['options'] = {'reduceOptions':{'calcs':['lastNotNull'],'values':False},'colorMode':'value','graphMode':'none','textMode':'auto'}
        if kind == 'logs':
            panel_data['options'] = {'showTime':True,'wrapLogMessage':True,'enableLogDetails':True,'sortOrder':'Descending'}
        panels.append(panel_data)
        next_id += 1

    row('1 · Tổng quan hệ thống và cảnh báo')
    panel('Service readiness — 1 healthy / 0 unavailable', 'biometric_service_health', 'stat', description='HTTP readiness, including the registered API champion. Internal services are admin-only.')
    panel('Alerts đang firing', 'sum(ALERTS{alertstate="firing"}) or vector(0)', 'stat')
    panel('Verification rate', 'sum(rate(biometric_verifications_total[5m]))')
    panel('Customer batch checks — platform aggregate', 'sum by (status) (increase(biometric_integrity_checks_total[24h]))', 'stat', description='Business results are delivered to companies through API/webhook; this is platform telemetry.')
    panel('Capture integrity detector availability', 'biometric_integrity_capability_ready', 'stat')
    panel('Suspicious evidence persistence', 'biometric_evidence_writes_total', 'stat')
    panel('Decisions (24h)', 'sum by (decision) (increase(biometric_verifications_total[24h]))', 'piechart')
    panel('Verification latency p50/p95', ['histogram_quantile(0.5, sum by (le) (rate(biometric_verification_seconds_bucket[5m])))','histogram_quantile(0.95, sum by (le) (rate(biometric_verification_seconds_bucket[5m])))'], unit='s')
    panel('HTTP request / error rate', ['sum by (status) (rate(biometric_requests_total[5m]))','sum(rate(biometric_requests_total{status=~"5.."}[5m])) / clamp_min(sum(rate(biometric_requests_total[5m])),0.001)'])
    panel('Pending/firing alerts — Prometheus rules', 'ALERTS', 'table', width=24)

    row('2 · Data quality và capture quality')
    panel('Training identities / samples — tenant demo mặc định', ['biometric_training_identities','biometric_training_samples'], 'stat')
    panel('Training validation / embedding dimensions', ['biometric_training_data_valid','biometric_embedding_dimension'], 'stat')
    panel('Face / voice similarity', "SELECT e.created_at AS time, e.face_score, e.voice_score FROM verification_events e JOIN people p ON p.id=e.person_id WHERE $__timeFilter(e.created_at) AND p.tenant_id IN (${tenant:sqlstring}) ORDER BY time", source='biometric-postgres')
    panel('Capture quality — face / voice', "SELECT e.created_at AS time, e.face_quality, e.voice_quality FROM verification_events e JOIN people p ON p.id=e.person_id WHERE $__timeFilter(e.created_at) AND p.tenant_id IN (${tenant:sqlstring}) ORDER BY time", source='biometric-postgres', unit='percentunit')
    panel('Reason codes trong khoảng thời gian chọn', "SELECT reason, count(*) AS events FROM verification_events e JOIN people p ON p.id=e.person_id CROSS JOIN LATERAL jsonb_array_elements_text(e.reasons::jsonb) AS reason WHERE $__timeFilter(e.created_at) AND p.tenant_id IN (${tenant:sqlstring}) GROUP BY reason ORDER BY events DESC", 'table','biometric-postgres')
    panel('Enrollment theo tenant / modality', "SELECT t.name AS tenant,s.modality,count(*) AS samples,avg(s.quality) AS mean_quality FROM biometric_samples s JOIN people p ON p.id=s.person_id JOIN tenants t ON t.id=p.tenant_id WHERE p.tenant_id IN (${tenant:sqlstring}) GROUP BY t.name,s.modality", 'table','biometric-postgres')

    row('3 · Drift và Evidently')
    panel('Production drift — PSI', 'biometric_feature_psi', description='PSI <0.1 stable, 0.1–0.2 investigate, >0.2 alert. Observations can include deliberate simulation.')
    panel('Drifted feature share', 'biometric_drifted_feature_share', 'stat', unit='percentunit')
    panel('Reference / current window sizes', 'biometric_monitor_samples', 'stat')
    panel('Drift report ready / age (seconds)', ['biometric_evidently_report_success','time()-biometric_monitor_last_success_unixtime'], 'stat')
    panel('Human report ready / available labels', ['biometric_reviewed_report_success{source="human"}','biometric_reviewed_samples{source="human"}'], 'stat', description='Insufficient human labels are displayed honestly; no synthetic labels substitute for them.')
    panel('Synthetic report ready / available labels', ['biometric_reviewed_report_success{source="synthetic"}','biometric_reviewed_samples{source="synthetic"}'], 'stat', description='Technical simulation only; not production biometric accuracy.')
    panel('Batch PSI theo công ty và phiên bản model', 'biometric_monitor_tenant_psi', description='Frozen reference versus a new tenant/model window. Review sample size and human labels before requesting a challenger.')
    panel('Mẫu batch monitoring theo công ty', 'biometric_monitor_tenant_samples', 'table')
    panel('Đề nghị train challenger — 1 có / 0 chưa', 'biometric_retrain_recommended', 'table', description='Two distinct drift windows or audited performance regression; only the consented training tenant may trigger.')
    panel('Tuổi batch monitoring DAG (giây)', 'time()-biometric_monitoring_etl_unixtime', 'stat')

    row('4 · Model Registry, evaluation và explainability')
    panel('Serving model version / backend', 'biometric_model_info', 'table')
    panel('Registry champion / challenger / candidate gate', ['biometric_registry_model_info','biometric_candidate_gate_passed'], 'table', description='Champion serves API; challenger is compared on the same holdout and reviewed shadow before alias promotion.')
    panel('Registered face / voice thresholds', 'biometric_registry_threshold', 'stat')
    panel('Calibration / identity CV / holdout FAR & FRR', 'biometric_registry_evaluation', 'stat', unit='percentunit', description='Offline identity-disjoint evaluation on demo feature data. Historical versions may lack holdout metrics.')
    panel('Human Evidently performance — reference / current', 'biometric_reviewed_performance{source="human"}', unit='percentunit')
    panel('Synthetic Evidently performance — technical demo', 'biometric_reviewed_performance{source="synthetic"}', unit='percentunit')
    panel('Human-reviewed accuracy — excludes simulation', 'biometric_feedback_accuracy', 'stat', unit='percentunit')
    panel('Ground truth counts / confusion matrix by source', "SELECT CASE WHEN f.reviewer='synthetic-simulation' THEN 'synthetic' WHEN f.reviewer LIKE 'operator:%' THEN 'human' ELSE 'untrusted' END AS source, f.is_genuine AS target,e.accepted AS prediction,count(*) AS events FROM verification_events e JOIN verification_feedback f ON f.event_id=e.id JOIN people p ON p.id=e.person_id WHERE $__timeFilter(e.created_at) AND p.tenant_id IN (${tenant:sqlstring}) GROUP BY 1,2,3", 'table','biometric-postgres')
    panel('Giải thích policy', [], kind='text')
    # Explainability is a text explanation, not a fabricated historical numerical series.
    panels[-1].update(type='text', targets=[], options={'mode':'markdown','content':'### Giải thích quyết định\nAPI trả **reason codes**, **score − threshold**, **threshold sensitivity ±0.05**, và **single-modality counterfactual**.\n\nĐây là giải thích policy; không chứng minh danh tính. Historic events chưa lưu threshold nên dashboard không suy diễn margins lịch sử.'})

    row('5 · Sessions, review và webhook')
    panel('Risk score', "SELECT e.created_at AS time,e.risk_score FROM verification_events e JOIN people p ON p.id=e.person_id WHERE $__timeFilter(e.created_at) AND p.tenant_id IN (${tenant:sqlstring}) ORDER BY time", source='biometric-postgres', unit='percentunit')
    panel('Session states theo tenant', "SELECT t.name AS tenant,CASE WHEN s.status='pending' AND s.expires_at<now() THEN 'expired' ELSE s.status END AS status,count(*) AS sessions FROM verify_sessions s JOIN tenants t ON t.id=s.tenant_id WHERE s.tenant_id IN (${tenant:sqlstring}) GROUP BY 1,2", 'table','biometric-postgres')
    panel('Review queue — chỉ phiên đang chờ quyết định', "SELECT s.created_at,s.id AS session_id,t.name AS tenant,p.external_ref AS candidate,s.expires_at,e.face_score,e.voice_score,e.reasons,e.model_version FROM verify_sessions s JOIN verification_events e ON e.id=s.event_id JOIN people p ON p.id=s.person_id JOIN tenants t ON t.id=s.tenant_id WHERE s.status='review' AND s.tenant_id IN (${tenant:sqlstring}) ORDER BY s.created_at ASC LIMIT 100", 'table','biometric-postgres', width=24)
    panel('Review turnaround / SLA 15 phút', "SELECT s.id,EXTRACT(EPOCH FROM now()-s.created_at)/60 AS waiting_minutes,s.expires_at FROM verify_sessions s WHERE s.status='review' AND s.tenant_id IN (${tenant:sqlstring}) ORDER BY waiting_minutes DESC LIMIT 100", 'table','biometric-postgres')
    panel('SaaS webhook delivery outcomes', 'sum by (outcome) (rate(biometric_webhook_attempts_total[5m]))')
    panel('SaaS webhook outbox', 'biometric_webhook_backlog', 'stat')
    panel('Webhook worker poll age', 'time()-biometric_webhook_last_cycle_unixtime', 'stat', unit='s')
    panel('Telegram configuration / notifications', ['biometric_telegram_configured','biometric_alert_notifications_total'], 'stat')
    panel('Operator review decisions / audit', "SELECT a.created_at,t.name AS tenant,a.action,a.target,a.details FROM audit_logs a JOIN tenants t ON t.id=a.tenant_id WHERE a.action IN ('session.approved','session.rejected') AND a.tenant_id IN (${tenant:sqlstring}) AND $__timeFilter(a.created_at) ORDER BY a.created_at DESC LIMIT 100", 'table','biometric-postgres')

    row('6 · Airflow, Responsible AI và freshness')
    panel('Latest Airflow DAG state', 'biometric_airflow_latest_run_state', 'stat')
    panel('Latest monitoring DAG state', 'biometric_monitoring_dag_state', 'stat')
    panel('Monitoring DAG last run age (seconds)', 'time()-biometric_monitoring_dag_unixtime', 'stat')
    panel('Latest run / collector ages', ['time()-biometric_airflow_latest_run_unixtime','time()-biometric_ops_last_success_unixtime'], 'stat', unit='s')
    panel('Latest DAG tasks — success / duration', ['biometric_airflow_task_success','biometric_airflow_task_seconds'], 'table')
    panel('Collectors — database / registry / Airflow', 'biometric_ops_collection_success', 'stat')
    panel('Human quality fairness status', ['biometric_fairness_status','biometric_fairness_accuracy_gap'], 'stat', description='Capture quality is an operational proxy. insufficient_data is not a fairness pass.')
    panel('Fairness quality slices — source-separated', 'biometric_fairness_slice', 'table', description='Compare source/slice/class counts; report includes Wilson 95% intervals.')

    row('7 · Infrastructure và logs')
    panel('Container CPU cores', 'sum by (service) (rate(biometric_container_cpu_seconds_total{project=~"$project"}[5m]))')
    panel('Container memory working set', 'sum by (service) (biometric_container_memory_bytes{project=~"$project"})', unit='bytes')
    panel('Container block IO bytes / second', 'sum by (service,operation) (rate(biometric_container_io_bytes_total{project=~"$project"}[5m]))', unit='Bps')
    panel('Container network bytes / second', 'sum by (service,direction) (rate(biometric_container_network_bytes_total{project=~"$project"}[5m]))', unit='Bps')
    panel('Database size / connections', ['biometric_database_bytes','biometric_database_connections'], 'stat')
    panel('Health probe latency', 'biometric_service_probe_seconds', unit='s')
    panel('Scrape targets', 'up', 'stat')
    panel('Logs tập trung — chọn service ở phía trên', '{project=~"$project",service=~"$service"}', 'logs', 'loki', width=24)
    panel('Error / exception logs', '{project=~"$project",service=~"$service"} |~ "(?i)(error|exception|failed)"', 'logs','loki',width=24)

    row('8 - Independent Face / Voice lifecycle')
    panel('Quality and embedding drift', 'biometric_modality_drift_score')
    panel('Genuine / impostor scores', 'biometric_modality_verification_score')
    panel('Template aging windows', 'biometric_template_aging', 'stat')
    panel('FMR / FNMR / EER / TAR at FAR', 'biometric_modality_performance', unit='percentunit', description='Trusted modality labels only; missing evidence remains NaN.')
    panel('Drift decisions by modality', 'biometric_modality_drift_state', 'table')
    panel('Eligible retrain requests', 'biometric_modality_retrain_required', 'stat')
    panel('Persisted deployment state', 'biometric_deployment_state', 'table')
    panel('Canary traffic percentage', 'biometric_canary_traffic_percent', 'stat')
    panel('Current stage samples', 'biometric_challenger_stage_samples', 'stat')
    panel('Rollback audit count', 'biometric_rollbacks_total', 'stat')

    return {'uid':'biometric-overview','title':'DDM501 — Monitoring Centre','schemaVersion':41,'version':2,
            'editable':False,'refresh':'15s','timezone':'browser','time':{'from':'now-6h','to':'now'},
            'tags':['ddm501','monitoring'],'panels':panels,
            'templating':{'list':[
                {'name':'tenant','label':'SQL tenant scope','type':'query','datasource':{'type':'postgres','uid':'biometric-postgres'},'query':'SELECT name AS __text,id AS __value FROM tenants ORDER BY name','multi':True,'includeAll':True,'refresh':1,'current':{'text':'All','value':'$__all'}},
                {'name':'project','type':'query','datasource':{'type':'prometheus','uid':'prometheus'},'query':'label_values(biometric_container_cpu_seconds_total,project)','refresh':1,'current':{'text':'ddm501-biometric-demo','value':'ddm501-biometric-demo'}},
                {'name':'service','type':'query','datasource':{'type':'loki','uid':'loki'},'query':'label_values({project=~"$project"},service)','multi':True,'includeAll':True,'allValue':'.*','refresh':1,'current':{'text':'All','value':'$__all'}}]},
            'links':[{'title':title,'url':url,'type':'link','targetBlank':True} for title,url in [
                ('Alert groups','/alerting/groups?alertmanager=alertmanager'),('Evidently data drift','/reports/data-drift.html'),
                ('Human performance','/reports/model-performance.html'),('Synthetic demo performance','/reports/synthetic-performance.html'),
                ('Model evaluation','/reports/model-evaluation.html'),('Data quality','/reports/data-quality.html'),
                ('Responsible AI','/reports/responsible-ai.html'),('Pipeline status','/reports/pipeline-status.html'),('Received alerts','/reports/alerts.html')]]}


if __name__ == '__main__':
    destination = Path(__file__).resolve().parents[1] / 'monitoring/grafana/dashboards/biometric-overview.json'
    destination.write_text(json.dumps(build(),ensure_ascii=False,indent=2),encoding='utf-8')
