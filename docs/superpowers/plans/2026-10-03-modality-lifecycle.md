# Independent Biometric Lifecycle Implementation Plan

Goal: extend the existing service, Airflow, MLflow, MinIO and monitoring; preserve API
contracts and PAD checks. The implemented model family is cosine threshold policy,
not an encoder trainer. Encoder weights remain pinned. No claim of production capacity.

## Design Decisions

- PSI for scalar quality and score distributions, bounded RBF MMD for normalized
  embeddings. Compare the same encoder and overlapping identity cohorts; report
  insufficient evidence otherwise. Trusted modality-specific labels only.
- PostgreSQL stores observations, versioned templates, monitoring state and deployment
  state. MinIO stores immutable monitoring reports/manifests, not a second registry.
- One active deployment per modality, audited revisions and row locks for
  transitions. MLflow aliases are reconciled from a durable promotion intent.
- Candidate threshold policies reuse SFace/ECAPA scores; real shadow evaluates both
  policies on requests without altering the response. Canary routes by a stable
  tenant/person/session hash independently per modality. PAD remains authoritative.
- Missing labels, cohort coverage or unhealthy inputs block automatic promotion.
  Runtime errors rollback immediately; delayed-label metric gates run in Airflow.
- Template updates require independently reviewed genuine observations, successful
  integrity checks, distinct captures, consistency and a disjoint labelled holdout.
  Candidate templates retain previous versions and never overwrite enrollment rows.
- Quality telemetry has no raw media. Query embedding retention is opt-in per
  deployment, time bounded, and excluded from Prometheus and public API responses.

## Execution

1. Add behavioral tests for decision evidence, persistence, missing labels and MMD.
   Implement `pipeline/drift_decision.py` with typed config and structured reports.
2. Add additive tables in `api/app/models.py`; integrate observations and independent
   policies in `main.py` and modality labels in `checks.py`. Preserve old API fields.
   Test actual API requests and database migrations with SQLite fixtures.
3. Implement template candidate evaluation/activation/rollback in
   `api/app/template_lifecycle.py`; test poisoning, stale versions and cohort isolation.
4. Extend `pipeline/model_rollout.py` with durable lifecycle controller; independent
   MLflow names, offline gates, live shadow, staged canary and recoverable promotion.
   Test failure gates, insufficient samples, duplicate runs, idempotency and rollback.
5. Extend the existing monitoring job and DAGs to process modalities, bounded windows,
   state persistence and independent retrain requests. Training remains in Airflow.
6. Extend ops metrics and generated dashboard with bounded modality/state labels.
   Document formulas, thresholds, operational entry points, privacy and capacity limits.
7. Run targeted tests, full pytest, Ruff, compilation, generated dashboard consistency,
   Compose validation and inspect the final diff. Document real versus synthetic evidence.

## Acceptance

Quality-only, embedding-only, unlabelled or old-template-only drift cannot retrain.
Only persistent, labelled cross-age degradation can request a modality-specific run.
Candidate cannot directly become champion. Every promotion requires offline, real
shadow and each configured canary stage, with both sample and time gates. Failures
retain artifacts and restore champion routing. No employee/vector metric labels.

## Execution Record: 2026-10-03

Steps 1-7 implemented and locally verified. Final full suite: 142 passed, zero skips,
82.52% coverage in the existing CI scope. Ruff, compile, Compose configuration and
generated dashboard consistency pass. The DAG source imports in the existing Airflow
environment. Registry tests use a real temporary MLflow store with synthetic scores.
No new production DAG, GitHub lifecycle run or deployment has been executed.

Additional regression fixes cover immutable manifest compatibility, retained review
labels, duplicate training intents/registration, reference renewal, restored MLflow
tags, legacy-bundle-independent readiness and template actions during active rollouts.
Production labels, representative cohort sizing and 50,000-user concurrency evidence
remain operational prerequisites; see `docs/MODALITY_LIFECYCLE.md`.
