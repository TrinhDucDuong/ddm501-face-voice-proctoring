"""Generate a separate Grafana view of real isolated simulation evidence."""
import json
from pathlib import Path


def build():
    panels = []
    scope = 'job="simulation",synthetic="true",scenario=~"$scenario",modality=~"$modality"'

    def query(metric, extra=''):
        return 'simulation_evidence_' + metric + '{' + scope + (',' + extra if extra else '') + '}'

    def panel(title, targets, unit='short', kind='bargauge', description=''):
        index = len(panels)
        value = {
            'id': index + 1, 'title': title, 'type': kind,
            'description': 'SYNTHETIC LAB ONLY. Latest run per scenario/modality, retained after reset. ' + description,
            'datasource': {'type': 'prometheus', 'uid': 'prometheus'},
            'gridPos': {'x': (index % 2) * 12, 'y': (index // 2) * 9, 'w': 12, 'h': 9},
            'targets': [{'refId': chr(65 + i), 'expr': expr, 'legendFormat': legend,
                         'instant': kind != 'timeseries', 'range': kind == 'timeseries'}
                        for i, (expr, legend) in enumerate(targets)],
            'fieldConfig': {'defaults': {'unit': unit, 'noValue': 'No evidence yet',
                                         'color': {'mode': 'fixed', 'fixedColor': 'blue'}}, 'overrides': []},
            'options': {'reduceOptions': {'calcs': ['lastNotNull'], 'values': False},
                        'orientation': 'horizontal', 'displayMode': 'basic',
                        'legend': {'displayMode': 'list', 'placement': 'bottom'}, 'tooltip': {'mode': 'multi'}},
        }
        panels.append(value)
        return value

    base = '{{modality}} / {{scenario}}'
    status = panel('Synthetic results / alert delivery / reset', [
        (query('result'), base + ' result'), (query('alert_received'), base + ' alert received'),
        (query('baseline_restored'), base + ' baseline restored'),
    ], kind='stat', description='Result: 0=in progress, 1=promoted, 2=rolled back, 3=failed, 4=reset before result. Alert/reset: 1=yes, 0=no.')
    status['options'].update(graphMode='none', colorMode='none')
    status['fieldConfig']['overrides'] = [
        {'matcher': {'id': 'byFrameRefID', 'options': 'A'}, 'properties': [
            {'id': 'mappings', 'value': [{'type': 'value', 'options': {
                str(i): {'text': label} for i, label in enumerate(['In progress', 'Promoted', 'Rolled back', 'Failed', 'Reset early'])
            }}]}]},
    ]
    panel('Evidence run started at (check freshness)', [(query('started_unixtime') + ' * 1000', base)],
          unit='dateTimeAsLocal', kind='stat', description='Snapshot values are not new production traffic on every scrape.')
    panel('Drift: healthy baseline vs final drift window', [(query('drift', 'window=~"0|3"'), 'W{{window}} {{kind}} / ' + base)],
          description='W0=healthy baseline; W3=final drift window. Quality/score PSI threshold=0.2; embedding MMD2 threshold=0.02.')
    panel('Genuine / impostor cosine scores', [(query('score_mean'), 'W{{window}} {{kind}} / ' + base)],
          description='Synthetic labelled distributions. Baseline policy threshold=0.8.')
    panel('Persistence and retrain decision', [
        (query('persistent_windows'), 'W{{window}} persistence / ' + base),
        (query('retrain_required'), 'W{{window}} retrain / ' + base),
    ], description='Three independent drift windows required; retrain required 1=yes, 0=no.')
    panel('Offline comparison on identical holdout', [
        (query('performance', 'phase="offline"'), '{{metric}} {{role}} / ' + base)], unit='percentunit',
        description='Synthetic FMR/FNMR/EER, not human-reviewed production accuracy.')
    panel('Shadow / canary / post-rollout HTTP samples', [
        (query('stage_samples'), '{{phase}} all / ' + base),
        (query('stage_served_candidate'), '{{phase}} candidate / ' + base),
        (query('probe_samples'), '{{probe}} all / ' + base),
        (query('probe_candidate_samples'), '{{probe}} candidate / ' + base),
    ], description='Shadow must serve zero candidate responses. Rollback probe must also serve zero candidate responses.')
    panel('Challenger stage security and rejection rates', [
        (query('performance', 'phase!="offline",role="candidate",metric=~"fmr|fnmr"'), '{{metric}} {{phase}} / ' + base)],
        unit='percentunit', description='Rollback scenario injects impostors at CANARY_25. No CANARY_50/100 evidence is expected after failure.')
    panel('Measured policy latency p95', [(query('policy_latency_p95_ms'), '{{phase}} / ' + base)], unit='ms',
          description='Policy routing/comparison time only; does not include pretrained encoder or network latency. Limit=10ms.')
    live = panel('Live canary / retrain - all scenarios', [
        ('simulation_canary_percent{job="simulation",synthetic="true",modality=~"$modality"}', '{{modality}} canary %'),
        ('max by (modality) (simulation_retrain_required{job="simulation",synthetic="true",modality=~"$modality"})', '{{modality}} retrain alert'),
    ], kind='timeseries', description='Live current run only; scenario filter does not apply. Reset returns both signals to zero. Short stages may fall between 15s scrapes; stage evidence above is authoritative.')
    live['fieldConfig']['defaults']['color'] = {'mode': 'palette-classic'}
    return {
        'uid': 'biometric-simulation', 'title': 'DDM501 - SYNTHETIC Simulation Evidence',
        'schemaVersion': 41, 'version': 1, 'editable': False, 'refresh': '15s',
        'timezone': 'browser', 'time': {'from': 'now-1h', 'to': 'now'}, 'panels': panels,
        'tags': ['ddm501', 'simulation', 'synthetic'],
        'description': 'Isolated synthetic embeddings and labels. Actual Airflow, alerts, HTTP routing and MLflow policy gates. Not production biometric accuracy.',
        'templating': {'list': [
            {'name': name, 'label': name.title(), 'type': 'custom', 'query': values,
             'includeAll': True, 'allValue': '.*', 'multi': False,
             'current': {'text': default, 'value': default}}
            for name, values, default in [('scenario', 'promotion,rollback', 'promotion'), ('modality', 'face,voice', 'voice')]
        ]},
        'links': [{'title': 'Production overview', 'url': '/d/biometric-overview', 'type': 'link'},
                  {'title': 'Simulation controls', 'url': 'http://localhost:18501', 'type': 'link'},
                  {'title': 'Simulation MLflow', 'url': 'http://localhost:15031', 'type': 'link'}],
    }


if __name__ == '__main__':
    destination = Path(__file__).resolve().parents[1] / 'monitoring/grafana/dashboards/biometric-simulation.json'
    destination.write_text(json.dumps(build(), indent=2) + '\n', encoding='utf-8')
