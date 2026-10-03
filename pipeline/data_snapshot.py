"""Content-addressed training inputs shared by extraction, validation and calibration."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect, text


def dataset_version(rows: list[dict]) -> str:
    canonical = json.dumps(sorted(rows, key=lambda row: row["id"]), sort_keys=True, allow_nan=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def training_scope() -> str:
    tenant = os.getenv('TRAINING_TENANT_ID', 'demo')
    if tenant != 'demo':
        raise ValueError('Customer training requires recorded data-use consent; only demo is eligible')
    return tenant


def extract(connection) -> dict:
    tenant = training_scope()
    rows = [dict(row) for row in connection.execute(text(
        "SELECT s.id, s.person_id, s.modality, s.embedding, s.quality, s.sha256 FROM biometric_samples s "
        "JOIN people p ON p.id=s.person_id WHERE p.tenant_id=:tenant AND p.active=true ORDER BY s.id"
    ), {"tenant": tenant}).mappings()]
    for row in rows:
        if isinstance(row["embedding"], str):
            row["embedding"] = json.loads(row["embedding"])
    modality = os.getenv('MODEL_MODALITY')
    if modality in ('face', 'voice') and inspect(connection).has_table('modality_observations'):
        reviewed = connection.execute(text(
            "SELECT id, person_id, modality, embedding, quality, media_sha256 FROM modality_observations "
            "WHERE tenant_id=:tenant AND modality=:modality AND truth=true AND random_audit=true "
            "AND integrity_passed=true AND embedding IS NOT NULL ORDER BY created_at DESC LIMIT 10000"
        ), {'tenant': tenant, 'modality': modality}).mappings()
        seen = {(r['person_id'], r['modality'], r['sha256']) for r in rows}
        for item in reviewed:
            key = (item['person_id'], item['modality'], item['media_sha256'])
            quality = json.loads(item['quality']) if isinstance(item['quality'], str) else item['quality']
            vector = json.loads(item['embedding']) if isinstance(item['embedding'], str) else item['embedding']
            if key not in seen and vector and quality.get('quality', 0) >= .7:
                rows.append({'id': 'reviewed-' + item['id'], 'person_id': item['person_id'],
                             'modality': item['modality'], 'embedding': vector,
                             'quality': quality['quality'], 'sha256': item['media_sha256']})
                seen.add(key)
    return {"schema_version": 2, "dataset_version": dataset_version(rows), "samples": rows,
            "tenant_scope": tenant,
            "created_at": datetime.now(timezone.utc).isoformat()}


def read_snapshot(path: str) -> dict:
    snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
    if dataset_version(snapshot["samples"]) != snapshot["dataset_version"]:
        raise ValueError("Snapshot fingerprint mismatch")
    return snapshot
