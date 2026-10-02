"""Create an auditable fairness/proxy-slice and explainability report from reviewed events."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

from sqlalchemy import create_engine, text

QUERY = """
SELECT
  CASE
    WHEN LEAST(COALESCE(e.face_quality, 0), COALESCE(e.voice_quality, 0)) < 0.4 THEN 'low'
    WHEN LEAST(COALESCE(e.face_quality, 0), COALESCE(e.voice_quality, 0)) < 0.7 THEN 'medium'
    ELSE 'high'
  END AS quality_slice,
  CASE WHEN f.reviewer = 'synthetic-simulation' THEN 'synthetic'
       WHEN f.reviewer LIKE 'operator:%' THEN 'human' ELSE 'untrusted' END AS label_source,
  COUNT(*) AS reviewed,
  SUM(CASE WHEN f.is_genuine THEN 1 ELSE 0 END) AS genuine_count,
  SUM(CASE WHEN NOT f.is_genuine THEN 1 ELSE 0 END) AS impostor_count,
  AVG(CASE WHEN e.accepted = f.is_genuine THEN 1.0 ELSE 0.0 END) AS accuracy,
  SUM(CASE WHEN NOT f.is_genuine AND e.accepted THEN 1.0 ELSE 0.0 END)
    / NULLIF(SUM(CASE WHEN NOT f.is_genuine THEN 1.0 ELSE 0.0 END), 0) AS false_accept_rate,
  SUM(CASE WHEN f.is_genuine AND NOT e.accepted THEN 1.0 ELSE 0.0 END)
    / NULLIF(SUM(CASE WHEN f.is_genuine THEN 1.0 ELSE 0.0 END), 0) AS false_reject_rate
FROM verification_events e
JOIN verification_feedback f ON f.event_id = e.id
GROUP BY 1, 2 ORDER BY 1, 2
"""


def build_report(rows: list[dict]) -> dict:
    slices = [{key: (float(value) if value is not None and (key.endswith("rate") or key == "accuracy") else value) for key, value in row.items()} for row in rows]
    accuracies = [row["accuracy"] for row in slices if row["reviewed"] >= 20 and row.get("label_source") == "human"
                  and row.get('genuine_count', 0) >= 5 and row.get('impostor_count', 0) >= 5]
    for row in slices:
        for rate, count in [('false_accept_rate', 'impostor_count'), ('false_reject_rate', 'genuine_count')]:
            n, p = row.get(count, 0), row.get(rate)
            if n and p is not None:
                z = 1.96
                center = (p + z*z/(2*n)) / (1 + z*z/n)
                half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
                row[rate + '_ci95'] = [max(0, center-half), min(1, center+half)]
            else:
                row[rate + '_ci95'] = None
    gap = max(accuracies) - min(accuracies) if len(accuracies) >= 2 else None
    return {
        "fairness_proxy": "capture_quality_slice",
        "slices": slices,
        "max_accuracy_gap": gap,
        "gate": "pass" if gap is not None and gap <= 0.10 else "insufficient_data" if gap is None else "review",
        "explainability": {
            "methods": ["policy_reason_codes", "decision_boundary_margins", "threshold_sensitivity", "single_modality_counterfactual"],
            "method": "policy reason codes and modality-level similarity/quality scores",
            "reason_codes": ["face_mismatch", "voice_mismatch", "low_face_quality", "low_voice_quality", "missing_face", "missing_voice"],
        },
        "limitations": "Quality slices are operational proxies, not demographic fairness. Consent-based demographic labels are required before demographic claims.",
    }


def main() -> None:
    engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./data/biometric.db"))
    with engine.connect() as connection:
        rows = [dict(row) for row in connection.execute(text(QUERY)).mappings().all()]
    report = build_report(rows)
    target = Path(os.getenv("RAI_REPORT", "/opt/project/data/reports/responsible-ai.json"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
