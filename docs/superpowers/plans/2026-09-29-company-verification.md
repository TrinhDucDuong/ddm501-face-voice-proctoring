# Company verification maintenance implementation plan

**Goal:** Deliver the approved batch verification service and company portal while preserving the course MLOps pipeline.
**Architecture:** Add a focused checks router and immutable check metadata alongside existing events. All reads, exports and evidence traverse tenant-scoped queries. Customer callbacks use the existing durable outbox; platform telemetry remains shared.
**Stack:** FastAPI, PostgreSQL/SQLAlchemy, MinIO, Streamlit, OpenCV, CPU PyTorch, ReportLab, Airflow/MLflow, Grafana/Evidently.
**Spec:** ../specs/2026-09-29-company-verification-design.md
**Execution:** Inline, following executing-plans and TDD; no subagents. Scope already approved in the conversation.

## Constraints

Preserve data/secrets and existing endpoints. No exam scoring, customer Telegram or paid billing. No unverified anti-spoof claims. Network downloads must be pinned and third-party attribution retained. Run baseline, focused red/green tests, complete CI checks and live multi-company checks before delivery.

## Tasks

- [x] 1. Batch checks and storage: create `api/app/checks.py`, add CheckRecord/Evidence models and safe migration. Tests `tests/test_checks.py` use isolated SQLite, genuine image/WAV enrollment, two tenants and an in-memory object-store adapter. Require `POST /v1/checks` to work with integration key, return identical check ID on retry, reject changed payload, and hide other tenant results. Existing event/outbox models are consumed; new checks output `integrity_status`, labelled reasons and capability details.
- [x] 2. Capture integrity: create `api/app/integrity.py`, vendor attributed pinned AASIST architecture, extend `pipeline/download_models.py`. Tests exercise missing-weight handling, face count, AASIST tensor output semantics, replay/segment decisions and disabled/test backend. Default pretrained checks use real detectors; report confidence and limitations.
- [x] 3. Company operations and exports: add registration/config/key routes; `api/app/company_reports.py` renders tenant-scoped event/range CSV/PDF. Tests assert cross-tenant 404, complete pagination, date filtering, protected evidence, spreadsheet formula escaping and readable Unicode PDF. Report metadata must exclude credentials/object keys.
- [x] 4. Portal/demo: update `ui/app.py` to employee/company navigation, direct batch API testing, clear statuses, named event selector, evidence playback and export. Update `legacy_demo` as customer-owned batch integration example, keeping admission compatibility endpoints. Verify Streamlit with actual API and browser flow.
- [x] 5. Platform operations: add check/capability/evidence metrics and dashboard panels/rules; update CI image dependencies and model packaging. Run dashboard consistency, full pytest coverage >=80%, Ruff, Compose config and real stack checks.
- [x] 6. Documentation and handoff: update requirements/architecture/integration/demo/mappings/operations/RAI/state; create `PROJECT_REPORT.md` and PDF, update presentation. Verify generated report visually, record real live results, commit and push main, then check GitHub Actions.

For each backend deliverable: write behavior tests, run to see missing-feature failures, implement, rerun until green. Keep live verification artifacts in ignored reports and all credentials in ignored files.

## Verification checkpoint

29/09: 65 tests pass, 86.50% local coverage; Ruff/compile/dashboard/Compose pass. Live two-company checks, MinIO evidence, callbacks ACK, exports and Streamlit AppTest pass. Full prior DAG/Registry/serving/monitoring remain verified. PDF rendered and reviewed; slides regenerated with bounds checked. Browser camera/mic/playback acceptance is a stated MVP limitation. Main pushed; GitHub run 36562882154 passed quality/containers/deploy-demo for executable commit 8b720fc, with 65 remote tests and 86.45% coverage. Deployed release SHA confirmed and company/monitoring checks rerun successfully. Documentation-only handoff commits preserve the tested executable code.
