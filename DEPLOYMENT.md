# Triển khai local, PaaS và private/on-premise

## Maintenance deployment

API image now includes Unicode PDF fonts, ONNX runtime and pretrained integrity wrappers. Portable serving image packages minifasnet_v2.onnx and aasist.pth alongside identity weights. download_models.py pins revisions/checksums. Suspicious evidence uses MinIO even when STORE_RAW_BIOMETRICS=false (that flag concerns raw enrollment). Preserve volumes and allow additive migration of outbox session_id to nullable.


## Quyết định kiến trúc

SaaS là mô hình cung cấp sản phẩm; PaaS là cách vận hành container. Local Docker Compose mô phỏng sự phân tách này, không được gọi là đã deploy lên public cloud. Private/on-premise là một installation riêng cùng code/API contract cho từng khách hàng.

| Service | Local/private | Khi chuyển PaaS |
|---|---|---|
| Verification API + hosted page | API container, CPU pretrained | Container service có HTTPS, warm instances, model weights trong image |
| Portal | Streamlit container | Container/web service, giữ cùng API contract |
| PostgreSQL | Named volume | Managed PostgreSQL, backup/HA tùy SLA |
| Webhook worker | Process/container polling outbox | Always-on worker; không đặt vòng lặp này vào request-only FaaS |
| MLflow/artifacts | MLflow + MinIO | Private tracking service + object storage |
| Airflow | Scheduler/webserver | Private orchestration service, tách khỏi request-serving |
| Monitoring | Prometheus/Grafana/Evidently/Alertmanager | Private managed hoặc self-hosted monitoring |

API/session/outbox state nằm trong DB, không dùng RAM process để làm nguồn dữ liệu chính. Model cache là per-process; test concurrency trước khi tăng replicas. Không expose PostgreSQL, MinIO, MLflow, Airflow hoặc Prometheus cho người dùng internet.

## Local course/demo

```powershell
docker compose up -d --build
python pipeline/provision_local_saas.py
python pipeline/verify_saas.py
powershell -File pipeline/ci_local.ps1
```

Không chạy `down -v` nếu cần giữ dữ liệu. Portal hiện yêu cầu API key; platform local mặc định `demo-internal-key` nếu `.env` chưa đổi. Airflow/Grafana demo `admin/admin`. Chỉ dùng các mặc định này ở local loopback.

## Image serving không phụ thuộc mount model

```powershell
docker compose build api
docker build -f deploy/Dockerfile.serving -t ddm501-saas-serving:local .
```

Image thứ hai chứa weights pinned đã tải trong `models/`, không chứa `.env`, dataset hay report. Đã smoke-test local không có bind mounts. Provider có thể cấp biến `PORT`; liveness `/health`, readiness `/ready` (503 nếu chưa có champion). Cấu hình DB, MLflow, artifact endpoint, credentials và signing secrets qua secret manager; `PUBLIC_API_URL` phải là URL HTTPS ngoài internet. Không đưa secrets vào build args/image layers.

Môi trường PaaS thật còn cần chọn region, sizing và nhà cung cấp, thiết lập mạng/secret manager/TLS và load-test theo lịch thi. Chưa provision tài nguyên cloud trả phí trong project này.

## Private/on-premise

1. Cài Docker/Compose trên máy khách; chuyển repository, images và pinned model weights. Chọn project name riêng để tách volumes.
2. Tạo `.env.private` từ `.env.example`; thêm `ENV_FILE=.env.private`. Đổi toàn bộ credentials, set independent `SESSION_SIGNING_KEY`, `WEBHOOK_MASTER_KEY` (ít nhất 32 ký tự ngẫu nhiên), URL HTTPS và callback allowlist. Đảm bảo URL kết nối DB đồng bộ với password.
3. Thiết lập TLS reverse proxy do khách quản lý tới API :18100 và portal :18501; monitoring chỉ mở qua VPN/SSO. Camera/microphone cần secure browser context; localhost là trường hợp demo.
4. Chạy:

```powershell
docker compose --env-file .env.private -f docker-compose.yml -f deploy/compose.private.yml config --quiet
docker compose --env-file .env.private -f docker-compose.yml -f deploy/compose.private.yml up -d --build
```

Overlay tắt simulation, yêu cầu HTTPS cho callback, không tự chạy legacy simulator. `OFFLINE_MODE=true` sử dụng weights đã chuyển sẵn và không gọi Hugging Face trong model-init. Build image/dependency hoặc pull image lần đầu vẫn cần internet trừ khi đã chuyển đủ images. Compose init MLflow/create-buckets hiện có pip bootstrap: triển khai air-gapped hoàn toàn cần đóng gói thêm các image này; chưa được xác nhận air-gap full stack.

Tạo tenant/key riêng bằng platform portal. Default training chỉ dùng tenant `demo`, không tự dùng dữ liệu khách hàng mới. Muốn calibrate từ dữ liệu khách phải có thỏa thuận và cấu hình `TRAINING_TENANT_ID` rõ ràng; shared default model không đồng nghĩa chia sẻ dữ liệu khách.

## Backup, restore và rollback

- Backup PostgreSQL trước migration. Lần nâng cấp SaaS đã lưu `data/backups/pre-saas-20260927.dump`, không xóa dữ liệu cũ.
- Backup PostgreSQL + MinIO/artifacts + pinned weights + secrets/config ở kho riêng; kiểm tra restore vào một database/môi trường mới trước, không restore đè khi hệ thống đang phục vụ.
- Migration SaaS chỉ thêm bảng/cột và gán hồ sơ cũ vào tenant `demo`; có regression test chạy hai lần và giữ nguyên dữ liệu.
- Rollback model: mở MLflow, chọn version đã được đánh giá và chuyển alias `champion`; gọi `POST /v1/admin/reload-model` bằng platform key rồi kiểm tra `/ready`/`/health` và một request verify. Không thay model chỉ để bỏ qua promotion gate.
- Rollback application: triển khai image digest/release trước đó, giữ DB volumes; đánh giá tương thích schema. Không có auto-rollback production trong bản môn học.
- Worker bị dừng: deliveries vẫn nằm trong DB, xử lý lại khi khởi động. Receiver phải deduplicate vì có thể crash sau khi gửi thành công nhưng trước khi commit.

## CI/CD và bằng chứng

GitHub Actions: lint → tests/coverage ≥80% trên phạm vi được khai báo → build trên Ubuntu → deploy `main` trên runner `self-hosted, Windows, ddm501-demo` → kiểm chứng Grafana. Runner dùng Python của runtime, xuất đúng Git commit sang release ngoài OneDrive để Docker đọc được binds; giữ secrets, named volumes và models/data/reports. Environment `demo` giới hạn main; PR không chạy trên máy local. `pipeline/ci_local.ps1` là kiểm tra local riêng. Setup theo [OPERATIONS.md](OPERATIONS.md); link và kết quả run thực tế ở [VERIFICATION.md](VERIFICATION.md).

Không thể thay thế phần yêu cầu thành viên có meaningful commits, quyền giảng viên và bài thuyết trình bằng code tự sinh. Xem DEMO_PRESENTATION.md và RUBRIC_MAPPING.md.
