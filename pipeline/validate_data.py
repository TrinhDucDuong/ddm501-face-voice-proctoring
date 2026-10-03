"""Fail-fast data quality gate for enrolled biometric feature records."""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict

import numpy as np
from sqlalchemy import create_engine


def validate(rows: list[dict], modalities=('face', 'voice')) -> dict:
    errors: list[str] = []
    counts = Counter(row["modality"] for row in rows)
    dimensions: dict[str, set[int]] = defaultdict(set)
    people: dict[str, set[str]] = defaultdict(set)
    hashes: set[tuple[str, str, str]] = set()
    for row in rows:
        modality = row["modality"]
        if modality not in {"face", "voice"}:
            errors.append(f"unsupported modality: {modality}")
            continue
        embedding = row["embedding"]
        if isinstance(embedding, str):
            embedding = json.loads(embedding)
        vector = np.asarray(embedding, dtype=float)
        dimensions[modality].add(vector.size)
        people[modality].add(str(row["person_id"]))
        if vector.ndim != 1 or vector.size < 16 or not np.isfinite(vector).all() or np.linalg.norm(vector) < 1e-8:
            errors.append(f"invalid embedding: {row['id']}")
        if not 0 <= float(row["quality"]) <= 1:
            errors.append(f"quality outside [0,1]: {row['id']}")
        key = (str(row["person_id"]), modality, row["sha256"])
        if key in hashes:
            errors.append(f"duplicate sample: {row['id']}")
        hashes.add(key)
    for modality in modalities:
        if len(dimensions[modality]) != 1:
            errors.append(f"inconsistent {modality} dimensions: {sorted(dimensions[modality])}")
        if len(people[modality]) < 3:
            errors.append(f"{modality} needs at least 3 identities")
        if counts[modality] < 10:
            errors.append(f"{modality} needs at least 10 samples")
    summary = {
        "valid": not errors, "errors": errors, "counts": dict(counts),
        "identities": {key: len(value) for key, value in people.items()},
        "dimensions": {key: sorted(value) for key, value in dimensions.items()},
    }
    if errors:
        raise ValueError(json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> None:  # pragma: no cover - thin database/CLI adapter
    if os.getenv("SNAPSHOT_PATH"):
        from data_snapshot import read_snapshot
        rows = read_snapshot(os.environ["SNAPSHOT_PATH"])["samples"]
    else:
        from data_snapshot import extract
        engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./data/biometric.db"))
        with engine.connect() as connection:
            rows = extract(connection)["samples"]
    modality = os.getenv('MODEL_MODALITY')
    if modality in ('face', 'voice'):
        rows = [r for r in rows if r['modality'] == modality]
    print(json.dumps(validate([dict(row) for row in rows], (modality,) if modality in ('face', 'voice')
                              else ('face', 'voice')), indent=2))


if __name__ == "__main__":
    main()
