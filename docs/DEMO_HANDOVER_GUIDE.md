# Bàn giao và demo dịch vụ

Cập nhật **05/10/2026**. Đây là điểm bắt đầu cho người tiếp quản; hướng dẫn chi
tiết nằm trong các tài liệu chính để tránh sao chép pipeline và danh sách panel cũ.

## Luồng chính

Công ty tạo nhân viên và ghi danh Face/Voice. Backend thi gửi ảnh/WAV cùng person,
session, request ID và consent tới `POST /v1/checks`. API tạo embedding pretrained,
so max cosine với active templates, chọn policy Face/Voice đang phục vụ và chạy
integrity inspectors. Kết quả lưu PostgreSQL cùng outbox; suspicious media được
lưu MinIO. API trả ngay, worker gửi lại canonical result qua webhook HMAC/retry.
Portal công ty xem lịch sử/evidence/PDF/CSV; công ty giữ quyết định bài thi.

Xem [hợp đồng API](../SAAS_INTEGRATION.md), [ghi danh nhân viên](EMPLOYEE_DEMO.md),
[kiến trúc](../ARCHITECTURE.md) và [sơ đồ](ARCHITECTURE_OVERVIEW.md).

## Các trang quản lý

| Trang | URL local | Quản lý / quan sát |
|---|---|---|
| Portal | http://localhost:18501 | Operator: nhân viên, enrollment, keys, history. Platform: tenant, MLOps và simulation |
| Employee example | http://localhost:18600 | Ghi danh qua invitation và gửi capture; mock login của khách hàng |
| API docs | http://localhost:18100/docs | Contract và request/response |
| Grafana overview | http://localhost:13000/d/biometric-overview | 10 panel tổng quan và link reports |
| Grafana simulation | http://localhost:13000/d/biometric-simulation | Synthetic drift/gates/routing/rollback/reset |
| Prometheus | http://localhost:19090 | Query metric, targets và rules; nhập `up` để bắt đầu |
| Alertmanager | http://localhost:19093 | Alert groups và routing |
| Airflow | http://localhost:18081 | Ba DAG, run và task logs |
| MLflow production | http://localhost:15030 | Policies Face/Voice độc lập, artifacts và aliases |
| MLflow simulation | http://localhost:15031 | `simulation-<run-id>-<modality>`, registry tổng hợp riêng |
| MinIO | http://localhost:19101 | Evidence, datasets và MLflow artifacts theo quyền vận hành |

## Luồng tự động hóa

Monitoring DAG hàng giờ đánh giá quality PSI, MMD² embeddings, score PSI,
trusted performance và template age. Input issue theo dõi; aging theo template
workflow; chỉ persistent verified degradation đủ bằng chứng mới yêu cầu calibration.
Model DAG theo intent có 7 task và không có lịch weekly. Candidate phải qua offline,
shadow và canary 5/10/25/50/100 trước champion; fail giữ champion và audit.
Airflow điều phối, Python calibrate thresholds, MLflow quản lý phiên bản.
Xem [lifecycle](MODALITY_LIFECYCLE.md) và [monitoring mapping](../MONITORING_MAPPING.md).

Simulation là đường demo riêng: chọn modality, promotion hoặc fail ở canary 25%,
reset về baseline. Nó dùng synthetic vectors/labels và stores riêng. Không đổi
production champion; có dùng chung host/Airflow. Runbook toàn diện, timebox và
phương án xử lý lỗi tại [DEMO_RUNBOOK](presentation/DEMO_RUNBOOK.md).

## Thứ tự tiếp quản

1. Kiểm tra checkout/revision và `git status`; đọc [README](../README.md) và
   [DEPLOYMENT](../DEPLOYMENT.md). Giữ `.env`, project name và volumes của runtime.
2. Kiểm tra `/health` và `/ready`. Registry rỗng chưa tự có evaluated champion;
   dùng backup được phép hoặc simulation riêng theo hướng dẫn, không hạ gate.
3. Mở Grafana kiểm tra scrape/freshness. Thiếu human labels là thiếu bằng chứng,
   không dùng synthetic thay cho human. Kiểm tra bằng [OPERATIONS](../OPERATIONS.md).
4. Xem Actions FSB đúng SHA và Windows JUnit không skip, rồi deploy job/artifacts.
   Runner hiện hành là Linux WSL gọi PowerShell, không phải Windows runner cũ.
5. Diễn tập tenant demo và hai scenario simulation; lưu evidence đúng run ID trước
   reset. Các verifier tích hợp có thể ghi dữ liệu; chỉ chạy trên demo được phép.
6. Kiểm tra [RAI](../RESPONSIBLE_AI.md) và [EVIDENCE](EVIDENCE.md) trước khi diễn giải
   chất lượng, fairness hoặc capacity. [CONTRIBUTING](../CONTRIBUTING.md) chỉ rõ owner.

Không dùng `docker compose down -v` để reset demo. Rollback policy qua lifecycle
endpoint, template qua endpoint riêng; nút reload bundle legacy không thay thế
rollback Face/Voice hiện hành. Không chạy lại commands/history cũ trong archive
như một runbook vận hành mới.
