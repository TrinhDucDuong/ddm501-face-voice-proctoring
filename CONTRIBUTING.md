# Contributing and team roles

Use feature branches and pull requests; require passing CI and one reviewer. Commit small, testable changes with imperative messages. Never commit `.env`, biometric samples, model weights, reports or database volumes.

Suggested ownership (replace names before submission): Product/Responsible AI owns requirements, risk and evaluation; ML/Data owns ingestion, validation, calibration and MLflow; Platform owns API, Docker, Airflow and CI/CD; Observability/QA owns tests, Prometheus, Grafana, Evidently and runbooks. Every member must review another area and be able to explain the end-to-end flow.

Before a pull request run `python -m compileall api pipeline monitoring airflow/dags ui`, `pytest -q`, and `docker compose config --quiet`. Include the test evidence, migration/rollback impact and screenshots for dashboard changes.
