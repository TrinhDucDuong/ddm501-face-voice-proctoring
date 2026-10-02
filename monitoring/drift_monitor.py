"""Production-data monitor: Prometheus exporter plus Evidently HTML report."""
from __future__ import annotations

import json
import logging
import math
import os
import time
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
from prometheus_client import Gauge, start_http_server
from sqlalchemy import create_engine, text

LOGGER = logging.getLogger("drift-monitor")
FEATURES = ("face_score", "voice_score", "face_quality", "voice_quality", "risk_score")
PSI = Gauge("biometric_feature_psi", "Population Stability Index", ["feature"])
DRIFT_SHARE = Gauge("biometric_drifted_feature_share", "Share of features with PSI >= threshold")
SAMPLES = Gauge("biometric_monitor_samples", "Rows in monitoring windows", ["window"])
ACCURACY = Gauge("biometric_feedback_accuracy", "Accuracy on human-reviewed events")
LAST_SUCCESS = Gauge("biometric_monitor_last_success_unixtime", "Last successful monitor calculation")
EVIDENTLY_SUCCESS = Gauge("biometric_evidently_report_success", "1 when the latest Evidently report succeeded")
PERFORMANCE_SUCCESS = Gauge("biometric_performance_report_success", "1 when the latest performance report succeeded")
PERFORMANCE_SAMPLES = Gauge("biometric_performance_samples", "Human-reviewed events available for performance")
PERFORMANCE = Gauge("biometric_model_performance", "Evidently classification quality on reviewed events", ["metric", "window"])
PERFORMANCE_METRICS = ("accuracy", "precision", "recall", "f1", "far", "frr")
SOURCE_PERFORMANCE = Gauge("biometric_reviewed_performance", "Reviewed performance separated by label source", ["source", "metric", "window"])
SOURCE_SUCCESS = Gauge("biometric_reviewed_report_success", "Report validity by label source", ["source"])
SOURCE_SAMPLES = Gauge("biometric_reviewed_samples", "Reviewed rows by label source", ["source"])


def load_feedback(database_url: str, limit: int, source: str = "human") -> pd.DataFrame:
    if source not in {"human", "synthetic"}:
        raise ValueError("Unknown feedback source")
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT e.created_at, e.accepted AS prediction, f.is_genuine AS target
                FROM verification_events e JOIN verification_feedback f ON f.event_id = e.id
                WHERE (:source = 'synthetic' AND f.reviewer = 'synthetic-simulation')
                   OR (:source = 'human' AND f.reviewer LIKE 'operator:%')
                ORDER BY e.created_at DESC, e.id DESC LIMIT :limit
            """), {"limit": limit, "source": source}).mappings().all()
        return pd.DataFrame(rows, columns=["created_at", "prediction", "target"])
    finally:
        engine.dispose()


def monitor_performance(database_url: str, window_size: int, path: Path, source: str = "human") -> dict:
    """Compare disjoint windows of reviewed decisions; unlabelled events are excluded."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if window_size < 2:
        raise ValueError("Performance window must contain at least two rows")
    SOURCE_SUCCESS.labels(source=source).set(0)
    SOURCE_SAMPLES.labels(source=source).set(0)
    if source == "human":
        PERFORMANCE_SUCCESS.set(0)
        PERFORMANCE_SAMPLES.set(0)
    for metric in PERFORMANCE_METRICS:
        for window in ("reference", "current"):
            SOURCE_PERFORMANCE.labels(source=source, metric=metric, window=window).set(math.nan)
            if source == "human":
                PERFORMANCE.labels(metric=metric, window=window).set(math.nan)
    summary = {"status": "waiting_for_feedback", "label_source": source, "required_samples": 2 * window_size}
    try:
        frame = load_feedback(database_url, 2 * window_size, source)
        SOURCE_SAMPLES.labels(source=source).set(len(frame))
        if source == "human":
            PERFORMANCE_SAMPLES.set(len(frame))
        summary["samples"] = len(frame)
        if len(frame) >= 2 * window_size:
            reference, current = split_windows(frame, window_size)
            for part in (reference, current):
                for column in ("target", "prediction"):
                    part[column] = part[column].astype(int)
            if any(part.target.nunique() < 2 for part in (reference, current)):
                summary["status"] = "waiting_for_both_classes"
            else:
                from evidently import ColumnMapping
                from evidently.metric_preset import ClassificationPreset
                from evidently.report import Report

                report = Report(metrics=[ClassificationPreset()])
                report.run(
                    reference_data=reference[["target", "prediction"]],
                    current_data=current[["target", "prediction"]],
                    column_mapping=ColumnMapping(target="target", prediction="prediction", pos_label=1),
                )
                result = next(item["result"] for item in report.as_dict()["metrics"]
                              if item["metric"] == "ClassificationQualityMetric")
                summary["quality"] = {}
                for window in ("reference", "current"):
                    part = reference if window == "reference" else current
                    values = {metric: float(result[window][metric])
                              for metric in PERFORMANCE_METRICS[:4]}
                    impostors, genuine = part[part.target == 0], part[part.target == 1]
                    values.update(far=float(impostors.prediction.mean()), frr=float(1 - genuine.prediction.mean()))
                    summary["quality"][window] = values
                    for metric, value in values.items():
                        SOURCE_PERFORMANCE.labels(source=source, metric=metric, window=window).set(value)
                        if source == "human":
                            PERFORMANCE.labels(metric=metric, window=window).set(value)
                report.save_html(str(path))
                summary["status"] = "ok"
                SOURCE_SUCCESS.labels(source=source).set(1)
                if source == "human":
                    PERFORMANCE_SUCCESS.set(1)
    except Exception:
        LOGGER.exception("Evidently performance report failed")
        summary["status"] = "error"
    if summary["status"] != "ok":
        path.write_text("<html><body><h1>Performance report pending</h1><p>"
                        + escape(summary["status"]) + "</p></body></html>", encoding="utf-8")
    path.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def population_stability_index(reference, current, bins: int = 10) -> float:
    """Calculate PSI using reference quantile bins and smoothed proportions."""
    expected = np.asarray(reference, dtype=float)
    actual = np.asarray(current, dtype=float)
    expected, actual = expected[np.isfinite(expected)], actual[np.isfinite(actual)]
    if len(expected) < bins or len(actual) < bins:
        return math.nan
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        spread = max(abs(float(expected[0])) * 0.01, 1e-3)
        edges = np.linspace(float(expected[0]) - spread, float(expected[0]) + spread, bins + 1)
    edges[0], edges[-1] = -np.inf, np.inf
    expected_pct = np.histogram(expected, bins=edges)[0] / len(expected)
    actual_pct = np.histogram(actual, bins=edges)[0] / len(actual)
    expected_pct, actual_pct = np.clip(expected_pct, 1e-6, None), np.clip(actual_pct, 1e-6, None)
    return float(np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct)))


def split_windows(frame: pd.DataFrame, window_size: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    if len(frame) < window_size * 2:
        raise ValueError(f"need at least {window_size * 2} events, found {len(frame)}")
    ordered = frame.sort_values("created_at")
    return ordered.iloc[-2 * window_size:-window_size].copy(), ordered.iloc[-window_size:].copy()


def load_events(database_url: str, limit: int) -> tuple[pd.DataFrame, float | None]:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT created_at, face_score, voice_score, face_quality, voice_quality, risk_score
            FROM verification_events
            WHERE face_score IS NOT NULL AND voice_score IS NOT NULL
            ORDER BY created_at DESC LIMIT :limit
        """), {"limit": limit}).mappings().all()
        performance = connection.execute(text("""
            SELECT AVG(CASE WHEN e.accepted = f.is_genuine THEN 1.0 ELSE 0.0 END) AS accuracy
            FROM verification_events e JOIN verification_feedback f ON f.event_id = e.id
            WHERE f.reviewer LIKE 'operator:%'
        """)).scalar()
    engine.dispose()
    return pd.DataFrame(rows, columns=["created_at", *FEATURES]), None if performance is None else float(performance)


def write_evidently(reference: pd.DataFrame, current: pd.DataFrame, report_path: Path) -> bool:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from evidently.metric_preset import DataDriftPreset
        from evidently.report import Report

        report = Report(metrics=[DataDriftPreset()])
        report.run(reference_data=reference[list(FEATURES)], current_data=current[list(FEATURES)])
        report.save_html(str(report_path))
        return True
    except Exception as exc:
        # PSI/Prometheus monitoring remains available if an optional report renderer fails.
        LOGGER.exception("Evidently report failed")
        report_path.write_text(
            "<html><body><h1>Evidently report unavailable</h1><pre>"
            + escape(f"{type(exc).__name__}: {exc}")
            + "</pre></body></html>",
            encoding="utf-8",
        )
        return False


def run_once() -> dict:
    database_url = os.getenv("DATABASE_URL", "sqlite:///./data/biometric.db")
    window_size = int(os.getenv("MONITOR_WINDOW_SIZE", "100"))
    threshold = float(os.getenv("PSI_ALERT_THRESHOLD", "0.2"))
    report_path = Path(os.getenv("EVIDENTLY_REPORT", "/reports/data-drift.html"))
    performance = monitor_performance(
        database_url, int(os.getenv("PERFORMANCE_WINDOW_SIZE", "100")),
        report_path.with_name("model-performance.html"),
    )
    synthetic_performance = monitor_performance(
        database_url, int(os.getenv("PERFORMANCE_WINDOW_SIZE", "100")),
        report_path.with_name("synthetic-performance.html"), "synthetic",
    )
    EVIDENTLY_SUCCESS.set(0)
    for feature in FEATURES:
        PSI.labels(feature=feature).set(math.nan)
    DRIFT_SHARE.set(math.nan)
    ACCURACY.set(math.nan)
    frame, accuracy = load_events(database_url, window_size * 4)
    reference, current = split_windows(frame, window_size)
    values = {feature: population_stability_index(reference[feature], current[feature]) for feature in FEATURES}
    for feature, value in values.items():
        if math.isfinite(value):
            PSI.labels(feature=feature).set(value)
    drifted = sum(value >= threshold for value in values.values() if math.isfinite(value))
    DRIFT_SHARE.set(drifted / len(FEATURES))
    SAMPLES.labels(window="reference").set(len(reference))
    SAMPLES.labels(window="current").set(len(current))
    if accuracy is not None:
        ACCURACY.set(accuracy)
    evidently_success = bool(write_evidently(reference, current, report_path))
    EVIDENTLY_SUCCESS.set(1 if evidently_success else 0)
    LAST_SUCCESS.set_to_current_time()
    summary = {
        "psi": values, "drifted_share": drifted / len(FEATURES),
        "feedback_accuracy": accuracy, "evidently_report_success": evidently_success,
        "performance": performance,
        "synthetic_performance": synthetic_performance,
    }
    report_path.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:  # pragma: no cover - long-running container loop
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    start_http_server(int(os.getenv("METRICS_PORT", "8001")))
    interval = int(os.getenv("MONITOR_INTERVAL_SECONDS", "60"))
    while True:
        try:
            LOGGER.info("monitor summary=%s", run_once())
        except Exception:
            LOGGER.exception("monitor cycle failed")
        time.sleep(interval)


if __name__ == "__main__":
    main()
