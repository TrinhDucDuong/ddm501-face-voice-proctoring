# Mapping monitoring → Grafana

## Platform alerts versus company events

Grafana/Prometheus/Evidently/Telegram serve platform operators. Added integrity checks by status, detector availability and suspicious-evidence storage outcomes. Model/service/collector/evidence failures trigger technical alerts. Per-check employee signals go immediately to company API/webhook and tenant history; portal exports PDF/CSV and protected media. No company needs Grafana credentials. Identity feedback performance and broader capture-integrity statuses are distinct metrics.


Trang chính: http://localhost:13000/d/biometric-overview. Portal đưa một link monitoring tới trang này; Airflow/MLflow/MinIO tiếp tục phục vụ thao tác quản trị tương ứng.

| Phần monitoring | Nguồn | Hiển thị tại Grafana |
|---|---|---|
| Readiness / latency / HTTP errors | API, probes, Prometheus | Nhóm 1 |
| Enrollment / training samples / dimension / validation | PostgreSQL + ops-monitor | Nhóm 2 |
| Similarity / capture quality / reason codes | PostgreSQL | Nhóm 2 |
| PSI / Evidently drift / windows / freshness | drift-monitor | Nhóm 3 + report data-drift |
| Human và synthetic classification metrics | drift-monitor, hai nguồn tách riêng | Nhóm 3–4 + hai report riêng |
| Serving / candidate / champion / threshold / gate | API + MLflow collector | Nhóm 4 |
| Calibration / identity CV / holdout FAR/FRR | MLflow collector | Nhóm 4 + model-evaluation |
| Explainability | API policy explanations | Nhóm 4 giải thích phương pháp; response trả margins/sensitivity/counterfactual |
| Session states / actual review queue / review SLA | PostgreSQL | Nhóm 5 |
| Webhook backlog / retries / failures | worker + PostgreSQL | Nhóm 5 |
| Telegram configuration / delivery outcomes | ops-monitor | Nhóm 5 + report alerts |
| DAG run/tasks/durations | Airflow DB collector | Nhóm 6 + pipeline-status |
| Fairness slices / class counts / confidence intervals | RAI audit/collector | Nhóm 6 + responsible-ai |
| Collector freshness / scrape targets | Prometheus | Nhóm 6–7 |
| Container CPU/RAM/network/block IO | Docker API read-only proxy | Nhóm 7 |
| Database size/connections | PostgreSQL | Nhóm 7 |
| Docker service logs/error logs | Alloy → Loki | Nhóm 7 |
| Firing/resolved alert notifications | Prometheus → Alertmanager → ops-monitor | Alert groups + Telegram |

Các báo cáo HTML/JSON nằm cùng origin Grafana và yêu cầu đăng nhập. Anonymous đã được kiểm tra nhận 401; authenticated nhận 200. `reports/monitoring-verification.json` kiểm tra các truy vấn PromQL/SQL/LogQL, freshness, báo cáo và gửi cảnh báo Alertmanager tới Telegram.

Metric không có đủ dữ liệu có thể hiển thị No data/NaN: human labels, fairness hoặc rate khi thiếu traffic. Đây không phải kết luận đạt chất lượng. Bộ chọn tenant chỉ giới hạn SQL; monitoring là quyền quản trị toàn nền tảng. Xem [OPERATIONS.md](OPERATIONS.md) để chạy lại kiểm chứng và vận hành bot.
