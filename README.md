# DDM501 - Face & Voice Integrity Service

Dịch vụ xác minh face/voice theo batch cho doanh nghiệp tổ chức kỳ đánh giá ngoại ngữ thường niên. Công ty giữ hệ thống thi, lịch capture, điểm và quyết định nghiệp vụ. Dự án cung cấp API/webhook, portal công ty và full pipeline MLOps.

Repository chính thức: [FSB-MSA36HN/DDM501-face-voice-proctoring](https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring), nhánh `main`. Theo dõi [GitHub Actions của FSB](https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring/actions) để xem trạng thái CI/CD theo đúng commit.

## Hai không gian vận hành

- Công ty: đăng ký gói giả lập, quản lý nhân viên, ghi danh qua camera/audio/upload hoặc API, integration keys, webhook, lịch sử, bằng chứng nghi vấn và PDF/CSV.
- Nền tảng: Airflow/MLflow/CI-CD cùng Grafana/Evidently/Telegram. Company portal chỉ có dữ liệu và chức năng của công ty đó.

## Demo và API

Portal http://localhost:18501; customer example http://localhost:18600; API http://localhost:18100/docs.
Grafana http://localhost:13000/d/biometric-overview; Airflow http://localhost:18081; MLflow http://localhost:15030; MinIO http://localhost:19101.

Trong **Vận hành MLOps**, **MLflow production** (`:15030`) hiển thị policy phục vụ Face/Voice; **MLflow simulation** (`:15031`) hiển thị các model của demo drift/promotion/rollback. Hai registry cách ly, nên model simulation không xuất hiện trong production. Grafana **System Overview** hiện có 10 panel chính và link tới báo cáo chi tiết; [Simulation dashboard](http://localhost:13000/d/biometric-simulation) có 10 panel riêng cho dữ liệu tổng hợp; nếu vẫn thấy dashboard cũ, kiểm tra job `deploy-demo` đã thành công trên đúng commit rồi tải lại trang. Grafana và Airflow có trang đăng nhập riêng.

Đăng ký công ty tại portal, lưu operator key được trả một lần. Ghi danh >=2 ảnh/WAV, cấp integration key và cấu hình webhook. Backend gọi POST /v1/checks với person_id, session_id, request_id, consent, face_file và voice_file. Nhịp 30 giây và WAV 10 giây là ví dụ do khách hàng cấu hình.

## Model và dữ liệu

Quản trị nền tảng có trang **Simulation MLOps** với ba nút: drift dẫn tới promotion, canary lỗi dẫn tới rollback, và khôi phục baseline demo. Simulation dùng network/database/MLflow riêng, dữ liệu và nhãn tổng hợp; xem [hướng dẫn và giới hạn](docs/SIMULATION.md). MLflow simulation: http://localhost:15031.

SFace/YuNet + ECAPA pretrained xác minh danh tính. Pipeline chỉ hiệu chỉnh ngưỡng riêng `face-verification` / `voice-verification`, không train lại weights encoder. `face-voice-risk-bundle` là bundle legacy còn giữ cho compatibility/bootstrap incumbent. MiniFASNet face PAD và AASIST audio anti-spoof là detector nghiên cứu pretrained/pinned. ECAPA segments là heuristic thay người nói. Missing detector trả inconclusive. Chưa có benchmark khách hàng cho mọi deepfake, physical replay hoặc simultaneous voices.

PostgreSQL lưu embedding/metadata/checks/review; MinIO lưu suspicious evidence, MLflow artifacts và các snapshot feature/nhãn có phiên bản cho MLOps. Raw enrollment và media check hợp lệ không được giữ mặc định. Lịch sử, exports và evidence downloads đều tenant-scoped. Webhook HMAC có durable outbox/retry; receiver phải deduplicate.

Airflow có hai DAG phục vụ lifecycle chính: monitoring mỗi giờ và hiệu chỉnh ngưỡng theo yêu cầu riêng Face/Voice; DAG `biometric_simulation` riêng nhận job demo. Source hiện có decision engine nhiều tầng, template có phiên bản và luồng `candidate → offline → challenger → shadow → canary → champion/rollback`; drift thống kê đơn lẻ không kích hoạt train. Xem [lifecycle và giới hạn thực tế](docs/MODALITY_LIFECYCLE.md), [Continuous MLOps](docs/CONTINUOUS_MLOPS.md) và [simulation](docs/SIMULATION.md). Simulation dùng dữ liệu tổng hợp, không phải bằng chứng rollout bằng dữ liệu production. Đối chiếu kết quả CI/deploy trên Actions của FSB theo đúng SHA, không dùng run của repository trước khi chuyển làm kết quả cho bản hiện tại.

## Cài đặt trên máy mới

Các lệnh dưới đây dùng PowerShell, chạy tại root repository. Trên Linux/macOS dùng Python 3.11 và Docker Engine/Desktop với Compose v2; thay đường dẫn `.venv/Scripts/python.exe` bằng `.venv/bin/python`.

Chuẩn bị Git, Docker Desktop chạy Linux containers (Windows cần WSL2), Docker Compose v2 và Python 3.11 nếu chạy script/test ngoài container. Lần đầu cần internet để tải images, dependencies và model weights; cần dung lượng đĩa cho các thành phần này và dữ liệu. Nên dành ít nhất 8 GB RAM cho Docker ở máy demo, tăng nếu tải model/build bị OOM; đây là khuyến nghị, không phải kết quả benchmark 50.000 nhân viên. Camera/microphone cần localhost hoặc HTTPS và quyền trình duyệt.

```powershell
git clone https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring.git
cd DDM501-face-voice-proctoring
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
New-Item -ItemType Directory -Force models, data, reports, airflow/logs | Out-Null
docker version
docker compose version
docker compose config --quiet
docker compose up -d --build --wait --wait-timeout 900
docker compose ps
Invoke-RestMethod http://localhost:18100/health
```

Chọn thư mục checkout ngoài OneDrive để tránh lỗi bind mount trên Docker Desktop. `model-init` tải weights pinned; API chỉ khởi động sau khi bước này thành công. Nếu tải chậm/lỗi, xem `docker compose logs --tail 100 model-init api airflow-init`; không xóa volumes để thử lại.

### Repository và remote Git

Bản clone mới ở trên có `origin` trỏ tới FSB. Với checkout đã có remote `fsb`, dùng rõ tên remote để tránh fetch/push nhầm:

```powershell
git remote -v
git fetch fsb
git push fsb HEAD:main
```

Chỉ push sau khi kiểm tra thay đổi, commit và hoàn tất review theo [CONTRIBUTING.md](CONTRIBUTING.md). Nếu clone mới chỉ có `origin` trỏ FSB, thay `fsb` bằng `origin` trong các lệnh trên. Script `pipeline/github_ci.py` ưu tiên `fsb`, chỉ dùng `origin` khi không có `fsb`, và kiểm tra URL thuộc repository FSB trước khi đọc credentials hoặc gọi GitHub API. Không cần đổi remote cá nhân để dùng remote FSB.

Chỉnh `.env` trước khi dùng ngoài demo loopback: đổi credentials và `API_KEY`, đặt `SESSION_SIGNING_KEY`, `WEBHOOK_MASTER_KEY`, `SIMULATION_SERVICE_KEY`, đồng bộ password trong các URL DB/S3. Telegram là tùy chọn. Không commit `.env`. Với môi trường đã có dữ liệu, **giữ nguyên `.env`, Compose project name và volumes**; xem [vận hành](OPERATIONS.md) và [triển khai](DEPLOYMENT.md), không chạy lại setup như một installation mới.

### Champion ban đầu và readiness

`/health` xác nhận dịch vụ hoạt động; `/ready` còn kiểm tra champion. Registry rỗng có thể trả `/ready` = 503 dù Compose báo healthy, vì healthcheck của container dùng `/health`. Bản hiện tại chưa có quy trình một lệnh để đánh giá và khởi tạo champion thật từ installation rỗng. API có ngưỡng `local-default`; không coi đó là model đã qua đánh giá.

Để tiếp tục lifecycle thật của bản demo đã bàn giao, phục hồi **bản backup được cấp quyền** gồm PostgreSQL, MLflow/MinIO artifacts và cấu hình/weights tương ứng vào môi trường riêng, rồi kiểm tra `/ready`. Không commit hoặc tải công khai backup. Khi có incumbent bundle đã đăng ký, endpoint platform `POST /v1/admin/lifecycle/bootstrap` (Airflow monitoring cũng gọi) chuyển sang hai policy Face/Voice; endpoint này không đánh giá một model mới và sẽ từ chối nếu chỉ có `local-default`. Xem [giới hạn và migration](docs/MODALITY_LIFECYCLE.md).

Simulation trên portal tự tạo baseline **tổng hợp trong registry riêng**, nên có thể demo lifecycle mà không khởi tạo champion production. Không dùng baseline simulation thay cho model phục vụ khách hàng.

### Python dependencies và kiểm tra local

Dockerfile cài dependencies theo service; không cần cài tất cả lên host để dùng portal. Nếu chạy script hoặc phát triển:

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.venv/Scripts/python.exe -m ruff check api pipeline monitoring tests legacy_demo
.venv/Scripts/python.exe -m pytest -q
```

| File | Phạm vi |
|---|---|
| `requirements.txt` | Tổng hợp API, pipeline và monitoring; không phải toàn bộ runtime |
| `requirements-api.txt` | FastAPI, DB/S3 client, OpenCV, ONNX, MLflow |
| `requirements-pipeline.txt` | Tải dataset, xử lý audio, pipeline |
| `requirements-monitoring.txt` | Evidently, exporters và collectors |
| `requirements-ui.txt` | Streamlit portal |
| `requirements-dev.txt` | Pytest, coverage, Ruff và UI cho kiểm thử |
| `requirements-models.txt` | SpeechBrain; Dockerfile API cài thêm CPU `torch==2.7.0`, `torchaudio==2.7.0` |
| `requirements-airflow.txt` | Dependencies bổ sung cho image Airflow 2.10.5/Python 3.11; cài trong image riêng để giữ tương thích |
| `requirements-docs.txt` | Sinh PowerPoint/PDF |

Inference pretrained trên host còn cần torch/torchaudio CPU, `requirements-models.txt`, weights và thư viện hệ điều hành tương ứng; ưu tiên image `api/Dockerfile` đã khai báo chúng. Không gộp dependencies Airflow vào venv ứng dụng. Ubuntu có thể skip test chỉ dành cho Windows; CI có job Windows riêng bắt buộc thực thi các test đó.

## Hướng dẫn sử dụng

1. Mở portal `http://localhost:18501`. Đăng ký công ty thử nghiệm, lưu operator key được hiển thị một lần rồi đăng nhập. Platform administrator dùng `API_KEY` trong cấu hình riêng của installation.
2. Tạo nhân viên, ghi danh ít nhất hai ảnh và hai WAV hợp lệ bằng capture/upload hoặc link tự ghi danh. Portal hiển thị trạng thái đủ mẫu; chỉ dùng dữ liệu có sự đồng ý.
3. Tạo integration key trong **API & Webhook**, cấu hình callback. Backend công ty gọi `POST /v1/checks` với header `X-API-Key` và multipart gồm `person_id`, `session_id`, `request_id`, `consent=true`, `face_file`, `voice_file`. Xem schema/thử request tại `http://localhost:18100/docs` và [hợp đồng tích hợp](SAAS_INTEGRATION.md).
4. Đọc `verified` / `suspicious` / `inconclusive`, reason codes và phiên bản policy; xem lịch sử, bằng chứng được phép truy cập và tải PDF/CSV trên portal. Backend nhận webhook HMAC, phải kiểm tra chữ ký và deduplicate. Công ty tự quyết định nghiệp vụ.
5. Để trình diễn tự động hóa, đăng nhập platform, mở **Simulation MLOps**, chọn Face/Voice rồi chạy một trong hai kịch bản. Xem alert, drift, offline, shadow, canary và kết quả; xuất JSON trước/sau **Restore demo baseline**. Hướng dẫn chi tiết tại [SIMULATION.md](docs/SIMULATION.md).

### Kiểm chứng và dữ liệu demo tùy chọn

Trên installation đã có dữ liệu/Registry, `.venv/Scripts/python.exe pipeline/verify_monitoring_centre.py` kiểm tra dashboard, reports và độ mới collectors; stack mới thiếu dữ liệu có thể chưa đủ điều kiện pass. Script không dùng cờ `--send-alert` sẽ không chủ động gửi alert thử.

Kiểm chứng tích hợp công ty cần `data/bootstrap/DEMO-001` và `DEMO-002`, model sẵn sàng, `legacy-demo` chạy và demo registration bật. Tạo media fixture tùy chọn:

```powershell
.venv/Scripts/python.exe pipeline/bootstrap_demo.py --identities 10 --samples 3
.venv/Scripts/python.exe pipeline/verify_company_service.py
```

Bootstrap tải các dataset công khai pinned (cần quyền truy cập/license phù hợp), ghép face/voice tổng hợp và không chứng minh hai modality thuộc cùng một người. Verifier tạo tenant, key, nhân viên, checks, callbacks và reports trong installation đang trỏ tới; chỉ chạy trên môi trường demo. Nó kiểm tra tích hợp, không chứng minh biometric accuracy. Simulation ba nút không cần bộ media này.

`http://localhost:18600` là ứng dụng thi compatibility, cần provision tenant riêng và `data/local-saas.json`; xem [triển khai](DEPLOYMENT.md). Không bắt buộc dùng ứng dụng đó để chạy portal hoặc simulation.

## Containers và CI/CD

Repository dùng nhiều Dockerfile theo service: `api/Dockerfile`, `ui/Dockerfile`, `airflow/Dockerfile`, `monitoring/Dockerfile`, `legacy_demo/Dockerfile`; `deploy/Dockerfile.serving` đóng gói thêm weights cho image portable. `docker-compose.yml` chỉ rõ build context/Dockerfile, healthchecks, dependencies, networks và volumes. Không có Dockerfile tổng ở root; dùng `docker compose build` hoặc `docker build -f api/Dockerfile .`.

CI tách `quality` (Ubuntu, unit tests/coverage) và `deployment-preflight` (Windows, hai test staging/reject SHA với runtime tạm, không cần secrets hoặc Docker daemon). Job Windows phải có JUnit không skip; `containers` chờ cả hai job trước khi `deploy-demo` được phép chạy. Preflight không thay thế kiểm chứng deploy thật qua WSL runner và Docker Desktop. Xem [workflow](.github/workflows/ci.yml), [hướng dẫn triển khai](DEPLOYMENT.md) và run tương ứng trên [Actions FSB](https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring/actions).

## Tài liệu

Bắt đầu tại [mục lục tài liệu hiện hành](docs/README.md). Các hướng dẫn chính:
[kiến trúc](ARCHITECTURE.md), [lifecycle](docs/MODALITY_LIFECYCLE.md),
[monitoring](MONITORING_MAPPING.md), [deployment](DEPLOYMENT.md),
[vận hành](OPERATIONS.md), [báo cáo](PROJECT_REPORT.md) và [đối chiếu đề bài](RUBRIC_MAPPING.md).

[Bộ trình bày](DEMO_PRESENTATION.md) có nguồn slide, lời thoại 15 phút,
demo 10–15 phút và Q&A 10 phút. Các PowerPoint/PDF đã xuất trước đây nằm trong
[archive](docs/archive/README.md), có thể khác nguồn hiện hành. Khi dùng làm bản
nộp mới, tạo lại và kiểm tra layout theo hướng dẫn trong bộ trình bày.

[CONTRIBUTING](CONTRIBUTING.md) ghi trách nhiệm bốn thành viên và quy trình branch/PR.
[EVIDENCE](docs/EVIDENCE.md) ghi riêng các run CI/local theo ngày, SHA và giới hạn;
không suy trạng thái deployment từ tài liệu hoặc số test của một lần chạy cũ.

GitHub https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring. Demo Grafana/Airflow
admin/admin, loopback only. Không commit credentials, biometric media hoặc backups.
