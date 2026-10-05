# Monitoring: metric đến từ đâu và xem ở đâu

Đối chiếu source ngày **05/10/2026**. [Mục lục](docs/README.md).
Monitoring dành cho platform operator; tenant dùng portal/API/webhook để xem
kết quả nghiệp vụ. Truy vấn hoặc biến lọc Grafana không thay thế tenant access control.

## Hai dashboard hiện hành

| Dashboard | URL | Phạm vi |
|---|---|---|
| System Overview | http://localhost:13000/d/biometric-overview | 10 panel vận hành tổng quan, ưu tiên tín hiệu thật |
| Simulation | http://localhost:13000/d/biometric-simulation | 10 panel evidence tổng hợp và tiến trình demo |

Cả hai dashboard hiện dùng **Prometheus** cho toàn bộ panel. PostgreSQL, Loki và
Alertmanager vẫn được provision làm datasource để Explore/điều tra; không còn bố
cục dashboard 7 nhóm với hàng chục panel SQL/LogQL. Source JSON được sinh bằng
`pipeline/build_dashboard.py` và `pipeline/build_simulation_dashboard.py`.

| System Overview | Đọc gì |
|---|---|
| Serving readiness | Readiness API/portal/MinIO, có điều kiện freshness |
| Active incidents | Alert warning/critical, loại synthetic demo |
| API traffic | Traffic nghiệp vụ; loại health/admin/simulation |
| HTTP 5xx | Tỷ lệ lỗi server theo cửa sổ query |
| Verification p95 | Latency đường verify; không tự đại diện toàn bộ batch checks |
| Container CPU/RAM | Tài nguyên container từ Docker collector |
| Webhook backlog | Pending/retry/failure của outbox |
| Modality drift | Trạng thái/score drift độc lập Face/Voice |
| Human-reviewed FAR/FRR | Sai số có nhãn human; thiếu mẫu có thể No data |
| Pipeline freshness/deployment | Độ mới monitoring và lifecycle state |

Simulation hiển thị outcome/alert/reset, thời điểm run, baseline so với drift cuối,
genuine/impostor score, persistence, offline gate, HTTP requests theo stage,
challenger FMR/FNMR, policy latency và canary/retrain đang chạy. Các snapshot sau
reset là evidence đã lưu, không phải traffic mới. Run ID chi tiết nằm trong portal,
Airflow và JSON; labels Prometheus được giới hạn, không dùng employee ID hoặc vector.

## Từ dữ liệu đến metric

| Exporter / collector | Dữ liệu nguồn | Trách nhiệm |
|---|---|---|
| API | Request handling, policy observation, lifecycle DB | Request/latency/decision và aggregate lifecycle telemetry |
| webhook-worker | Outbox PostgreSQL và callback HTTP | Backlog, retries, delivery, poll freshness |
| drift-monitor | Verification events và feedback | Custom PSI, Evidently drift, human/synthetic performance reports |
| ops-monitor | PostgreSQL, MLflow, Airflow, probes, Docker read-only proxy | Registry, task trạng thái, resources, readiness, RAI, reports và Telegram |
| simulation | SQLite/file registry của simulation và run evidence | Synthetic drift/gate/routing/rollback/reset metrics |

[prometheus.yml](monitoring/prometheus/prometheus.yml) scrape 5 targets mỗi 15 giây.
Grafana query Prometheus; Prometheus không tự đọc trực tiếp database nghiệp vụ.
Alloy thu container logs vào Loki. Alertmanager nhận rules từ Prometheus và gom/
định tuyến alert. Production đi tới ops-monitor rồi Telegram nếu cấu hình;
simulation đi tới receiver riêng và không gửi Telegram. Alert không tự thay champion.

## Hai cách theo dõi drift cần phân biệt

**Lifecycle decision:** Airflow hàng giờ gọi lifecycle API; `pipeline/drift_decision.py`
dùng quality PSI, embedding RBF MMD², labelled score PSI, trusted FMR/FNMR và template
age. Reference/current mặc định 100/100, persistence 3 cửa sổ mới. Chỉ quyết định
đủ điều kiện mới phát intent retrain. Xem [MODALITY_LIFECYCLE](docs/MODALITY_LIFECYCLE.md).

**Operational reporting:** `monitoring/drift_monitor.py` mỗi 60 giây dùng cửa sổ
events và custom PSI cho `face_score`, `voice_score`, `face_quality`, `voice_quality`,
`risk_score`. Evidently DataDriftPreset tự chọn test theo loại/cỡ dữ liệu, không
đồng nghĩa mọi kết quả Evidently đều là PSI. ClassificationPreset và phần bổ sung
FAR/FRR dùng feedback, tách human khỏi legacy synthetic-simulation. Báo cáo này
không phải một trigger retrain độc lập và không phải registry simulation :15031.

## Report chi tiết qua Grafana gateway

Đăng nhập Grafana rồi mở `http://localhost:13000/reports/<name>.html` hoặc `.json`.
Gateway kiểm tra session Grafana; không phải public report tách khỏi xác thực.

| Report name | Nội dung / cách diễn giải |
|---|---|
| `data-drift` | Operational PSI/Evidently, windows, freshness |
| `model-performance` | Human reviewed performance; thiếu labels không kết luận khỏe |
| `synthetic-performance` | Legacy synthetic feedback report, không phải benchmark human |
| `data-quality` | Validation snapshot/count/dimension/fingerprint |
| `model-evaluation` | Offline calibration/CV/holdout từ collector; kiểm tra model/version, có thể là bundle legacy |
| `pipeline-status` | Model DAG run và từng task |
| `responsible-ai` | Quality slices, class counts, Wilson CI và giới hạn fairness |
| `alerts` | Alert đã nhận và trạng thái chuyển tiếp |

Để kiểm chứng rollout modality hiện hành, đối chiếu `GET /v1/admin/lifecycle/state`,
MLflow production :15030 và audit; không suy champion mới từ report bundle cũ.
Simulation xem MLflow :15031 và report của đúng run.

## Query và xử lý No data

Prometheus http://localhost:19090/query không tự vẽ metric khi chưa nhập query.
Thử `up`, `up{job="simulation"}` hoặc `biometric_service_health` rồi Execute.
Trong Grafana Explore chọn Prometheus; muốn logs thì chọn Loki. Xem targets tại
http://localhost:19090/targets và alerts tại http://localhost:19090/alerts.

Khi panel trống, kiểm tra time range, scrape target, collector freshness, dữ liệu
nguồn và đủ trusted labels. Không tạo human labels giả để lấp panel. Simulation
có dashboard riêng; khi run quá ngắn có thể khó nhìn các stage trên time series,
hãy dùng evidence snapshot và HTTP stage counts. Xem [SIMULATION](docs/SIMULATION.md).

`python pipeline/verify_monitoring_centre.py` kiểm tra overview/reports/freshness
trên stack đã có dữ liệu; `--send-alert` còn gửi alert thử thật. Việc gửi thông báo
hoặc chạy verifier tạo dữ liệu là thao tác riêng, không cần cho một lần sửa tài liệu.
Run/check đã ghi nhận nằm trong [EVIDENCE](docs/EVIDENCE.md).
