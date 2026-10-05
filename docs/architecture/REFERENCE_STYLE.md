# Reference-style architecture graphic

> LOCAL DRAFT: pre-existing untracked assets, retained without regenerating figures.
> Use [current architecture](../../ARCHITECTURE.md) and
> [monitoring mapping](../../MONITORING_MAPPING.md) for operational details.
> The current dashboards use Prometheus panels; SQL/LogQL remain available in Explore.

Created 2026-10-03 from the current working-tree implementation. This overview uses
the supplied reference's three colored lanes, numbered headings, component icons,
connector arrows, and promotion/rollback panels.

- [Full-resolution PNG](DDM501_Architecture_Reference_Style.png): 3840 x 2560.
- [Editable SVG](DDM501_Architecture_Reference_Style.svg): vector shapes and text.
- [Preview PNG](DDM501_Architecture_Reference_Style_preview.png): 1920 x 1280.

## Reading the diagram

1. Code delivery and on-demand threshold calibration, with the seven actual
   `biometric_model_pipeline` tasks and shared storage/registry services.
2. Customer-scheduled batch checks, identity/integrity processing, durable metadata,
   suspicious evidence, immediate responses, and signed asynchronous callbacks.
3. Hourly evidence-based lifecycle decisions, separate template updates, operational
   monitoring, and guarded policy promotion or rollback.

Repeated PostgreSQL/MinIO labels denote responsibilities of shared services, not
additional deployments. Face/Voice and integrity blocks are capabilities inside
FastAPI, not separate model-server containers. The customer owns exam decisions.

The training task registers a candidate; the offline gate, shadow, and staged canary
control whether it becomes champion. Passing an intermediate canary stage advances
to the next percentage; only passing the final stage promotes. Failed stages keep
the current champion. An explicit operator rollback restores a previous champion.
Production model gates require sufficient trusted labels. Quality drift alone does
not request training. Encoders remain pretrained; training calibrates thresholds.

The observability row summarizes information flow: Prometheus actively scrapes
metrics, Grafana queries Prometheus/PostgreSQL/Loki, and production notifications
pass through Alertmanager and ops-monitor to configured Telegram destinations.
The isolated synthetic simulation shares the host and Airflow, but uses a separate
SQLite lifecycle store, file-backed MLflow and data volume. Its alerts have their
own receiver.

## Sources checked

- `ARCHITECTURE.md` and `docs/ARCHITECTURE_OVERVIEW.md`
- `docker-compose.yml` and `.github/workflows/ci.yml`
- `airflow/dags/biometric_ml_pipeline.py`
- `airflow/dags/biometric_monitoring_pipeline.py`
- `api/app/checks.py`, `api/app/lifecycle_service.py`, `api/app/observation.py`

This is an implementation overview, not evidence of runtime health or measured
production accuracy. Legacy hosted-session compatibility and detailed lifecycle
gate thresholds are omitted for readability.

## Rebuild

From the repository root on Windows, with Pillow installed and Segoe UI available:

```powershell
.venv/Scripts/python.exe docs/architecture/build_reference_architecture.py
```

Both exports share the same drawing coordinates. The builder checks label widths
before saving. Inspect the preview after editing content or coordinates.
