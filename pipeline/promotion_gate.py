"""Validate candidate metrics and promote the MLflow alias only when gates pass."""
from __future__ import annotations

import json
import math
import os


def compare_paired_holdout(scores, champion_thresholds, challenger_thresholds,
                           tolerance: float = .02, minimum_gain: float = .01) -> dict:
    """Compare both policies on identical identity-held-out score arrays."""
    results = {'champion': {}, 'challenger': {}}
    for modality in ('face', 'voice'):
        positive, negative = scores[modality]
        if min(len(positive), len(negative)) < 5:
            raise ValueError(f'Insufficient paired {modality} holdout scores')
        for role, thresholds in (('champion', champion_thresholds), ('challenger', challenger_thresholds)):
            threshold = float(thresholds[f'{modality}_threshold'])
            results[role][modality] = {
                'far': sum(bool(score >= threshold) for score in negative) / len(negative),
                'frr': sum(bool(score < threshold) for score in positive) / len(positive),
                'positive_pairs': len(positive), 'negative_pairs': len(negative),
            }
    values = [(results['champion'][modality][metric], results['challenger'][modality][metric])
              for modality in ('face', 'voice') for metric in ('far', 'frr')]
    regression = bool(any(new > old + tolerance for old, new in values))
    gain = float(sum(old - new for old, new in values))
    results.update(promote=not regression and gain >= minimum_gain,
                   reason='holdout_regression' if regression else
                          'no_measured_gain' if gain < minimum_gain else 'improved',
                   aggregate_error_gain=gain)
    return results


def compare_reviewed_shadow(rows, champion_thresholds, challenger_thresholds,
                            min_per_class: int = 5, tolerance: float = .02) -> dict:
    """Replay both identity policies on the same independently audited checks."""
    audited = [row for row in rows if row.get('selection_reason') == 'random_audit'
               and row.get('is_genuine') is not None and row.get('face_score') is not None
               and row.get('voice_score') is not None]
    genuine = [row for row in audited if row['is_genuine']]
    impostors = [row for row in audited if not row['is_genuine']]
    if min(len(genuine), len(impostors)) < min_per_class:
        return {'status': 'insufficient_data', 'sample_count': len(audited),
                'genuine_count': len(genuine), 'impostor_count': len(impostors)}

    def rates(thresholds):
        def accepted(row):
            return (row['face_score'] >= float(thresholds['face_threshold']) and
                    row['voice_score'] >= float(thresholds['voice_threshold']))
        return {'far': sum(accepted(row) for row in impostors) / len(impostors),
                'frr': sum(not accepted(row) for row in genuine) / len(genuine)}

    incumbent, challenger = rates(champion_thresholds), rates(challenger_thresholds)
    regression = any(challenger[key] > incumbent[key] + tolerance for key in ('far', 'frr'))
    return {'status': 'regression' if regression else 'pass', 'sample_count': len(audited),
            'champion': incumbent, 'challenger': challenger}


def load_reviewed_shadow(database_url: str, tenant_id: str, limit: int = 500) -> list[dict]:
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT e.face_score, e.voice_score, r.identity_truth, r.selection_reason
                FROM check_reviews r JOIN integrity_checks c ON c.id=r.check_id
                JOIN verification_events e ON e.id=c.event_id
                WHERE c.tenant_id=:tenant AND r.selection_reason='random_audit'
                  AND r.identity_truth IN ('genuine','impostor')
                ORDER BY r.updated_at DESC LIMIT :limit
            """), {'tenant': tenant_id, 'limit': limit}).mappings().all()
        return [{**dict(row), 'is_genuine': row['identity_truth'] == 'genuine'} for row in rows]
    finally:
        engine.dispose()


def paired_scores_from_snapshot(snapshot: dict) -> dict:
    if __package__:
        from pipeline.dataset_ledger import identity_split
        from pipeline.evaluation import policy_scores
    else:
        from dataset_ledger import identity_split
        from evaluation import policy_scores

    holdout = set(identity_split(snapshot['samples'])['holdout_identities'])
    return {modality: policy_scores([row for row in snapshot['samples']
                                    if row['modality'] == modality and str(row['person_id']) in holdout])
            for modality in ('face', 'voice')}


def get_champion(client, model_name):
    try:
        return client.get_model_version_by_alias(model_name, 'champion')
    except Exception as exc:
        if getattr(exc, 'error_code', None) == 'RESOURCE_DOES_NOT_EXIST':
            return None
        raise


def gate(metrics: dict[str, float], max_error_rate: float = 0.20, min_pairs: int = 5, require_identity: bool = True) -> list[str]:
    failures = []
    for modality in ("face", "voice"):
        for metric in ("far", "frr", "cv_far", "cv_frr") + (("holdout_far", "holdout_frr") if require_identity else ()):
            value = metrics.get(f"{modality}_{metric}")
            if value is None or not math.isfinite(value) or not 0 <= value <= max_error_rate:
                failures.append(f"{modality}_{metric}={value} > {max_error_rate}")
        for metric in ("positive_pairs", "negative_pairs") + (("holdout_positive_pairs", "holdout_negative_pairs") if require_identity else ()):
            value = metrics.get(f"{modality}_{metric}", 0)
            if not math.isfinite(value) or value < min_pairs:
                failures.append(f"{modality}_{metric}={value} < {min_pairs}")
    return failures


def promote(client, model_name, candidate, expected_run_id=None):
    run = client.get_run(candidate.run_id)
    if expected_run_id and candidate.run_id != expected_run_id:
        raise RuntimeError('Candidate belongs to another pipeline run')
    failures = gate(run.data.metrics, float(os.getenv('MAX_BIOMETRIC_ERROR_RATE', '0.20')))
    if os.getenv('REQUIRE_HUMAN_FAIRNESS', 'false').lower() == 'true':
        report = json.loads(__import__('pathlib').Path(os.environ['RAI_REPORT']).read_text())
        if report.get('gate') != 'pass':
            failures.append('human fairness evidence is insufficient or rejected')
    result = {'model': model_name, 'candidate': candidate.version, 'metrics': run.data.metrics, 'failures': failures}
    champion = None if failures else get_champion(client, model_name)
    if champion is not None:
        if not os.getenv('SNAPSHOT_PATH'):
            raise RuntimeError('Locked snapshot required for paired champion/challenger comparison')
        if __package__:
            from pipeline.data_snapshot import read_snapshot
        else:
            from data_snapshot import read_snapshot

        snapshot = read_snapshot(os.environ['SNAPSHOT_PATH'])
        scores = paired_scores_from_snapshot(snapshot)
        incumbent = client.get_run(champion.run_id)
        result['paired_holdout'] = compare_paired_holdout(scores, incumbent.data.params, run.data.params)
        result['previous_champion'] = champion.version
        if not result['paired_holdout']['promote']:
            failures.append(result['paired_holdout']['reason'])
        if os.getenv('REQUIRE_REVIEWED_SHADOW', 'true').lower() == 'true':
            if not os.getenv('DATABASE_URL'):
                raise RuntimeError('DATABASE_URL required for reviewed shadow gate')
            reviewed = load_reviewed_shadow(os.environ['DATABASE_URL'],
                                            snapshot.get('tenant_scope', 'demo'))
            result['reviewed_shadow'] = compare_reviewed_shadow(reviewed, incumbent.data.params,
                                                                run.data.params)
            if result['reviewed_shadow']['status'] != 'pass':
                failures.append('reviewed_shadow_' + result['reviewed_shadow']['status'])
    print(json.dumps(result, indent=2))
    client.set_model_version_tag(model_name, candidate.version, 'promotion_status', 'rejected' if failures else 'passed')
    if 'paired_holdout' in result:
        client.set_model_version_tag(model_name, candidate.version, 'paired_holdout',
                                     json.dumps(result['paired_holdout']))
    if failures:
        # A valid but non-improving candidate is retained for inspection; champion stays pinned.
        if set(failures) <= {'no_measured_gain', 'reviewed_shadow_insufficient_data'}:
            return result
        raise RuntimeError('candidate rejected by model validation gate')
    if champion is not None:
        client.set_model_version_tag(model_name, candidate.version, 'rollback_version', champion.version)
    client.set_registered_model_alias(model_name, 'champion', candidate.version)
    return result


def main() -> None:  # pragma: no cover - exercised against MLflow in the Airflow integration test
    if os.getenv('MODEL_MODALITY') in ('face', 'voice'):
        from pathlib import Path

        import requests
        evidence = json.loads(Path(os.environ['SNAPSHOT_PATH'] + '.candidate.json').read_text(encoding='utf-8'))
        response = requests.post(os.environ['API_URL'].rstrip('/') +
                                 '/v1/admin/lifecycle/' + evidence['modality'] + '/candidate',
                                 headers={'X-API-Key': os.environ['API_KEY']},
                                 json={'version': evidence['version'], 'window_id': evidence['window_id']}, timeout=90)
        response.raise_for_status()
        print(json.dumps(response.json()))
        return
    raise RuntimeError('Direct champion promotion is disabled; supply MODEL_MODALITY through Airflow')


if __name__ == "__main__":
    main()
