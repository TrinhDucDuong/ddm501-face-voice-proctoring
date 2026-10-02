"""Generate stable then shifted score observations through the serving API."""
from __future__ import annotations

import argparse
import os
import uuid

import numpy as np
import requests


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=120, help="samples per reference/current window")
    parser.add_argument("--seed", type=int, default=501)
    parser.add_argument("--with-feedback", action="store_true",
                        help="Generate labelled synthetic scenarios for Evidently; never real human review")
    args = parser.parse_args()
    api = os.getenv("PUBLIC_API_URL", "http://127.0.0.1:18100")
    headers = {"X-API-Key": os.getenv("API_KEY", "demo-internal-key")}
    external_id = f"DRIFT-{uuid.uuid4().hex[:8]}"
    response = requests.post(
        f"{api}/v1/people", headers=headers,
        json={"external_id": external_id, "display_name": "Drift simulation identity"}, timeout=10,
    )
    response.raise_for_status()
    person_id = response.json()["id"]
    rng = np.random.default_rng(args.seed)
    regimes = (("reference", 0.78, 0.05), ("shifted", 0.48, 0.09))
    for regime, center, spread in regimes:
        for index in range(args.samples):
            genuine = index % 2 == 0
            score_center = center
            if args.with_feedback:
                # Ground truth is generated first; shifted data deliberately contradicts it.
                score_center = 0.95 if genuine == (regime == "reference") else 0.02
            payload = {
                "person_id": person_id, "session_id": f"sim-{regime}-{index:04d}",
                "face_score": float(np.clip(rng.normal(score_center, spread), 0, 1)),
                "voice_score": float(np.clip(rng.normal(score_center - 0.05, spread), 0, 1)),
                "face_quality": float(np.clip(rng.normal(0.8 if regime == "reference" else 0.5, 0.08), 0, 1)),
                "voice_quality": float(np.clip(rng.normal(0.82 if regime == "reference" else 0.55, 0.08), 0, 1)),
            }
            result = requests.post(f"{api}/v1/simulation/observations", headers=headers, json=payload, timeout=10)
            result.raise_for_status()
            if args.with_feedback:
                feedback = requests.put(
                    f"{api}/v1/events/{result.json()['event_id']}/feedback", headers=headers,
                    json={"is_genuine": genuine, "reviewer": "synthetic-simulation",
                          "notes": f"Generated {regime} ground truth; pipeline test only, not a human review"},
                    timeout=10,
                )
                feedback.raise_for_status()
    print(f"created {args.samples * 2} observations for {person_id}")


if __name__ == "__main__":
    main()
