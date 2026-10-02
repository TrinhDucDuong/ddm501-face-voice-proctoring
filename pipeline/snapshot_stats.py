import json
import os
from datetime import datetime, timezone
from pathlib import Path

from data_snapshot import extract, read_snapshot
from sqlalchemy import create_engine

path = Path(os.getenv("SNAPSHOT_PATH", str(
    Path(os.getenv("SNAPSHOT_DIR", "/opt/project/data/snapshots"))
    / f"snapshot-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json"
)))
if path.exists():
    snapshot = read_snapshot(str(path))
else:
    engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./data/biometric.db"))
    with engine.connect() as connection:
        snapshot = extract(connection)
    engine.dispose()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
print(json.dumps({"path": str(path), "dataset_version": snapshot["dataset_version"],
                  "samples": len(snapshot["samples"])}))
