import math

import numpy as np
import pandas as pd
import pytest

import monitoring.drift_monitor as monitor
from monitoring.drift_monitor import population_stability_index, split_windows


def test_psi_detects_shift_and_stability():
    rng = np.random.default_rng(501)
    reference = rng.normal(0.75, 0.05, 1000)
    stable = rng.normal(0.75, 0.05, 1000)
    shifted = rng.normal(0.45, 0.08, 1000)
    assert population_stability_index(reference, stable) < 0.2
    assert population_stability_index(reference, shifted) > 0.2


def test_psi_handles_constant_and_small_windows():
    assert population_stability_index(np.ones(100), np.ones(100)) == pytest.approx(0)
    assert math.isnan(population_stability_index([1, 2], [2, 3]))


def test_split_windows_uses_latest_ordered_observations():
    frame = pd.DataFrame({"created_at": [4, 1, 3, 2], "value": [4, 1, 3, 2]})
    reference, current = split_windows(frame, 2)
    assert reference.value.tolist() == [1, 2]
    assert current.value.tolist() == [3, 4]
    with pytest.raises(ValueError):
        split_windows(frame.iloc[:3], 2)


def test_monitor_cycle_exports_psi_and_report(monkeypatch, tmp_path):
    rng = np.random.default_rng(7)
    size = 40
    frame = pd.DataFrame({
        "created_at": range(size),
        "face_score": np.r_[rng.normal(.8, .03, 20), rng.normal(.4, .03, 20)],
        "voice_score": np.r_[rng.normal(.75, .03, 20), rng.normal(.45, .03, 20)],
        "face_quality": np.r_[rng.normal(.8, .03, 20), rng.normal(.5, .03, 20)],
        "voice_quality": np.r_[rng.normal(.8, .03, 20), rng.normal(.5, .03, 20)],
        "risk_score": np.r_[rng.normal(.2, .03, 20), rng.normal(.6, .03, 20)],
    })
    monkeypatch.setattr(monitor, "load_events", lambda *_: (frame, 0.9))
    monkeypatch.setattr(monitor, "load_feedback", lambda *_: pd.DataFrame())
    monkeypatch.setattr(monitor, "write_evidently", lambda _r, _c, path: path.write_text("report"))
    monkeypatch.setenv("MONITOR_WINDOW_SIZE", "20")
    monkeypatch.setenv("EVIDENTLY_REPORT", str(tmp_path / "drift.html"))
    result = monitor.run_once()
    assert result["drifted_share"] > 0
    assert result["feedback_accuracy"] == 0.9
    assert (tmp_path / "drift.html").exists()
    assert (tmp_path / "drift.json").exists()


def test_evidently_performance_real_report_and_degradation(monkeypatch, tmp_path):
    frame = pd.DataFrame({
        "created_at": range(40), "target": [0, 1] * 20,
        "prediction": [0, 1] * 10 + [1, 0] * 10,
    })
    monkeypatch.setattr(monitor, "load_feedback", lambda *_: frame)
    path = tmp_path / "model-performance.html"
    result = monitor.monitor_performance("unused", 20, path)
    assert result["status"] == "ok"
    assert result["quality"]["reference"]["accuracy"] == 1
    assert result["quality"]["current"]["accuracy"] == 0
    assert result["quality"]["current"]["f1"] == 0
    assert path.stat().st_size > 1000
    assert path.with_suffix(".json").exists()
    # Losing labels must invalidate the previous successful report and metrics.
    monkeypatch.setattr(monitor, "load_feedback", lambda *_: frame.iloc[:0])
    result = monitor.monitor_performance("unused", 20, path)
    assert result["status"] == "waiting_for_feedback"
    assert "waiting_for_feedback" in path.read_text()
    assert math.isnan(monitor.PERFORMANCE.labels(metric="accuracy", window="current")._value.get())


def test_performance_single_class_and_failure(monkeypatch, tmp_path):
    frame = pd.DataFrame({"created_at": range(4), "target": [1] * 4, "prediction": [1] * 4})
    monkeypatch.setattr(monitor, "load_feedback", lambda *_: frame)
    path = tmp_path / "performance.html"
    assert monitor.monitor_performance("unused", 2, path)["status"] == "waiting_for_both_classes"

    def fail(*_):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(monitor, "load_feedback", fail)
    assert monitor.monitor_performance("unused", 2, path)["status"] == "error"


def test_feedback_query_excludes_unreviewed_and_limits_latest(tmp_path):
    from sqlalchemy import create_engine, text

    url = f"sqlite:///{(tmp_path / 'events.db').as_posix()}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE verification_events (id TEXT, created_at INTEGER, accepted BOOLEAN)"))
        connection.execute(text("CREATE TABLE verification_feedback (event_id TEXT, is_genuine BOOLEAN, reviewer TEXT)"))
        connection.execute(text("INSERT INTO verification_events VALUES ('a', 1, 1), ('b', 2, 0), ('c', 3, 1)"))
        connection.execute(text("INSERT INTO verification_feedback VALUES "
                                "('a', 1, 'operator:proctor'), ('b', 1, 'operator:proctor')"))
    frame = monitor.load_feedback(url, 1)
    assert frame.to_dict("records") == [{"created_at": 2, "prediction": 0, "target": 1}]
    engine.dispose()
