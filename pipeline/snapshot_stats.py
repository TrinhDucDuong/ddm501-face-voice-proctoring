import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./data/biometric.db"))
with engine.connect() as connection:
    stats = dict(connection.execute(text("""
        SELECT
          (SELECT count(*) FROM people WHERE active = true) AS people,
          (SELECT count(*) FROM biometric_samples WHERE modality = 'face') AS face_samples,
          (SELECT count(*) FROM biometric_samples WHERE modality = 'voice') AS voice_samples,
          (SELECT count(*) FROM verification_events) AS verification_events
    """)).mappings().one())
stats["created_at"] = datetime.now(timezone.utc).isoformat()
target = Path(os.getenv("SNAPSHOT_DIR", "/opt/project/data/snapshots"))
target.mkdir(parents=True, exist_ok=True)
path = target / f"snapshot-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
print(path, stats)

