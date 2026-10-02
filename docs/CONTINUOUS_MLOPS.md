# Continuous MLOps: dữ liệu, monitoring, challenger và rollback

## Hai pipeline và ranh giới

`biometric_monitoring_pipeline` chạy mỗi giờ. Nó đọc các **batch check thật** theo tenant và model version, tạo cửa sổ feature không nhãn, lấy nhãn do operator kiểm duyệt, khóa reference lần đầu đủ mẫu và lưu snapshot trong MinIO. Mỗi cửa sổ có `window_id` dựa trên check ID và thời điểm review; cùng một cửa sổ không trigger hai lần. Monitoring 60 giây bằng Evidently/Prometheus vẫn chạy độc lập để phát hiện nhanh; DAG dùng cho bằng chứng ETL có phiên bản và quyết định yêu cầu train.

`biometric_model_pipeline` chạy hằng tuần hoặc khi monitoring DAG trigger. Dữ liệu train mặc định chỉ từ tenant `demo`, không tự lấy media/embedding của công ty khách hàng. Bảy task: snapshot → validate → publish data lake → hiệu chỉnh candidate/challenger → Responsible AI → so gate → reload kèm rollback. “Train” hiện là hiệu chỉnh ngưỡng trên encoder pretrained, chưa fine-tune encoder.

## MinIO data lake và nhãn

Bucket `biometric` chứa các object riêng với bằng chứng `evidence/`:

| Prefix | Nội dung |
|---|---|
| `datasets/training/<tenant>/<dataset_version>/` | Snapshot embedding và manifest SHA-256, nguồn nhãn enrollment, identity train/CV/holdout không giao nhau. Hiện chỉ tenant training được cấu hình. |
| `datasets/monitoring/<tenant>/<model_version>/reference.json` | Cửa sổ feature tham chiếu khóa lần đầu đủ mẫu; không có raw media. |
| `.../prediction-inputs/<window_id>.json` | Check ID và feature/score, **không có nhãn**. |
| `.../reviewed-labels/<window_id>.json` | Nhãn danh tính do operator kiểm duyệt, tách khỏi input dự đoán. |
| `.../reports/<window_id>/<report_hash>.json` | Report bất biến theo nội dung: PSI, cỡ mẫu, hiệu năng random audit, quyết định và lý do; `latest.json` là con trỏ cập nhật. |

Ảnh/audio check `verified` vẫn không được giữ. Review về cheating là phán đoán nghiệp vụ riêng; `identity_truth` mới được dùng để đo FAR/FRR của chính sách định danh. Nhãn `synthetic-simulation` không đi vào tập human. Công ty xem và gắn nhãn trên **Lịch sử & báo cáo → Các lượt cần kiểm duyệt**; API `PUT /v1/checks/{check_id}/review` yêu cầu operator đúng tenant. Queue lấy mọi ca nghi vấn/chưa kết luận và một cohort khoảng 10% theo hash ID trên **mọi kết quả**. Cohort cố định khi trạng thái check hay queue thay đổi; API không cho tự khai `random_audit` với ID ngoài cohort. Khi check vừa nghi vấn vừa được chọn, lý do `random_audit` được ưu tiên để giữ nguồn mẫu độc lập với dự đoán. Chính sách lấy mẫu MVP chưa có ước lượng khoảng tin cậy hay hiệu chỉnh theo tỷ lệ lớp trong production.

## Điều kiện yêu cầu train và promotion

- PSI dùng `face_score`, `voice_score`, `face_quality`, `voice_quality`, `risk_score`; mặc định cần 40 check của **cùng tenant và model version** ở current và 40 ở reference. PSI >0,2 đánh dấu drift. Hai cửa sổ khác nhau liên tiếp có drift mới trigger; có cooldown 24 giờ. Performance thật chỉ tính khi random audit có ít nhất 5 genuine và 5 impostor; FAR hoặc FRR >20% cũng có thể trigger.
- Chỉ tenant `demo` đủ ít nhất 10 identity ghi danh và `CONTINUOUS_TRAINING_ENABLED=true` được trigger train. Đổi `TRAINING_TENANT_ID` sang công ty khách hàng bị chặn cho tới khi có hồ sơ consent sử dụng dữ liệu huấn luyện. Drift của khách hàng khác đưa ra cảnh báo/điều tra nhưng không tự dùng dữ liệu họ để train. Ít mẫu hiển thị `insufficient_data`, không báo ổn định giả. Monitoring DAG đặt run ID train theo tenant/window và kiểm tra Airflow DagRun đã tồn tại; nếu task trigger thất bại, giờ kế tiếp có thể thử lại cùng yêu cầu.
- MLflow `candidate` và `challenger` cùng trỏ bản mới để thử; `champion` trỏ bản API đang phục vụ. Gate FAR/FRR calibration, CV, holdout vẫn bắt buộc. Với champion hiện hữu, cả hai phiên bản còn được chạy trên **cùng holdout khóa**; challenger phải cải thiện tổng lỗi ít nhất 0,01 và không làm bất kỳ FAR/FRR modality nào tăng quá 0,02. Replay shadow trên các ca random audit thật phải đủ nhãn và không hồi quy. Thiếu nhãn giữ nguyên champion.
- Chỉ khi candidate thực sự được promote, task rollout mới reload API và kiểm tra `/ready` trong 30 giây. Nếu không nạp đúng version hoặc readiness lỗi, alias được chuyển về `rollback_version` và API reload bản trước. Nếu đây là champion đầu tiên nên chưa có bản trước, alias lỗi được gỡ và cần operator xử lý serving. Đây là **shadow offline + quan sát sức khỏe phục vụ**, chưa phải canary phân tuyến lưu lượng thật. Model artifact được đổi qua Registry/Airflow; GitHub Actions dùng cho thay đổi code/image.

## Grafana và Telegram

Hàng Drift có PSI/cỡ mẫu theo tenant/model, đề nghị train challenger và tuổi monitoring DAG. Prometheus alert `BiometricTenantDataDrift`, `BiometricRetrainRecommended`, `MonitoringETLStale` bổ sung cho alert drift thời gian gần thực. Telegram nêu công ty, version, feature, số mẫu và việc nên làm. Alert kỹ thuật đến platform, còn kết quả từng nhân viên vẫn tới công ty qua API/webhook.

## Demo và rollback

1. Mở portal công ty → **Lịch sử & báo cáo** → review một check được queue chọn. Nêu rõ `genuine/impostor` khác với kết luận cheating.
2. Mở Airflow hai DAG. Monitoring DAG cho report hiện hành; nếu mới có vài batch, `insufficient_data` là kết quả đúng. Mở MinIO xem manifest versioned. Training DAG mở task `publish_versioned_dataset`, `evaluate_and_promote_candidate` và MLflow aliases; candidate không hơn champion sẽ không được deploy.
3. Mở Grafana hàng Drift, đổi time range, xem PSI, sample count, recommendation và alert. Chỉ dùng simulation để chứng minh cơ chế alert, không gọi đó là accuracy người thật.

**Checkpoint trước thay đổi:** Git branch `checkpoint/2026-10-02-before-mlops-continuous`, commit `4913b7b`. PostgreSQL dump đã kiểm tra restore: `data/backups/ddm501_restore_drill_20261001_184709.dump` (gitignored). Trước khi rollback runtime, dừng traffic và sao lưu dữ liệu mới phát sinh; Git checkpoint không tự khôi phục database/MinIO. Bảng `check_reviews` là migration cộng thêm nên code cũ có thể chạy với DB mới; muốn quay lại đúng dữ liệu ban đầu cần restore dump trong cửa sổ bảo trì.

**Giới hạn cần tiếp quản:** Không đủ nhãn human để tự kết luận performance/chuyển champion trên bộ dữ liệu hiện tại; benchmark người thật, consent dùng dữ liệu liên công ty và canary phân tuyến traffic cần được thiết kế/kiểm chứng trước production. QWK chỉ phù hợp nếu sau này chấm điểm nói/viết tiếng Anh theo thang bậc; face/voice integrity hiện dùng FAR/FRR và precision/recall.
