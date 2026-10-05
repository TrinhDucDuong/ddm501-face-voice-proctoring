# Independent Face / Voice Lifecycle

This implementation extends the existing service and its Airflow, MLflow, MinIO,
Prometheus and Grafana infrastructure. It trains **threshold policies**, not SFace
or ECAPA encoder weights. Face and Voice have separate state, aliases and routing.
The target of 50,000 employees is a design target, not a measured capacity result.

## Current Component -> Change

| Existing component | Previous behavior / gap | Implemented change |
|---|---|---|
| `api/app/biometrics.py` | Aggregate quality only | Named image/audio measurements; fixed encoder identifier |
| `api/app/main.py`, `checks.py` | One bundle version; combined identity labels | Independent policy routing and telemetry; explicit human modality labels |
| `pipeline/monitoring_etl.py`, `monitoring_job.py` | PSI alone could request training | Existing Airflow job calls the evidence decision engine; legacy helpers are not the production trigger |
| `BiometricSample` | Unversioned enrollment collection | Preserve enrollment; add reversible template versions/pointers |
| `calibrate_and_register.py`, `promotion_gate.py` | Joint model and direct promotion | Modality-specific registration; offline gate starts shadow instead of replacing champion |
| `model_rollout.py` | Reload and 30-second readiness | Drive persisted shadow/canary/promotion controller |
| Airflow DAGs | Weekly unconditional joint training | Monitoring requests modality-specific runs; DB claim prevents overlapping training |
| MinIO | Training and monitoring snapshots | Reuse dataset ledger; separate scalar inputs, reviewed labels, immutable reports |
| Ops collector/dashboard | Joint drift and alias panels | Modality drift, rates, decisions, rollout stages, sample counts and rollback audits |

## Methods Actually Used

- Scalar quality/score drift: PSI = sum((current_bin - reference_bin) *
  log(current_bin/reference_bin)); ten reference quantile bins, probabilities
  clipped at 1e-6. Scores are separated into genuine/impostor using trusted labels;
  mean, standard deviation, p05/p50/p95, mean threshold margin and separation are reported.
- Embedding drift: biased squared RBF MMD = mean(Krr) + mean(Kcc) - 2 mean(Krc),
  unit-normalized vectors and kernel exp(-squared_distance/2). At most 512 vectors
  per window. Never inspect individual dimensions as independent drift tests.
- Compare only one pinned encoder and at least 80% identity-set overlap. Changed
  employee populations return insufficient evidence. Matching identity sets does
  not eliminate every sampling-frequency confound; this is a conservative heuristic.
  The 100-observation defaults are for a pilot. With 50,000 uniformly active employees,
  overlap can be too small and automation will remain INSUFFICIENT_DATA. Representative
  cohort/window sizing must be validated before enabling large-population automation.
- Quality: image brightness, contrast, Laplacian variance, resolution; pretrained
  YuNet also supplies detection confidence and face area ratio. Audio duration,
  RMS, clipping, amplitude-based silence fraction, original sample rate. Audio RMS
  is measured before peak normalization. Silence fraction is not a learned VAD.
  SNR, pose and occlusion are not fabricated when detectors do not provide them.
- Performance: per-modality FMR = false accepts / reviewed impostors; FNMR = false
  rejects / reviewed genuine attempts. EER is the empirical ROC crossing estimate;
  TAR at configured FAR is the best empirical TAR meeting the FAR budget. These
  are finite-sample estimates, not proof of a population FAR guarantee.
- Template age: time since active template creation, or most recent original
  enrollment sample; buckets <=30, <=90, <=180, <=365, >365 days. Reports contain
  sample counts, genuine mean, FNMR/FMR and quality mean by bucket.
  The aging heuristic compares the first (<=30 days) and last (>365 days)
  buckets: recent FNMR <=0.05, oldest FNMR >0.07 and overall FMR <=0.01.
  This is not a fitted age/performance correlation or proof that every
  intermediate cohort is healthy; sparse or missing extreme cohorts limit it.

## Configuration

All lifecycle thresholds live in `pipeline/lifecycle_config.json`, loaded through
`LIFECYCLE_CONFIG_PATH`. Configuration changes invalidate drift persistence via a
configuration hash. Current defaults are pilot settings requiring calibration:

| Setting | Default |
|---|---:|
| Reference/current window | 100 / 100 observations |
| Minimum trusted labels per class for drift | 20 |
| PSI / squared MMD threshold | 0.2 / 0.02 |
| Consecutive qualifying new windows | 3 |
| Performance degradation | >=0.02 absolute and >=25% relative; absolute rule when baseline is zero |
| Cohort FNMR / FMR budgets | 0.05 / 0.01 |
| Training cooldown / new reviewed observations | 24 hours / 40 |
| Canary stages | 5, 10, 25, 50, 100 percent |
| Shadow and EACH canary stage | >=1,000 observations AND >=3,600 seconds |
| Rollout minimum labels per class | 30 |
| Allowed FMR / FNMR regression | 0 / 0.005 |
| Policy p95 latency / disagreement | <=10 ms / <=0.1 |
| Trusted template creation / holdout per class | 10 / 20 |
| Template quality / margin / consistency | >=0.7 / >=0.1 / >=0.85 |
| Maximum templates per person/modality | 8 |

Quality-cohort gates also block a pooled pass that hides a labelled cohort regression.
The policy latency is threshold/routing latency, not encoder latency. Both policies
share the pinned encoder computation; CPU/memory/overall latency remain observable
through the existing infrastructure metrics. No independent encoder resource
comparison is claimed by this policy rollout.

## Decision Rules And Persistence

Quality drift -> INPUT_DRIFT; investigate capture, do not retrain.
Missing trusted labels, incompatible cohorts or unavailable embeddings ->
INSUFFICIENT_DATA, never a healthy performance claim.
Old-template-only degradation with healthy recent templates ->
TEMPLATE_UPDATE_REQUIRED. Three qualifying windows are required before action.
Template activation also waits for an idle lifecycle and evidence from the current
champion, so a model rollout cannot silently change its template cohort mid-stage.
Persistent embedding AND score drift AND verified performance degradation across
at least two age cohorts -> RETRAIN_REQUIRED. Otherwise monitor/score/embedding
states describe the unresolved evidence. Rules suggest causes, not causal proof.

With only 100 eligible observations and no existing frozen reference, the
default lifecycle cannot compare reference/current: it needs 100 + 100
non-overlapping observations. After a reference exists, a further 100 current
observations can support one comparison if labels/vectors/cohorts also pass.
Three fresh qualifying current windows, not three polls of those 100 rows,
are required for persistence.

Count a new persistence window only after at least one full window of new
observation IDs since the last counted window. Refreshing labels or polling the
same window does not increase persistence. Face and Voice counters are independent.

## Airflow And Training

The existing hourly `biometric_monitoring_pipeline` calls platform-only lifecycle
endpoints to bootstrap the incumbent policies, calculate reports and advance rollouts.
It writes versioned scalar input/label/report evidence to the existing MinIO lake.
Each eligible modality produces a deterministic training run ID. The existing
`biometric_model_pipeline` accepts `modality` and `window_id` in its DagRun conf.
It has no unconditional weekly schedule: statistical drift alone cannot train.

The service claims TRAINING under a PostgreSQL row lock, with one active lifecycle
per modality. Retries of the same intent are idempotent. Failed training is marked
REJECTED by an Airflow callback. Snapshot -> validate -> publish -> calibration ->
RAI report -> offline gate -> lifecycle tick retain the seven-task DAG structure.
Training is still restricted to tenant `demo`; customer training needs recorded
data-use consent and a separate approved data scope.

Calibration uses original enrollment plus retained high-quality, human-random-audit
genuine samples that passed capture integrity. Identity-disjoint CV/holdout is
preserved. At most 20 templates per identity and 10,000 sampled impostor identity
pairs bound evaluation work. These limits and MMD sampling do not constitute a
50,000-user latency/concurrency benchmark.

## Templates

Only explicit human modality labels count; model acceptance is never ground truth.
Require distinct media hashes, successful capture-integrity checks, high quality,
large score margin, consistency and no conflicting labels for the same capture.
Add the normalized centroid of trusted observations to the previous template set;
the oldest original enrollment remains available. The evaluation holdout excludes
creation hashes and must have sufficient genuine/impostor labels. FMR cannot rise
or exceed its budget; FNMR cannot worsen. Insufficient evidence stays PENDING_REVIEW.

Activation locks the employee row, stores a TemplateVersion and changes the
ActiveTemplate pointer. Reusing observations from an earlier template is blocked.
Rollback moves the pointer to the previous version; original biometric_samples
are never deleted. Platform endpoint:
`POST /v1/admin/lifecycle/templates/{person_id}/{modality}/rollback`.
Authorized enrollment appends to an active versioned template instead of silently
leaving the serving template stale. It also preserves the preceding version.

## Registry, Shadow, Canary And Rollback

One existing MLflow service, two registered policy models: `face-verification` and
`voice-verification`. Migration bootstraps policies with the current registered
bundle thresholds; this is preserving the incumbent, not promoting an unevaluated
retrained model. Candidate records source dataset and training intent. Offline
checks compare both policies on the SAME locked holdout. Direct CLI promotion is
disabled. Only a passing candidate receives challenger alias and enters SHADOW.
After both modalities are initialized, readiness and monitoring no longer require
the retired joint bundle to be loaded again.

For actual verification requests, compute both policies against the same similarity
score. Shadow records both thresholds/decisions/versions/latencies but returns the
champion result. Canary uses a stable hash of modality, deployment, tenant, person
and session. New stages expand the same cohort; routing is real policy selection
in the API, not a simulated percentage in a log. Existing PAD/anti-spoof checks
remain authoritative. Responses add `model_versions`; `model_version` becomes a
composite when independent policies are active.
The deployment evidence includes score delta, policy latency delta and disagreement.
Score delta is exactly zero for these threshold-only policies; decision disagreement
can still be nonzero. No second encoder execution is claimed.

PostgreSQL stores deployment state, stage start, percentage, revision and audit
evidence. Every canary gate uses only candidate-served observations AFTER its own
stage start. Missing labels pause advancement. Metric regression -> FAILED_CANARY,
traffic zero, existing champion unchanged. Invalid policy or unhandled verification
system failure also stops active rollout. Metrics with delayed ground truth are
evaluated by the hourly Airflow tick, not instantaneously when a label appears.

Final stage -> durable PROMOTING intent -> MLflow previous_champion and champion
aliases -> DB champion switch. Retrying after an external-call crash reconciles
the same intent; serving stays on the old champion until DB commit. The previous
version gets lifecycle_status=archived; MLflow alias conventions are used instead
of deprecated Registry stages. Failed models remain registered with audit reasons.
No automatic retry of a rejected candidate. Platform rollback endpoint:
`POST /v1/admin/lifecycle/{face|voice}/rollback`.

## Privacy, Storage And Operations

`RETAIN_MONITORING_EMBEDDINGS=false` by default. An operator must enable it only
under the deployment's data-use authorization. Query embeddings are removed after
`MONITORING_EMBEDDING_RETENTION_DAYS=30`; observation metadata defaults to 90 days.
Reference vectors are also scrubbed; expired references cannot support MMD until
a new reference is deliberately established. Frozen references are not silently
replaced with drifted current traffic. Scalar snapshot/label audit objects remain
in MinIO; vectors are NOT copied into these monitoring exports. Retained enrollment,
activated templates and approved training snapshots have separate lifecycle needs.
To renew a reviewed baseline, a platform operator can call
`POST /v1/admin/lifecycle/{face|voice}/reference` with `tenant_id` and a recorded
`reason`. It requires an idle champion, retained embeddings, sufficient independent
labels and rates inside the reference safety budgets. It resets persistence and
waits for a complete future window; baseline samples cannot also be current samples.
Monitoring reports and scalar evidence are captured in the same API transaction.

The system-error handler attempts to persist a stop immediately. If PostgreSQL is
unavailable, verification fails; the handler cannot durably change routing until
the database recovers. Existing in-flight requests are not retroactively cancelled.
Template rollback is explicit; subsequent template-specific automatic rollback is
not implemented. Reference renewal remains an operator action.

Prometheus contains modality, kind, class and bounded state labels, no employee IDs,
raw media or vector labels. The compact Grafana overview includes modality drift
and deployment/freshness panels; further metrics are available in Explore.
The separate ten-panel simulation dashboard displays synthetic lifecycle evidence.
See [monitoring mapping](../MONITORING_MAPPING.md). Existing
60-second Evidently monitoring remains the operational dashboard/report loop; it
does not independently trigger training. Automation decisions come from the hourly
Airflow job. GitHub Actions/Docker Compose remain the code/image deployment path.

## Evidence And Limits

Tests cover drift decisions/persistence, real API shadow capture, template poisoning
and rollback, actual local MLflow aliases, live-policy state progression, canary
failure, independent Face/Voice state, migration, retention and aggregate metrics.
Test observations and labels are synthetic fixtures. The DAG generates a RAI report, but the modality candidate endpoint does not
enforce the legacy `REQUIRE_HUMAN_FAIRNESS` flag; see [RAI](../RESPONSIBLE_AI.md).
No fresh production shadow,
canary, template activation or new human benchmark was executed by these tests.
PostgreSQL locking behavior and a 50,000-employee concurrent deployment still need
load/concurrency validation against a staging environment. This is not a claim of
production readiness, demographic fairness, liveness accuracy or encoder retraining.

## Source Map And Tests

- Serving and persistence: `api/app/{biometrics,checks,config,main,models,schemas}.py`;
  new `observation.py`, `lifecycle_api.py`, `lifecycle_service.py`,
  `model_lifecycle.py`, `template_lifecycle.py`; existing review form in `ui/app.py`.
- Drift and training: new `pipeline/drift_decision.py`, `lifecycle_config.json`,
  `modality_training.py`; updated `calibrate_and_register.py`, `data_snapshot.py`,
  `dataset_ledger.py`, `evaluation.py`, `validate_data.py`, `promotion_gate.py`,
  `model_rollout.py`, `monitoring_job.py`, `verify_stack.py` and both existing DAGs.
- Monitoring: `monitoring/ops_monitor.py`, `monitoring/prometheus/alerts.yml`,
  `pipeline/build_dashboard.py` and its generated Grafana dashboard.
- Configuration/documentation: `.env.example`, `README.md`, [dated evidence](EVIDENCE.md),
  `docs/CONTINUOUS_MLOPS.md`, this document and the implementation plan.
  `docs/DEMO_HANDOVER_GUIDE.md` links to current operator and demo runbooks.
- New suites: `test_drift_decision.py`, `test_live_lifecycle.py`,
  `test_template_lifecycle.py`, `test_lifecycle_monitoring.py`,
  `test_lifecycle_registry_integration.py`. Existing API, collector, immutable
  dataset, enrollment and verifier tests also gain regression coverage.

The real local MLflow integration test covers independent migration, training intent,
idempotent registration, artifact/provenance validation, shadow/canary gates, promotion,
rollback aliases/tags, reference renewal and transaction-consistent evidence. Separate
API tests demonstrate live threshold routing and restored responses after rollback.
