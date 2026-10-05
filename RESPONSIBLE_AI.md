# Responsible AI and privacy

Reviewed against source on **2026-10-05**. This is decision support: `suspicious`
and `inconclusive` are signals for customer review, not accusations or exam verdicts.
The customer owns consequences and must provide an appropriate recapture/review
process. The legacy hosted session supports manual review; a complete customer
appeals/case-management workflow is not implemented by this service.

## Detectors and harm boundaries

SFace/ECAPA identity embeddings do not prove liveness. MiniFASNet single-image PAD
and AASIST LA inference add research detector signals. ECAPA segment consistency
is a speaker-change heuristic, not overlap diarization. Physical audio replay,
unseen deepfakes and customer anti-spoof accuracy have not been validated. Missing
detectors or inadequate captures must not be treated as all-clear. An idempotent
retry returns its original result; exact reuse under another request can be flagged.

Capture quality, template age and population changes can harm legitimate users.
Drift rules distinguish input investigation, template update and policy calibration.
Those root-cause labels are heuristics, not causal proof. Multiple high-confidence
observations and a disjoint labelled holdout reduce template poisoning risk; model
acceptance alone never authorizes a template update.

## Fairness: measurement and enforcement

`pipeline/responsible_ai_report.py` measures accuracy/FAR/FRR across low, medium
and high capture-quality slices. Comparable human slices need at least 20 labels,
including at least 5 genuine and 5 impostor cases. An accuracy gap greater than
10 percentage points is flagged. Wilson 95% intervals express finite-sample
uncertainty for class-conditional error rates. Quality is an operational proxy,
not a demographic attribute; this report does not demonstrate demographic fairness.

The training DAG generates a RAI report before its offline gate. **The current
modality candidate endpoint does not enforce `REQUIRE_HUMAN_FAIRNESS`.** That flag
is used by the legacy bundle gate. Enabling it is not sufficient to block the
current Face/Voice rollout when human fairness evidence is missing. Treat this as
an open enforcement gap, requiring explicit human evaluation before a real pilot.

Human and synthetic labels are separated in operational reports. The lifecycle
uses explicit modality labels from the server-selected random-audit cohort for
performance gates. Predictions are never ground truth; reviewing only suspicious
cases would bias estimates. Random audit reduces selection bias but does not
establish representative demographic or device coverage. Missing classes/labels
remain insufficient evidence. Never relabel simulation feedback as human evidence.

## Explainability

Responses expose scores, quality, thresholds, versions and reasons. The policy
explanation path includes score margins, threshold sensitivity +/-0.05 and
single-modality counterfactuals subject to the other modality/quality constraints.
These explain deterministic policy behavior, not causal encoder internals or a
calibrated probability of cheating. Integrity detector results are separate.

Older `VerificationEvent` records lack historic thresholds, so do not reconstruct
their margins from today's threshold. New `ModalityObservation` records retain
thresholds, versions and champion/challenger decisions, enabling lifecycle audit.
Both policies share one encoder/score; zero score delta does not mean their
decisions agree. MLflow artifacts record threshold selection and evaluation lineage.

## Data protection: implemented controls and gaps

Tenant-scoped credentials and queries restrict company data. API keys are hashed;
signed webhook payloads carry no raw media/embeddings. Company evidence downloads
require authorization. Hosted session tokens use a URL fragment rather than query
strings. Consent assertions are recorded, but the customer must establish that
consent and the purpose of processing are valid; a checkbox does not establish
lawful use on its own.

Raw enrollment and ordinary check media are discarded by default. Suspicious
checks can retain image/audio evidence in MinIO despite raw enrollment being off.
Embeddings are sensitive biometric data, not anonymous identifiers. Query-vector
retention is opt-in (`RETAIN_MONITORING_EMBEDDINGS=false` by default), with default
30-day vector and 90-day observation retention in lifecycle maintenance. This does
not automatically expire enrollment, active templates, evidence, backups or every
MinIO training artifact. Deactivating a subscription blocks access without deleting
history. A complete cross-store erasure/retention workflow remains to be implemented.

Training currently rejects tenants other than `demo`; changing an environment
variable is not authorization or implementation of customer training. Isolated
simulation uses synthetic data and separate stores; shared host/Airflow resources
remain a possible source of contention. Prometheus labels must remain aggregate,
without employee IDs, vectors or media.

## Before a customer pilot

Obtain purpose-limited consented benchmarks, independent genuine/impostor labels,
device/environment and appropriate demographic slices with class counts and
confidence intervals. Validate false accept/reject costs with the customer and
provide recapture, manual review and appeal routes. Add fairness enforcement in
the actual lifecycle gate, complete deletion/retention procedures, TLS/SSO/RBAC,
secret management, encryption policy, access audits and incident response.

Capacity and anti-spoof tests must reflect real customer captures and concurrency.
Do not reuse data for unrelated surveillance or identification. Current scope is
declared-identity verification 1:1. [EVIDENCE](docs/EVIDENCE.md) identifies what has
actually been tested; [lifecycle](docs/MODALITY_LIFECYCLE.md) records gate limits.
