> HISTORICAL PLAN / SPEC: retained for design history, not current runtime status.
> See [current documentation](../README.md) for implementation, commands and evidence.

# Plan: Grafana overview tối giản

## Phạm vi

Chỉ thay cách hiển thị dashboard provisioned và generator tương ứng. Giữ UID
`biometric-overview`, đường dẫn JSON, datasource và provisioning hiện tại.
Không thay API, exporter, database, pipeline, alert rules, notification hoặc
Docker Compose. Không cài thêm dependency và không restart hệ thống.

## Các bước

1. [x] Rà dashboard, nguồn metric và các kiểm tra liên quan.
2. [x] Thay 71 panel nội dung bằng 10 panel: serving readiness, active incidents,
   API traffic, HTTP 5xx, verification p95, CPU/RAM, webhook backlog,
   input drift face/voice, human FAR/FRR, pipeline freshness/deployment.
3. [x] Bỏ tenant/service filter không còn dùng; giữ project cho container.
   Đưa logs, evaluation và báo cáo chi tiết thành link.
4. [x] Sinh lại JSON và cập nhật kiểm tra dashboard cho phạm vi mới.
5. [x] Kiểm tra JSON/generator, layout và scope thay đổi.
   Kiểm chứng live bị giới hạn vì máy hiện không có Docker daemon chạy.

## Giới hạn có chủ ý

Chỉ dùng metric đã có. Không bổ sung CPU/RAM limits, disk, tuổi webhook,
nhãn genuine/impostor hoặc lần DAG thành công gần nhất. Mô tả panel nêu rõ
các giới hạn; thiếu dữ liệu không mặc định là khỏe. Các cảnh báo synthetic
chỉ bị lọc khỏi bảng incidents; alert rules và thông báo không bị sửa.

## Áp dụng và hoàn tác

Grafana đang chạy với bind mount hiện tại đọc lại dashboard file mỗi 30 giây.
Reload trình duyệt sau khi provisioning cập nhật; không cần restart API.
Nếu stack chạy từ bản checkout/copy khác, cần chuyển đúng hai file generator
và JSON tới bản đó. Có thể hoàn tác hai file này về phiên bản trước mà không
thay dữ liệu hoặc runtime nghiệp vụ.

## Kết quả kiểm tra

- Regression check dashboard thực tế trong `tests/test_monitoring_centre.py`
  chạy độc lập bằng Python stdlib: PASS (10 panel, unique IDs, đúng datasource,
  không overlap, traffic loại simulation, model quality chỉ human).
- JSON provisioned khớp chính xác kết quả generator: PASS.
- `git diff --check`: PASS.
- Không chạy toàn bộ pytest: Python hiện tại thiếu pytest và môi trường ML.
  Không cài dependency chỉ để đổi dashboard.
- Không xác nhận render/query trên Grafana live: Docker socket không tồn tại.
  Không start/restart service, không gửi alert thử.
