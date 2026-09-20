"""Calibrate verification thresholds from enrolled samples and register an MLflow bundle."""
from __future__ import annotations

import argparse
import itertools
import json
import os
import tempfile
import time

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd
from mlflow import MlflowClient
from mlflow.models import infer_signature
from sqlalchemy import create_engine, text


def cosine(a, b) -> float:
    a, b = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def pairs(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    positive, negative = [], []
    by_person: dict[str, list[list[float]]] = {}
    for row in rows:
        by_person.setdefault(row["person_id"], []).append(row["embedding"])
    for vectors in by_person.values():
        positive.extend(cosine(a, b) for a, b in itertools.combinations(vectors, 2))
    people = sorted(by_person)
    for index, first in enumerate(people):
        for second in people[index + 1:index + 6]:
            negative.append(cosine(by_person[first][0], by_person[second][0]))
    return np.asarray(positive), np.asarray(negative)


def choose_threshold(positive: np.ndarray, negative: np.ndarray) -> tuple[float, dict[str, float]]:
    if len(positive) < 5 or len(negative) < 5:
        raise RuntimeError("Cần ít nhất 5 positive và 5 negative pairs để calibrate")
    best = None
    for threshold in np.linspace(-0.2, 0.95, 1151):
        far = float(np.mean(negative >= threshold))
        frr = float(np.mean(positive < threshold))
        objective = (far + frr) / 2
        if best is None or objective < best[0]:
            best = (objective, float(threshold), far, frr)
    _, threshold, far, frr = best
    return threshold, {"far": far, "frr": frr, "positive_pairs": len(positive), "negative_pairs": len(negative)}


class RiskBundle(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        with open(context.artifacts["thresholds"], encoding="utf-8") as handle:
            self.thresholds = json.load(handle)

    def predict(self, context, model_input, params=None):
        face = np.asarray(model_input.get("face_score", np.nan), dtype=float)
        voice = np.asarray(model_input.get("voice_score", np.nan), dtype=float)
        return ((face < self.thresholds["face_threshold"]) | (voice < self.thresholds["voice_threshold"])).astype(int)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--promote", action="store_true", help="Move champion alias to this version")
    args = parser.parse_args()
    database_url = os.getenv("DATABASE_URL", "sqlite:///./data/biometric.db")
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:15020")
    model_name = os.getenv("MLFLOW_MODEL_NAME", "face-voice-risk-bundle")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        raw = connection.execute(text("SELECT person_id, modality, embedding FROM biometric_samples")).mappings().all()
    grouped = {"face": [], "voice": []}
    for row in raw:
        embedding = row["embedding"]
        if isinstance(embedding, str):
            embedding = json.loads(embedding)
        grouped[row["modality"]].append({"person_id": row["person_id"], "embedding": embedding})
    metrics, thresholds = {}, {}
    for modality in ("face", "voice"):
        positive, negative = pairs(grouped[modality])
        threshold, result = choose_threshold(positive, negative)
        thresholds[f"{modality}_threshold"] = threshold
        metrics.update({f"{modality}_{key}": value for key, value in result.items()})
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("face-voice-calibration")
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "thresholds.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(thresholds, handle, indent=2)
        with mlflow.start_run() as run:
            mlflow.log_params({"dataset": "enrolled-samples", "modalities": "face,voice"})
            mlflow.log_metrics(metrics)
            input_example = pd.DataFrame({"face_score": [0.8], "voice_score": [0.7]})
            model_info = mlflow.pyfunc.log_model(
                artifact_path="bundle", python_model=RiskBundle(), artifacts={"thresholds": path},
                registered_model_name=model_name,
                input_example=input_example,
                signature=infer_signature(input_example, np.asarray([0], dtype=int)),
            )
            mlflow.set_tags({"purpose": "threshold-calibration", "run_id": run.info.run_id})
    client = MlflowClient()
    versions = client.search_model_versions(f"name='{model_name}'")
    version = max(versions, key=lambda item: int(item.version))
    for _ in range(30):
        version = client.get_model_version(model_name, version.version)
        if version.status == "READY":
            break
        time.sleep(1)
    client.set_registered_model_alias(model_name, "candidate", version.version)
    try:
        client.get_model_version_by_alias(model_name, "champion")
        champion_exists = True
    except Exception:
        champion_exists = False
    if args.promote or not champion_exists:
        client.set_registered_model_alias(model_name, "champion", version.version)
    print(json.dumps({"model": model_name, "version": version.version, "thresholds": thresholds, "metrics": metrics}, indent=2))


if __name__ == "__main__":
    main()
