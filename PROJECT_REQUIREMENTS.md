# Product requirements and current scope

Reviewed against implementation on 2026-10-05. Original assignment files remain
in [ddm501-final-project-required](ddm501-final-project-required); this document
describes product scope, not a replacement for the assignment.

## Business and users

Annual employee language assessments need evidence of who supplied each capture.
The customer owns login, exams, scheduling, scores and business decisions. The
service supplies tenant-scoped identity/integrity signals through API/webhooks;
company administrators manage enrollment, history and evidence. Platform operators
manage models, infrastructure and monitoring. Cheating reduction is a proposed
pilot benefit, not a measured result.

## Implemented product capabilities

- Simulated active registration/subscriptions, tenant keys and approved webhooks.
- Person identifiers scoped to a company; Face/Voice enrollment and one-time
  enrollment invitations, consent assertions, JSON embeddings in PostgreSQL.
- `POST /v1/checks`: batch image/WAV verification, reason codes, versions,
  idempotency, immutable history and signed durable callback outbox.
- Face count, MiniFASNet PAD, AASIST, exact capture reuse and speaker-change
  heuristic; unavailable checks remain inconclusive, not passed.
- Suspicious-only MinIO evidence with authenticated access, filtered history and
  PDF/CSV exports. Ordinary capture and raw enrollment retention are off by default.
- Existing hosted sessions/manual review remain compatibility flows; the main API
  does not decide exam admission or score.

## Implemented MLOps scope

Pinned pretrained SFace/ECAPA encoders; retraining calibrates an independent Face
or Voice threshold policy. Versioned snapshots and identity-disjoint calibration,
CV and holdout feed MLflow candidate registration. Offline gates precede shadow,
progressive canary and recoverable champion promotion/rollback. Template updates
have independent trusted-data and holdout gates plus reversible versions.

Hourly Airflow monitoring uses quality PSI, multivariate embedding MMD squared,
score PSI, reviewed performance and template age. Statistical drift alone never
requests training. The 60-second operational PSI/Evidently loop only reports.
Automatic training is restricted to tenant `demo`; current code rejects other
training scopes. Isolated synthetic simulation demonstrates promotion and rollback.

## Acceptance and remaining work

The primary contract requires matching API/callback results, tenant isolation on
people/checks/exports/evidence/keys, honest detector availability and reproducible
lineage. CI enforces >=80% coverage in its declared scope, plus separate Windows
deployment preflight. Deployment evidence belongs to a specific SHA/run.

[lifecycle_config.json](pipeline/lifecycle_config.json) defines pilot defaults:
FMR <=1%, FNMR <=5%, no FMR regression, FNMR regression <=0.005 and sufficient
trusted labels/time/samples at every rollout stage. The legacy/internal calibration
budget of 20% is not the current promotion acceptance criterion. These settings
need customer risk review and statistical validation before deployment to people.

Initial evaluated champion provisioning from an empty registry is not automated.
Query embedding retention is opt-in; missing vectors/labels block full drift
automation. RAI reports exist, but the modality candidate path does not enforce
the legacy fairness flag. Customer training, demographic/anti-spoof benchmarks,
50,000-employee load testing, SSO/billing, end-to-end deletion and cloud HA remain
future pilot work. See [ARCHITECTURE](ARCHITECTURE.md), [RAI](RESPONSIBLE_AI.md)
and [EVIDENCE](docs/EVIDENCE.md).
