import numpy as np
import pytest

from pipeline.calibrate_and_register import choose_threshold, cross_validate
from pipeline.data_snapshot import dataset_version, read_snapshot
from pipeline.promotion_gate import gate
from pipeline.validate_data import validate


def sample_rows():
    rows = []
    for modality in ("face", "voice"):
        for person in range(5):
            for sample in range(2):
                rows.append({
                    "id": f"{modality}-{person}-{sample}", "person_id": f"p{person}",
                    "modality": modality, "embedding": [0.1] * 16, "quality": 0.8,
                    "sha256": f"{modality}-{person}-{sample}",
                })
    return rows


def test_data_validation_accepts_complete_features():
    result = validate(sample_rows())
    assert result["valid"] is True
    assert result["counts"] == {"face": 10, "voice": 10}


def test_snapshot_fingerprint_pins_training_rows(tmp_path):
    import json

    rows = sample_rows()
    version = dataset_version(rows)
    assert dataset_version(list(reversed(rows))) == version
    path = tmp_path / "snapshot.json"
    snapshot = {"samples": rows, "dataset_version": version}
    path.write_text(json.dumps(snapshot))
    assert read_snapshot(str(path))["dataset_version"] == version
    rows[0]["embedding"][0] = 0.9
    path.write_text(json.dumps(snapshot))
    with pytest.raises(ValueError, match="fingerprint"):
        read_snapshot(str(path))


def test_data_validation_rejects_bad_quality_and_duplicate():
    rows = sample_rows()
    rows[0]["quality"] = 2
    rows[1]["sha256"] = rows[0]["sha256"]
    with pytest.raises(ValueError) as exc:
        validate(rows)
    assert "quality outside" in str(exc.value)
    assert "duplicate sample" in str(exc.value)


def test_data_validation_rejects_unknown_inconsistent_and_too_small_data():
    rows = sample_rows()
    rows[0]["modality"] = "retina"
    rows[1]["embedding"] = [float("nan")] * 3
    rows = rows[:8]
    with pytest.raises(ValueError) as exc:
        validate(rows)
    message = str(exc.value)
    assert "unsupported modality" in message
    assert "invalid embedding" in message
    assert "needs at least" in message


def test_model_promotion_gate():
    metrics = {}
    for modality in ("face", "voice"):
        metrics.update({
            f"{modality}_far": 0.05, f"{modality}_frr": 0.10,
            f"{modality}_cv_far": 0.07, f"{modality}_cv_frr": 0.12,
            f"{modality}_holdout_far": 0.07, f"{modality}_holdout_frr": 0.12,
            f"{modality}_holdout_positive_pairs": 20, f"{modality}_holdout_negative_pairs": 50,
            f"{modality}_positive_pairs": 20, f"{modality}_negative_pairs": 50,
        })
    assert gate(metrics) == []
    metrics["voice_far"] = 0.5
    assert "voice_far" in gate(metrics)[0]
    failures = gate({})
    assert any("face_far=None" in failure for failure in failures)
    assert any("positive_pairs=0" in failure for failure in failures)
    metrics["voice_far"] = 0.05
    metrics["voice_cv_frr"] = float("nan")
    assert any("voice_cv_frr" in failure for failure in gate(metrics))


def test_threshold_tuning_and_cross_validation():
    rng = np.random.default_rng(501)
    positive = rng.normal(0.8, 0.04, 100)
    negative = rng.normal(0.2, 0.04, 100)
    threshold, metrics = choose_threshold(positive, negative)
    assert 0.25 < threshold < 0.75
    assert metrics["far"] == 0
    assert metrics["frr"] == 0
    cv = cross_validate(positive, negative)
    assert cv["cv_folds"] == 5
    assert cv["cv_balanced_error_mean"] < 0.02
    assert cross_validate(positive[:5], negative[:5]) == {}
