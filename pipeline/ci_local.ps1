param([switch]$Build)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m ruff check api pipeline monitoring tests legacy_demo
if ($LASTEXITCODE -ne 0) { throw 'Lint failed' }
python -m pytest -q --cov=app --cov=pipeline.evaluation --cov=pipeline.data_snapshot --cov=pipeline.validate_data --cov=pipeline.promotion_gate --cov=pipeline.responsible_ai_report --cov=monitoring --cov-report=term-missing --cov-report=json:reports/coverage.json --cov-fail-under=80
if ($LASTEXITCODE -ne 0) { throw 'Tests/coverage failed' }
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose validation failed' }
docker compose exec -T prometheus promtool check rules /etc/prometheus/alerts.yml
if ($LASTEXITCODE -ne 0) { throw 'Prometheus rules failed' }
if ($Build) {
    docker compose build api ui drift-monitor ops-monitor airflow-scheduler webhook-worker legacy-demo
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
}
Write-Output 'Local CI checks passed (this is not a GitHub Actions run).'
