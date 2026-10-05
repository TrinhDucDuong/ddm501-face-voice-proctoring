"""Bounded aggregate evidence from the isolated lab; never production telemetry."""
import json
import math
import sqlite3
from datetime import datetime

from prometheus_client import CollectorRegistry, Gauge, generate_latest


def evidence_metrics(runner):
    registry, gauges = CollectorRegistry(), {}

    def emit(name, value, labels):
        if value is None or not math.isfinite(float(value)):
            return
        name = 'simulation_evidence_' + name
        labels = {'synthetic': 'true', **labels}
        if name not in gauges:
            gauges[name] = Gauge(name, 'Latest isolated synthetic evidence; see run timestamp.', list(labels), registry=registry)
        gauges[name].labels(**labels).set(value)

    def read(path, default):
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

    state = runner.status()
    current = state['current']
    with runner.control() as connection:
        runs = [json.loads(row[0]) for row in connection.execute('SELECT body FROM runs ORDER BY rowid DESC LIMIT 20')]
    alerts = []
    alert_path = runner.root / 'alerts.sqlite'
    if alert_path.exists():
        with sqlite3.connect(f'{alert_path.as_uri()}?mode=ro', uri=True) as connection:
            alerts = [json.loads(row[0]) for row in connection.execute('SELECT body FROM alerts')]
    seen = set()
    for saved in runs:
        pair = saved['scenario'], saved['modality']
        if pair in seen:
            continue
        seen.add(pair)
        run = current if current and current['id'] == saved['id'] else saved
        directory = runner.directory(run)
        # Reset restores serving state, but must not erase the experiment's result.
        result = read(directory / 'result-before-reset.json', run) if run['status'] == 'RESET' else run
        labels = {'scenario': run['scenario'], 'modality': run['modality']}
        emit('result', {'SUCCEEDED': 1, 'ROLLED_BACK': 2, 'FAILED': 3, 'RESET': 4}.get(result['status'], 0), labels)
        emit('started_unixtime', datetime.fromisoformat(run['started_at']).timestamp(), labels)
        emit('baseline_restored', int(run['status'] == 'RESET'), labels)
        emit('alert_received', int(any(a.get('run_id') == run['id'] and a.get('status') == 'firing' for a in alerts)), labels)
        reports = read(directory / 'drift-reports.json', [])
        baseline = read(directory / 'baseline-report.json', None)
        windows = ([('0', baseline)] if baseline else []) + [(str(i + 1), r) for i, r in enumerate(reports)]
        for index, report in windows:
            window_labels = {**labels, 'window': index}
            for kind in ('quality', 'embedding'):
                emit('drift', report.get(kind, {}).get('score'), {**window_labels, 'kind': kind})
            for kind in ('genuine', 'impostor'):
                score = report.get('verification_score', {}).get(kind, {})
                emit('drift', score.get('psi'), {**window_labels, 'kind': kind + '_score'})
                emit('score_mean', score.get('current', {}).get('mean'), {**window_labels, 'kind': kind})
            emit('persistent_windows', report['persistence']['consecutive_windows'], window_labels)
            emit('retrain_required', int(report['decision'] == 'RETRAIN_REQUIRED'), window_labels)
        for role in ('champion', 'candidate'):
            for metric in ('fmr', 'fnmr', 'eer'):
                emit('performance', result.get('offline', {}).get(role, {}).get(metric),
                     {**labels, 'phase': 'offline', 'role': role, 'metric': metric})
        for stage in result.get('stages', []):
            phase = stage['stage'] + ('_' + str(int(stage['traffic_percent'])) if stage['stage'] == 'CANARY' else '')
            stage_labels = {**labels, 'phase': phase}
            for key in ('samples', 'served_candidate', 'response_mismatches', 'fault_injected'):
                emit('stage_' + key, stage.get(key), stage_labels)
            evaluation = stage.get('evaluation', {})
            emit('policy_latency_p95_ms', evaluation.get('policy_latency_p95_ms'), stage_labels)
            emit('disagreement', evaluation.get('disagreement'), stage_labels)
            for role, key in [('champion', 'champion_metrics'), ('candidate', 'challenger_metrics')]:
                for metric in ('fmr', 'fnmr', 'eer'):
                    emit('performance', evaluation.get(key, {}).get(metric), {**stage_labels, 'role': role, 'metric': metric})
        for key in ('rollback_probe', 'champion_probe'):
            probe = result.get(key, {})
            emit('probe_samples', probe.get('samples'), {**labels, 'probe': key})
            emit('probe_candidate_samples', probe.get('served_candidate'), {**labels, 'probe': key})
    return generate_latest(registry).decode()
