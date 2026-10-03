"""Verify the running demo stack and save reproducible evidence (no secrets)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values

EXPECTED_MODEL_TASK_IDS = {
    "ingest_versioned_snapshot",
    "validate_data_quality",
    "publish_versioned_dataset",
    "feature_engineer_train_register_candidate",
    "generate_responsible_ai_audit",
    "evaluate_and_promote_candidate",
    "reload_current_champion",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dag-run", required=True)
    parser.add_argument("--inference", action="store_true", help="Submit two real-media verification events")
    parser.add_argument("--require-alerts", action="store_true")
    args = parser.parse_args()
    config = {**dotenv_values(".env"), **os.environ}
    session = requests.Session()
    api = "http://127.0.0.1:18100"
    mlflow = "http://127.0.0.1:15030"
    prometheus = "http://127.0.0.1:19090"
    headers = {"X-API-Key": config.get("API_KEY", "demo-internal-key")}
    evidence = {"checked_at": datetime.now(timezone.utc).isoformat(), "checks": {}}

    def get(url, **kwargs):
        response = session.get(url, timeout=30, **kwargs)
        response.raise_for_status()
        return response.json()

    def check(name, function):
        try:
            evidence["checks"][name] = {"status": "pass", "evidence": function()}
            print(f"PASS {name}", flush=True)
        except Exception as exc:
            evidence["checks"][name] = {"status": "fail", "error": str(exc)}
            print(f"FAIL {name}: {exc}", flush=True)

    def serving():
        health = get(api + "/health")
        assert health["status"] == "healthy" and health["backend"] == "pretrained", health
        assert health["model_version"] != "local-default", health
        return health

    def registry():
        model = get(mlflow + "/api/2.0/mlflow/registered-models/alias", params={
            "name": "face-voice-risk-bundle", "alias": "champion",
        })["model_version"]
        assert model["version"] == get(api + "/health")["model_version"]
        run = get(mlflow + "/api/2.0/mlflow/runs/get", params={"run_id": model["run_id"]})["run"]
        parameters = {item["key"]: item["value"] for item in run["data"]["params"]}
        assert len(parameters["dataset_version"]) == 64
        assert parameters['selection_method'] == 'internal_cv_only_holdout_reserved'
        metrics = {item['key']:item['value'] for item in run['data']['metrics']}
        assert metrics['face_cv_folds'] == metrics['voice_cv_folds'] == 4
        files = get(mlflow + "/api/2.0/mlflow/artifacts/list", params={
            "run_id": model["run_id"], "path": "data",
        })["files"]
        paths = [item["path"] for item in files]
        assert "data/snapshot.json" in paths and "data/validation.json" in paths
        return {"version": model["version"], "run_id": model["run_id"], "params": parameters,
                "metrics": run["data"]["metrics"], "data_artifacts": paths}

    def airflow():
        result = subprocess.run([
            "docker", "compose", "exec", "-T", "airflow-scheduler", "airflow", "tasks",
            "states-for-dag-run", "biometric_model_pipeline", args.dag_run, "-o", "json",
        ], capture_output=True, text=True, check=True, encoding="utf-8")
        tasks = json.loads(result.stdout)
        task_ids = [task["task_id"] for task in tasks]
        assert set(task_ids) == EXPECTED_MODEL_TASK_IDS and len(task_ids) == len(set(task_ids)), tasks
        assert all(task["state"] == "success" for task in tasks), tasks
        return tasks

    def targets():
        data = get(prometheus + "/api/v1/targets")["data"]["activeTargets"]
        status = {target["labels"]["job"]: target["health"] for target in data}
        assert status.get("biometric-api") == status.get("drift-monitor") == "up", status
        return status

    def reports():
        performance = json.loads(Path("reports/synthetic-performance.json").read_text())
        human = json.loads(Path("reports/model-performance.json").read_text())
        drift = json.loads(Path("reports/data-drift.json").read_text())
        assert performance["status"] == "ok", performance
        assert drift["evidently_report_success"] and max(drift["psi"].values()) > 0.2, drift
        assert performance["quality"]["current"]["accuracy"] < performance["quality"]["reference"]["accuracy"]
        for name in ("synthetic-performance", "data-drift"):
            assert Path(f"reports/{name}.html").stat().st_size > 1000
        metrics = get(prometheus + "/api/v1/query", params={"query": 'biometric_reviewed_performance{source="synthetic"}'})["data"]["result"]
        assert len(metrics) == 12, metrics
        assert human['label_source'] == 'human' and performance['label_source'] == 'synthetic'
        return {"synthetic_performance": performance, "human_status":human['status'], "psi": drift["psi"], "prometheus_metrics": metrics}

    def grafana():
        base = "http://127.0.0.1:13000"
        assert get(base + "/api/health")["database"] == "ok"
        dashboard = get(base + "/api/dashboards/uid/biometric-overview", auth=("admin", "admin"))["dashboard"]
        panels = [panel["title"] for panel in dashboard["panels"]]
        assert any("Human Evidently performance" in title for title in panels), panels
        return panels

    def alerts():
        prom = get(prometheus + "/api/v1/alerts")["data"]["alerts"]
        manager = get("http://127.0.0.1:19093/api/v2/alerts")
        firing = {item["labels"]["alertname"] for item in prom if item["state"] == "firing"}
        received = {item["labels"]["alertname"] for item in manager}
        if args.require_alerts:
            required = {"BiometricDataDrift", "BiometricSyntheticPerformanceDegraded"}
            assert required <= firing and required <= received, {"firing": sorted(firing), "received": sorted(received)}
        return {"prometheus_firing": sorted(firing), "alertmanager_received": sorted(received)}

    def inference():
        manifest = json.loads(Path("data/bootstrap/manifest.json").read_text(encoding="utf-8"))
        people = {person["external_id"]: person for person in get(api + "/v1/people", headers=headers) if person["ready"]}
        selected = [row for row in manifest if row["external_id"] in people][:2]
        assert len(selected) == 2, "Need two enrolled bootstrap identities"
        results = {}
        for label, media in (("same_identity", selected[0]), ("different_identity", selected[1])):
            files = {}
            for field, paths, mime in (("face_file", media["faces"], "image/jpeg"),
                                       ("voice_file", media["voices"], "audio/wav")):
                path = Path(paths[0].replace("\\", "/"))
                files[field] = (path.name, path.read_bytes(), mime)
            response = session.post(api + "/v1/verify", headers=headers, files=files, timeout=180,
                                    data={"person_id": people[selected[0]["external_id"]]["id"],
                                          "session_id": "e2e-" + label})
            response.raise_for_status()
            result = response.json()
            assert result["model_version"] == get(api + "/health")["model_version"]
            assert result["accepted"] == (label == "same_identity"), result
            results[label] = {key: result[key] for key in (
                "event_id", "decision", "face_score", "voice_score", "model_version", "latency_ms", "reasons",
            )}
        return results

    for name, function in (("serving", serving), ("registry_lineage", registry), ("airflow", airflow),
                           ("prometheus_targets", targets), ("evidently_reports", reports),
                           ("grafana", grafana), ("alerts", alerts)):
        check(name, function)
    if args.inference:
        check("real_media_inference", inference)
    evidence["status"] = "pass" if all(item["status"] == "pass" for item in evidence["checks"].values()) else "fail"
    Path("reports").mkdir(exist_ok=True)
    Path("reports/verification.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    if evidence["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
