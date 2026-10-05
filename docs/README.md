# Mục lục tài liệu

Rà soát theo source ngày **05/10/2026**. Tài liệu mô tả implementation trong checkout;
trạng thái đang chạy phải đối chiếu SHA, cấu hình và bằng chứng của deployment đó.

## Hướng dẫn hiện hành

| Cần tìm | Tài liệu chính |
|---|---|
| Giới thiệu, setup, dependencies, sử dụng | [README](../README.md) |
| Phạm vi sản phẩm và điều kiện nghiệm thu | [PROJECT_REQUIREMENTS](../PROJECT_REQUIREMENTS.md) |
| Thiết kế, lưu trữ, luồng xử lý và giới hạn | [ARCHITECTURE](../ARCHITECTURE.md), [sơ đồ Mermaid](ARCHITECTURE_OVERVIEW.md) |
| API, tenant, enrollment, webhook | [SAAS_INTEGRATION](../SAAS_INTEGRATION.md), [employee demo](EMPLOYEE_DEMO.md) |
| Drift, công thức, ngưỡng, template, retrain, rollout | [MODALITY_LIFECYCLE](MODALITY_LIFECYCLE.md) |
| Luồng tự động hóa tóm tắt | [CONTINUOUS_MLOPS](CONTINUOUS_MLOPS.md) |
| Hai kịch bản simulation và reset | [SIMULATION](SIMULATION.md) |
| Metric đến từ đâu, xem ở đâu | [MONITORING_MAPPING](../MONITORING_MAPPING.md) |
| Khởi động, CI/CD, backup, rollback | [DEPLOYMENT](../DEPLOYMENT.md), [OPERATIONS](../OPERATIONS.md) |
| RAI, quyền riêng tư và phần chưa triển khai | [RESPONSIBLE_AI](../RESPONSIBLE_AI.md) |
| Mục tiêu 50.000 nhân viên và cách tính capacity/cost | [SCALABILITY_COST](../SCALABILITY_COST.md) |
| Báo cáo dự án và đối chiếu đề bài | [PROJECT_REPORT](../PROJECT_REPORT.md), [RUBRIC_MAPPING](../RUBRIC_MAPPING.md) |
| Phân công, branch, commit, PR | [CONTRIBUTING](../CONTRIBUTING.md) |
| Bàn giao ngắn gọn | [DEMO_HANDOVER_GUIDE](DEMO_HANDOVER_GUIDE.md) |
| Trình bày 15 phút, demo 10–15 phút, Q&A 10 phút | [DEMO_PRESENTATION](../DEMO_PRESENTATION.md) |
| Bằng chứng theo thời điểm, phạm vi và nguồn | [EVIDENCE](EVIDENCE.md) |
| Những gì đã làm sạch trong đợt này | [DOCUMENTATION_AUDIT](DOCUMENTATION_AUDIT.md) |

## Nguồn quyết định khi tài liệu và code khác nhau

Đối chiếu [cấu hình lifecycle](../pipeline/lifecycle_config.json),
[Compose](../docker-compose.yml), [workflow CI](../.github/workflows/ci.yml),
[DAGs](../airflow/dags), [API](../api/app) và [dashboard JSON](../monitoring/grafana/dashboards).
Giá trị `.env` của installation có thể khác default; không đưa secrets vào tài liệu.
Markdown là nguồn hướng dẫn hiện hành. Số test, phiên bản champion và dữ liệu mẫu
không phải hằng số của kiến trúc.

## Lịch sử, bản xuất và bản nháp

- [Archive](archive/README.md) giữ checkpoint cũ và các bản PowerPoint/PDF đã xuất.
  Chúng có ngày và không phải hướng dẫn vận hành hiện hành.
- `plans/` và `superpowers/plans/`, `superpowers/specs/` giữ lịch sử thiết kế ở vị trí
  cũ để bảo toàn tham chiếu; banner đầu mỗi file chỉ tới hướng dẫn thay thế.
- `architecture/` là bộ bản nháp/đồ họa local đã có trước đợt rà soát, chưa được
  Git theo dõi. HLD cũ còn mô tả weekly training và direct reload. Không sử dụng
  nó làm nguồn kiến trúc hiện hành; dùng sơ đồ Mermaid được liên kết ở bảng trên.
- Đề bài gốc trong [ddm501-final-project-required](../ddm501-final-project-required)
  và attribution trong [vendor README](../api/app/vendor/README.md) được giữ nguyên.

Khi sửa tính năng, sửa tài liệu chính tương ứng và các link liên quan. Chỉ ghi
“đã kiểm chứng” khi có run/report của đúng revision; không đổi ngày của kết quả cũ
thành ngày cập nhật tài liệu.
