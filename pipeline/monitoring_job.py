"""Airflow monitoring ETL: tenant-scoped windows, immutable S3 evidence and retrain signal."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import create_engine, text

from pipeline.dataset_ledger import publish_json
from pipeline.monitoring_etl import FEATURES, assess_window


def blind_review_sets(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    inputs = [{'check_id': row['id'], **{feature: row[feature] for feature in FEATURES}}
              for row in rows]
    labels = [{'check_id': row['id'], 'is_genuine': row['is_genuine'],
               'selection_reason': row['selection_reason']}
              for row in rows if row.get('is_genuine') is not None]
    return inputs, labels


def report_artifact(report: dict) -> tuple[str, dict]:
    """Content-address a report while excluding run-clock pointer metadata."""
    payload = {key: value for key, value in report.items()
               if key not in {'calculated_at', 'last_trigger_at', 'tenant_name'}}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return f"reports/{report['window_id']}/{digest}.json", payload


def training_run_id(report: dict) -> str:
    return f"monitor__{report['tenant_id']}__{report['window_id'][:32]}"


def training_run_exists(report: dict) -> bool:
    url = os.getenv('AIRFLOW__DATABASE__SQL_ALCHEMY_CONN')
    if not url:
        return False
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            return bool(connection.execute(text("""
                SELECT 1 FROM dag_run WHERE dag_id='biometric_model_pipeline'
                AND run_id=:run_id LIMIT 1
            """), {'run_id': training_run_id(report)}).scalar())
    finally:
        engine.dispose()


def build_report(rows: list[dict], *, tenant_id: str, model_version: str, window_size: int,
                 reference: list[dict] | None = None, previous_report: dict | None = None,
                 training_eligible: bool = False) -> tuple[dict, list[dict] | None]:
    current = rows[-window_size:]
    if reference is None and len(rows) >= 2 * window_size:
        reference = [{feature: row[feature] for feature in FEATURES}
                     for row in rows[-2 * window_size:-window_size]]
    marker = [{'id': row['id'], 'label': row.get('is_genuine'),
               'selection': row.get('selection_reason'), 'reviewed_at': str(row.get('reviewed_at'))}
              for row in current]
    feature_window_id = hashlib.sha256(json.dumps([row['id'] for row in current]).encode()).hexdigest()
    window_id = hashlib.sha256(json.dumps(marker, sort_keys=True).encode()).hexdigest()
    if previous_report and previous_report.get('window_id') == window_id:
        return {**previous_report, 'unchanged': True}, reference
    labels = [row for row in current if row.get('is_genuine') is not None]
    assessment = assess_window(reference or [], current, labels,
                               previous_drift=bool(previous_report and
                                                   previous_report.get('status') == 'drift_detected' and
                                                   previous_report.get('feature_window_id') is not None and
                                                   previous_report['feature_window_id'] != feature_window_id),
                               min_samples=window_size, training_eligible=training_eligible)
    return {**assessment, 'schema_version': 1, 'tenant_id': tenant_id,
            'model_version': model_version, 'window_id': window_id,
            'feature_window_id': feature_window_id,
            'current_first_event': current[0]['id'] if current else None,
            'current_last_event': current[-1]['id'] if current else None,
            'reviewed_count': len(labels), 'unchanged': False}, reference


def read_json(client, bucket: str, key: str):
    try:
        response = client.get_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') in {'404', 'NoSuchKey', 'NotFound'}:
            return None
        raise
    body = response['Body']
    try:
        return json.loads(body.read())
    finally:
        body.close()


def load_rows(connection, tenant_id: str, model_version: str, limit: int) -> list[dict]:
    rows = connection.execute(text("""
        SELECT c.id, e.face_score, e.voice_score, e.face_quality, e.voice_quality,
               e.risk_score, e.accepted, r.identity_truth, r.selection_reason,
               r.updated_at AS reviewed_at
        FROM integrity_checks c JOIN verification_events e ON e.id=c.event_id
        LEFT JOIN check_reviews r ON r.check_id=c.id
        WHERE c.tenant_id=:tenant AND e.model_version=:version
          AND e.face_score IS NOT NULL AND e.voice_score IS NOT NULL
        ORDER BY e.created_at DESC, c.id DESC LIMIT :limit
    """), {'tenant': tenant_id, 'version': model_version, 'limit': limit}).mappings().all()
    return [{**dict(row), 'is_genuine': True if row['identity_truth'] == 'genuine' else
             False if row['identity_truth'] == 'impostor' else None} for row in reversed(rows)]


def run_job() -> dict:
    engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
    client = boto3.client('s3', endpoint_url=os.getenv('MINIO_ENDPOINT', 'http://minio:9000'),
                          aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
                          aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])
    bucket = os.getenv('BIOMETRIC_BUCKET', 'biometric')
    window_size = int(os.getenv('MONITOR_ETL_WINDOW_SIZE', '40'))
    training_tenant = os.getenv('TRAINING_TENANT_ID', 'demo')
    enabled = os.getenv('CONTINUOUS_TRAINING_ENABLED', 'true').lower() == 'true'
    now = datetime.now(timezone.utc)
    summaries = []
    with engine.connect() as connection:
        tenants = connection.execute(text('SELECT id, name FROM tenants WHERE active=true')).mappings().all()
        for tenant in tenants:
            version = connection.execute(text("""
                SELECT e.model_version FROM integrity_checks c
                JOIN verification_events e ON e.id=c.event_id
                WHERE c.tenant_id=:tenant ORDER BY e.created_at DESC LIMIT 1
            """), {'tenant': tenant['id']}).scalar()
            if version is None:
                continue
            rows = load_rows(connection, tenant['id'], version, 2 * window_size)
            prefix = f"datasets/monitoring/{tenant['id']}/{version}"
            reference = read_json(client, bucket, prefix + '/reference.json')
            previous = read_json(client, bucket, prefix + '/latest.json')
            count = connection.execute(text("""
                SELECT count(DISTINCT p.id) FROM biometric_samples s JOIN people p ON p.id=s.person_id
                WHERE p.tenant_id=:tenant AND p.active=true
            """), {'tenant': tenant['id']}).scalar() or 0
            eligible = enabled and training_tenant == 'demo' and tenant['id'] == 'demo' and count >= 10
            report, new_reference = build_report(rows, tenant_id=tenant['id'], model_version=version,
                                                  window_size=window_size, reference=reference,
                                                  previous_report=previous, training_eligible=eligible)
            last_trigger = (previous or {}).get('last_trigger_at')
            if report['trigger_training'] and last_trigger and not report['unchanged']:
                if training_run_exists(previous) and now - datetime.fromisoformat(last_trigger) < timedelta(hours=24):
                    report['trigger_training'] = False
                    report['recommendation'] = 'training_cooldown'
            report['last_trigger_at'] = (now.isoformat() if report['trigger_training'] and not report['unchanged']
                                         else last_trigger)
            report['tenant_name'] = tenant['name']
            report['calculated_at'] = now.isoformat()
            if new_reference is not None and reference is None:
                publish_json(client, bucket, prefix + '/reference.json', new_reference)
            if not report['unchanged']:
                inputs, labels = blind_review_sets(rows[-window_size:])
                input_key = prefix + '/prediction-inputs/' + report['window_id'] + '.json'
                label_key = prefix + '/reviewed-labels/' + report['window_id'] + '.json'
                publish_json(client, bucket, input_key, inputs)
                publish_json(client, bucket, label_key, labels)
                report['prediction_input_key'] = input_key
                report['label_snapshot_key'] = label_key
                report_suffix, immutable_report = report_artifact(report)
                publish_json(client, bucket, prefix + '/' + report_suffix, immutable_report)
                report['report_key'] = prefix + '/' + report_suffix
                client.put_object(Bucket=bucket, Key=prefix + '/latest.json',
                                  Body=json.dumps(report, allow_nan=False).encode(),
                                  ContentType='application/json')
            summaries.append(report)
    engine.dispose()
    summary = {'calculated_at': now.isoformat(), 'tenants': summaries,
               'trigger_training': any(row['trigger_training'] for row in summaries)}
    path = Path(os.getenv('MONITORING_SUMMARY_PATH', '/opt/project/data/monitoring/latest.json'))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, allow_nan=False, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    print(json.dumps(run_job(), allow_nan=False))
