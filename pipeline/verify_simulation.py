"""Execute both isolated scenarios and restore baseline; never starts production training."""
import argparse
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


def verify(base, key, timeout=600, all_modalities=False):
    session = requests.Session()
    session.headers['X-API-Key'] = key

    def call(method, path, **kwargs):
        response = session.request(method, base.rstrip('/') + path, timeout=240, **kwargs)
        response.raise_for_status()
        return response.json()

    prefix = '/v1/admin/simulation'
    before = call('GET', '/v1/admin/lifecycle/state')
    state = call('GET', prefix + '/state')
    if state['current'] and state['current']['status'] in {'RUNNING', 'QUEUED'}:
        raise RuntimeError('An existing simulation is active; verifier will not interrupt it')
    if state['current']:
        call('POST', prefix + '/reset')
    results = []
    scenarios = [('promotion', 'voice'), ('rollback', 'face')]
    if all_modalities:
        scenarios += [('promotion', 'face'), ('rollback', 'voice')]
    for scenario, modality in scenarios:
        run = call('POST', prefix + '/runs', json={'scenario': scenario, 'modality': modality, 'seed': 501})
        deadline, phase = time.monotonic() + timeout, None
        while time.monotonic() < deadline:
            status = call('GET', prefix + '/state')
            current = status['current']
            if (current['status'], current['phase']) != phase:
                phase = (current['status'], current['phase'])
                print(scenario, run['id'], *phase, flush=True)
            if current['status'] not in {'QUEUED', 'RUNNING'}:
                break
            time.sleep(3)
        report = call('GET', prefix + '/evidence/' + run['id'])
        Path('reports').mkdir(exist_ok=True)
        evidence = json.dumps({'state': status, **report}, indent=2)
        Path(f'reports/simulation-{scenario}.json').write_text(evidence, encoding='utf-8')
        Path(f'reports/simulation-{scenario}-{modality}.json').write_text(evidence, encoding='utf-8')
        assert current['status'] == ('SUCCEEDED' if scenario == 'promotion' else 'ROLLED_BACK'), current
        assert current.get('airflow_run_id'), 'No Airflow run evidence'
        assert any(a['run_id'] == run['id'] and a['status'] == 'firing' for a in status['alerts']), 'No alert delivery'
        assert current['offline']['passed']
        assert current['offline']['candidate']['fnmr'] < current['offline']['champion']['fnmr']
        for stage in current['stages']:
            assert stage['samples'] == 200 and stage['response_mismatches'] == 0
            if stage['traffic_percent']:
                assert stage['served_candidate'] > 0
            else:
                assert stage['served_candidate'] == 0
        if scenario == 'promotion':
            assert [s['traffic_percent'] for s in current['stages']] == [0, 5, 10, 25, 50, 100]
            assert current['champion_probe']['versions'] == [current['candidate_version']]
        else:
            assert current['deployment']['evidence']['failure']['metric'] == 'fmr'
            assert current['rollback_probe']['served_candidate'] == 0
            assert current['rollback_probe']['versions'] == [current['baseline_version']]
        reset = call('POST', prefix + '/reset')['current']
        assert reset['status'] == 'RESET'
        assert reset['deployment']['champion_version'] == current['baseline_version']
        assert reset['deployment']['traffic_percent'] == 0
        results.append({'scenario': scenario, 'modality': modality, 'run_id': run['id'], 'outcome': current['status'],
                        'airflow_run_id': current['airflow_run_id'], 'reset': 'PASS'})
    after = call('GET', '/v1/admin/lifecycle/state')
    fields = ('modality', 'state', 'champion_version', 'challenger_version', 'traffic_percent')
    def snapshot(data):
        return sorted([{k: row[k] for k in fields} for row in data], key=lambda row: row['modality'])
    assert snapshot(before) == snapshot(after), 'Production policies changed'
    summary = {'status': 'PASS', 'synthetic': True, 'production_policies_unchanged': True, 'scenarios': results}
    Path('reports/simulation-verification.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True, help='Run both isolated scenarios and reset them')
    parser.add_argument('--all-modalities', action='store_true', help='Run promotion and rollback for both Face and Voice')
    args = parser.parse_args()
    load_dotenv()
    verify(os.getenv('PUBLIC_API_URL', 'http://localhost:18100'), os.environ['API_KEY'], all_modalities=args.all_modalities)
