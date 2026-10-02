.PHONY: config up down logs models bootstrap calibrate simulate monitor test

config:
	docker compose config --quiet

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api ui airflow-scheduler

models:
	docker compose run --rm model-init

bootstrap:
	python pipeline/bootstrap_demo.py --identities 50 --samples 3 --enroll-api

calibrate:
	docker compose exec airflow-scheduler python /opt/project/pipeline/calibrate_and_register.py
	docker compose exec airflow-scheduler python /opt/project/pipeline/promotion_gate.py

simulate:
	python pipeline/simulate_drift.py --samples 120

monitor:
	docker compose exec drift-monitor python -c "from monitoring.drift_monitor import run_once; print(run_once())"

test:
	pytest -q --cov=app.biometrics --cov=app.decision --cov=pipeline.validate_data --cov=pipeline.promotion_gate --cov=monitoring.drift_monitor --cov-report=term-missing
