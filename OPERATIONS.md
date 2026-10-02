# Vận hành: Grafana, Telegram và CI/CD

## Current company service

Customer business results use API and integrity.checked webhook; platform Telegram receives only technical alerts. Company admins use portal history/evidence/reports. Extra Grafana panels expose aggregate batch outcomes, detector readiness and evidence writes. Detector readiness reflects last execution; missing/short captures may mark capability unavailable/not assessed. No per-company Telegram. Demo registration enabled by default on loopback; disable for production.


## Trang monitoring chính

Mở http://localhost:13000/d/biometric-overview, đăng nhập Grafana `admin` / `admin` ở demo loopback. Portal đưa một link monitoring tới Grafana; các link Airflow/MLflow/MinIO phục vụ quản trị pipeline.

Dashboard có bảy nhóm: service/alerts; data quality; drift/Evidently; Registry/evaluation/explainability; sessions/review/webhooks; Airflow/RAI/freshness; infrastructure/logs. Bộ chọn tenant áp dụng cho SQL; project/service áp dụng cho container/logs. Grafana là trang quản trị toàn nền tảng, không cung cấp tài khoản này cho tenant khách hàng.

Report cùng origin `/reports/<name>.html` và `.json`: `data-drift`, `model-performance`, `synthetic-performance`, `data-quality`, `model-evaluation`, `pipeline-status`, `responsible-ai`, `alerts`. Nginx kiểm tra phiên đăng nhập qua Grafana `/api/user`; anonymous nhận 401/403. Các endpoint Prometheus/Airflow/MLflow tiếp tục dùng nội bộ.

## Nguồn dữ liệu

| Nguồn | Nội dung |
|---|---|
| API / webhook-worker | Requests, decisions, latency, outbox, delivery |
| drift-monitor | PSI/Evidently drift; classification từ reviewed events |
| ops-monitor | DB validation, Registry, DAG/tasks, RAI, readiness, Docker stats, Telegram |
| PostgreSQL datasource | Events, quality, enrollment, sessions, review queue, audit |
| Alloy → Loki | Docker logs lọc Compose project, retention 7 ngày |
| Prometheus / Alertmanager | Scrape freshness và alert groups |

CPU/RAM/network/block IO lấy qua Docker API read-only proxy. Review queue chỉ lấy `verify_sessions.status='review'`; event có `accepted=false` đã xử lý không được tính pending review. Khi dữ liệu hết freshness, kiểm tra collector trước khi dùng kết quả cũ.

## Human và synthetic performance

`model-performance` dùng reviewer khác `synthetic-simulation`; `synthetic-performance` dùng reviewer đó. Hai cửa sổ thời gian không giao nhau, mỗi cửa sổ `PERFORMANCE_WINDOW_SIZE` feedback, phải có cả genuine và impostor. Nếu thiếu nhãn human, báo cáo chờ và metrics NaN.

`biometric_reviewed_performance{source,metric,window}` có accuracy/precision/recall/F1/FAR/FRR. `biometric_reviewed_report_success{source}` biểu thị tính hợp lệ. Positive là genuine. REVIEW được tính là không accept. Đây là performance trên reviewed subset, có selection bias.

Tạo kịch bản kỹ thuật: `python pipeline/simulate_drift.py --samples 100 --with-feedback`. Reference được thiết kế đúng và current cố tình sai. Alert `BiometricSyntheticPerformanceDegraded` có `evidence=synthetic_demo`; không trình bày như human accuracy. Human alert giữ tên `BiometricPerformanceDegraded`.

## Telegram

Bot: `@ddm501_face_voice_proctoring_bot`. `.env` giữ `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`; không đưa vào code/logs/commit. Luồng: Prometheus → Alertmanager → ops-monitor `/alerts` → Telegram. Gửi cả firing/resolved. Lỗi gửi trả 503 để Alertmanager retry.

`python pipeline/verify_telegram.py` gửi tin thử trực tiếp. `python pipeline/verify_monitoring_centre.py --send-alert` kiểm tra Alertmanager và lưu `reports/monitoring-verification.json`. Transport xác minh TLS/CA/hostname; có fallback tới IP chính thức khi mạng reset kết nối SNI. Link localhost trong Telegram mở được trên máy chạy stack; điện thoại cần VPN/tunnel hoặc domain cấu hình riêng.

## Kiểm chứng và recovery

```powershell
python pipeline/verify_stack.py --dag-run isolated_holdout_20260928 --inference --require-alerts
python pipeline/verify_monitoring_centre.py --send-alert
python pipeline/verify_saas.py
python pipeline/verify_recovery.py --rollback
```

Inference/SaaS tạo thêm event demo. Recovery lưu dump dưới `data/backups/`; restore vào DB tạm riêng, so sánh row counts rồi xóa DB tạm. `--rollback` đổi champion trong thời gian ngắn, reload/readiness rồi phục hồi champion ban đầu trong `finally`. Khi dùng thật phải điều phối traffic.

Airflow: snapshot → validate → identity evaluation/register → RAI audit → gate → reload. Calibration/CV/holdout FAR và FRR phải ≤20% ở demo; snapshot candidate phải khớp run. `REQUIRE_HUMAN_FAIRNESS=true` chặn cả insufficient evidence.

## CI/CD GitHub trên repo FSB, 02/10/2026

Repo `FSB-MSA36HN/DDM501-face-voice-proctoring` triển khai demo bằng runner Ubuntu 24.04 trong WSL với nhãn `self-hosted`, `Linux`, `ddm501-linux-demo`. Runner chạy dưới systemd với tài khoản `ddm501runner`; thư mục work của runner nằm trên ext4 để `actions/checkout` giải nén được. Job sao chép đúng checkout sang `%LOCALAPPDATA%/DDM501/runner-checkouts/<run-id>-<attempt>` trên ổ C rồi gọi `powershell.exe` để dùng Python runtime, Docker Desktop, `.env` và volumes Windows đã có. Hai đường dẫn runtime và checkout root nằm trong systemd drop-in `runtime.conf`. Job chỉ chạy trên `main` sau `quality` và `containers`; PR không được deploy. `pipeline/deploy_local.ps1` kiểm tra SHA đầy đủ, stage release ngoài OneDrive, build Compose, chờ health và kiểm tra Grafana. Bản cũ chạy trên Windows bị Code Integrity chặn `Runner.Worker.exe` (event 3033/3077), nên không dùng runner đó cho repo FSB.

Sau khi khởi động lại Windows, shortcut trong Startup của người dùng mở Docker Desktop và giữ một phiên `Ubuntu-24.04` chạy nền để systemd đưa runner online. Kiểm tra bằng:

```powershell
docker desktop start
wsl -d Ubuntu-24.04 -u root -- systemctl status actions.runner.FSB-MSA36HN-DDM501-face-voice-proctoring.ddm501-fsb-linux-demo.service --no-pager
```

Nếu WSL báo runner offline, dùng `wsl -d Ubuntu-24.04 -u root -- systemctl restart actions.runner.FSB-MSA36HN-DDM501-face-voice-proctoring.ddm501-fsb-linux-demo.service`. Runtime root của runner đặt trong systemd drop-in `runtime.conf` và trỏ tới repo local giữ `.env`, models, data, reports; không đưa các file này lên GitHub. Các container tutorial cũ đã được dừng và đặt `restart=no` để RAM 6 GB của WSL phục vụ stack chính. Nếu WSL service kẹt sau khi Docker quá tải, dừng Docker Desktop rồi khởi động lại `WslService` bằng quyền quản trị Windows.

## CI/CD GitHub trước 02/10 (lịch sử)

**Tình trạng 01/10/2026:** job `quality` và `containers` trên GitHub-hosted runner qua, nhưng `deploy-demo` trên máy này chưa thể chạy tự động: Windows Code Integrity chặn `Runner.Worker.dll` vì không đạt Enterprise signing policy (`0x800711C7`). Chuyển runner ra ngoài OneDrive không giải quyết được. Không tắt chính sách này; cần IT cho phép binary runner hoặc dùng runner Windows đã được phê duyệt. Cho đến khi đó, triển khai local bằng `pipeline/prepare_runner_env.py --stage-deployment` và `docker compose up -d --build`, sau đó chạy `pipeline/verify_stack.py`. Xem kết quả trong `VERIFICATION.md`.

Quality chạy Ruff, compile, dashboard consistency, pytest + coverage ≥80% và Compose config. Coverage gồm toàn `app`, toàn `monitoring`, `pipeline.evaluation`, `data_snapshot`, `validate_data`, `promotion_gate`, `responsible_ai_report`; không phải toàn repository. CLI/frontend/Airflow/weights có live verification riêng. Artifact `quality-evidence` giữ JUnit/coverage XML.

Container build dùng GitHub-hosted Ubuntu. Deploy trusted `main` dùng runner Windows `ddm501-local-windows`, labels `self-hosted`, `Windows`, `ddm501-demo`. Environment `demo` giới hạn main. PR không chạy trên runner local. Concurrency bảo đảm một deploy.

Runner ở `data/github-runner` (gitignored), chạy hidden. `DDM501_RUNTIME_ROOT` trỏ repo runtime ban đầu. `prepare_runner_env.py --stage-deployment` xuất đúng commit bằng Git archive vào `%LOCALAPPDATA%/DDM501/deployments/<sha>` ngoài OneDrive; các relative binds cấu hình/DAG/source dùng release này. Script giữ secrets/project name/DB volumes và absolute paths models/data/reports/logs; không overwrite runtime `.env` bằng `.env.example`. Không xóa release đang được container mount. Cách này xử lý lỗi file bind trong checkout OneDrive mà Docker Desktop không đọc được, dù Windows đọc được.

Deploy sử dụng `.venv/Scripts/python.exe` trong runtime đã kiểm chứng, có `python-dotenv` và `requests`; quality dùng Python 3.11 trên Ubuntu. Cách này tránh script cài Python bị execution policy của Windows chặn, không đổi policy hệ thống.

Các bước PowerShell của job dùng `-ExecutionPolicy Bypass` trong riêng process chạy script workflow; exit code Python/Docker được kiểm tra rõ ràng. Không thay policy ở mức máy/người dùng.

Sau khi binary runner được chính sách máy cho phép, khởi động lại runner sau reboot từ repo runtime:

```powershell
$env:DDM501_RUNTIME_ROOT = (Get-Location).Path
Start-Process cmd.exe -ArgumentList '/c','run.cmd' -WorkingDirectory data/github-runner -WindowStyle Hidden
```

Runner theo phiên người dùng, chưa cài Windows service. CI URL/kết quả thực tế ở `VERIFICATION.md`. Local checks: `powershell -ExecutionPolicy Bypass -File pipeline/ci_local.ps1` sau khi activate venv.
