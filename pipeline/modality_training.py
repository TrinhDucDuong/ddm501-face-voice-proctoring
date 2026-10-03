"""Reuse identity-disjoint calibration for one independent threshold policy."""
import json
import math
import os
import tempfile
from pathlib import Path

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
from mlflow import MlflowClient
from mlflow.models import infer_signature

from pipeline.data_snapshot import read_snapshot
from pipeline.drift_decision import DriftConfig, performance
from pipeline.evaluation import identity_evaluation, policy_scores


def paired_gate(positive, negative, champion_threshold, candidate_threshold, metrics, limits):
    evidence = [{'score': float(value), 'threshold': champion_threshold, 'truth': truth, 'random_audit': True}
                for truth, values in [(True, positive), (False, negative)] for value in values]
    config = DriftConfig(min_labels_per_class=limits.min_labels_per_class, target_far=limits.max_fmr)
    incumbent = performance(evidence, config)
    candidate = performance([{**r, 'threshold': candidate_threshold} for r in evidence], config)
    passed = incumbent['status'] == candidate['status'] == 'READY'
    for metric, limit, regression in [('fmr', limits.max_fmr, limits.max_security_regression),
                                    ('fnmr', limits.max_fnmr, limits.max_fnmr_regression)]:
        passed = passed and candidate[metric] <= min(limit, incumbent[metric] + regression)
    for key in ('far', 'frr', 'cv_far', 'cv_frr', 'holdout_far', 'holdout_frr'):
        value = metrics.get(key, float('nan'))
        passed = passed and math.isfinite(value) and 0 <= value <= (limits.max_fmr if 'far' in key else limits.max_fnmr)
    return {'passed': bool(passed), 'champion': incumbent, 'candidate': candidate}


class ThresholdPolicy(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        self.threshold = json.loads(Path(context.artifacts['policy']).read_text())['threshold']

    def predict(self, context, model_input, params=None):
        scores = np.asarray(model_input['score'], dtype=float)
        return np.isfinite(scores) & (np.abs(scores) <= 1) & (scores >= self.threshold)


def register_policy(modality, threshold, metrics, evidence, provenance, registry_name=None):
    if modality not in ('face', 'voice'):
        raise ValueError('Unknown modality')
    name = registry_name or f'{modality}-verification'
    client = MlflowClient()
    if provenance.get('training_window'):
        for version in client.search_model_versions(f"name='{name}'"):
            params = client.get_run(version.run_id).data.params
            if params.get('training_window') == provenance['training_window']:
                if (params.get('dataset_version') != provenance['dataset_version'] or
                        float(params['threshold']) != threshold):
                    raise ValueError('Training retry changed the locked dataset or policy')
                return str(version.version)
    mlflow.set_experiment(f'{modality}-threshold-policy')
    with tempfile.TemporaryDirectory() as directory, mlflow.start_run() as run:
        path = Path(directory) / 'policy.json'
        path.write_text(json.dumps({'modality': modality, 'threshold': threshold}), encoding='utf-8')
        mlflow.log_params({'modality': modality, 'threshold': threshold, **provenance})
        mlflow.log_metrics(metrics)
        mlflow.log_dict(evidence, 'evaluation/paired-scores.json')
        frame = pd.DataFrame({'score': [.1, .9]})
        mlflow.pyfunc.log_model(artifact_path='policy', python_model=ThresholdPolicy(),
            artifacts={'policy': str(path)}, registered_model_name=name,
            pip_requirements=['mlflow==2.22.0', 'numpy==1.26.4', 'pandas==2.2.3'],
            input_example=frame, signature=infer_signature(frame, np.array([False, True])))
        client = MlflowClient()
        versions = client.search_model_versions(f"name='{name}'")
        version = next(v for v in versions if v.run_id == run.info.run_id)
        client.set_registered_model_alias(name, 'candidate', version.version)
        client.set_model_version_tag(name, version.version, 'lifecycle_status', 'CANDIDATE')
        return str(version.version)


def train(modality):
    import requests

    base = os.environ['API_URL'].rstrip('/')
    headers = {'X-API-Key': os.environ['API_KEY']}
    window = os.environ['TRAINING_WINDOW_ID']
    claimed = requests.post(base + f'/v1/admin/lifecycle/{modality}/claim',
                            headers=headers, json={'window_id': window}, timeout=30)
    claimed.raise_for_status()
    snapshot = read_snapshot(os.environ['SNAPSHOT_PATH'])
    rows = [r for r in snapshot['samples'] if r['modality'] == modality]
    threshold, metrics, evaluation = identity_evaluation(rows)
    holdout = set(evaluation['holdout_identities'])
    positive, negative = policy_scores([r for r in rows if str(r['person_id']) in holdout])
    mlflow.set_tracking_uri(os.environ['MLFLOW_TRACKING_URI'])
    version = register_policy(modality, threshold, metrics,
        {'positive': positive.tolist(), 'negative': negative.tolist(), 'evaluation': evaluation},
        {'dataset_version': snapshot['dataset_version'], 'training_window': window,
         'tenant_scope': snapshot['tenant_scope'], 'model_family': 'cosine-threshold-policy'})
    result = {'version': version, 'window_id': window, 'modality': modality}
    Path(os.environ['SNAPSHOT_PATH'] + '.candidate.json').write_text(json.dumps(result), encoding='utf-8')
    print(json.dumps(result))
