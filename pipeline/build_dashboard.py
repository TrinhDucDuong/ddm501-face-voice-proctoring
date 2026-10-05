"""Generate the compact Grafana operations overview using existing telemetry."""
import json
from pathlib import Path


def build():
    panels = []

    def panel(title, queries, kind='timeseries', unit='short', description=''):
        targets = [{'refId': chr(65 + i), 'expr': query, 'legendFormat': legend,
                    **({'instant': True, 'range': False} if kind in ('stat', 'table') else {}),
                    **({'format': 'table'} if kind == 'table' else {})}
                   for i, (query, legend) in enumerate(queries)]
        panels.append({
            'id': len(panels) + 1, 'title': title, 'type': kind, 'description': description,
            'datasource': {'type': 'prometheus', 'uid': 'prometheus'}, 'targets': targets,
            'fieldConfig': {'defaults': {'unit': unit, 'noValue': 'Chưa có dữ liệu'}, 'overrides': []},
            'options': ({'reduceOptions': {'calcs': ['last'], 'values': False},
                         'colorMode': 'none', 'graphMode': 'none', 'textMode': 'auto'} if kind == 'stat'
                        else {'legend': {'displayMode': 'list', 'placement': 'bottom'},
                              'tooltip': {'mode': 'multi'}}),
        })
        return panels[-1]

    health = panel('Serving readiness', [
        ('biometric_service_health{service=~"api|portal|minio"} and on() (up{job="ops-monitor"} == 1) and on() (time() - max(biometric_ops_last_success_unixtime) < 180)', '{{service}}'),
        ('biometric_integrity_capability_ready and on() (up{job="biometric-api"} == 1)', 'Integrity detector'),
    ], 'stat', description='Readiness nội bộ; không phải uptime từ phía khách hàng. 0 = unavailable, 1 = ready. Thiếu telemetry = chưa rõ.')
    health['fieldConfig']['defaults'].update(
        mappings=[{'type': 'value', 'options': {'0': {'text': 'Unavailable', 'color': 'red'},
                                               '1': {'text': 'Ready', 'color': 'green'}}}],
        thresholds={'mode': 'absolute', 'steps': [{'color': 'red', 'value': None}, {'color': 'green', 'value': 1}]})
    health['options']['colorMode'] = 'value'

    alerts = panel('Active incidents — warning / critical', [
        ('ALERTS{alertstate="firing",severity=~"warning|critical",evidence!="synthetic_demo",synthetic!="true",alertname!~".*Synthetic.*|Simulation.*"}', '{{alertname}}'),
    ], 'table', description='Chỉ lọc hiển thị. Alert rules và việc gửi thông báo giữ nguyên. Bảng trống có thể là không có incident hoặc thiếu telemetry; kiểm tra panel freshness.')
    alerts['transformations'] = [{'id': 'organize', 'options': {
        'excludeByName': {'Time': True, '__name__': True, 'Value': True, 'alertstate': True, 'job': True, 'instance': True},
        'indexByName': {'severity': 0, 'alertname': 1, 'service': 2, 'component': 3, 'modality': 4},
    }}]
    alerts['options'] = {'showHeader': True, 'sortBy': [{'displayName': 'severity', 'desc': False}]}

    scope = 'job="biometric-api",route!~"/health|/ready|/metrics.*|/v1/simulation.*|/v1/admin.*|/docs.*|/openapi.json|/redoc"'
    panel('API traffic', [(f'sum(rate(biometric_requests_total{{{scope}}}[5m]))', 'requests/s')],
          unit='reqps', description='Request API ngoài health, metrics, admin và simulation; gồm cả enrollment và nghiệp vụ khác. Dùng counter HTTP để tránh trộn observation synthetic vào verification traffic.')
    panel('API HTTP 5xx', [(f'sum(rate(biometric_requests_total{{{scope},status=~"5.."}}[5m])) / sum(rate(biometric_requests_total{{{scope}}}[5m]))', '5xx ratio')],
          unit='percentunit', description='Cùng phạm vi với API traffic. Không có request = chưa có tỷ lệ; không ép về 0. Exception chưa gán route được ghi là unhandled. Review/reject không phải HTTP 5xx.')
    panel('Verification latency p95', [
        ('histogram_quantile(0.95, sum by (le) (rate(biometric_verification_seconds_bucket{job="biometric-api"}[5m])))', 'p95'),
    ], unit='s', description='Thời gian xử lý verification đã được instrumentation; không phải latency HTTP end-to-end và không bao gồm mọi request lỗi. Không có mẫu = chưa có dữ liệu.')

    resources = panel('Core containers — CPU / RAM', [
        ('sum by (service) (rate(biometric_container_cpu_seconds_total{project=~"$project",service=~"api|postgres|webhook-worker|drift-monitor"}[5m]))', '{{service}} CPU'),
        ('sum by (service) (biometric_container_memory_bytes{project=~"$project",service=~"api|postgres|webhook-worker|drift-monitor"})', '{{service}} RAM'),
    ], description='API, PostgreSQL, webhook worker và drift monitor. CPU theo cores; RAM working set theo bytes. Dịch vụ khác xem Explore. Telemetry hiện tại chưa có capacity/limit/disk: panel này không đánh giá phần trăm saturation.')
    resources['fieldConfig']['overrides'] = [
        {'matcher': {'id': 'byFrameRefID', 'options': 'A'}, 'properties': [
            {'id': 'unit', 'value': 'short'}, {'id': 'custom.axisLabel', 'value': 'CPU cores'}, {'id': 'custom.axisPlacement', 'value': 'left'}]},
        {'matcher': {'id': 'byFrameRefID', 'options': 'B'}, 'properties': [
            {'id': 'unit', 'value': 'bytes'}, {'id': 'custom.axisLabel', 'value': 'RAM'}, {'id': 'custom.axisPlacement', 'value': 'right'}]},
    ]

    panel('Webhook backlog', [
        ('biometric_webhook_backlog{status=~"pending|failed"} and on() (up{job="webhook-worker"} == 1)', '{{status}}'),
    ], 'stat', description='Số webhook pending/failed hiện tại. Chưa có metric tuổi item chờ lâu nhất; chi tiết xem portal/outbox.')
    panel('ML input drift — face / voice', [
        ('biometric_modality_drift_score and on() (up{job="ops-monitor"} == 1)', '{{modality}} / {{kind}}'),
    ], description='Quality/embedding drift: giá trị lớn nhất qua các tenant window theo modality. Hai loại score không nhất thiết cùng thang đo; không áp ngưỡng PSI chung. Xem freshness trước khi diễn giải. Thiếu mẫu không phải drift = 0.')
    performance = panel('Human-reviewed quality — FAR / FRR', [
        ('biometric_reviewed_performance{source="human",metric=~"far|frr",window="current"} and on(source) (biometric_reviewed_report_success{source="human"} == 1) and on() (up{job="drift-monitor"} == 1)', '{{metric}} / current'),
        ('biometric_reviewed_samples{source="human"} and on() (up{job="drift-monitor"} == 1)', 'Human labels available'),
    ], 'stat', 'percentunit', 'Chỉ feedback người review, không dùng synthetic. FAR/FRR trên window hiện tại; nhãn available là tổng nhãn monitor đã tải, không phải số genuine/impostor. Thiếu hai lớp hoặc thiếu mẫu = chưa có dữ liệu. Đây là chất lượng trên tập được review, không phải toàn traffic.')
    performance['fieldConfig']['overrides'] = [
        {'matcher': {'id': 'byFrameRefID', 'options': 'B'}, 'properties': [{'id': 'unit', 'value': 'short'}]},
    ]

    freshness = panel('Pipeline freshness & deployment', [
        ('time() - biometric_monitoring_etl_unixtime', 'Batch report age'),
        ('time() - biometric_monitor_last_success_unixtime', 'Drift calculation age'),
        ('max(time() - biometric_ops_last_success_unixtime)', 'Oldest collector age'),
        ('time() - biometric_webhook_last_cycle_unixtime', 'Webhook poll age'),
        ('biometric_monitoring_dag_state == 1', 'Monitoring DAG: {{state}}'),
        ('biometric_deployment_state == 1', '{{modality}} rollout: {{state}}'),
        ('biometric_model_info and on() (up{job="biometric-api"} == 1)', 'Serving bundle: {{version}} / {{backend}}'),
        ('min(up{job=~"biometric-api|ops-monitor|drift-monitor|webhook-worker"})', 'Scrape: 1 all up / 0 target down'),
    ], 'stat', 's', 'Age là tuổi report/calculation/collector/poll, không suy diễn lần DAG thành công từ start_date. Serving bundle là metadata API hiện có; rollout state theo face/voice. Scrape 0 hoặc age tăng cao: telemetry có thể stale. Toàn hệ thống, không lọc tenant.')
    freshness['fieldConfig']['overrides'] = [
        {'matcher': {'id': 'byFrameRefID', 'options': ref}, 'properties': [{'id': 'unit', 'value': 'short'}]}
        for ref in ('E', 'F', 'G', 'H')
    ]

    # Status first, then HTTP signals, resources/delivery, and ML health.
    layout = [(0, 0, 6, 7), (6, 0, 8, 7), (0, 7, 8, 7), (8, 7, 8, 7),
              (16, 7, 8, 7), (0, 14, 12, 7), (12, 14, 12, 7),
              (0, 21, 12, 7), (12, 21, 12, 7), (14, 0, 10, 7)]
    for item, (x, y, w, h) in zip(panels, layout, strict=True):
        item['gridPos'] = {'x': x, 'y': y, 'w': w, 'h': h}

    return {
        'uid': 'biometric-overview', 'title': 'DDM501 — System Overview', 'schemaVersion': 41, 'version': 3,
        'description': 'Tổng quan vận hành toàn hệ thống từ telemetry hiện có. Chi tiết debug/evaluation xem các liên kết. Không thay alert rules hoặc instrumentation.',
        'editable': False, 'refresh': '30s', 'timezone': 'browser', 'time': {'from': 'now-6h', 'to': 'now'},
        'tags': ['ddm501', 'monitoring'], 'panels': panels,
        'templating': {'list': [
            {'name': 'project', 'label': 'Container project', 'type': 'query',
             'datasource': {'type': 'prometheus', 'uid': 'prometheus'},
             'query': 'label_values(biometric_container_cpu_seconds_total,project)', 'refresh': 1,
             'current': {'text': 'ddm501-biometric-demo', 'value': 'ddm501-biometric-demo'}},
        ]},
        'links': [{'title': title, 'url': url, 'type': 'link', 'targetBlank': True} for title, url in [
            ('Synthetic simulation', '/d/biometric-simulation'),
            ('Logs / Explore', '/explore'), ('Alert groups', '/alerting/groups?alertmanager=alertmanager'),
            ('Human performance', '/reports/model-performance.html'), ('Data drift', '/reports/data-drift.html'),
            ('Model evaluation', '/reports/model-evaluation.html'), ('Pipeline status', '/reports/pipeline-status.html'),
            ('Responsible AI', '/reports/responsible-ai.html'),
        ]],
    }


if __name__ == '__main__':
    destination = Path(__file__).resolve().parents[1] / 'monitoring/grafana/dashboards/biometric-overview.json'
    destination.write_text(json.dumps(build(), ensure_ascii=False, indent=2), encoding='utf-8')
