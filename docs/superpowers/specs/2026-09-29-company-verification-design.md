> HISTORICAL PLAN / SPEC: retained for design history, not current runtime status.
> See [current documentation](../../README.md) for implementation, commands and evidence.

# Company verification service - approved scope

The user approved this scope in the conversation on 29 September 2026 and requested implementation. The annual foreign-language examination belongs to the customer. This project supplies verification and integrity signals through API/webhooks, a tenant portal, and a course MLOps platform. Airflow orchestrates snapshots, validation, evaluation and model promotion; it does not run customer examinations.

## Contract and compatibility

Add authenticated `POST /v1/checks` for customer-scheduled media batches. Inputs are person_id, session_id (customer attempt), request_id (idempotency), consent, image and WAV. Both operator and integration keys may submit checks; enrollment remains operator-only. Each request creates one immutable verification event, evidence metadata and a signed durable `integrity.checked` webhook transaction. Same request replay returns the existing result; a changed payload returns 409. A unique tenant/request constraint protects concurrent requests. Keep existing verification/session APIs as a compatibility example, outside the primary product flow.

Results expose stable event codes and Vietnamese labels, face/voice matches, integrity status (`verified`, `suspicious`, `inconclusive`), capability details, model provenance and evidence state. Suspicion is a model signal; the customer's software decides consequences. Never claim unsupported spoof/overlap detection passed. Face PAD uses pinned MiniFASNet ONNX; audio synthetic/converted-speech detection uses pinned AASIST. Multi-speaker suspicion uses consecutive ECAPA segments and must be labelled a heuristic, not simultaneous-speaker diarization. Single-image PAD is not universal video/deepfake detection. Exact repeated captures are a replay signal, not proof of fraud. Missing detectors produce inconclusive results and are visible in platform monitoring.

## Tenant portal and storage

Allow simulated company registration with an operator key returned once. No real billing or email verification. Existing platform provisioning stays available. Company admins configure approved webhook destinations, obtain/revoke integration keys, manage employees, enroll via upload/camera/audio, submit test checks, view employee/session check ranges and export filtered CSV/PDF. No scores, exam engine or manual admission decisions in the primary portal. Grafana links are platform-only.

PostgreSQL stores companies, employees, embeddings, immutable checks and outbox. MinIO stores only suspicious-check image/WAV under tenant/event prefixes; ordinary check media and raw enrollment are discarded by default. Inconclusive checks do not automatically imply cheating or retain media. Evidence downloads are authenticated and scoped through the API; object keys and unrestricted URLs are never exposed. Failed evidence writes are explicit and do not suppress a suspicious result. Retain data during simulated active registration; deactivation blocks access without deleting prior data. Additive migrations preserve all existing data.

## Platform and course deliverables

Retain Airflow/MLflow/gated identity evaluation, CI/CD, Grafana/Evidently/Telegram and recovery procedures. Extend telemetry for batch checks, detector readiness and evidence failures without tenant/customer identifiers in metric labels. Company webhooks carry business results; Telegram carries platform operations only. Update every conflicting document and presentation; add a unified business/technical project report with actual verification evidence, capability limits, references and genuine team contribution requirements. Demo two companies and prove isolation on API, history, exports and evidence.

## Verification

Meaningful tests cover role boundaries, identical employee codes in two tenants, idempotency/payload conflicts, missing detectors, suspicious-only retention, webhook consistency, evidence/export isolation, CSV injection, PDF Unicode and registration/key management. Live checks use actual enrolled media and MinIO, without manufacturing human ground truth or claiming production anti-spoof accuracy.
