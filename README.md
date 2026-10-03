# DDM501 - Face & Voice Integrity Service

Dịch vụ xác minh face/voice theo batch cho doanh nghiệp tổ chức kỳ đánh giá ngoại ngữ thường niên. Công ty giữ hệ thống thi, lịch capture, điểm và quyết định nghiệp vụ. Dự án cung cấp API/webhook, portal công ty và full pipeline MLOps.

## Hai không gian vận hành

- Công ty: đăng ký gói giả lập, quản lý nhân viên, ghi danh qua camera/audio/upload hoặc API, integration keys, webhook, lịch sử, bằng chứng nghi vấn và PDF/CSV.
- Nền tảng: Airflow/MLflow/CI-CD cùng Grafana/Evidently/Telegram. Company portal chỉ có dữ liệu và chức năng của công ty đó.

## Demo và API

Portal http://localhost:18501; customer example http://localhost:18600; API http://localhost:18100/docs.
Grafana http://localhost:13000/d/biometric-overview; Airflow http://localhost:18081; MLflow http://localhost:15030; MinIO http://localhost:19101.

Đăng ký công ty tại portal, lưu operator key được trả một lần. Ghi danh >=2 ảnh/WAV, cấp integration key và cấu hình webhook. Backend gọi POST /v1/checks với person_id, session_id, request_id, consent, face_file và voice_file. Nhịp 30 giây và WAV 10 giây là ví dụ do khách hàng cấu hình.

## Model và dữ liệu

Quản trị nền tảng có trang **Simulation MLOps** với ba nút: drift dẫn tới promotion, canary lỗi dẫn tới rollback, và khôi phục baseline demo. Simulation dùng network/database/MLflow riêng, dữ liệu và nhãn tổng hợp; xem [hướng dẫn và giới hạn](docs/SIMULATION.md). MLflow simulation: http://localhost:15031.

SFace/YuNet + ECAPA xác minh danh tính. MiniFASNet face PAD và AASIST audio anti-spoof là detector nghiên cứu pretrained/pinned. ECAPA segments là heuristic thay người nói. Missing detector trả inconclusive. Chưa có benchmark khách hàng cho mọi deepfake, physical replay hoặc simultaneous voices.

PostgreSQL lưu embedding/metadata/checks/review; MinIO lưu suspicious evidence, MLflow artifacts và các snapshot feature/nhãn có phiên bản cho MLOps. Raw enrollment và media check hợp lệ không được giữ mặc định. Lịch sử, exports và evidence downloads đều tenant-scoped. Webhook HMAC có durable outbox/retry; receiver phải deduplicate.

Airflow có hai DAG phục vụ lifecycle chính: monitoring mỗi giờ và hiệu chỉnh ngưỡng theo yêu cầu riêng Face/Voice; DAG `biometric_simulation` riêng nhận job demo. Source hiện có decision engine nhiều tầng, template có phiên bản và luồng `candidate → offline → challenger → shadow → canary → champion/rollback`; drift thống kê đơn lẻ không kích hoạt train. Xem [lifecycle và giới hạn thực tế](docs/MODALITY_LIFECYCLE.md), [Continuous MLOps](docs/CONTINUOUS_MLOPS.md) và [bằng chứng theo từng phiên bản](VERIFICATION.md). Lifecycle commit `76169cf` đã có GitHub CI/deploy thành công; phần simulation mới được kiểm chứng local, không phải bằng chứng rollout bằng dữ liệu production.

## Chạy và kiểm chứng

Giữ nguyên .env và volumes đã có; xem PROJECT_STATE.md về deployment ngoài OneDrive.

```powershell
docker compose up -d --build --wait
python pipeline/verify_company_service.py
python pipeline/verify_monitoring_centre.py
```

CI tách `quality` (Ubuntu, unit tests/coverage) và `deployment-preflight` (Windows, hai test staging/reject SHA với runtime tạm, không cần secrets hoặc Docker daemon). Job Windows phải có JUnit không skip; `containers` chờ cả hai job trước khi `deploy-demo` được phép chạy. Preflight không thay thế kiểm chứng deploy thật qua WSL runner và Docker Desktop; xem [bằng chứng CI/deploy ngày 02/10](VERIFICATION.md#deploy-github-actions-02102026-đối-chiếu-ngày-03102026).

[Report](PROJECT_REPORT.md) · [Sơ đồ kiến trúc Mermaid](docs/ARCHITECTURE_OVERVIEW.md) · [Continuous MLOps](docs/CONTINUOUS_MLOPS.md) · [Demo và bàn giao](docs/DEMO_HANDOVER_GUIDE.md) · [Scope](PROJECT_REQUIREMENTS.md) · [Kiến trúc kỹ thuật](ARCHITECTURE.md) · [Tích hợp](SAAS_INTEGRATION.md) · [Mapping](RUBRIC_MAPPING.md) · [Bằng chứng](VERIFICATION.md) · [Vận hành](OPERATIONS.md).

GitHub https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring. Demo Grafana/Airflow admin/admin, loopback only. Không commit credentials, biometric media hoặc backups.
