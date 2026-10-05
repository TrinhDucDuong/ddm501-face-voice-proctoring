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

Máy mới: làm theo [README: setup, dependencies và readiness](README.md#cài-đặt-trên-máy-mới).
Compose tạo hạ tầng và tải weights, nhưng không tự tạo champion đã đánh giá trên
registry rỗng. Simulation tạo baseline synthetic riêng và không phụ thuộc champion
production. Với runtime đã bàn giao, giữ `.env`, project name, volumes và artifacts.

```powershell
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 900
docker compose ps
Invoke-RestMethod http://localhost:18100/health
Invoke-RestMethod http://localhost:18100/ready
```

`/ready` = 503 khi thiếu champion không đồng nghĩa Docker bị lỗi. Không bỏ qua gate
hoặc đổi alias tùy ý để làm endpoint xanh. Migration lifecycle yêu cầu incumbent
bundle đã đăng ký; xem [lifecycle](docs/MODALITY_LIFECYCLE.md).

Ứng dụng thi compatibility ở :18600 là tùy chọn. Sau khi có media tại
`data/bootstrap/manifest.json` và dependencies Python, provision bằng
`.venv/Scripts/python.exe pipeline/provision_local_saas.py`; script tạo tenant/keys,
ghi danh và lưu cấu hình riêng tại `data/local-saas.json`. Với `API_KEY` đã tùy chỉnh,
script đọc từ `.env`. Sau đó có thể chạy `pipeline/verify_saas.py` trong môi trường
demo; verifier tạo dữ liệu, không phải kiểm tra chỉ đọc. Portal công ty và simulation
không yêu cầu bước provision compatibility này.

Không chạy `down -v` nếu cần giữ dữ liệu. Portal hiện yêu cầu API key; platform local mặc định `demo-internal-key` nếu `.env` chưa đổi. Airflow/Grafana demo `admin/admin`. Chỉ dùng các mặc định này ở local loopback.

## Image serving không phụ thuộc mount model

```powershell
docker compose build api
docker build -f deploy/Dockerfile.serving -t ddm501-saas-serving:local .
```

Image thứ hai chứa weights pinned đã tải trong `models/`, không chứa `.env`, dataset hay report. Có ghi nhận smoke test không bind mounts ở checkpoint lịch sử 28/09; đây không phải kết quả build lại cho revision hiện tại. Provider có thể cấp biến `PORT`; liveness `/health`, readiness `/ready` (503 nếu chưa có champion). Cấu hình DB, MLflow, artifact endpoint, credentials và signing secrets qua secret manager; `PUBLIC_API_URL` phải là URL HTTPS ngoài internet. Không đưa secrets vào build args/image layers.

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

Overlay tắt endpoint simulation legacy trong API bằng `ENABLE_SIMULATION=false`, yêu cầu HTTPS cho callback và chuyển `legacy-demo` sang profile `demo`. Nó **chưa loại bỏ** các service simulation cách ly, network hay DAG simulation kế thừa từ Compose chính. Cần cấu hình loại bỏ/khóa riêng những thành phần đó trước khi dùng overlay làm installation khách hàng; không coi overlay hiện tại là bản hardening hoàn chỉnh. `OFFLINE_MODE=true` sử dụng weights đã chuyển sẵn và không gọi Hugging Face trong model-init. Build image/dependency hoặc pull image lần đầu vẫn cần internet trừ khi đã chuyển đủ images. Compose init MLflow/create-buckets hiện có pip bootstrap: triển khai air-gapped hoàn toàn cần đóng gói thêm các image này; chưa được xác nhận air-gap full stack.

Tạo tenant/key riêng bằng platform portal. Default training chỉ dùng tenant `demo`, không tự dùng dữ liệu khách hàng mới. `pipeline/data_snapshot.py` hiện từ chối `TRAINING_TENANT_ID` khác `demo`. Muốn calibrate dữ liệu khách cần thỏa thuận sử dụng dữ liệu, bổ sung scope/consent enforcement và kiểm thử isolation; đổi biến môi trường đơn lẻ chưa đủ. Shared policy không đồng nghĩa được phép dùng chung dữ liệu khách hàng.

## Backup, restore và rollback

- Backup PostgreSQL trước migration. Backup local cũ có thể không tồn tại trên clone mới; tạo và kiểm tra backup của chính installation cần nâng cấp, không dùng đường dẫn lịch sử như một bảo đảm phục hồi.
- Backup PostgreSQL + MinIO/artifacts + pinned weights + secrets/config ở kho riêng; kiểm tra restore vào một database/môi trường mới trước, không restore đè khi hệ thống đang phục vụ.
- Migration SaaS chỉ thêm bảng/cột và gán hồ sơ cũ vào tenant `demo`; có regression test chạy hai lần và giữ nguyên dữ liệu.
- Rollback policy: gọi `POST /v1/admin/lifecycle/face/rollback` hoặc `POST /v1/admin/lifecycle/voice/rollback` bằng platform key trong header `X-API-Key`. Khi đang shadow/canary/promotion, endpoint dừng rollout và giữ champion; sau promotion, phục hồi `previous_version` nếu có. Endpoint phối hợp trạng thái PostgreSQL với MLflow, nên không chỉ sửa alias bằng giao diện MLflow hoặc gọi reload bundle cũ. Thiếu lifecycle trả 404; không có phiên bản trước có thể trả 409. Kiểm tra `GET /v1/admin/lifecycle/state`, Registry, `/ready` và request xác minh với dữ liệu được phép sau khi rollback.
- Rollback template: `POST /v1/admin/lifecycle/templates/{person_id}/{face|voice}/rollback` với platform key chuyển con trỏ sang phiên bản trước và giữ audit/dữ liệu ghi danh. Không có phiên bản trước trả 409. Template rollback sau activation là thao tác operator, chưa có tự động theo dõi để rollback template.
- Rollback application: triển khai image digest/release trước đó, giữ DB volumes; đánh giá tương thích schema. Không có auto-rollback production trong bản môn học.
- Worker bị dừng: deliveries vẫn nằm trong DB, xử lý lại khi khởi động. Receiver phải deduplicate vì có thể crash sau khi gửi thành công nhưng trước khi commit.

Canary policy có rollback tự động khi gate phát hiện regression: đặt challenger
traffic = 0, champion giữ nguyên, lưu failure evidence và model thất bại trong MLflow.
Đánh giá nhãn đến muộn diễn ra theo monitoring tick hàng giờ. Gate thiếu nhãn chờ
thêm dữ liệu; không tự thông qua. Promotion cuối dùng durable PROMOTING intent và
reconciliation để phục hồi khi thao tác Registry bị gián đoạn. Đây không phải
auto-rollback image/application hay bằng chứng đã rollout bằng nhãn production.

Reset simulation dùng nút **Restore demo baseline**, không dùng các endpoint
rollback production và không xóa volumes. Xem [SIMULATION.md](docs/SIMULATION.md).

## CI/CD và bằng chứng

Workflow hiện hành là [.github/workflows/ci.yml](.github/workflows/ci.yml):

| Job | Runner | Điều kiện và bằng chứng |
|---|---|---|
| `quality` | GitHub-hosted Ubuntu, Python 3.11 | Ruff, compile, dashboard consistency, pytest/coverage >=80% trong phạm vi khai báo, Compose config; artifact `quality-evidence` |
| `deployment-preflight` | GitHub-hosted Windows, Python 3.11 | Test stage exact SHA/reject mismatch với runtime tạm; JUnit phải có ít nhất hai test, không skip/failure/error; artifact `deployment-preflight-evidence` |
| `containers` | GitHub-hosted Ubuntu | Chờ cả quality và preflight; build service images, bao gồm simulation |
| `deploy-demo` | `self-hosted`, `Linux`, `ddm501-linux-demo` | Chờ build; eligible push `main` hoặc manual dispatch trên `main` với `deploy=true`; environment `demo`, concurrency một deployment; artifact `deployment-monitoring-evidence` |

Runner deploy là Ubuntu trong WSL, gọi PowerShell Windows để dùng Docker Desktop
và Python runtime. Biến `DDM501_RUNTIME_ROOT` và `DDM501_WINDOWS_CHECKOUT_ROOT`
phải được cấu hình trên runner; runtime có `.env`, `.venv`, models/data/reports.
Job bridge checkout theo run sang Windows, kiểm tra SHA đầy đủ rồi stage source
ngoài OneDrive; giữ secrets và named volumes. Không yêu cầu workflow chứa credentials.
PR không chạy deploy trên runner local. Các push chỉ thay Markdown hoặc `docs/**`
không kích hoạt workflow tự động; PR và manual dispatch vẫn có thể kiểm chứng.

App deployment là thay container trên một Docker Compose host, có thể có gián đoạn;
không có application canary, load balancer đa replica hay Kubernetes. Canary
Face/Voice là lựa chọn threshold policy trong API qua lifecycle state. Windows
preflight không thay thế deploy thật; job xanh chỉ chứng minh các bước job đã chạy,
không chứng minh hiệu năng biometric trên người thật. Setup runner theo
[OPERATIONS.md](OPERATIONS.md); link và kết quả theo phiên bản tại
[EVIDENCE](docs/EVIDENCE.md). `pipeline/ci_local.ps1` là kiểm tra local riêng.

Không thể thay thế phần yêu cầu thành viên có meaningful commits, quyền giảng viên và bài thuyết trình bằng code tự sinh. Xem DEMO_PRESENTATION.md và RUBRIC_MAPPING.md.
