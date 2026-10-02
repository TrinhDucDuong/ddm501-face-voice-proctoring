# Báo cáo dự án DDM501 - Face & Voice Integrity Service

Ngày cập nhật: 29/09/2026. Phạm vi: demo môn học và MVP tích hợp thử cho doanh nghiệp.

## 1. Câu chuyện business

Doanh nghiệp tổ chức kỳ đánh giá năng lực ngoại ngữ thường niên cho nhân viên. Kết quả ảnh hưởng đến kế hoạch đào tạo và phân công công việc. Người thi hộ, thay người hoặc media giả làm giảm độ tin cậy của đánh giá. Phần mềm thi đã có câu hỏi, chấm điểm và xử lý nghiệp vụ; doanh nghiệp cần bổ sung dịch vụ kiểm tra danh tính mà không thay toàn bộ phần mềm.

Dự án cung cấp API xác minh face/voice theo nhân viên đã ghi danh, cùng portal cho quản trị công ty xem lịch sử và bằng chứng. Khách hàng tự quyết định lúc bắt đầu hoặc trong quá trình thi sẽ gửi media. Ví dụ mỗi 30 giây gửi một ảnh và WAV khoảng 10 giây; dịch vụ xử lý từng lượt và trả kết quả qua API/webhook. Không stream toàn bộ quá trình thi về nền tảng.

## 2. Phạm vi và trách nhiệm

Hệ thống khách hàng quản lý bài thi, danh tính đăng nhập, lịch capture, điểm và quyết định nghiệp vụ. Dịch vụ này quản lý tenant, nhân viên, embedding, kiểm tra media, kết quả, bằng chứng nghi vấn và callbacks. Gói đăng ký được giả lập đang hoạt động, chưa có thanh toán thật hoặc SSO. Portal sử dụng API key quản trị công ty; integration key dành cho backend.

Airflow điều phối snapshot dữ liệu, quality gate, calibration/evaluation, Responsible AI, promotion và reload model. Serving API và portal là các dịch vụ runtime của cùng nền tảng. Grafana/Evidently/Telegram dành cho đội vận hành toàn dự án. Portal công ty là monitoring nghiệp vụ với dữ liệu riêng theo tenant.

## 3. Kiến trúc kỹ thuật

Khách hàng -> FastAPI /v1/checks -> SFace + ECAPA + integrity inspectors -> PostgreSQL + MinIO + transactional outbox -> webhook khách hàng.

PostgreSQL lưu công ty, nhân viên, embedding JSON, SHA256 mẫu, check ID, request ID, mã phiên khách hàng, thời gian, scores, capability details, kết quả và metadata bằng chứng. MinIO lưu artifact MLflow và ảnh/WAV của lượt suspicious. Raw media của lượt verified/inconclusive không giữ; enrollment giữ embedding theo cấu hình mặc định. Bằng chứng tải qua API có xác thực; object keys không đưa vào kết quả/public URLs.

API tenant-scoped, key lưu digest, namespace mã nhân viên theo công ty. Cùng EMP-001 có thể tồn tại ở hai công ty. Retry cùng request ID và payload trả lại một kết quả; payload khác trả 409; unique constraint bảo vệ concurrency. Kết quả/check/event/outbox cùng DB transaction. Webhook ký HMAC timestamp, có retry và at-least-once delivery; receiver xác minh chữ ký và deduplicate webhook ID.

## 4. Model và giới hạn khả năng

SFace/YuNet và ECAPA cung cấp xác minh danh tính 1:1. Pipeline hiệu chỉnh threshold theo identity CV và holdout riêng; không train foundation encoders từ đầu. Champion identity hiện có bằng chứng version 9 ngày 28/09.

MiniFASNetV2 bổ sung single-image face PAD cho dấu hiệu print/screen replay. AASIST pretrained trên ASVspoof2019 logical access bổ sung dấu hiệu speech synthesis/voice conversion. Model được pin revision/checksum; source AASIST giữ MIT attribution. Segment ECAPA cung cấp heuristic nghi vấn thay người nói. Exact repeated capture của cùng nhân viên/phiên tạo dấu hiệu capture_reused.

Những kiểm tra trên không bảo đảm nhận diện mọi deepfake/video, physical audio replay hoặc người nói đồng thời. Speaker consistency không phải diarization/đếm chính xác người nói. Chưa có benchmark anti-spoof trên dữ liệu khách hàng có consent; chưa có demographic fairness ground truth. Missing detector, capture không hợp lệ hoặc audio quá ngắn trả inconclusive, không giả lập detector thành passed. Suspicious là tín hiệu để khách hàng xử lý, không phải kết luận pháp lý về gian lận.

## 5. Full flow MLOps

Ghi danh/embedding -> fingerprinted snapshot -> validation -> max-template feature pairs -> calibration/CV/holdout -> MLflow params/metrics/artifacts/signature -> RAI audit -> gate -> candidate/champion -> API hot reload -> Prometheus/Grafana/Evidently -> Alertmanager/Telegram -> điều tra/cập nhật có kiểm soát.

Training mặc định chỉ tenant demo. Bootstrap LFW + Speech Commands ghép tổng hợp phục vụ pipeline; không dùng kết quả đó để công bố accuracy đa phương thức thật. Identity holdout không tham gia chọn thresholds. Gate FAR/FRR 20% là gate demo. Auxiliary spoof detectors hiện pretrained/pinned, chưa được hiệu chỉnh hoặc promotion bằng benchmark anti-spoof địa phương; report phải tách hai loại evidence.

## 6. Monitoring và alert

Monitoring nền tảng gồm readiness, requests/errors, latency, capture quality, PSI/Evidently, performance có human feedback, Registry/evaluation, DAG/tasks, RAI, CPU/RAM/logs, outbox và detector/evidence availability. Telegram chung nhận cảnh báo vận hành, không nhận lịch sử nhân viên của từng công ty.

Monitoring công ty gồm mã/tên nhân viên, mã phiên, các lượt check, thời điểm đầu/cuối đã nhận, trạng thái có nhãn, lý do và ảnh/audio nghi vấn. Khoảng thời gian đầu-cuối không chứng minh hệ thống đã giám sát liên tục giữa hai lượt. API/webhook gửi kết quả để backend khách hàng hành động. Portal cho xuất PDF/CSV theo nhân viên, phiên và khoảng ngày; không chứa điểm thi hoặc quyết định giám thị.

## 7. Demo và kiểm chứng

Đăng ký hai công ty; cấp integration keys; thêm nhân viên cùng mã ở cả hai; ghi danh; gửi media đúng và media người khác; kiểm tra identity và integrity signals riêng; xem webhook, evidence và lịch sử; xuất PDF/CSV; dùng key công ty thứ hai thử đọc check/evidence/export công ty thứ nhất để xác nhận từ chối. Media bootstrap là dữ liệu thử, không phải nhân viên thật hoặc nhãn human.

GitHub Actions run 36562882154, executable commit 8b720fc: quality, containers và deploy-demo success; remote 65 tests, coverage 86,45%. Chi tiết trong VERIFICATION.md.

Kiểm chứng maintenance local: 65 tests pass, coverage 86,50%; 62 panels và 67 truy vấn Grafana; hai công ty được kiểm tra isolation, enrollment, batch identity, MinIO evidence, PDF/CSV và callbacks acknowledged HTTP 200. Streamlit AppTest kiểm tra sáu trang mỗi công ty và export CSV với API thật. Ảnh ghép hai khuôn mặt/audio ghép hai người tạo cảnh báo tương ứng. Những dữ liệu bootstrap và audio kéo dài tổng hợp này không cung cấp accuracy anti-spoof hoặc fairness người dùng thật.

## 8. Vận hành và hướng phát triển

Deploy local ngoài OneDrive giữ nguyên secrets, named volumes và runtime dữ liệu. Runner Windows đã đăng ký; chạy theo phiên người dùng, chưa là Windows service. Có backup/restore và model rollback rehearsal từ đợt trước. Data giữ khi công ty đăng ký gói giả lập active; deactivation chặn tenant access và giữ lịch sử, chưa triển khai tự động xoá theo hợp đồng.

Hướng phát triển: benchmark anti-spoof có consent, diarization/overlap detector, temporal challenge cho replay/deepfake, identity validation khi onboarding, SSO, billing, retention/deletion và cloud/TLS/capacity pilot. Business benefits về giảm gian lận chưa đo trên doanh nghiệp thật. Thành viên phải bổ sung tên và đóng góp thật theo CONTRIBUTING.md; không dựng bằng chứng team.

## 9. Tài liệu và nguồn tham khảo

- PROJECT_REQUIREMENTS.md, ARCHITECTURE.md, SAAS_INTEGRATION.md: scope và hợp đồng hệ thống.
- RUBRIC_MAPPING.md, MONITORING_MAPPING.md, VERIFICATION.md: tiêu chí môn học và bằng chứng.
- OPERATIONS.md, DEPLOYMENT.md, RESPONSIBLE_AI.md: vận hành, triển khai và giới hạn.
- SFace/YuNet: https://github.com/opencv/opencv_zoo
- ECAPA: https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb
- MiniFASNet: https://github.com/minivision-ai/Silent-Face-Anti-Spoofing
- AASIST (Jung et al.): https://arxiv.org/abs/2110.01200 và https://github.com/clovaai/aasist
- Pipeline requirement và rubric gốc: ddm501-final-project-required/.
