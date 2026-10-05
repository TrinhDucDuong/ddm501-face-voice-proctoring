# Báo cáo dự án Face & Voice Integrity

Cập nhật theo source ngày **05/10/2026**. [Mục lục tài liệu](docs/README.md)
và [bằng chứng có ngày/phiên bản](docs/EVIDENCE.md) tách hướng dẫn hiện hành khỏi
kết quả của những lần chạy trước.

## Bài toán và phạm vi

Một nhân viên đăng nhập đúng tài khoản nhưng người khác có thể làm thay phần nói
trong kỳ đánh giá ngoại ngữ. HR khó xác minh lại nếu chỉ có bài làm và điểm số.
Đây là tình huống giả định dẫn tới dự án, chưa phải sự cố hoặc tỷ lệ cheating được
đo tại doanh nghiệp. Camera tối, mic kém và mẫu ghi danh cũ cũng có thể làm score
giảm, nên một mismatch không đủ kết luận gian lận.

Dịch vụ nhận batch ảnh/WAV theo lịch của phần mềm thi, xác minh danh tính 1:1 và
trả tín hiệu integrity, lý do và bằng chứng. Khách hàng giữ đăng nhập, lịch thi,
điểm và quyết định nghiệp vụ. Portal công ty quản lý nhân viên, mẫu ghi danh,
integration keys, webhook, lịch sử và PDF/CSV. Đăng ký/subscription là giả lập.

## Model, input/output và dữ liệu

YuNet phát hiện/căn chỉnh mặt; SFace và ECAPA-TDNN pretrained tạo embedding chuẩn
hóa từ ảnh và WAV. API tính max cosine với các template của người được khai báo.
Policy Face/Voice áp dụng ngưỡng riêng. MiniFASNet PAD, AASIST và heuristic voice
segments bổ sung tín hiệu integrity; thiếu khả năng đánh giá trả inconclusive.
Kết quả API là verified/suspicious/inconclusive, scores, reasons và phiên bản policy.

Pipeline hiện **hiệu chỉnh threshold policy**, không fine-tune encoder hoặc detector.
`face-verification` và `voice-verification` có lifecycle độc lập. Model
`face-voice-risk-bundle` là bundle legacy, còn dùng làm nguồn incumbent khi migration;
nó không phải encoder mới và không phải template riêng của từng nhân viên.

Embedding/template JSON, checks, labels, outbox và lifecycle audit nằm trong
PostgreSQL; không có vector DB riêng. MinIO chứa suspicious media, versioned
training/monitoring snapshots và MLflow artifacts. Artifacts policy gồm cấu hình,
metrics, paired scores, MLmodel và môi trường chạy; không phải weights encoder
được train mới. Weights pretrained được tải pinned vào kho models của runtime.
Raw enrollment và media check thường không được giữ mặc định.

Training hiện chỉ cho tenant `demo`. Bootstrap ghép nguồn ảnh/giọng nói công khai
thành identity tổng hợp, không chứng minh cùng một người ở hai modality. Số mẫu
thay đổi theo snapshot, nên phải đọc manifest của run thay vì lấy một tổng cố định
trong báo cáo. Evaluation chia 5 nhóm identity: 20% holdout, 80% calibration;
4-fold CV trên phần 80% tương ứng 60/20/20 train/validation/holdout mỗi lượt.
Final fit dùng 80%, đánh giá cuối dùng holdout 20%. Tỷ lệ tính theo identity,
không bắt buộc bằng đúng tỷ lệ số file khi mỗi người có số mẫu khác nhau.

## Drift và quyết định hành động

Airflow monitoring hàng giờ gọi decision engine trong lifecycle service. Mỗi
tenant/modality/policy version có reference và current riêng, mặc định 100+100
observations. Reference được đóng băng; encoder phải tương thích và identity
overlap ít nhất 80%. Query embedding retention tắt mặc định: thiếu vector/nhãn
thì INSUFFICIENT_DATA, không mặc định model khỏe.

Quality và genuine/impostor score dùng PSI 10 bins, threshold 0,2. Embedding dùng
RBF MMD bình phương trên toàn vector chuẩn hóa, threshold 0,02. Performance dùng
FMR/FNMR, EER, TAR@FAR từ nhãn review tin cậy; không dùng dự đoán làm ground truth.
Template aging so lỗi theo tuổi mẫu. Công thức, feature và các điều kiện nằm trong
[MODALITY_LIFECYCLE](docs/MODALITY_LIFECYCLE.md).

Quality drift dẫn tới điều tra input. Thống kê embedding/score đơn lẻ chỉ yêu cầu
theo dõi. Template cũ suy giảm theo heuristic và template mới khỏe dẫn tới workflow
template: nhiều quan sát trusted, quality/margin/consistency gate, holdout riêng,
version và rollback. Retrain cần embedding và score drift kéo dài, performance
suy giảm qua ít nhất hai cohort tuổi, đủ labels và dữ liệu mới, ba cửa sổ mới,
cooldown 24 giờ và không có lifecycle đang chạy cho modality đó.

## Training và triển khai policy

Ba DAG có ba trách nhiệm: monitoring hàng giờ, model pipeline theo intent và
simulation poll mỗi phút. `biometric_model_pipeline` có bảy task:
snapshot, validate, publish dataset, calibrate/register, RAI report, offline gate,
lifecycle tick. Airflow điều phối; code Python thực hiện calibration; MLflow theo
dõi experiment và Registry. Tên task legacy không có nghĩa promote trực tiếp.

Candidate và champion được so trên cùng holdout. Candidate đạt gate trở thành
challenger và vào shadow; champion vẫn trả kết quả. Canary lần lượt 5/10/25/50/100%
traffic dùng threshold mới. Mỗi stage production cần ít nhất 1.000 observations
và 3.600 giây, 30 nhãn mỗi class, FMR <=1%, FNMR <=5%, không tăng FMR, FNMR tăng
tối đa 0,5 điểm phần trăm, cùng gate latency/disagreement/cohort. Gate selection CV
20% trong code calibration không phải ngân sách promotion này.

Fail canary đưa challenger traffic về 0 và giữ champion, lưu failure evidence.
Pass stage cuối mới ghi PROMOTING, reconcile MLflow aliases rồi chuyển DB champion.
Giữ previous_champion để rollback. Nhãn đến muộn được đánh giá theo tick hàng giờ;
không bảo đảm rollback tức thời trước mọi sự cố. Hai policy dùng chung encoder
và similarity nên score delta bằng 0; decision vẫn có thể khác do threshold.

## Monitoring, simulation và CI/CD

Prometheus scrape API, worker, drift-monitor, ops-monitor và simulation. Grafana có
System Overview 10 panel và Simulation 10 panel. Chi tiết RAI/evaluation/Evidently
nằm ở report có xác thực, còn logs xem qua Loki/Explore. Vòng drift-monitor 60 giây
chỉ báo cáo, không tạo trigger train thứ hai. Alertmanager định tuyến cảnh báo
production tới ops-monitor/Telegram khi cấu hình, simulation tới receiver riêng.

Simulation dùng vectors/labels tổng hợp, SQLite và file MLflow riêng, nhưng chạy
logic calibration/gate, HTTP routing và nhận alert thật. Hai scenario là promotion
và FMR regression tại canary 25% dẫn tới rollback; reset phục hồi baseline demo,
giữ audit. Nó không đổi production policies, nhưng chia sẻ host/Airflow nên có thể
tranh chấp tài nguyên. Xem [SIMULATION](docs/SIMULATION.md).

GitHub Actions FSB chạy Ubuntu quality và Windows deployment-preflight, build
containers, rồi trusted-main deploy qua Linux WSL runner gọi PowerShell/Docker
Desktop. Application deployment là thay container trên một Compose host; canary
là lựa chọn policy trong API. [EVIDENCE](docs/EVIDENCE.md) dẫn run và kết quả đã ghi
nhận, không coi quality xanh hoặc simulation thành bằng chứng accuracy production.

## Responsible AI và giới hạn

Consent, tenant isolation, hashed keys, authenticated evidence, immutable prediction
và review labels riêng giúp kiểm soát dữ liệu và audit. RAI report đánh giá quality
slices với class counts và Wilson intervals; chưa chứng minh demographic fairness.
DAG sinh report nhưng endpoint candidate modality chưa enforce cờ fairness legacy.
Cần human review trước pilot; report tồn tại không chứng minh fairness gate đã chạy.

Chưa có benchmark chống mọi deepfake/replay, load test 50.000 nhân viên, SSO/TLS/HA
cloud hoàn chỉnh, quy trình xóa biometric end-to-end hay khởi tạo champion đã đánh
giá một lệnh từ registry rỗng. Template rollback sau activation còn là thao tác
operator. Các mục tiêu kinh doanh/cost là giả thuyết cần pilot đo, không phải ROI
đã đạt được. Chi tiết tại [RAI](RESPONSIBLE_AI.md), [capacity/cost](SCALABILITY_COST.md)
và [deployment](DEPLOYMENT.md).

## Nhóm và bàn giao

[CONTRIBUTING](CONTRIBUTING.md) ghi trách nhiệm bốn thành viên và quy trình branch/PR.
Bằng chứng đóng góp phải là công việc, review và demo thực tế; metadata Git riêng
lẻ không thay thế bằng chứng đó. Bộ [trình bày](DEMO_PRESENTATION.md) dùng 15 phút
present, 10–15 phút demo, 10 phút Q&A. [RUBRIC_MAPPING](RUBRIC_MAPPING.md) đối chiếu
đề bài mà không tự gán điểm hoặc tuyên bố production-ready.
