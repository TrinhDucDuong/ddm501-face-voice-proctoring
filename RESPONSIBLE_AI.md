# Responsible AI and privacy

## Integrity detectors - MVP boundary

Primary portal reports model signals, not exam verdicts. Missing detector produces inconclusive, not an all-clear. MiniFASNet single-image PAD and AASIST LA inference are implemented; no customer anti-spoof benchmark or universal deepfake/replay accuracy is claimed. ECAPA segment change is heuristic, not overlap diarization. Exact media reuse may have legitimate retry/capture causes; idempotent retries do not create reuse alerts. Raw ordinary checks are discarded; suspicious media needs consent and restricted operator access. Historical statements that anti-spoof is entirely absent now refer to the pre-maintenance baseline.


This is decision support. In the batch contract a mismatch becomes `suspicious`; missing information becomes `inconclusive`. Neither is an accusation or an exam decision. The compatibility identity/session contract uses `review`. Capture quality and identity similarity are separate from face PAD and voice anti-spoofing.

## Fairness

`pipeline/responsible_ai_report.py` measures accuracy/FAR/FRR across low, medium and high capture-quality slices after proctors submit labels. A >10-point accuracy gap is flagged for review once each comparable human slice has at least 20 labels, including at least five genuine and five impostor cases. The report supplies Wilson 95% confidence intervals for class-conditional rates. This detects an operational harm pathway (devices/network/environment), but it is not demographic fairness. The synthetic LFW + Speech Commands pairing has no valid demographic labels, so the project makes no demographic parity claim. A production pilot must collect optional, consented, purpose-limited evaluation labels and report intersectional FAR/FRR with confidence intervals before launch.

Mitigations include multi-sample enrollment, explicit image/audio quality gates, two modalities, no automatic rejection, slice monitoring, accessible re-capture and manual appeal.

## Explainability

Verification responses include scores, quality, thresholds, model version, reason codes, score margins, threshold sensitivity ±0.05, and single-modality counterfactuals. Counterfactuals preserve the other modality and quality constraints; improving a score alone may still yield REVIEW. Stored events preserve scores/quality/reasons/version but historical events do not contain the threshold, so Grafana does not infer historical margins. These are faithful explanations of a deterministic threshold policy; they do not explain the causal internals of the pretrained encoders. The MLflow artifact records threshold selection, identity folds and evaluation metrics.

RAI audit precedes promotion in the DAG. `REQUIRE_HUMAN_FAIRNESS=true` makes insufficient/rejected human evidence block promotion; the course demo defaults to false and shows insufficient evidence explicitly. Synthetic feedback never supplies human performance/fairness metrics.

## Privacy and ethics

SaaS sessions record explicit consent time before verification. Tenant queries and credentials are scoped; platform monitoring pages are admin-only. New customer templates do not enter default training (`TRAINING_TENANT_ID=demo`). Manual approval/rejection is audited separately from the model prediction, preserving performance evaluation integrity. API keys are hashed, session tokens are not placed in query strings/access logs, and webhook payloads contain no media/templates.

Synthetic simulation labels are identified separately in the quality-slice report. FAR uses impostor count as denominator, FRR uses genuine count; missing classes produce null rates. The human fairness gate returns `insufficient_data` until enough actual human-labelled slices exist. Do not rename simulation feedback as human review to make this gate pass.

- Biometric embeddings and media are sensitive personal data; obtain explicit consent and publish purpose/retention rules.
- Raw enrollment and ordinary check storage are disabled by default. Suspicious batch checks retain image/audio evidence in MinIO with consent and tenant-scoped operator access. Demo subscriptions retain history; deactivation blocks access without deleting records. Production requires TLS, KMS-backed encryption, secret management, SSO/RBAC, audit access and deletion/export workflows.
- Do not reuse data for surveillance or unrelated identification. This system supports 1:1 declared identity only.
- Limit retention for raw samples, templates and events separately; document lawful basis and incident response.
- Known risks include demographic performance gaps, disability/accent effects, replay/deepfake attacks, coercion and over-reliance by proctors.
