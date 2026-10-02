# Demo ghi danh và kiểm tra nhiều công ty

## Người quản trị công ty

1. Mở portal `http://localhost:18501`, nhập **operator key** của công ty. Key chỉ lưu ở phía quản trị; không đưa cho nhân viên.
2. Vào **Nhân viên**, tạo nhân viên và bấm **Tạo liên kết ghi danh**. Sao chép liên kết riêng; liên kết dùng một lần và hết hạn sau 24 giờ.
3. Mở **Lịch sử & báo cáo** sau khi nhân viên gửi các lượt kiểm tra. Xem kết quả bằng nhãn dễ đọc, mở bằng chứng chỉ khi nghi vấn, xuất CSV/PDF. JSON kỹ thuật nằm trong phần mở rộng.

## Nhân viên

1. Mở `http://localhost:18600` hoặc liên kết ghi danh do công ty cấp. Chọn đúng công ty và tên của mình. Bộ chọn tên trên trang này chỉ mô phỏng bước đăng nhập của hệ thống thi khách hàng.
2. Với liên kết ghi danh, bấm **Kiểm tra lời mời**, chụp hai ảnh hơi khác góc nhìn và thu hai đoạn giọng nói khoảng 10 giây; cũng có thể tải hai ảnh và hai WAV đã chuẩn bị. Đánh dấu đồng ý rồi **Gửi bốn mẫu ghi danh** một lần. Trình duyệt không thấy operator/integration key.
3. Trong phần **Xác minh trong bài thi**, dùng ảnh và WAV mới, đánh dấu đồng ý và gửi lượt đầu. Những lượt sau là các batch do công ty quyết định thời điểm. Thông báo chính là trạng thái ngắn gọn; dữ liệu JSON chỉ hiện khi mở **Xem dữ liệu kỹ thuật**.

## Luồng kỹ thuật và giới hạn

PostgreSQL lưu lời mời đã băm, tenant, người, embedding và lịch sử. MinIO lưu bằng chứng ảnh/audio cho lượt nghi vấn; mẫu ghi danh gốc không được giữ theo cấu hình mặc định. API trả kết quả ngay, outbox gửi webhook có chữ ký cho backend công ty. Prometheus/Grafana/Evidently/Telegram theo dõi nền tảng và vòng đời model, tách khỏi quyết định bài thi của công ty.

Camera và microphone chỉ hoạt động khi trình duyệt được cấp quyền. Bản demo local dùng `localhost`; khi triển khai từ xa cần HTTPS. Audio thu trên trang được mã hóa thành WAV trong trình duyệt. Dữ liệu bootstrap được dùng để chứng minh luồng vận hành, không đại diện cho độ chính xác sinh trắc trên người thật hoặc độ bền trước deepfake.

Kiểm chứng tự động: `python pipeline/verify_employee_demo.py`, `python pipeline/verify_company_service.py`, `python pipeline/verify_monitoring_centre.py` sau khi Compose đã chạy. Bằng chứng được ghi trong `reports/` và không chứa key.
