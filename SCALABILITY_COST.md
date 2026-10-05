# Capacity and cost plan

## Batch service cost update

Customer schedules requests. At 30s/check, request rate = concurrently tested employees / 30. Suspicious evidence bytes ~= suspicious checks * (image bytes + WAV bytes); enrollment raw and ordinary captures default off. Add PAD/AASIST and multiple ECAPA segments to CPU service time; previous legacy identity-only latency cannot represent full check latency. Data retained for simulated active subscriptions; no commercial pricing/billing yet.


## Pilot targets and measurement

Proposed pilot acceptance targets: at least 70% of genuine sessions automatically allowed, at least 50% less manual review time per 1,000 sessions, review turnaround below 15 minutes, and no increase in the consented pilot FAR baseline. These are requirements to validate with the customer, not measured business results. Record the initial manual workflow, operator minutes, genuine/impostor labels and confidence intervals before evaluating improvement.

Current policy rollout defaults require FMR <=1%, FNMR <=5%, no FMR regression and FNMR regression <=0.005; see [lifecycle configuration](pipeline/lifecycle_config.json). The 20% internal CV calibration budget and historical bundle gate are not the current promotion criterion. None of these small-sample budgets establishes a population security guarantee; a customer pilot must choose and validate its own risk limits.

## Sizing model

The target is 50,000 enrolled employees, not 50,000 concurrent inference requests. If all 50,000 submit once per 30 seconds, arrival rate is about 1,667 checks/s; if 1,000 are concurrently active, it is about 33.3 checks/s. Neither load has been demonstrated by the local stack.

For arrival rate λ requests/s and measured CPU service time S seconds/request, start with `workers ≥ ceil(λ × S / 0.65)`. Validate against p95 latency, memory, review backlog and burst traffic in Grafana. Keep model weights loaded in each worker and warm them before routing traffic. Add API replicas behind a gateway; share PostgreSQL/MinIO and preserve session/outbox transactions. Model registry and orchestration do not need to scale with every inference request.

Illustration only: 1,000 single-check requests spread over one hour means λ=0.278/s; if measured S=1 CPU second, one warmed worker averages 28% utilization. A tenfold burst requires at least five such workers at 65% target utilization. This calculation does not establish capacity: face/speaker locks, media size, DB contention and cold starts require load measurement.

Local course stack: start with a 16 GB host and reserve roughly 6–8 GB for Docker. Defaults use one Airflow LocalExecutor slot, one DAG parser, one webserver worker and one MLflow worker; `AIRFLOW_PARALLELISM`, `AIRFLOW_WEBSERVER_WORKERS`, `MLFLOW_WORKERS` are configurable. CPU/RAM are visible in the compact Grafana overview; network/block IO remain available through Prometheus/Explore. The Docker API collector uses read-only access and filters this Compose project. Increasing worker counts increases RAM usage. Other tutorial stacks share the same Docker memory budget and must be included in capacity planning.

## Cost worksheet

Use supplier quotes rather than claiming an unmeasured cloud bill:

`monthly cost = app-hours × app-rate + control-plane-hours × control-plane-rate + database + storage + egress + reviewer-hours × reviewer-rate`.

| Item | Quantity to measure | Cost driver |
|---|---|---|
| API replicas | Worker count, warm CPU service time, RAM per loaded model | Instance/GPU hours |
| Shared control plane | Airflow/MLflow uptime, retention | Compute and metadata DB |
| Data and artifacts | Embedding/model/log bytes, retention, backups | GB/month, requests |
| Network | Hosted media ingress, callbacks, downloads | Egress GB |
| Human review | REVIEW share × sessions × minutes/review | Staff hours |

Log retention is seven days in the demo. Raw enrollment and ordinary check storage are off by default; suspicious evidence is retained separately, and embeddings/templates still require storage/retention budgeting. Logs and operational reports still require restricted access and a retention policy. Prefer queue/backlog and service latency alarms before adding replicas. No paid resources have been provisioned.
