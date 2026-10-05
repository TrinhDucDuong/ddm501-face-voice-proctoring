# Vận hành: Grafana, Telegram và CI/CD

## Current company service

Customer business results use API and integrity.checked webhook; platform Telegram receives only technical alerts. Company admins use portal history/evidence/reports. Aggregate batch outcomes, detector readiness and evidence metrics remain available in Prometheus/Explore; the compact overview does not display every instrumented metric. Detector readiness reflects last execution; missing/short captures may mark capability unavailable/not assessed. No per-company Telegram. Demo registration enabled by default on loopback; disable for production.


## Trang monitoring chính

Mở http://localhost:13000/d/biometric-overview, đăng nhập Grafana `admin` / `admin` ở demo loopback. Portal đưa một link monitoring tới Grafana; các link Airflow/MLflow/MinIO phục vụ quản trị pipeline.

System Overview có 10 panel vận hành. [Simulation](http://localhost:13000/d/biometric-simulation) có 10 panel synthetic riêng; cả hai dùng Prometheus. PostgreSQL/Loki/Alertmanager vẫn có trong datasource để Explore/điều tra. Danh sách panel, nguồn metric và reports tại [MONITORING_MAPPING](MONITORING_MAPPING.md). Grafana là quyền quản trị toàn nền tảng, không cấp tài khoản này cho tenant khách hàng.

Report cùng origin `/reports/<name>.html` và `.json`: `data-drift`, `model-performance`, `synthetic-performance`, `data-quality`, `model-evaluation`, `pipeline-status`, `responsible-ai`, `alerts`. Nginx kiểm tra phiên đăng nhập qua Grafana `/api/user`; anonymous nhận 401/403. Các endpoint Prometheus/Airflow/MLflow tiếp tục dùng nội bộ.

## Nguồn dữ liệu

| Nguồn | Nội dung |
|---|---|
| API / webhook-worker | Requests, decisions, latency, outbox, delivery |
| drift-monitor | PSI/Evidently drift; classification từ reviewed events |
| ops-monitor | DB validation, Registry, DAG/tasks, RAI, readiness, Docker stats, Telegram |
| PostgreSQL datasource | Truy vấn Explore cho điều tra; panel dashboard hiện hành dùng Prometheus |
| simulation | Synthetic drift, alert receipt, offline/shadow/canary/rollback/reset evidence |
| Alloy → Loki | Docker logs lọc Compose project, retention 7 ngày |
| Prometheus / Alertmanager | Scrape freshness và alert groups |

CPU/RAM/network/block IO lấy qua Docker API read-only proxy. Review queue chỉ lấy `verify_sessions.status='review'`; event có `accepted=false` đã xử lý không được tính pending review. Khi dữ liệu hết freshness, kiểm tra collector trước khi dùng kết quả cũ.

## Human và synthetic performance

`model-performance` chỉ dùng reviewer có prefix `operator:`; `synthetic-performance` dùng reviewer `synthetic-simulation`. Hai cửa sổ thời gian không giao nhau, mỗi cửa sổ `PERFORMANCE_WINDOW_SIZE` feedback, phải có cả genuine và impostor. Nếu thiếu nhãn human, báo cáo chờ và metrics NaN.

`biometric_reviewed_performance{source,metric,window}` có accuracy/precision/recall/F1/FAR/FRR. `biometric_reviewed_report_success{source}` biểu thị tính hợp lệ. Positive là genuine. REVIEW được tính là không accept. Đây là performance trên reviewed subset, có selection bias.

Kịch bản legacy `python pipeline/simulate_drift.py --samples 100 --with-feedback` tạo event/nhãn synthetic trong DB ứng dụng chính, không có isolation của trang simulation mới. Không dùng nó để minh họa một demo không tác động dữ liệu runtime. Alert `BiometricSyntheticPerformanceDegraded` có `evidence=synthetic_demo`; human alert giữ tên `BiometricPerformanceDegraded`.

Demo hiện hành: đăng nhập platform trên portal và mở **Simulation MLOps**. Hai nút
kịch bản dùng DB/MLflow/volume riêng; nút **Restore demo baseline** reset routing và
aliases demo, giữ lịch sử. `biometric_simulation` poll queue mỗi phút; Prometheus và
Alertmanager gửi alert thật về simulation receiver trước khi retrain, không gửi
Telegram. Xem [hướng dẫn](docs/SIMULATION.md). Không trộn bằng chứng tổng hợp này
với metric human hoặc đánh giá capacity production.

## Telegram

Bot: `@ddm501_face_voice_proctoring_bot`. `.env` giữ `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`; không đưa vào code/logs/commit. Luồng: Prometheus → Alertmanager → ops-monitor `/alerts` → Telegram. Gửi cả firing/resolved. Lỗi gửi trả 503 để Alertmanager retry.

`python pipeline/verify_telegram.py` gửi tin thử trực tiếp. `python pipeline/verify_monitoring_centre.py --send-alert` kiểm tra Alertmanager và lưu `reports/monitoring-verification.json`. Transport xác minh TLS/CA/hostname; có fallback tới IP chính thức khi mạng reset kết nối SNI. Link localhost trong Telegram mở được trên máy chạy stack; điện thoại cần VPN/tunnel hoặc domain cấu hình riêng.

## Kiểm chứng và recovery

```powershell
.venv/Scripts/python.exe pipeline/verify_monitoring_centre.py
docker compose ps
Invoke-RestMethod http://localhost:18100/health
Invoke-RestMethod http://localhost:18100/ready
```

Verifier monitoring yêu cầu dữ liệu/report/collectors hiện hành; installation rỗng
có thể chưa đủ bằng chứng để pass. Cờ `--send-alert` gửi thông báo thử thật tới
Telegram nếu cấu hình; chỉ thêm khi muốn kiểm tra delivery. `verify_stack.py`
nhận `--dag-run` của run thực tế trên installation, không dùng run ID lịch sử cố định.
Cờ `--inference` và các verifier SaaS/company tạo event demo; chuẩn bị fixtures theo
[README.md](README.md) trước khi chạy.

`pipeline/verify_recovery.py --rollback` là kiểm chứng legacy bundle, không phải
runbook rollback policy Face/Voice hiện hành. Dùng endpoint platform
`POST /v1/admin/lifecycle/{face|voice}/rollback`, rồi kiểm tra lifecycle state,
Registry, readiness và serving; template có endpoint riêng. Xem
[backup/restore/rollback](DEPLOYMENT.md#backup-restore-và-rollback). Không phục hồi
backup đè lên installation đang phục vụ hoặc xóa volumes để xử lý lỗi.

Airflow model DAG có bảy task: snapshot → validate → publish dataset →
calibrate/register → RAI audit → offline gate → lifecycle tick. Không có lịch train
vô điều kiện; monitoring hàng giờ phát intent theo từng modality, service khóa claim
để tránh train trùng. Offline pass chỉ vào challenger/shadow. Canary tăng traffic
5/10/25/50/100%, kiểm tra tối thiểu 1.000 mẫu và 3.600 giây/stage, 30 nhãn/class,
FMR <=1%, FNMR <=5%, không tăng FMR và FNMR tăng tối đa 0,5 điểm phần trăm.
Tham số đầy đủ nằm trong `pipeline/lifecycle_config.json`; thiếu nhãn chờ thêm bằng
chứng. Chỉ stage cuối pass mới chuyển champion, fail giữ champion và lưu audit.
RAI report được sinh trong DAG, nhưng candidate endpoint của lifecycle modality
hiện chưa dùng `REQUIRE_HUMAN_FAIRNESS` để chặn promotion. Cờ này thuộc gate bundle
legacy; cần reviewer kiểm tra RAI thủ công, không coi nó là fairness gate tự động
đã được thực thi trong luồng mới.

Kiểm tra lifecycle bằng `GET /v1/admin/lifecycle/state` với `X-API-Key` platform.
Không ghi key vào log/report. Drift engine dùng PSI chất lượng/score, embedding
MMD², reviewed performance và template cohorts, cần ba cửa sổ mới đủ điều kiện.
Query embedding retention tắt mặc định: thiếu vector/nhãn không có nghĩa model khỏe.
Vòng Evidently 60 giây chỉ là báo cáo; không có trigger train độc lập thứ hai.

## CI/CD GitHub trên repo FSB

Repo `FSB-MSA36HN/DDM501-face-voice-proctoring` triển khai demo bằng runner Ubuntu 24.04 trong WSL với nhãn `self-hosted`, `Linux`, `ddm501-linux-demo`. Runner chạy dưới systemd với tài khoản `ddm501runner`; thư mục work của runner nằm trên ext4 để `actions/checkout` giải nén được. Job sao chép đúng checkout sang `%LOCALAPPDATA%/DDM501/runner-checkouts/<run-id>-<attempt>` trên ổ C rồi gọi `powershell.exe` để dùng Python runtime, Docker Desktop, `.env` và volumes Windows đã có. Hai đường dẫn runtime và checkout root nằm trong systemd drop-in `runtime.conf`. Job chỉ chạy trên `main` sau `quality`, Windows `deployment-preflight` và `containers`; PR không được deploy. Preflight bắt buộc JUnit có ít nhất hai test và không skip/failure/error. `pipeline/deploy_local.ps1` kiểm tra SHA đầy đủ, stage release ngoài OneDrive, build Compose, chờ health và kiểm tra Grafana. Bản cũ chạy trên Windows bị Code Integrity chặn `Runner.Worker.exe` (event 3033/3077), nên không dùng runner đó cho repo FSB.

Push chỉ thay Markdown/`docs/**` bị loại bởi path filter. Khi cần CI cho bản tài
liệu, dùng PR hoặc manual workflow dispatch; bật `deploy=true` trên `main` mới yêu
cầu deploy thủ công. Không suy diễn việc sửa tài liệu hoặc rewrite Git metadata
thành một lần deployment đã thành công.

Sau khi khởi động lại Windows, shortcut trong Startup của người dùng mở Docker Desktop và giữ một phiên `Ubuntu-24.04` chạy nền để systemd đưa runner online. Kiểm tra bằng:

```powershell
docker desktop start
wsl -d Ubuntu-24.04 -u root -- systemctl status actions.runner.FSB-MSA36HN-DDM501-face-voice-proctoring.ddm501-fsb-linux-demo.service --no-pager
```

Nếu WSL báo runner offline, dùng `wsl -d Ubuntu-24.04 -u root -- systemctl restart actions.runner.FSB-MSA36HN-DDM501-face-voice-proctoring.ddm501-fsb-linux-demo.service`. Runtime root của runner đặt trong systemd drop-in `runtime.conf` và trỏ tới repo local giữ `.env`, models, data, reports; không đưa các file này lên GitHub. Các container tutorial cũ đã được dừng và đặt `restart=no` để RAM 6 GB của WSL phục vụ stack chính. Nếu WSL service kẹt sau khi Docker quá tải, dừng Docker Desktop rồi khởi động lại `WslService` bằng quyền quản trị Windows.

## Phạm vi kiểm chứng

Quality chạy Ruff, compile, dashboard consistency, pytest/coverage >=80% và Compose
config. Lệnh coverage trong workflow khai báo chính xác module được đo; không phải
mọi CLI/frontend/Airflow task hoặc model weights. Artifact giữ JUnit và coverage XML.
Local checks chạy bằng `pipeline/ci_local.ps1` sau khi chuẩn bị đúng venv/runtime.

Không lấy kết quả local hoặc preflight làm bằng chứng deployment thật. Xem
[EVIDENCE](docs/EVIDENCE.md) và run GitHub FSB đúng SHA. Hướng dẫn runner Windows
trước 02/10 và version champion cố định đã chuyển khỏi runbook; lịch sử tại
[archive](docs/archive/README.md) và Git history.
