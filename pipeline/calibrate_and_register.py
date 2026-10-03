"""Calibrate verification thresholds from enrolled samples and register an MLflow bundle."""
from __future__ import annotations

import itertools
import json
import os

import mlflow
import mlflow.pyfunc
import numpy as np

if __package__:
    pass
else:
    pass


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
    if os.getenv('MODEL_MODALITY') not in ('face', 'voice'):
        raise ValueError('Airflow training requires face or voice modality and an eligible monitoring window')
    from pipeline.modality_training import train
    train(os.environ['MODEL_MODALITY'])


if __name__ == "__main__":
    main()
