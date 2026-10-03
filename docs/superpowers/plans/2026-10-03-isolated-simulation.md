# Isolated lifecycle simulation implementation plan

Approved scope: the conversation's two scenarios and baseline reset, with no
production data, template, threshold or registry mutations. Implement inline.

## Design

Use a separate simulation service and persistent volume. Each run owns a SQLite
database, namespaced models in a separate MLflow file registry and immutable synthetic datasets. Reuse production
PSI/MMD decisions, identity-disjoint calibration, paired offline gate, routing,
rollout gates and MLflow reconciliation. No encoder training or raw-media claim.
The existing Airflow instance polls a user-started queue through a separate simulation DAG; it only
calls the simulation service. Prometheus/Alertmanager deliver synthetic alerts to
the simulation receiver, with an explicit route excluding Telegram.

The platform API authenticates and proxies only fixed simulation endpoints. The
portal presents modality selection, success/failure buttons, reset, live evidence
and history. A single active run and locked step transitions reject stale tasks.
Reset invalidates the run before restoring baseline aliases and routing; old DAG
tasks cannot mutate it. Artifacts and failure evidence remain available.

## Tasks

- [x] Data and shared gates: tests for consistent cosine scores, healthy baseline,
  three persistent drift windows, disjoint calibration/holdout, measured offline
  improvement. Files: pipeline/simulation_data.py, modality_training.py,
  api/app/lifecycle_api.py, tests/test_simulation.py.
- [x] Isolated runner: durable state, MLflow registration, actual policy routing,
  all canary stages, failed-canary recovery and baseline restoration. Test duplicate
  starts, retries, stale steps, invalid phases and modality independence.
  Files: pipeline/simulation_runner.py, api/app/simulation_server.py.
- [x] Orchestration and UI: protected proxy, separate Airflow DAG, authenticated
  internal calls, alert routing, Compose volume/service, admin panel and UI tests.
  Files: api/app/simulation_api.py, config.py, main.py, ui/simulation.py,
  ui/app.py, ui/Dockerfile, docker-compose.yml, airflow/dags/biometric_simulation.py,
  monitoring/prometheus/*.yml, monitoring/alertmanager/alertmanager.yml.
- [x] Verify and deploy locally: run tests and existing quality checks; exercise
  both scenarios through real Airflow/alerts and reset; compare production champion
  before/after. Document URLs, accelerated limits, evidence and limitations in
  docs/SIMULATION.md and VERIFICATION.md. Do not claim production biometric quality.

## Demo limits

Synthetic embeddings and ground truth only, seed recorded. Same code, different
storage. Default windows 100 and persistence 3; rollout uses 200 samples/stage,
5 seconds minimum, 20 labels/class and disagreement allowance 0.6 to make the
constructed threshold shift visible. Security FMR remains 1%, FNMR 5%. Runtime
resource limits protect the shared host; Airflow itself remains shared.
