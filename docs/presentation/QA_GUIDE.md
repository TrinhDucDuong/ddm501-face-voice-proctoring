# Q&A 10 phút: câu hỏi và câu trả lời theo implementation

**Dương điều phối**, Hiệp trả lời evaluation/drift, Hải trả lời platform/integration,
Đức mở evidence và giữ thời gian. Ưu tiên câu hỏi thật từ giảng viên. Các câu dưới
là ngân hàng luyện tập, không đọc tuần tự toàn bộ trong 10 phút.

## Cách phân bổ thời gian

| Khoảng thời gian | Hoạt động |
|---|---|
| 00:00–00:30 | Mời câu hỏi, nhắc lại câu đầu nếu cần |
| 00:30–08:30 | Khoảng 5–6 câu hỏi, mỗi câu 60–90 giây kể cả follow-up |
| 08:30–09:30 | Câu cuối hoặc một câu chưa khép lại |
| 09:30–10:00 | Ghi nhận phần cần kiểm chứng thêm và cảm ơn |

Mỗi câu trả lời theo ba nhịp: **trả lời trực tiếp**, **chỉ bằng chứng/code**,
**nêu giới hạn liên quan**. Không tranh nhau nói. Người đầu trả lời xong mới mời
người khác bổ sung. Nếu thiếu số liệu, nói “nhóm chưa có phép đo đó” thay vì dự đoán.

Nếu chưa có câu hỏi, gợi mở tối đa hai chủ đề: “Thầy cô muốn nhóm làm rõ việc thiếu
nhãn thì xử lý drift thế nào, hay cách canary rollback giữ champion?” Không dùng
Q&A để kéo dài bài trình bày thêm mười phút.

## Các câu trọng tâm nên tập trước

### 1. Dự án có thực sự phát hiện gian lận không?

**Người trả lời: Dương.**

“Dự án phát hiện tín hiệu danh tính và integrity trên những capture đã nhận, như
face/voice mismatch hoặc dấu hiệu media giả. Nó không đủ để kết luận mọi hành vi
gian lận. Nhãn suspicious có reason/evidence để doanh nghiệp review; khách hàng
giữ quyết định nghiệp vụ. Nhóm chưa đo tỷ lệ giảm cheating tại doanh nghiệp thật.”

**Nếu hỏi sâu:** Không bao phủ chắc chắn nhờ gợi ý ngoài màn hình, đọc tài liệu,
mọi replay/deepfake hoặc khoảng thời gian giữa hai capture. Xem slide 4 và
`SAAS_INTEGRATION.md` / `RESPONSIBLE_AI.md`.

### 2. Model input/output là gì? Retrain cái gì?

**Người trả lời: Dương, Hải bổ sung serving.**

“Encoder nhận ảnh hoặc WAV, trả embedding chuẩn hóa. Serving tính max cosine với
template của người được khai báo. Policy nhận score và áp dụng ngưỡng riêng Face
hoặc Voice để đưa ra identity decision. Retrain hiện tại hiệu chỉnh threshold
policy; SFace và ECAPA vẫn là pretrained encoder, chưa fine-tune weights.”

**Nếu hỏi sâu:** Inspector PAD/anti-spoof và quyết định integrity cuối là lớp riêng.
Không gọi toàn bộ response API là output duy nhất của encoder. Xem slide 7,
`api/app/biometrics.py`, `pipeline/modality_training.py`.

### 3. Check drift bằng phương pháp nào và theo feature nào?

**Người trả lời: Hiệp.**

“Quality và score dùng PSI. Quality gồm brightness, contrast, blur, face area hoặc
audio RMS, clipping, silence, duration, sample rate theo những gì code đo được.
Embedding drift dùng RBF MMD bình phương trên vector đa chiều chuẩn hóa. Performance
dùng reviewed FMR/FNMR, EER và TAR@FAR. Cuối cùng so sai số theo tuổi template.”

**Nếu hỏi sâu:** Không kiểm từng embedding dimension độc lập. SNR/yaw/occlusion
không được tự đưa vào khi chưa có measurement. Mở slide 28, `pipeline/drift_decision.py`.

### 4. Drift có lập tức trigger retrain không?

**Người trả lời: Hiệp.**

“Không. Quality drift đi sang kiểm tra capture. Embedding/score drift đơn lẻ là tín
hiệu theo dõi. Retrain cần ba cửa sổ mới đủ điều kiện, performance có trusted labels
suy giảm qua nhiều cohort tuổi, đủ dữ liệu mới và cooldown. Thiếu vector hoặc labels
thì insufficient data, không tự train chỉ để pipeline tiếp tục.”

**Nếu hỏi sâu:** Mặc định 100 observations/window, 20 nhãn/class, 40 reviewed mới,
cooldown 24 giờ. Same-window polling không tăng persistence. Xem slide 12,
`pipeline/lifecycle_config.json`, `api/app/lifecycle_service.py`.

### 5. Tại sao cập nhật template thay vì retrain model?

**Người trả lời: Hiệp hoặc Dương.**

“Nếu chỉ template cũ suy giảm trong khi template mới còn khỏe, encoder/policy có
thể không phải nguyên nhân chính. Hệ thống tạo candidate template từ nhiều quan
sát trusted, dùng holdout riêng và chỉ activate khi không tăng FMR hoặc FNMR.
Giữ version trước để rollback. Một lần model accept không được coi là ground truth.”

**Nếu hỏi sâu:** Đây là heuristic theo cohort, chưa phải chứng minh nhân quả.
Thiếu bằng chứng ở PENDING_REVIEW; post-activation template rollback tự động chưa có.
Xem slide 13, `api/app/template_lifecycle.py`.

### 6. Champion/challenger là alias môi trường hay chọn model tốt hơn?

**Người trả lời: Dương.**

“Alias biểu thị vai trò của phiên bản trong cùng lifecycle. Champion là policy
đang phục vụ; challenger là policy đã qua offline gate và đang được thử. Chúng
không đơn thuần là dev/staging/prod. Chỉ sau shadow và canary mới chuyển champion.
Champion được chấp nhận theo bằng chứng hiện có, không phải model tối ưu tuyệt đối.”

**Nếu hỏi sâu:** Gate hiện chặn hồi quy và yêu cầu đạt budget, không nhất thiết
bắt buộc candidate thắng tuyệt đối mọi metric. Face/Voice có registry name riêng.
Xem slide 14, `api/app/model_lifecycle.py`.

### 7. Score champion/challenger bằng nhau thì shadow có ý nghĩa gì?

**Người trả lời: Dương.**

“Hai policy dùng chung encoder và cosine nên score delta bằng không. Threshold
khác nhau vẫn có thể làm quyết định khác nhau. Shadow ghi decision disagreement,
reviewed FMR/FNMR và latency policy mà không ảnh hưởng response champion. Nó kiểm
tra threshold rollout, không phải thử hai encoder khác nhau.”

**Nếu hỏi sâu:** Policy p95 không phải latency end-to-end của inference/upload.
Xem slide 7, 14 và `docs/MODALITY_LIFECYCLE.md`.

### 8. Deployment có thật là canary không?

**Người trả lời: Hải.**

“Có canary ở lớp policy: hash ổn định theo modality/deployment/tenant/person/session
chọn request dùng threshold challenger. Code ứng dụng vẫn deploy bằng thay container
Docker Compose trên một host. Nhóm chưa triển khai application canary bằng nhiều
replica hoặc Kubernetes.”

**Nếu hỏi sâu:** Cần chỉ served_candidate count và response version, không chỉ
traffic_percent. Xem slide 16, 23 và `api/app/model_lifecycle.py`.

### 9. Demo simulation chứng minh được điều gì?

**Người trả lời: Hiệp, Đức mở evidence.**

“Nó chứng minh luồng drift, alert, calibration, offline gate, HTTP routing, Registry
transition và rollback trên dữ liệu tổng hợp. Alert và request là thao tác thật
trong môi trường simulation. Dữ liệu là vector/labels synthetic, không chạy camera
hoặc WAV qua encoder, nên không chứng minh accuracy người thật.”

**Nếu hỏi sâu:** Historical holdout được dựng để cho một threshold correction rõ
ràng; FNMR giảm lớn không phải kết quả benchmark khách hàng. Xem `docs/EVIDENCE.md`
và `docs/SIMULATION.md`.

### 10. Simulation có làm hỏng dữ liệu đang chạy không?

**Người trả lời: Hải.**

“Simulation có DB/MLflow/volume riêng và không nhận production credentials/weights.
Reset chỉ phục hồi baseline simulation, giữ audit. Evidence lịch sử cho thấy policy
production không đổi. Nhưng host/Airflow dùng chung nên vẫn có khả năng tranh chấp
tài nguyên. Phần demo sản phẩm trước đó có thêm dữ liệu vào tenant demo của app.”

**Nếu hỏi sâu:** Đối chiếu fields policy trước/sau nếu đã chụp snapshot live. Không
khẳng định live không đổi khi chưa kiểm chứng. Xem `docker-compose.yml`.

## Câu hỏi bổ sung

### 11. Chưa có nhãn thì có biết model khỏe hay không?

**Hiệp:** “Không đủ để kết luận performance. Drift phân phối có thể quan sát được
nếu có feature/vector, nhưng thiếu trusted labels thì không tính được performance
đáng tin cậy. Hệ thống trả insufficient evidence và chờ, không dùng dự đoán làm nhãn.”
Nhắc thêm selection bias nếu chỉ review suspicious, nên có random audit và labels
riêng cho Face/Voice. Không tuyên bố random audit loại hết bias.

### 12. Có embedding database hay cần thêm pgvector không?

**Hải:** “Hiện embedding JSON nằm trong PostgreSQL, lookup template theo person ID
cho verification 1:1. Không có vector DB riêng. Vector search hữu ích cho tìm danh
tính 1:N, nhưng chưa phải bắt buộc với đường truy vấn hiện tại. Muốn tối ưu ở quy mô
lớn cần benchmark truy vấn, storage và concurrency trước.”

### 13. 50.000 nhân viên có chạy được không?

**Hải:** “Đó là design target, chưa có load test chứng minh. Cần biết số người thi
đồng thời, cadence, latency budget, kích thước capture và thời gian lưu. Không thể
nhân một request demo để suy ra capacity. Cửa sổ drift 100 mẫu và overlap 80% cũng
cần xem lại khi số identity lớn.”

### 14. Vì sao Face và Voice không dùng chung lifecycle?

**Dương:** “Môi trường capture, score distribution và sai số hai modality khác nhau.
Mic thay đổi không buộc Face retrain. Tách state, alias, persistence và routing giúp
một modality rollout trong khi modality kia giữ ổn định. Integrity decision vẫn
tổng hợp theo logic sản phẩm.”

### 15. Làm sao biết candidate tốt hơn nếu dùng lại dữ liệu train?

**Hiệp:** “Threshold được chọn qua calibration/CV theo identity, giữ holdout riêng
ngoài tuning. Candidate và champion được so trên cùng holdout để tránh so hai metric
trên hai tập khác nhau. Sau đó mới dùng shadow/canary có labels. Dataset demo vẫn
có giới hạn đại diện, nên kết quả không thay thế customer benchmark.”

### 16. Rollback có ngay lập tức trong mọi trường hợp không?

**Dương:** “Gate fail đặt challenger traffic về không và giữ champion, nhưng nhãn
đến muộn được kiểm tra theo tick hàng giờ. In-flight request không bị thu hồi.
Nếu DB không hoạt động thì hệ thống không thể ghi trạng thái routing bền vững ngay.
Vì vậy không có bảo đảm zero-risk hoặc rollback tức thì cho mọi sự cố.”

### 17. MLflow alias và DB không đồng bộ khi crash thì sao?

**Dương:** “Promotion ghi intent PROMOTING trước khi thao tác Registry, rồi mới đổi
champion trong DB. Retry/reconciliation tiếp tục intent đó; serving giữ incumbent
cho tới khi DB switch commit. Không coi đây là một transaction ACID xuyên hai hệ
thống. Các lỗi ngoài đường promotion vẫn cần recovery và kiểm chứng.”

### 18. Chứng minh test Windows và deploy thật đã chạy thế nào?

**Hải:** “Mở đúng run GitHub FSB, xem deployment-preflight trên Windows và JUnit
không skip. Deploy thật là job deploy-demo riêng cùng artifact monitoring. Ubuntu
quality xanh không đủ chứng minh test chỉ dành cho Windows đã thực thi. Lấy bằng
chứng theo đúng SHA/run, không lấy số test local làm trạng thái GitHub.”

### 19. Có fairness hoặc Responsible AI gate chưa?

**Hiệp:** “DAG sinh RAI report nhưng candidate endpoint lifecycle mới chưa enforce
cờ fairness legacy. Chưa có demographic labels đủ để tuyên bố fairness. Nhóm ghi
đây là limitation cần xử lý trước pilot, không trình bày report generation như gate
đã được thực thi.”

### 20. Tại sao không tự retrain encoder cho đầy đủ?

**Dương:** “Phạm vi hiện có là threshold calibration vì thiếu raw data và trainer
được kiểm chứng cho encoder fine-tuning. Huấn luyện encoder cần consented dataset,
identity splits, compute, đánh giá và serving compatibility riêng. Nhóm hoàn thiện
lifecycle thật cho policy hiện có trước khi mở rộng loại model.”

### 21. Tính mới hoặc giá trị môn học nằm ở đâu?

**Dương:** “Giá trị nằm ở tích hợp service và vòng đời có bằng chứng: tenant-scoped
checks, lineage snapshot, reviewed drift decisions, template versioning, guarded
policy rollout và rollback. Nhóm không tuyên bố thuật toán encoder hay PSI/MMD do
mình phát minh. Các pretrained model và thư viện đều có nguồn được ghi trong repo.”

### 22. Chi phí, ROI hay mức giảm cheating là bao nhiêu?

**Đức/Hải:** “Nhóm chưa có phép đo business outcome trên doanh nghiệp thật. Pilot
nên đo thời gian review, tỷ lệ kết luận nhầm, latency, cost theo request và phản hồi
người dùng. Báo cáo tính toán giả định phải ghi rõ giả định, không biến thành số
liệu tiết kiệm đã đạt được.”

### 23. Làm thế nào chứng minh mọi thành viên đóng góp?

**Dương:** “Phân công hiện có trong CONTRIBUTING.md. Bằng chứng cần gồm phần việc
thực tế, PR/review, sản phẩm bàn giao và khả năng giải thích/demo. Metadata Git sau
rewrite không tự chứng minh ai thực hiện phần việc ban đầu. Nhóm cần trình bày
trung thực công việc từng người đã làm và phần đang chịu trách nhiệm.”

## Câu kết sau Q&A

“Nhóm xin ghi nhận các góp ý về dữ liệu thật, fairness gate và kiểm thử tải. Những
phần đó là điều kiện cho pilot tiếp theo. Phạm vi đã trình diễn hôm nay là dịch vụ
xác minh và cơ chế kiểm soát vòng đời policy trên môi trường demo. Nhóm xin cảm ơn.”
