> HISTORICAL PLAN / SPEC: retained for design history, not current runtime status.
> See [current documentation](../../README.md) for implementation, commands and evidence.

# Continuous MLOps Implementation Plan

**Goal:** Turn production drift and reviewed outcomes into versioned monitoring evidence, safe candidate evaluation, and controlled champion deployment.

**Checkpoint:** `checkpoint/2026-10-02-before-mlops-continuous` at `4913b7b`; PostgreSQL restore-tested dump in `data/backups/ddm501_restore_drill_20261001_184709.dump`.

**Architecture:** The customer service keeps tenant-scoped check and human-review records. A monitoring DAG snapshots unlabeled telemetry and human-labeled performance into MinIO, then publishes an actionable decision. The training DAG consumes eligible versioned embeddings, evaluates the candidate against the current champion on the same identity holdout, then promotes only after offline and serving gates. GitHub Actions remains the code delivery path.

**Tech stack:** FastAPI, SQLAlchemy/PostgreSQL, MinIO/S3, Airflow, MLflow, Evidently, Prometheus, Grafana, Streamlit, pytest.

## Constraints

- Do not treat model predictions or synthetic demo labels as human ground truth.
- Keep company checks, evidence and reviews tenant-scoped; the default model-training tenant stays `demo` until explicit data-use consent is represented.
- Do not retain ordinary raw media by default. The data lake stores versioned features, labels and manifests; suspicious evidence keeps the existing policy.
- Drift alone must never promote a candidate. A failing gate leaves champion unchanged.
- Keep the pre-change checkpoint and database dump usable for rollback.

## Tasks

1. **Review and labels:** Add tenant-scoped review API and portal controls for identity truth, integrity judgement, reviewer provenance and audit. Make reviewed data usable by performance monitoring without conflating identity mismatch and cheating. Test cross-tenant denial and review updates.
2. **Dataset ledger:** Build versioned, immutable training/holdout/reference/current manifests from eligible data, record splits by identity and time, publish safe feature/label snapshots to MinIO, and verify checksums. Test no overlap and no synthetic labels in human sets.
3. **Monitoring DAG:** Create the second Airflow DAG to run a reproducible monitoring ETL, calculate drift and reviewed performance with sample gates, publish recommendation/status and freshness, and avoid duplicate train triggers. Test stable, drift, performance regression and insufficient-data cases.
4. **Challenger gate:** Compare candidate and champion on the same locked holdout and human-reviewed window where available; record paired metrics, shadow outcome and rollback target in MLflow. Promote only when both pass; keep previous champion on failure. Test gate decisions and alias behavior.
5. **Serving and rollout:** Add configurable shadow/canary observation and safe automatic rollback when model health fails; keep operational API responses deterministic and tenant-scoped. Test version tracking and rollback.
6. **Observability and delivery:** Enrich Prometheus/Grafana and Telegram drift alerts with tenant scope, feature, sample size, model version, recommendation and links. Keep CI/CD for code separate from model rollout. Update operations docs and run full tests, DAG parse, dashboard generation and local end-to-end verification.
