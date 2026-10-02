"""Content-addressed training inputs shared by extraction, validation and calibration."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text


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
    return {"schema_version": 2, "dataset_version": dataset_version(rows), "samples": rows,
            "tenant_scope": tenant,
            "created_at": datetime.now(timezone.utc).isoformat()}


def read_snapshot(path: str) -> dict:
    snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
    if dataset_version(snapshot["samples"]) != snapshot["dataset_version"]:
        raise ValueError("Snapshot fingerprint mismatch")
    return snapshot
