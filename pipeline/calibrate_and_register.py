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
from sqlalchemy import create_engine

if __package__:
    from .data_snapshot import extract, read_snapshot
    from .evaluation import identity_evaluation, select_trial
    from .validate_data import validate
else:
    from data_snapshot import extract, read_snapshot
    from evaluation import identity_evaluation, select_trial
    from validate_data import validate


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
        objective = (max(far, frr), (far + frr) / 2)
        if best is None or objective < best[0]:
            best = (objective, float(threshold), far, frr)
    _, threshold, far, frr = best
    return threshold, {"far": far, "frr": frr, "positive_pairs": len(positive), "negative_pairs": len(negative)}


def cross_validate(positive: np.ndarray, negative: np.ndarray, folds: int = 5) -> dict[str, float]:
    """Deterministic stratified CV for threshold stability and out-of-fold error."""
    if min(len(positive), len(negative)) < 10:
        return {}
    rng = np.random.default_rng(501)
    positive, negative = rng.permutation(positive), rng.permutation(negative)
    results, far_results, frr_results = [], [], []
    positive_folds = np.array_split(np.arange(len(positive)), folds)
    negative_folds = np.array_split(np.arange(len(negative)), folds)
    for positive_index, negative_index in zip(positive_folds, negative_folds, strict=False):
        positive_test, negative_test = positive[positive_index], negative[negative_index]
        positive_train = np.delete(positive, positive_index)
        negative_train = np.delete(negative, negative_index)
        threshold, _ = choose_threshold(positive_train, negative_train)
        far = float(np.mean(negative_test >= threshold))
        frr = float(np.mean(positive_test < threshold))
        results.append((far + frr) / 2)
        far_results.append(far)
        frr_results.append(frr)
    return {
        "cv_balanced_error_mean": float(np.mean(results)),
        "cv_balanced_error_std": float(np.std(results)),
        "cv_folds": float(folds),
        "cv_far": float(np.mean(far_results)),
        "cv_frr": float(np.mean(frr_results)),
    }


class RiskBundle(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        with open(context.artifacts["thresholds"], encoding="utf-8") as handle:
            self.thresholds = json.load(handle)

    def predict(self, context, model_input, params=None):
        face = np.asarray(model_input.get("face_score", np.nan), dtype=float)
        voice = np.asarray(model_input.get("voice_score", np.nan), dtype=float)
        invalid = ~np.isfinite(face) | ~np.isfinite(voice) | (np.abs(face) > 1) | (np.abs(voice) > 1)
        return (invalid | (face < self.thresholds["face_threshold"]) | (voice < self.thresholds["voice_threshold"])).astype(int)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--promote", action="store_true", help="Move champion alias to this version")
    args = parser.parse_args()
    database_url = os.getenv("DATABASE_URL", "sqlite:///./data/biometric.db")
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:15020")
    model_name = os.getenv("MLFLOW_MODEL_NAME", "face-voice-risk-bundle")
    if os.getenv("SNAPSHOT_PATH"):
        snapshot = read_snapshot(os.environ["SNAPSHOT_PATH"])
    else:
        engine = create_engine(database_url)
        with engine.connect() as connection:
            snapshot = extract(connection)
        engine.dispose()
    raw = snapshot["samples"]
    quality = validate(raw)
    grouped = {"face": [], "voice": []}
    for row in raw:
        embedding = row["embedding"]
        if isinstance(embedding, str):
            embedding = json.loads(embedding)
        grouped[row["modality"]].append({"person_id": row["person_id"], "embedding": embedding})
    metrics, thresholds, evaluations = {}, {}, {}
    for modality in ("face", "voice"):
        threshold, result, evaluation = identity_evaluation(grouped[modality], max_error_rate=float(os.getenv('MAX_BIOMETRIC_ERROR_RATE', '.20')))
        evaluations[modality] = evaluation
        thresholds[f"{modality}_threshold"] = threshold
        metrics.update({f"{modality}_{key}": value for key, value in result.items()})
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("face-voice-calibration")
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "thresholds.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(thresholds, handle, indent=2)
        with mlflow.start_run() as run:
            mlflow.log_params({
                "dataset": "enrolled-samples", "modalities": "face,voice",
                "dataset_version": snapshot["dataset_version"],
                "dataset_samples": len(raw),
                "training_tenant_scope": snapshot.get("tenant_scope", "demo"),
                "threshold_grid_min": -0.2, "threshold_grid_max": 0.95,
                "threshold_grid_steps": 1151, "objective": "minimize_worst_far_frr_then_minimum_cv_gate_margin",
                "selection_method": "internal_cv_only_holdout_reserved",
            })
            mlflow.log_metrics(metrics)
            mlflow.log_params({**thresholds, 'evaluation_method': 'identity-disjoint-max-template'})
            mlflow.log_dict(evaluations, 'evaluation/identity-disjoint.json')
            for modality, evaluation in evaluations.items():
                for objective in ('minimax', 'balanced_error', 'far_constrained'):
                    trial = select_trial(evaluation['trials'], objective)
                    with mlflow.start_run(run_name=f'{modality}-{objective}', nested=True):
                        mlflow.log_params({'modality': modality, 'objective': objective,
                                           'threshold': trial['threshold'], 'dataset_version': snapshot['dataset_version']})
                        mlflow.log_metrics({k:trial[k] for k in ('far', 'frr')})
            mlflow.log_dict(snapshot, "data/snapshot.json")
            mlflow.log_dict(quality, "data/validation.json")
            mlflow.log_artifact(path, artifact_path="evaluation")
            input_example = pd.DataFrame({"face_score": [0.8], "voice_score": [0.7]})
            mlflow.pyfunc.log_model(
                artifact_path="bundle", python_model=RiskBundle(), artifacts={"thresholds": path},
                registered_model_name=model_name,
                input_example=input_example,
                signature=infer_signature(input_example, np.asarray([0], dtype=int)),
            )
            mlflow.set_tags({
                "purpose": "threshold-calibration", "run_id": run.info.run_id,
                "data_stage": "validated", "model_family": "cosine-threshold-policy",
            })
    client = MlflowClient()
    versions = client.search_model_versions(f"name='{model_name}'")
    version = max((item for item in versions if item.run_id == run.info.run_id), key=lambda item: int(item.version))
    for _ in range(30):
        version = client.get_model_version(model_name, version.version)
        if version.status == "READY":
            break
        time.sleep(1)
    client.set_registered_model_alias(model_name, "candidate", version.version)
    client.set_registered_model_alias(model_name, "challenger", version.version)
    if args.promote:
        if __package__:
            from .promotion_gate import promote
        else:
            from promotion_gate import promote
        promote(client, model_name, version, run.info.run_id)
    print(json.dumps({"model": model_name, "version": version.version, "thresholds": thresholds, "metrics": metrics}, indent=2))


if __name__ == "__main__":
    main()
