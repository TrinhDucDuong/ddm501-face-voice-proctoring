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
receiver. Training waits for the alert for that run to arrive. Alert correlation
uses a simulation run UUID; aggregate evidence metrics use bounded scenario,
modality, stage and metric labels. No employee data or vectors are exposed as labels.

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

## Grafana simulation evidence

Open http://localhost:13000/d/biometric-simulation (local Grafana login: admin/admin).
Choose one **Scenario** and one **Modality** to keep the ten panels readable.
This is a separate, explicitly SYNTHETIC dashboard; the production overview still
requires actual production observations and human review labels.

| Case | Action | Evidence in Grafana |
|---|---|---|
| Healthy baseline | Prepared automatically before each run | W0 drift report; retrain required = 0 |
| Persistent drift | Three independent windows in either scenario | W1-W3 PSI/MMD2, genuine score drop, consecutive windows 1/2/3; retrain required = 1 at W3 |
| Alert and threshold retraining | Airflow waits for Alertmanager delivery, then calibrates | Alert received = 1; offline champion/candidate FMR, FNMR, EER on identical holdout |
| Successful rollout | Select Face or Voice, press button 1 | Shadow then canary 5/10/25/50/100; 200 HTTP samples per stage; result = 1 (promoted) |
| Security regression | Select Face or Voice, press button 2 | Candidate FMR rises at CANARY_25; result = 2 (rolled back); rollback probe candidate samples = 0 |
| Restore baseline | Press button 3 after each run | Baseline restored = 1; live canary and retrain signals return to 0; historical evidence remains |

To execute both rollout outcomes for both modalities, with assertions and baseline
restoration after every run, execute from the repository root:

```powershell
.venv/Scripts/python.exe -m pipeline.verify_simulation --execute --all-modalities
```

Requires the running stack and platform `API_KEY` in `.env`. The verifier refuses
to interrupt an active simulation. It writes `reports/simulation-verification.json`
and `reports/simulation-{promotion|rollback}-{face|voice}.json`, including run IDs,
Airflow references, alert receipts, stage counts and full JSON artifacts. It also
asserts that the production lifecycle state is unchanged.

`simulation_evidence_*` metrics are read from the existing lab SQLite/JSON evidence,
not invented independently by Grafana. All have `synthetic="true"`. Labels use
bounded scenario, modality, window, phase and metric values, without employee IDs
or embeddings. The latest run per scenario/modality among the latest 20 runs is
exported; reset preserves the pre-reset result. A newer run replaces the snapshot
for that pair. Check the **Evidence run started at** panel: a retained snapshot is
not fresh production traffic. Missing evidence remains missing. Full historical
JSON remains accessible through the authenticated simulation evidence API.

Prometheus scrapes every 15 seconds. The per-stage panels retain all stages even
if the live time series misses a short stage. For a slower classroom demonstration,
set `SIMULATION_STAGE_SECONDS=20` on the simulation service via a Compose override;
the service default is 5 seconds. Restart only while no simulation is active.
The local monitoring preview uses this 20-second setting.

Dashboard source: `pipeline/build_simulation_dashboard.py`; regenerate with
`python pipeline/build_simulation_dashboard.py`. Compose automatically provisions
`monitoring/grafana/dashboards/biometric-simulation.json` on a normal deployment.
The local preview runs the updated simulation image and both dashboards through
`%LOCALAPPDATA%/DDM501/monitoring-preview/compose.json`, layered over the existing
deployment Compose file. No production container image or data volume is replaced.
Deploy this checkout normally to make the changes part of the next release.

These scenarios demonstrate threshold-policy calibration and orchestration, not
encoder retraining. FMR/FNMR values on deliberately separable synthetic vectors
are not evidence of accuracy on real employees. Production panels for human labels
and encoder verification latency can remain empty until real data is available.

### Recorded local verification: 2026-10-04

Seed 501, minimum 20 seconds per stage. All four Airflow DAG runs succeeded;
all received actual Prometheus/Alertmanager notifications and passed reset checks.

| Modality | Scenario | Run ID | Outcome |
|---|---|---|---|
| Voice | promotion | `06dcd24d-0bfe-4667-9791-924456653862` | SUCCEEDED, canary through 100% |
| Face | rollback | `1e17fc9a-9db7-4fa6-b57a-a6130356a7c4` | ROLLED_BACK at 25% |
| Face | promotion | `f819f41e-9254-44bf-8e69-d605b2f6e7c6` | SUCCEEDED, canary through 100% |
| Voice | rollback | `1187a0ca-45cb-4ff0-a251-a5aeb088c626` | ROLLED_BACK at 25% |

Observed: genuine mean 0.90 -> 0.60, impostor mean 0.10 -> 0.35,
embedding MMD2 approximately 0.120 (>0.02), stable quality PSI 0.
The calibrated threshold was approximately 0.401 versus baseline 0.8.
Offline FNMR improved from 1.0 to 0.0, with FMR 0.0 for both policies.
Failure injection raised challenger FMR to 1.0 at 25%; each rollback probe served
200 incumbent responses and zero challenger responses. These extreme distributions
are intentional classroom fixtures, not realistic estimates of employee error rates.

Validation: 163 repository tests passed; all 17 queries across the 10 simulation
panels returned finite data; rendered promotion/rollback dashboards had no JavaScript
errors. The existing production monitoring verifier passed all four checks. The
scenario verifier confirmed unchanged production lifecycle policies. JSON evidence
and dashboard screenshots are under the local ignored `reports/` directory.

The runner endpoints are internal and require `SIMULATION_SERVICE_KEY`. Replace
the development default when exposing this classroom stack beyond localhost.
