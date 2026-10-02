"""Immutable, tenant-scoped feature snapshots for calibration and audit."""
import hashlib
import json
import os
from pathlib import Path

import boto3
import numpy as np
from botocore.exceptions import ClientError


def identity_split(rows: list[dict], folds: int = 5) -> dict:
    people = sorted({str(row['person_id']) for row in rows})
    if len(people) < folds * 2:
        raise ValueError('At least two identities per partition are required')
    partitions = np.array_split(np.random.default_rng(501).permutation(people), folds)
    holdout = sorted(map(str, partitions[0]))
    return {'method': 'identity-disjoint-seed-501', 'holdout_identities': holdout,
            'calibration_identities': sorted(set(people) - set(holdout)),
            'calibration_fold_identities': [sorted(map(str, fold)) for fold in partitions[1:]]}


def manifest_for_snapshot(snapshot: dict) -> dict:
    return {'schema_version': 1, 'dataset_version': snapshot['dataset_version'],
            'tenant_scope': snapshot['tenant_scope'], 'sample_count': len(snapshot['samples']),
            'label_provenance': 'enrollment_identity_only', 'contains_raw_media': False,
            'split': identity_split(snapshot['samples'])}


def publish_json(client, bucket: str, key: str, payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, allow_nan=False).encode('utf-8')
    digest = hashlib.sha256(body).hexdigest()
    try:
        item = client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get('Error', {}).get('Code') not in {'404', 'NoSuchKey', 'NotFound'}:
            raise
    else:
        if item.get('Metadata', {}).get('sha256') != digest:
            raise ValueError(f'Immutable dataset object changed: {key}')
        return digest
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType='application/json',
                      Metadata={'sha256': digest})
    return digest


def publish_snapshot(snapshot: dict, client=None) -> dict:
    client = client or boto3.client('s3', endpoint_url=os.getenv('MINIO_ENDPOINT', 'http://localhost:19100'),
                                   aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
                                   aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'])
    bucket = os.getenv('BIOMETRIC_BUCKET', 'biometric')
    prefix = f"datasets/training/{snapshot['tenant_scope']}/{snapshot['dataset_version']}"
    manifest = manifest_for_snapshot(snapshot)
    stable = {key: value for key, value in snapshot.items() if key != 'created_at'}
    stable['samples'] = sorted(snapshot['samples'], key=lambda row: row['id'])
    snapshot_key = prefix + '/snapshot.json'
    try:
        digest = publish_json(client, bucket, snapshot_key, stable)
    except ValueError:
        # Early manifests included a run timestamp. Preserve that immutable object
        # when the actual dataset is identical instead of rewriting history.
        response = client.get_object(Bucket=bucket, Key=snapshot_key)
        body = response['Body']
        try:
            raw = body.read()
        finally:
            body.close()
        existing = json.loads(raw)
        existing.pop('created_at', None)
        existing['samples'] = sorted(existing['samples'], key=lambda row: row['id'])
        if existing != stable:
            raise
        digest = hashlib.sha256(raw).hexdigest()
    manifest['snapshot_sha256'] = digest
    publish_json(client, bucket, prefix + '/manifest.json', manifest)
    return {'bucket': bucket, 'prefix': prefix, 'manifest': manifest}


if __name__ == '__main__':
    from pipeline.data_snapshot import read_snapshot
    path = Path(os.environ['SNAPSHOT_PATH'])
    print(json.dumps(publish_snapshot(read_snapshot(str(path))), indent=2))
