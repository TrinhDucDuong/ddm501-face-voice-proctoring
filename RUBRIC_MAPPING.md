# Mapping yêu cầu DDM501 với implementation

Rà soát ngày **05/10/2026**. Đối chiếu [đề bài gốc](ddm501-final-project-required/DDM501_Final_Project.docx.pdf)
và [full pipeline](ddm501-final-project-required/MLOps_full_pipeline.txt).
Đây là mapping để kiểm tra, không tự gán điểm thay giảng viên.

## Development rubric

| Tiêu chí | Trọng số | Implementation / tài liệu | Bằng chứng hoặc giới hạn cần xét |
|---|---:|---|---|
| Problem / requirements | 10% | [Scope](PROJECT_REQUIREMENTS.md), [capacity/cost](SCALABILITY_COST.md) | Business outcomes và ROI chưa đo tại khách hàng |
| Architecture | 15% | [Thiết kế](ARCHITECTURE.md), [Mermaid](docs/ARCHITECTURE_OVERVIEW.md), [API contract](SAAS_INTEGRATION.md) | Compose một host; cloud HA chưa triển khai |
| ML pipeline | 15% | Snapshot/hash, validation, threshold minimax/CV/holdout, paired evaluation, MLflow và lifecycle riêng Face/Voice | Encoder pretrained; dữ liệu demo không chứng minh biometric accuracy |
| Deployment | 15% | [Compose/serving/readiness/rollback](DEPLOYMENT.md), stateful policy shadow/canary | Canary policy khác app deployment; registry rỗng chưa tự có evaluated champion |
| Monitoring | 10% | [Mapping](MONITORING_MAPPING.md), overview/simulation dashboards, reports, alerts | Human labels có thể thiếu; synthetic phải tách riêng |
| Testing / CI/CD | 15% | [Workflow](.github/workflows/ci.yml), unit/integration tests, Windows preflight và Linux WSL deploy | Coverage >=80% trong phạm vi khai báo; đối chiếu [run đúng SHA](docs/EVIDENCE.md) |
| Responsible AI | 10% | [RAI](RESPONSIBLE_AI.md): consent, labels riêng, quality slices, Wilson CI, reasons/margins | Chưa demographic benchmark; modality candidate path chưa enforce fairness flag legacy |
| Documentation | 10% | [Mục lục](docs/README.md), API OpenAPI, guides, report, demo/Q&A | Bản xuất lịch sử được lưu archive; contribution cần công việc/review thật |

Các tiêu chí con được đối chiếu như sau: problem/requirements/success metrics trong
scope và capacity; design/data flow/trade-offs trong architecture; data pipeline/
training/tracking trong lifecycle; API/container/orchestration trong deployment;
metrics/dashboard/alerting trong monitoring; coverage/test types/CI trong workflow;
fairness/explainability/ethics trong RAI; README/API docs/code quality trong README
và CONTRIBUTING. Coverage không đại diện mọi CLI, UI, DAG, model weights hoặc
accuracy thực tế; xem chính xác lệnh `--cov` của workflow.

## Full pipeline và vị trí code

| Bước | Code / nơi kiểm tra | Hành vi hiện tại |
|---|---|---|
| Enrollment / inference | `api/app/biometrics.py`, `checks.py` | 1:1 SFace/ECAPA max cosine, tenant scope, identity/integrity riêng |
| Snapshot / validate | `pipeline/data_snapshot.py`, `validate_data.py`, `dataset_ledger.py` | Snapshot tenant demo, fingerprint, validation và MinIO lineage |
| Calibration / CV | `pipeline/evaluation.py`, `modality_training.py` | Threshold minimax, 5 identity partitions, holdout 20%, CV trên 80% |
| Registry | `pipeline/modality_training.py`, `api/app/model_lifecycle.py` | `face-verification` / `voice-verification`, candidate/challenger/champion/previous_champion |
| Offline gate | `pipeline/promotion_gate.py`, lifecycle candidate endpoint | Cùng holdout với incumbent; offline pass bắt đầu shadow |
| RAI | `pipeline/responsible_ai_report.py` | Report quality slices; enforcement gap được ghi rõ |
| Shadow / canary / rollback | `api/app/model_lifecycle.py`, `observation.py` | DB state, actual policy routing, stage evidence, recoverable promotion |
| Drift decision | `pipeline/drift_decision.py`, `api/app/lifecycle_service.py` | PSI/MMD², trusted error rates, age, persistence và cooldown |
| Template update | `api/app/template_lifecycle.py` | Trusted captures, disjoint holdout, version và operator rollback |
| Airflow | `airflow/dags/` | Monitoring mỗi giờ; model DAG theo intent 7 task; simulation poll mỗi phút |
| Operational reports | `monitoring/drift_monitor.py`, `ops_monitor.py` | PSI/Evidently, human/synthetic split, Registry/DAG/resources |
| Dashboards / alerting | `monitoring/`, dashboard builders | 10 overview + 10 simulation panels; Prometheus/Alertmanager/Telegram |
| Isolated simulation | `pipeline/simulation_runner.py`, `api/app/simulation_server.py` | Synthetic drift, alert receipt, HTTP shadow/canary, promotion hoặc rollback |
| API integration | `api/app/checks.py`, webhook worker | Immutable check/outbox, HMAC retry, receiver dedup |
| Code delivery | `.github/workflows/ci.yml`, `pipeline/deploy_local.ps1` | Ubuntu quality + Windows preflight, build, Linux WSL/PowerShell Compose deploy |

Full pipeline có hai phần: Airflow/training/Registry/API và serving/monitoring/
drift/alerts/automation. Source và simulation chứng minh cơ chế; [bằng chứng](docs/EVIDENCE.md)
chỉ có hiệu lực trong phạm vi dữ liệu, runtime và revision đã ghi nhận.

## Required files và thuyết trình

| Required file | Vị trí |
|---|---|
| README | [README.md](README.md): overview, setup, usage |
| Architecture | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Team responsibilities | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Python dependencies | [requirements.txt](requirements.txt) và profiles theo service |
| Container configuration | [docker-compose.yml](docker-compose.yml), Dockerfile tại `api/`, `ui/`, `airflow/`, `monitoring/`, `legacy_demo/`, `deploy/` |
| CI/CD | [.github/workflows/ci.yml](.github/workflows/ci.yml) |

Không có Dockerfile tổng tại root; Compose tham chiếu đúng Dockerfile từng service.
Nếu giảng viên yêu cầu đúng tên/vị trí root, cần giải thích cấu trúc multi-service,
không gọi root Dockerfile là đã tồn tại.

Rubric thuyết trình: Problem & Solution 15%, Technical Deep Dive 40%, RAI 15%, Q&A
15%, Live Demo 15%. [Kịch bản](DEMO_PRESENTATION.md) tổ chức 15 phút present,
10–15 phút demo và 10 phút Q&A theo kế hoạch nhóm. Mọi thành viên cần meaningful
commits, PR/review và tham gia thật; lịch sử Git bị rewrite không tự chứng minh
đóng góp. Kiểm tra quyền truy cập repository cho giảng viên tại thời điểm nộp.
