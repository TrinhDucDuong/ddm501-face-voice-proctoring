.PHONY: config up down logs models bootstrap calibrate test

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
	docker compose exec airflow-scheduler python /opt/project/pipeline/calibrate_and_register.py --promote

test:
	pytest -q

