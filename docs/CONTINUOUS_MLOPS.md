# Continuous MLOps: independent Face / Voice policies

The current source implements the lifecycle described in
[MODALITY_LIFECYCLE.md](MODALITY_LIFECYCLE.md). That document contains the component
mapping, actual formulas, complete configuration, decision rules, API entry points,
template safeguards, registry transitions, tests and limitations.

This replaces the previous two-window PSI trigger and direct joint-bundle promotion.
Existing runtime/CI evidence is historical unless its tested revision includes this
change; see [EVIDENCE](EVIDENCE.md).

## One Automation Path

`biometric_monitoring_pipeline` runs hourly and calls the existing API to evaluate
quality, multivariate embeddings, labelled verification scores, performance and
age cohorts. Independent Face/Voice reports are persisted in PostgreSQL and MinIO.
The 60-second Evidently loop remains operational reporting only.

A statistical shift alone cannot train. Retraining requires three fresh qualifying
windows, verified cross-age performance degradation, enough reviewed samples, no
input-quality explanation, no aging-only explanation, a cooldown and no active
lifecycle for that modality. Missing labels or retained vectors block automation.

`biometric_model_pipeline` has seven tasks and no unconditional schedule. Monitoring
supplies a modality and a deterministic window ID. It calibrates one cosine threshold
policy on pinned SFace/ECAPA, using identity-disjoint CV and holdout. It does not
fine-tune encoders. Automatic training remains restricted to the demo tenant.

## Registry And Serving

One MLflow service manages `face-verification` and `voice-verification`. Candidate
registration does not replace champion. Offline paired evaluation grants challenger;
actual requests then execute shadow policies without changing the real response.
Passing shadow starts real canary routing at 5, 10, 25, 50 and 100 percent. Each stage
requires sample, duration, trusted-label, security and policy-latency gates.

Failed canary sets candidate traffic to zero and retains the current champion.
Final success persists a promotion intent, reconciles MLflow aliases and changes the
serving policy in the DB. Previous champion remains available for rollback. The
previous joint bundle is retained as migration history and an incumbent source.

Code/image deployment still uses GitHub Actions, the Linux/WSL self-hosted runner,
PowerShell staging and Docker Compose. Model-policy rollout occurs inside the API;
it does not create a second container deployment system.

## Templates, Labels And Storage

Reviewers label Face and Voice separately through the existing company review form
or `PUT /v1/checks/{check_id}/review`. Ground truth is never copied from predictions.
Only the server-selected random-audit cohort contributes to performance gates.

Template updates need multiple distinct, trusted, high-quality captures, identity
consistency and a separate labelled holdout. Activation creates a version and keeps
the previous template. Pending evidence stays pending; no latest-success overwrite.
Existing authorized enrollment also updates an active template version.

Query-vector retention is opt-in and expires after 30 days by default. Observation
metadata expires after 90 days. Monitoring lake paths are
`datasets/monitoring/<tenant>/<modality>/<version>/{reference,inputs,labels,reports}/`;
objects use content hashes. No query vectors are exported in these monitoring
objects. Approved training snapshots remain in the existing training ledger.

## Operational Limits

Default thresholds are pilot settings. Empirical FMR/FNMR from small fixtures are
not population guarantees. Missing impostor labels pause promotion. Policy latency
does not measure a separate encoder: champion and challenger share the encoder.
50,000-employee throughput, PostgreSQL concurrency and production cohort quality
still require staging validation. See the lifecycle document before activation.

Historical checkpoints and restore notes are indexed in
[archive](archive/README.md). A source rollback does not restore DB/MinIO data;
use the [current deployment recovery guidance](../DEPLOYMENT.md#backup-restore-và-rollback).
