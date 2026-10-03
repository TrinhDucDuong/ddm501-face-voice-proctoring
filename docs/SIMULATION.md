# Isolated classroom simulation

Open the portal at http://localhost:18501, log in with the platform key, and select
**Simulation MLOps**. Company operators cannot access these controls.

1. **Drift -> upgrade champion** creates three distinct drift windows, waits for a
   real Prometheus/Alertmanager notification, calibrates a threshold, runs paired
   offline evaluation, shadow and 5/10/25/50/100 percent canary, then reconciles the
   MLflow champion alias if all gates pass.
2. **Canary failure -> rollback** follows the same path, then injects high-scoring
   impostors at the 25 percent stage. The existing FMR gate rejects the challenger.
   A subsequent request batch must use only the incumbent policy.
3. **Restore demo baseline** signals cancellation, waits for the active step to
   stop, rejects subsequent stale DAG tasks, and restores the baseline registry
   aliases and routing. Registry versions, reports and lifecycle audit survive.

Reset between runs. Airflow picks up a queued run within approximately one minute;
normal runtime depends on shared-host resources. If Airflow or alert delivery is
unavailable, the UI must not show a successful lifecycle. Reset a failed run before
trying again. Service restart during a step marks the run failed for explicit reset.

## Isolation

`simulation` and `simulation-mlflow` use the dedicated `simulation-data` volume and
the internal `simulation-lab` network. They do not receive the production `.env`,
PostgreSQL credentials, MinIO credentials, model weights or production registry
mounts. They cannot resolve the production database on its default Docker network.
The main API proxies fixed routes only after platform authentication. Airflow,
Prometheus and Alertmanager bridge into the simulation network as orchestrators.
The MLflow browser service also has a dedicated `simulation-ui` ingress network
to publish its localhost port; it is not on the production database network.

Each run owns a SQLite lifecycle database, immutable JSON datasets/reports and
registered model names prefixed `simulation-<run-id>-`. The file-backed MLflow store
is separate from production MLflow, browsable at http://localhost:15031. Synthetic
artifacts remain on the simulation volume, not the production MinIO data lake.

The simulation alert route goes to `http://simulation:8000/alerts`, with no Telegram
receiver. Training waits for the alert for that run to arrive. Prometheus labels
contain only modality, synthetic flag and a simulation run UUID, no employee data.

The host and Airflow scheduler remain shared. Container CPU/memory limits reduce
contention but do not establish a production latency SLA. Never use `down -v` to
reset a demo; the UI reset preserves all audit artifacts and production volumes.

## Actual methods and limits

The generator emits 201-dimensional unit vectors with mathematically consistent
cosine scores and explicitly synthetic genuine/impostor truth. No raw image/audio
inference or encoder fine-tuning is performed. Face and Voice each have an initial
simulation threshold of 0.8; only the selected modality is changed.

Production implementations reused: `drift_decision.evaluate` (PSI and RBF MMD2),
`identity_evaluation` (disjoint identity calibration/CV/holdout), `paired_gate`,
`register_policy`, `route`, `advance` and `reconcile_registry`. The threshold is
chosen by calibration, not assigned by the scenario. Offline metrics are computed
from the same holdout scores for both policies. The injection used for failure is
introduced only at canary, not hidden in the offline evaluation.

Drift: 100 samples/window, 3 new windows, default PSI >0.2 and MMD2 >0.02, stable
quality, audited synthetic labels, performance degradation across age cohorts.
Rollout: 200 HTTP requests/stage to the authenticated simulation verification
endpoint, minimum 5 seconds/stage, 20 labels/class, FMR <=1%, FNMR <=5%, no FMR
regression, FNMR regression <=0.005, policy latency p95 <=10ms. Disagreement allowance
is 0.6 for this deliberately large threshold correction. Production rollout limits
remain unchanged. HTTP transport time and encoder latency are not policy latency.

Real thresholds are selected on constructed data, so no claim of biometric accuracy
or production safety follows from a successful classroom run. Request observations
are replayed synthetic vectors; they are not camera/microphone verification requests.

## Evidence

The UI shows drift decisions, gate metrics, actual routed counts, MLflow versions,
Airflow run, alert receipts, failed metric and post-promotion/rollback probes. Export
the JSON report for all datasets, scores and lifecycle evidence. Historical runs
remain on disk; the UI lists the latest 20. Reset preserves historical drift reports
but disables the active retrain signal and restores baseline policy selection.

Airflow: http://localhost:18081/dags/biometric_simulation/grid

MLflow simulation: http://localhost:15031

The runner endpoints are internal and require `SIMULATION_SERVICE_KEY`. Replace
the development default when exposing this classroom stack beyond localhost.
