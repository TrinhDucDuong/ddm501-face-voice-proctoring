# Báo cáo cuối kỳ dự án Face Voice Proctoring

FSB – FPT University

DDM501 – AI in DevOps, DataOps, MLOps

**Face and Voice Integrity Service**

Xác minh danh tính và quản lý vòng đời policy sinh trắc học trong kỳ đánh giá ngoại ngữ doanh nghiệp

**Nhóm thực hiện:** Trịnh Đức Dương, Đỗ Quang Hiệp, Tô Thanh Hải, Ngô Anh Đức

**Repository:** https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring

**Ngày hoàn thiện báo cáo:** 05/10/2026

**Phạm vi:** Implementation trong checkout hiện tại, bao gồm cập nhật local. Bằng chứng CI và simulation được ghi theo từng ngày, revision và run; không coi nội dung báo cáo là một lần kiểm chứng runtime mới.

<!-- toc -->

## 1 Tổng quan dự án

Dự án xây dựng dịch vụ xác minh khuôn mặt và giọng nói theo từng batch ảnh/WAV cho doanh nghiệp tổ chức kỳ đánh giá ngoại ngữ. Công ty tiếp tục quản lý tài khoản, bài thi, lịch thu dữ liệu, điểm và quyết định nghiệp vụ. Dịch vụ cung cấp API, webhook và portal để đối chiếu danh tính, trả tín hiệu nghi vấn, lưu bằng chứng phù hợp và hỗ trợ người có thẩm quyền xem xét.

Kết quả chính là một luồng vận hành kết nối dữ liệu, inference, giám sát và cập nhật policy có kiểm soát. Face và Voice dùng encoder pretrained; phần được huấn luyện lại là ngưỡng quyết định, không phải trọng số SFace hoặc ECAPA. Hai modality có reference, quyết định drift, phiên bản MLflow và trạng thái rollout riêng. Một thay đổi của Voice không mặc nhiên yêu cầu cập nhật Face.

Pipeline tạo candidate từ snapshot có phiên bản, đánh giá candidate với champion trên cùng holdout, rồi thực hiện shadow và canary trước khi đổi champion. Monitoring phân biệt thay đổi chất lượng capture, embedding, similarity score, performance có nhãn và tuổi template. Drift thống kê đơn lẻ không đủ để retrain. Khi bằng chứng thiếu, hệ thống giữ trạng thái chưa đủ dữ liệu thay vì tự suy ra model khỏe.

Phần simulation minh họa hai outcome: một policy đi qua đủ gate và trở thành champion; một policy bị chặn tại canary vì tăng nhận nhầm. Các kịch bản dùng vector và nhãn tổng hợp, nhưng thực thi logic quyết định, calibration, HTTP routing, alert receipt và MLflow trong môi trường riêng. Đây là bằng chứng cơ chế MLOps, không phải phép đo accuracy trên nhân viên thật.

| Hạng mục | Kết quả triển khai | Giới hạn cần hiểu |
|---|---|---|
| Sản phẩm | Batch API, portal tenant, enrollment, history, evidence và webhook | Không chấm điểm hoặc tự kết luận gian lận |
| ML lifecycle | Hai threshold policy độc lập, offline, shadow, canary và rollback | Chưa fine-tune encoder |
| Vận hành | Airflow, MLflow, MinIO, Prometheus, Grafana và CI/CD | Docker Compose trên một host |
| Kiểm chứng | CI theo SHA, tests và bốn run simulation lưu ngày 04/10 | Chưa chứng minh chất lượng hay tải production |

Nguồn đối chiếu: README, ARCHITECTURE, MODALITY_LIFECYCLE và EVIDENCE [S1–S4].

## 2 Bài toán nghiệp vụ và yêu cầu

### 2.1 Câu chuyện bắt đầu dự án

Giả sử 08:55 một nhân viên đăng nhập đúng tài khoản để làm bài đánh giá ngoại ngữ. Đến phần nói, người khác có năng lực tốt hơn hỗ trợ hoặc làm thay. Hệ thống thi vẫn nhận bài làm dưới tài khoản ban đầu. Khi kết quả được dùng cho đào tạo hoặc phân công công việc, sai lệch danh tính có thể làm sai lệch quyết định nhân sự. Đây là tình huống giả định để xác định yêu cầu, không phải sự cố đã đo tại một khách hàng.

Ba khó khăn cần xử lý là xác minh người đang cung cấp capture, giảm công sức tìm lại bằng chứng và hạn chế kết luận nhầm. Camera tối, micro kém hoặc mẫu ghi danh cũ có thể làm similarity giảm dù nhân viên trung thực. Vì vậy, chỉ trả một nhãn đúng/sai là chưa đủ; hệ thống cần phiên bản policy, chất lượng capture, reason codes và thông tin về những detector chưa đánh giá được.

### 2.2 Người dùng và ranh giới trách nhiệm

Quản trị công ty quản lý nhân viên, ghi danh, quyền tích hợp và lịch sử của tenant mình. Backend khách hàng xác thực nhân viên, quyết định thời điểm gửi ảnh/WAV và xử lý kết quả nghiệp vụ. Platform operator quản lý tenant, model lifecycle, monitoring và hạ tầng. Trang employee demo mô phỏng tích hợp phía khách hàng; bộ chọn tên trên đó không phải hệ thống xác thực nhân viên đủ điều kiện dùng thật.

| Nhóm yêu cầu | Yêu cầu cụ thể | Cách kiểm tra |
|---|---|---|
| Chức năng | So khớp Face/Voice, integrity signals, lịch sử và callback | Request, response và canonical check cùng nội dung |
| Dữ liệu | Tenant isolation, idempotency, lineage snapshot | Cross-tenant bị chặn; retry không tạo kết quả mới |
| Model | So cùng holdout, không promote trực tiếp, rollback có audit | State, aliases và phiên bản trả trong response |
| Vận hành | Health, readiness, freshness, logs và alerts | Theo dõi cả service lẫn bằng chứng model |
| An toàn | Labels độc lập, consent, limited raw retention | Không dùng dự đoán làm ground truth |

Phạm vi chưa gồm giám sát video liên tục, phát hiện mọi cách nhắc bài, mọi deepfake hoặc quyết định kỷ luật. Đăng ký/subscription của demo chưa có thanh toán hay xác minh pháp nhân [S1, S5].

## 3 Mục tiêu và tiêu chí thành công

Mục tiêu nghiệp vụ là cung cấp bằng chứng đúng lúc để hỗ trợ review, không phải tối đa hóa số nhân viên bị gắn cờ. Mục tiêu kỹ thuật là tái lập được dữ liệu và model đã tạo ra một quyết định, giữ dịch vụ quan sát được và kiểm soát rủi ro khi cập nhật policy. Chất lượng model phải được đánh giá bằng nhãn độc lập, tách khỏi HTTP availability.

| Cấp mục tiêu | Chỉ số hoặc tiêu chí | Trạng thái |
|---|---|---|
| Nghiệp vụ | Thời gian review, tỷ lệ nghi vấn được xác nhận, sai sót ảnh hưởng người thật | Chưa đo tại khách hàng |
| API | Canonical response, tenant isolation, idempotency, signed delivery | Có implementation và tests |
| Chất lượng policy | FMR, FNMR, EER và TAR tại FAR cấu hình | Có phương pháp; thiếu benchmark production đại diện |
| Rollout | Đủ mẫu, thời gian, nhãn; không tăng FMR; có rollback | Có state machine và simulation |
| CI | Coverage ít nhất 80% trong phạm vi khai báo; Windows preflight thực thi | Đối chiếu artifacts đúng run |
| Quy mô | Khoảng 50.000 nhân viên được quản lý | Mục tiêu thiết kế, chưa load test chứng minh |

Một pilot có thể đo giảm thời gian review trên 1.000 lượt đánh giá, thời gian xử lý một nghi vấn, tỷ lệ recapture và chi phí mỗi check. Các mục tiêu kinh doanh trong SCALABILITY_COST là giả thuyết cần kiểm chứng, không phải ROI đã đạt được. FMR không vượt 1% và FNMR không vượt 5% là cấu hình pilot của gate hiện tại, không phải bảo đảm thống kê cho toàn bộ dân số.

Khi không có đủ impostor labels, không thể suy FMR thấp chỉ từ nhiều genuine samples được accept. Tương tự, không phát hiện lỗi trong một demo nhỏ không đủ để tuyên bố dịch vụ đáp ứng 50.000 người hoặc công bằng giữa các nhóm [S3, S6].

## 4 Kiến trúc hệ thống và quyết định thiết kế

<!-- figure: architecture -->

Hệ thống triển khai bằng Docker Compose trên một máy. FastAPI chứa xử lý Face/Voice và các integrity inspectors; đây là các capability trong cùng serving container, không phải mỗi model có một server riêng. PostgreSQL giữ dữ liệu ứng dụng và trạng thái lifecycle. MLflow là registry; database điều phối routing, trạng thái và các chuyển tiếp cần phục hồi.

| Thành phần | Trách nhiệm | Đầu ra chính |
|---|---|---|
| FastAPI và Streamlit | Xác minh, quản trị công ty/platform, review | Check, versions, evidence và lịch sử |
| PostgreSQL | Tenant, embedding JSON, template, labels, outbox, lifecycle | Dữ liệu có quan hệ và audit bền vững |
| MinIO | Object storage cho evidence, datasets và artifacts | Object theo scope/fingerprint |
| Airflow | Điều phối monitoring, calibration và simulation | DAG run, task state, training intent |
| MLflow | Tracking và Model Registry | Params, metrics, artifacts, aliases |
| Prometheus và Grafana | Thu metric và trình bày telemetry | Dashboard, query và alert evidence |
| Alertmanager, ops-monitor, Loki | Định tuyến alert, collectors, logs | Thông báo vận hành và dữ liệu điều tra |

PostgreSQL JSON embeddings phù hợp đường verification 1:1 vì hệ thống đã biết person ID, không cần tìm hàng xóm gần nhất trong toàn bộ nhân viên. Việc thêm vector DB chỉ hữu ích khi yêu cầu truy vấn thay đổi hoặc benchmark chỉ ra nhu cầu; đó không phải thành phần hiện có.

Airflow tách khỏi request-serving để inference không phụ thuộc một training task đang chạy. Registry và artifact store tách identity của model khỏi code image. Đổi lại, hệ thống có nhiều dependency hơn một ứng dụng đơn lẻ; cần health, readiness, backup và kiểm tra consistency giữa DB với Registry. CI/CD cập nhật code/container, còn model lifecycle cập nhật threshold policy bên trong API [S2, S7].

## 5 Dữ liệu và quản trị Data Lake

### 5.1 Nguồn và ý nghĩa dữ liệu

Ghi danh cần các capture khác nhau của cùng người, tối thiểu hai ảnh và hai WAV được chấp nhận để hồ sơ sẵn sàng. Raw enrollment mặc định không giữ; embedding và metadata được lưu. Query mới dùng cho xác minh, và nhãn review được lưu riêng với dự đoán để giữ nguyên lịch sử quyết định.

Bootstrap kỹ thuật dùng LFW từ `marcelohaps/lfw` và Speech Commands từ `mteb/speech-commands-mini`, với revision được pin trong `pipeline/bootstrap_demo.py`. Hai nguồn được ghép thành identity tổng hợp; ảnh và giọng nói không được xác nhận thuộc cùng một người thật. Nhãn speaker/identity của dataset hỗ trợ tạo cặp so sánh kỹ thuật, không biến bộ dữ liệu đó thành benchmark Face+Voice doanh nghiệp. Cần xem quyền sử dụng dataset trước khi phân phối hoặc dùng ngoài demo.

Một report validation local lúc 22:37 ngày 04/10/2026, múi giờ Việt Nam, ghi nhận snapshot tenant `demo` như sau. Đây là số của snapshot đã lưu, không phải tổng cố định của database hiện tại.

| Modality | Embedding rows | Identities | Số chiều |
|---|---:|---:|---:|
| Face | 128 | 52 | 128 |
| Voice | 154 | 54 | 192 |
| Tổng rows | 282 | Không cộng identity giữa hai modality | Khác nhau theo encoder |

Report có `valid=true`, không có validation errors; dataset fingerprint bắt đầu `e986b94b66d186b4`. Validation chứng minh cấu trúc đạt điều kiện của code, không chứng minh đại diện dân số. Nguồn: `reports/data-quality.json` [S8].

### 5.2 Lưu trữ và lineage

| Kho | Dữ liệu | Mục đích |
|---|---|---|
| PostgreSQL ứng dụng | People, embedding/template JSON, checks, labels, outbox, rollout audit | Serving 1:1, tenant scope và truy vết |
| PostgreSQL metadata | Airflow và MLflow metadata trong database tương ứng | Run/task/experiment registry state |
| MinIO biometric-samples | Suspicious media, training snapshot/manifest, monitoring scalar inputs/labels/reports | Evidence và Data Lake có phiên bản |
| MinIO MLflow artifacts | Policy JSON, MLmodel, serialized policy, dependencies, metrics/evaluation artifacts | Tái tải và kiểm tra model policy |
| Models của runtime | Weights SFace, ECAPA và detectors pinned | Inference pretrained |
| Simulation volume | SQLite, synthetic datasets, file MLflow và run reports | Demo cách ly dữ liệu |

Snapshot được fingerprint bằng SHA-256, validate và publish trước calibration. Artifact model liên kết dataset/version, modality và intent huấn luyện. Monitoring xuất scalar inputs, labels và report theo tenant/modality/policy version vào MinIO; query vectors không được chép vào các monitoring exports này. Approved training snapshots có thể chứa embeddings và cần chính sách lưu riêng.

`RETAIN_MONITORING_EMBEDDINGS=false` là mặc định. Nếu được phép bật, query vectors mặc định giữ 30 ngày và observation metadata 90 ngày theo lifecycle maintenance. Điều này không tự xóa enrollment, active templates, mọi object MinIO hoặc backup. Suspicious evidence là ngoại lệ của chính sách bỏ raw capture thông thường. Tắt subscription chặn truy cập, không đồng nghĩa xóa dữ liệu [S2, S3, S8].

## 6 Model và phương pháp đánh giá

### 6.1 Input và output theo từng lớp

| Lớp | Input | Xử lý và output |
|---|---|---|
| Face encoder | Ảnh có mặt | YuNet phát hiện/căn chỉnh; SFace trả embedding chuẩn hóa |
| Voice encoder | WAV | Kiểm tra audio, preprocessing; ECAPA-TDNN trả embedding chuẩn hóa |
| So khớp | Query embedding và active templates của person | Max cosine similarity cho từng modality |
| Threshold policy | Similarity và ngưỡng đang được route | Quyết định identity Face/Voice và margins |
| Integrity checks | Media, metadata và context request | PAD, AASIST, face count, reuse, speaker-change signals |
| API contract | Các kết quả trên | verified, suspicious hoặc inconclusive cùng reasons/versions |

Với các vector được chuẩn hóa, similarity là tích vô hướng. Nếu người i có nhiều template, score bằng giá trị cosine lớn nhất giữa query và các template của người đó. Threshold policy trả identity match khi score đạt ngưỡng. Chất lượng capture và integrity signals còn ảnh hưởng kết quả sản phẩm; một identity match không đủ bảo đảm capture sống hoặc hợp lệ.

SFace và ECAPA-TDNN là pretrained, không do nhóm tự train từ đầu. YuNet, MiniFASNet và AASIST cũng dùng model/research code có nguồn và weights pinned. ECAPA được dùng thêm trên segments để tạo heuristic thay người nói. Cơ chế này chưa phải diarization đầy đủ hoặc bằng chứng phát hiện mọi physical replay [S9].

### 6.2 Calibration và tách train validation test

`identity_evaluation` tạo năm partition theo identity với seed 501. Một partition, xấp xỉ 20% identities, được giữ làm holdout. Bốn partition còn lại dùng cho calibration và 4-fold CV. Mỗi vòng CV dùng khoảng 60% toàn bộ identities để chọn ngưỡng, 20% để validation và giữ nguyên 20% holdout ngoài tuning. Final fit dùng toàn bộ phần calibration 80%, sau đó đánh giá trên holdout 20%.

Tỷ lệ trên là theo identity; tỷ lệ số rows có thể khác do mỗi người có số mẫu khác nhau. Scoring genuine dùng một capture làm probe và các capture còn lại cùng identity làm template. Impostor scoring so probe với templates của identity khác. Cách max-template thống nhất với serving, nhưng bộ cặp vẫn chịu bias của nguồn dữ liệu và sampling. Evaluation giới hạn số templates/identity và impostor identity pairs để khống chế chi phí.

Ngưỡng được tìm trên 1.151 giá trị từ -0,2 đến 0,95. Objective hiện hành là minimax: giảm giá trị lớn nhất giữa FAR và FRR, dùng tổng hai sai số làm tiêu chí phụ. CV chọn margin nhỏ nhất đạt budget từ tập cố định 0; 0,002; 0,005; 0,01; 0,02. Holdout không tham gia chọn margin. Budget 20% trong calibration/CV nội bộ không phải gate promotion 1%/5% của lifecycle [S10].

### 6.3 Metrics và diễn giải

**FMR = false accepts / impostor attempts. FNMR = false rejects / genuine attempts.** Trong các báo cáo kỹ thuật, FAR/FRR được dùng tương ứng cho tỷ lệ nhận nhầm/từ chối nhầm ở đường identity. Chúng không đo trực tiếp tỷ lệ bỏ sót mọi hình thức gian lận.

EER là ước lượng điểm giao của hai error rates khi quét ngưỡng. TAR tại FAR cấu hình là tỷ lệ genuine được accept tốt nhất thỏa budget FAR trên mẫu đánh giá. Với threshold-only policies dùng cùng scores, EER/TAR@FAR có thể bằng nhau trong khi FMR/FNMR ở ngưỡng phục vụ khác nhau. Do đó, cần đọc cả score separability và operating threshold, không chỉ chọn một metric thuận lợi.

## 7 Serving và luồng sử dụng sản phẩm

Backend khách hàng gửi `POST /v1/checks` với person ID, session ID, request ID, consent, ảnh và WAV; xác thực bằng integration key. Person binding phải xuất phát từ đăng nhập hợp lệ của hệ thống khách hàng. API key của tenant không được đưa vào browser của nhân viên.

Luồng xử lý gồm xác thực tenant và payload, kiểm tra idempotency, đọc active templates, chạy encoders/inspectors, chọn policy Face/Voice, tạo kết quả và lưu check/event/outbox. API trả canonical result ngay. Webhook worker gửi cùng kết quả qua callback được allowlist, ký HMAC với timestamp, và retry độc lập với request đầu vào. Receiver cần kiểm tra chữ ký, chống replay và deduplicate delivery ID vì delivery là at-least-once.

| Tình huống | Hành vi cần giữ |
|---|---|
| Cùng request ID và payload | Trả kết quả đã có, không tạo check mới |
| Cùng request ID nhưng payload khác | Conflict 409 |
| Truy cập check/evidence tenant khác | Bị chặn, thường trả 404 theo contract |
| Identity mismatch hoặc integrity signal đáng ngờ | Suspicious cùng reasons, không tự kết tội |
| Thiếu detector hoặc không đủ dữ liệu đánh giá | Inconclusive/capability unavailable theo kết quả tổng hợp |
| Webhook chưa giao được | Giữ check và outbox để retry |
| Evidence storage lỗi | Ghi rõ partial/unavailable, không giả định media đã lưu |

Check metadata và outbox có transaction PostgreSQL, nhưng object write MinIO không phải cùng một transaction ACID. Nếu database thất bại sau upload, có thể còn object mồ côi; cần reconciliation/retention khi phát triển production. Portal tenant chỉ đọc lịch sử/bằng chứng được phép, có lọc session, person và thời gian, xuất CSV/PDF.

`/health` xác nhận service sống, còn `/ready` kiểm tra điều kiện phục vụ model. Installation registry rỗng có thể health 200 và ready 503. Readiness không thay thế đánh giá chất lượng sinh trắc, và việc handler có trả HTTP 200 không chứng minh mọi capability đã pass [S5, S7].

## 8 Airflow và pipeline huấn luyện

Airflow là bộ điều phối các bước, không phải thuật toán train; MLflow theo dõi experiment và Registry, không tự quyết định khi nào retrain. Python pipeline thực hiện snapshot, validation, calibration và evaluation. Ba DAG có trách nhiệm khác nhau.

| DAG | Lịch | Trách nhiệm |
|---|---|---|
| biometric_monitoring_pipeline | Mỗi giờ | Bootstrap incumbent hợp lệ, đánh giá drift, tick rollout và phát training intent đủ điều kiện |
| biometric_model_pipeline | schedule=None | Hiệu chỉnh threshold cho Face hoặc Voice được yêu cầu |
| biometric_simulation | Poll mỗi phút | Nhận job demo, thực thi drift/alert/train/offline/shadow/canary |

Model DAG nhận modality và window ID trong DagRun conf. Nó có bảy task theo thứ tự dưới đây, không có lịch weekly train vô điều kiện.

| Bước | Task ID | Hành vi thực tế |
|---|---|---|
| 1 | ingest_versioned_snapshot | Đóng băng snapshot và provenance |
| 2 | validate_data_quality | Kiểm tra vector, dimension, sample/identity và dữ liệu hợp lệ |
| 3 | publish_versioned_dataset | Lưu dataset/manifest trong MinIO |
| 4 | feature_engineer_train_register_candidate | Calibration modality và đăng ký candidate MLflow |
| 5 | generate_responsible_ai_audit | Sinh report RAI theo dữ liệu có sẵn |
| 6 | evaluate_and_promote_candidate | Offline gate; đạt thì khởi động challenger/shadow |
| 7 | reload_current_champion | Lifecycle tick; tên legacy không có nghĩa luôn đổi champion |

Monitoring không train bên trong code tính drift. Nó tạo intent xác định theo modality/window, lifecycle service dùng row lock và state để tránh job trùng. Retry cùng intent không tạo một chuỗi training độc lập. Training thất bại được ghi trạng thái rejected qua callback. Face và Voice độc lập về claim, dù tài nguyên Airflow/host vẫn dùng chung.

Training hiện chỉ cho tenant `demo`; `data_snapshot.py` từ chối tenant khác. Thay biến môi trường chưa đủ để dùng dữ liệu khách hàng: cần triển khai phạm vi dữ liệu, consent enforcement và kiểm thử isolation. Bootstrap lifecycle chỉ chuyển incumbent bundle đã đăng ký sang hai policy; nó không tạo một champion đã đánh giá từ `local-default` [S3, S11].

## 9 Drift monitoring và decision engine

### 9.1 Tổ chức cửa sổ dữ liệu

Lifecycle so reference với current riêng theo tenant, modality và policy version. Default là 100 observations mỗi cửa sổ. Reference được đóng băng; current lấy các observations về sau. Encoder phải phù hợp và identity-set overlap ít nhất 80%; quality/embedding/score comparison dựa trên identities chung để giảm nhiễu do đổi population. Điều kiện này không loại bỏ mọi sampling bias.

Nếu database chỉ có 100 observations hợp lệ và chưa có reference, chưa đủ tạo hai cửa sổ 100+100 để kết luận drift. Nếu đã có reference độc lập 100 mẫu từ trước, 100 mẫu mới có thể tạo một phép so sánh, nhưng vẫn cần vector, quality và labels phù hợp. Refresh cùng cửa sổ ba lần không phải ba cửa sổ mới.

### 9.2 Năm lớp bằng chứng

| Lớp | Feature hoặc input | Phương pháp và output |
|---|---|---|
| Quality | Face brightness, contrast, blur, resolution, detector confidence/area khi có; Voice duration, RMS, clipping, silence, sample rate | PSI từng scalar; quality score là max PSI hợp lệ |
| Embedding | Vector chuẩn hóa cùng encoder | RBF MMD bình phương, tối đa 512 vector/cửa sổ |
| Verification score | Similarity genuine và impostor có trusted labels | PSI riêng, mean/std/quantiles, margin và separation |
| Performance | Labels độc lập và score/threshold đã ghi | FMR, FNMR, EER, TAR@FAR; thiếu labels báo insufficient |
| Template age | Tuổi active template hoặc enrollment gốc | Sample counts, genuine score và error rates theo age bucket |

PSI được tính theo **PSI = Σᵢ (cᵢ − rᵢ) ln(cᵢ/rᵢ)**, với rᵢ và cᵢ là tỷ lệ reference/current trong bin i. Implementation dùng 10 bins theo quantile reference và clip probability tại 10⁻⁶ để tránh log(0). Giá trị lớn hơn 0,2 được xem là drift theo cấu hình. Các feature SNR, yaw/pitch/roll hoặc occlusion chưa đo được thì không được tự thêm vào report. Silence ratio là đo theo biên độ, chưa phải neural VAD.

Embedding drift dùng **MMD² = mean(Krr) + mean(Kcc) − 2 mean(Krc)** với **K(x,y) = exp(−‖x−y‖²/2)** trên vector chuẩn hóa. Đây là biased squared MMD có đường chéo, threshold 0,02, không phải kiểm từng dimension hoặc p-value. Tên MMD trong giao diện cần hiểu theo công thức bình phương này.

Score drift tách genuine/impostor dựa trên nhãn tin cậy. Genuine dịch trái hoặc impostor dịch phải có thể thu hẹp độ phân tách. Margin genuine bằng similarity trừ verification threshold; margin thấp cho biết điểm gần biên từ chối. Tuy nhiên, drift score đơn lẻ chưa chứng minh hiệu quả xác minh đã giảm.

Performance yêu cầu ít nhất 20 nhãn genuine và 20 impostor ở mỗi cửa sổ. Degradation được ghi nhận khi FMR hoặc FNMR tăng ít nhất 0,02 tuyệt đối và ít nhất 25% tương đối; baseline bằng 0 dùng điều kiện tuyệt đối. Hai điểm phần trăm tuyệt đối khác với tăng 2% tương đối. Label source phải độc lập với dự đoán, và lifecycle dùng cohort random-audit được server chọn để giảm selection bias.

Tuổi template chia <=30, 31–90, 91–180, 181–365 và >365 ngày. Heuristic aging hiện so nhóm đầu/cuối: recent FNMR <=5%, oldest FNMR >7%, có đủ performance evidence và overall FMR <=1%. Đây chưa phải mô hình tương quan nhân quả; nhóm giữa có thể còn vấn đề. Cross-age degradation yêu cầu ít nhất hai buckets vượt budget FMR/FNMR [S3, S12].

### 9.3 Quyết định và persistence

| Bằng chứng | Trạng thái | Hành động |
|---|---|---|
| Quality drift | INPUT_DRIFT | Điều tra capture, không tự retrain |
| Thiếu nhãn/vector hoặc cohorts không phù hợp | INSUFFICIENT_DATA | Thu thêm dữ liệu, không coi performance khỏe |
| Aging heuristic và performance degraded | TEMPLATE_UPDATE_REQUIRED | Chờ persistence và template evidence gate |
| Embedding và score drift kéo dài, cross-age performance degraded | RETRAIN_REQUIRED | Xem cooldown, dữ liệu mới và idle lifecycle trước khi phát intent |
| Chỉ score/embedding drift | SCORE_DRIFT hoặc EMBEDDING_DRIFT | Theo dõi thêm |
| Performance giảm nhưng chưa đủ nguyên nhân | MONITOR | Điều tra thay vì thay model ngay |
| Các bằng chứng đo được trong giới hạn | HEALTHY | Tiếp tục giám sát |

Mỗi modality có persistence riêng. Một cửa sổ chỉ được tính mới khi có ít nhất một window đầy observations IDs mới kể từ lần đếm trước. Retrain cần ba cửa sổ mới đủ điều kiện, ít nhất 40 reviewed observations mới, cooldown 24 giờ, đủ identities và lifecycle không đang training/rollout. Hệ thống ưu tiên xử lý input/template trước model; statistical drift không trực tiếp gọi train.

Output là structured report gồm modality, model version, windows, quality feature PSI, MMD², score summaries, performance status, age buckets, persistence, decision và reasons. Report và audit giúp giải thích tại sao hành động xảy ra hoặc bị chặn. Khi vector retention tắt, tự động hóa có thể dừng ở insufficient evidence dù đồ thị score vẫn có dữ liệu.

## 10 Cập nhật template có kiểm soát

Template đại diện người dùng khác với threshold policy dùng cho modality. Thay template nhằm cập nhật mẫu tham chiếu của một người; calibration thay biên quyết định của model policy. Một nhân viên thay đổi ngoại hình hoặc giọng theo thời gian không mặc nhiên đòi retrain encoder cho toàn hệ thống.

Khi có bằng chứng aging, workflow không lấy capture mới nhất đã accept để thay mẫu ngay. Candidate cần nhiều observations có modality labels tin cậy, media hashes khác nhau, capture integrity hợp lệ, chất lượng cao, score đủ xa threshold và không có conflict danh tính. Defaults là ít nhất 10 creation observations, quality >=0,7, margin >=0,1 và consistency >=0,85.

Candidate template thêm centroid chuẩn hóa từ observations vào template set hiện có, giới hạn tám templates/person/modality và giữ enrollment gốc. Holdout loại creation hashes, cần ít nhất 20 genuine và 20 impostor labels. FMR không được tăng hoặc vượt 1%; FNMR không được xấu đi. Không đủ confidence thì giữ PENDING_REVIEW.

Activation chờ model lifecycle idle và evidence phù hợp champion, khóa person row, ghi TemplateVersion rồi đổi ActiveTemplate pointer. Phiên bản trước được giữ để operator rollback. Authorized enrollment mới cũng cập nhật template version phù hợp, tránh để con trỏ serving bỏ qua mẫu vừa ghi danh. Hệ thống chưa có vòng tự động theo dõi để rollback template sau activation; endpoint rollback là thao tác riêng của platform [S3, S13].

## 11 MLflow và triển khai policy có trạng thái

<!-- figure: lifecycle -->

### 11.1 Registry và ý nghĩa champion

Production MLflow quản lý hai registered models `face-verification` và `voice-verification`. Alias candidate xác định phiên bản vừa đăng ký; challenger là phiên bản qua offline gate và đang thử; champion là policy được chấp nhận phục vụ theo bằng chứng/gate; previous_champion giữ phiên bản trước. Đây là vai trò trong cùng lifecycle, không đơn thuần là alias môi trường dev/test/prod.

`face-voice-risk-bundle` là policy bundle legacy và nguồn incumbent cho migration, không phải template hay encoder. Khi independent lifecycle đã khởi tạo, routing dùng trạng thái ModalityDeployment trong DB. MLflow giữ model identity/artifacts; DB giữ traffic, stage time, revision và audit. Chỉ đổi alias thủ công không đủ để đảm bảo serving routing cũng đổi đúng.

Candidate và champion được đánh giá trên cùng holdout, gồm class counts, FMR/FNMR và các chỉ số supporting. Candidate giảm FNMR nhưng tăng FMR bị security regression gate chặn. Gate chấp nhận theo tiêu chí cấu hình, không chứng minh candidate tốt nhất với mọi dữ liệu tương lai hoặc luôn thắng tuyệt đối tất cả metrics.

### 11.2 Shadow và canary

Shadow tính decisions của hai policy trên cùng similarity, ghi versions, thresholds, latency và disagreement, nhưng response thật vẫn theo champion. Hai policy dùng chung encoder nên score delta bằng 0; thay threshold vẫn tạo decision disagreement. Policy p95 latency không phải thời gian end-to-end upload, encoder và inspectors.

Canary dùng hash ổn định theo modality, deployment, tenant, person và session để chọn cohort nhận challenger. Stages mặc định 5%, 10%, 25%, 50%, 100%; tỷ lệ quan sát ở mẫu nhỏ không nhất thiết đúng bằng phần trăm cấu hình. Gate production chỉ dùng candidate-served observations sau thời điểm bắt đầu stage hiện tại; labels đến muộn được xét khi lifecycle tick.

| Điều kiện mỗi shadow hoặc canary stage | Default production/pilot |
|---|---:|
| Số observations và thời gian tối thiểu | 1.000 và 3.600 giây |
| Trusted labels tối thiểu mỗi class | 30 |
| FMR / FNMR tối đa | 0,01 / 0,05 |
| FMR regression cho phép | 0 |
| FNMR regression cho phép | 0,005 |
| Policy p95 / disagreement tối đa | 10 ms / 0,1 |
| Cohort quality sample threshold | 20 |

Thiếu dữ liệu thì chờ, không coi chưa thấy lỗi là pass. Gate xét cả cohorts để tránh pooled metric che khuất suy giảm một nhóm. Rollout đang diễn ra được lưu bằng state, không suy từ log text [S3, S14].

### 11.3 Promotion và rollback

Fail canary đặt challenger traffic về 0, giữ champion và lưu metric, observed value, limit, timestamp, stage, model version. Model lỗi vẫn tồn tại trong MLflow phục vụ audit. Một candidate rejected không tự retry promotion chỉ vì được polling lại.

Pass stage cuối mới ghi durable PROMOTING intent, reconcile aliases Registry, rồi commit champion mới trong DB. Nếu external call bị gián đoạn, retry tiếp tục intent đó; serving giữ incumbent đến lúc DB switch hoàn tất. Đây là chuyển tiếp có thể phục hồi, không phải transaction ACID xuyên PostgreSQL và MLflow.

Rollback khi rollout đang chạy giữ incumbent; rollback sau promotion có thể khôi phục previous version. Label-dependent gates chạy theo tick hàng giờ, không bảo đảm phản ứng tức thì lúc một nhãn vừa được nhập. System failure/invalid policy có đường dừng rollout sớm, nhưng khi DB mất kết nối không thể ghi state bền vững ngay. In-flight responses không bị thu hồi. Application rollback là quy trình khác với policy rollback.

## 12 Monitoring và cảnh báo

Prometheus scrape mỗi 15 giây từ API, webhook-worker, drift-monitor, ops-monitor và simulation. API/worker xuất số liệu request, decisions, latency và delivery. ops-monitor lấy thông tin từ PostgreSQL, MLflow, Airflow, health probes và Docker read-only proxy rồi xuất metric. Alloy chuyển logs tới Loki. Grafana query metric, không tự thực hiện calibration hoặc drift decision.

Hai dashboard hiện hành đều có 10 panel dùng Prometheus. System Overview tập trung readiness, active incidents, traffic, 5xx, verify p95, CPU/RAM, outbox, modality drift, human FAR/FRR và pipeline/lifecycle freshness. Simulation hiển thị synthetic baseline/drift, persistence, alert, offline, routed samples, candidate errors, latency, outcome/reset. PostgreSQL, Loki và Alertmanager còn được provision cho Explore/điều tra; chúng không phải datasource của các panel hiện hành.

Operational `drift-monitor` chạy mỗi 60 giây trên verification events/feedback. Nó tính custom PSI cho face_score, voice_score, face_quality, voice_quality và risk_score; Evidently DataDriftPreset chọn phương pháp theo dữ liệu. Vì vậy không gọi mọi giá trị Evidently là PSI. Performance reports dùng ClassificationPreset và FAR/FRR bổ sung, tách operator human feedback khỏi legacy synthetic-simulation feedback.

| Nơi xem | Nội dung và lưu ý |
|---|---|
| Grafana System Overview | Telemetry tổng quan; No data cần xem freshness/labels |
| Grafana Simulation | Evidence tổng hợp; snapshot sau reset vẫn là lịch sử |
| Reports qua Grafana gateway | data-drift, model-performance, synthetic-performance, data-quality, model-evaluation, pipeline-status, responsible-ai, alerts |
| Prometheus Query và Targets | Nhập query như up để xem metric; trang trống khi chưa query không phải mất dữ liệu |
| Alertmanager | Nhóm và định tuyến firing/resolved alerts |
| Lifecycle API và MLflow | State và versions thực tế; report bundle legacy không đủ chứng minh rollout modality |

Prometheus rules gửi alert đến Alertmanager. Production alerts đi qua ops-monitor tới Telegram nếu cấu hình; simulation alert gửi receiver riêng và không gửi Telegram. Business check result đi API/webhook cho công ty, không gửi Telegram theo từng nhân viên. Vòng Evidently là báo cáo vận hành, không tạo thêm một retrain trigger độc lập bên cạnh Airflow decision path.

Không dùng employee IDs, raw media hay embedding vectors làm Prometheus labels. Mẫu số, nhãn và freshness là điều kiện diễn giải performance; hệ thống có thể scrape UP nhưng report chưa đủ bằng chứng [S15].

## 13 CI CD và triển khai ứng dụng

Workflow FSB chạy quality trên GitHub-hosted Ubuntu, deployment-preflight trên Windows, build containers trên Ubuntu và deploy-demo trên self-hosted Linux WSL. Windows job chạy hai test staging đúng SHA/reject mismatch với runtime tạm, không cần Docker daemon; JUnit phải không skip/failure/error. Quality xanh ở Ubuntu không chứng minh hai test Windows đã chạy.

| Job | Nội dung | Bằng chứng |
|---|---|---|
| quality | Ruff, compile, generated dashboard consistency, pytest/coverage, Compose config | quality-evidence chứa JUnit và coverage |
| deployment-preflight | Hai test Windows bắt buộc thực thi | deployment-preflight-evidence |
| containers | Build service images sau hai job trên | Build logs |
| deploy-demo | Trusted main, runner Linux WSL gọi PowerShell/Docker Desktop | deployment-monitoring-evidence |

Runner deploy dùng nhãn self-hosted, Linux, ddm501-linux-demo. Workflow chuyển đúng checkout sang Windows, kiểm tra full SHA, stage release ngoài OneDrive và giữ runtime secrets, project name, volumes, models/data/reports. Đây là application replacement trên một Docker Compose host, có thể có gián đoạn; chưa có application canary nhiều replica, ALB hoặc Kubernetes. Canary của dự án hiện nằm ở lớp threshold policy trong API.

PR không deploy lên runner local. Push chỉ thay Markdown hoặc docs bị path filter loại khỏi tự động chạy workflow; PR/manual dispatch vẫn có thể chạy CI, và deploy thủ công cần điều kiện main cùng input deploy. Coverage gate 80% chỉ áp dụng phạm vi module khai báo trong workflow, không đo đầy đủ UI, DAG, CLI, pretrained weights hoặc chất lượng sinh trắc [S7, S16].

## 14 Kiểm thử và kết quả kiểm chứng

### 14.1 Chiến lược kiểm thử

Các tests bao phủ API/tenant, media validation, idempotency, immutable events, outbox, snapshot/evaluation, drift persistence, template poisoning safeguards, retention, lifecycle routing, canary failure và registry integration. MLflow integration test kiểm tra registration, aliases, reconciliation và rollback bằng registry local; phần dữ liệu/labels vẫn là fixtures tổng hợp. Tests SQLite hoặc local không thay load/concurrency tests trên PostgreSQL production.

| Nhóm | Hành vi quan trọng | Nguồn |
|---|---|---|
| Drift | Input drift không train; thiếu labels không healthy; distinct windows | test_drift_decision.py |
| Serving lifecycle | Shadow giữ response champion; canary/rollback route đúng | test_live_lifecycle.py |
| Template | Candidate evidence, holdout và rollback | test_template_lifecycle.py |
| Registry | Alias độc lập, registration và interrupted promotion recovery | test_lifecycle_registry_integration.py |
| Monitoring/simulation | Aggregate telemetry, synthetic scenarios và reset | test_lifecycle_monitoring.py, test_simulation.py |
| Deployment | Exact-SHA staging và mismatch rejection | test_deploy_local.py |

### 14.2 Bằng chứng CI đã ghi nhận

Run FSB **37176107308** cho revision **22f64daa7f31181130d5b1355c97eb62eeac5ab6** được ghi nhận ngày 04/10/2026: quality, deployment-preflight, containers và deploy-demo success. Ubuntu ghi nhận 161 test cases với 2 skip; Windows thực thi 2 test không skip. Deploy kiểm tra 20 queries của dashboard tổng quan. Link run nằm trong phụ lục nguồn [S4, S16].

Đợt local bổ sung monitoring simulation cùng ngày ghi nhận 163 tests pass và dashboard simulation 10 panel/17 queries có giá trị hữu hạn. Các kết quả thuộc revision/worktree tại thời điểm đó; không gộp chúng thành số test của một run CI mới, không đổi ngày kiểm chứng sang ngày viết báo cáo. Không có rerun full test hoặc redeploy được thực hiện chỉ để soạn báo cáo này.

### 14.3 Bốn run simulation có lưu evidence

| Modality | Scenario | Outcome | Run ID |
|---|---|---|---|
| Voice | Promotion | SUCCEEDED, reset PASS | 06dcd24d-0bfe-4667-9791-924456653862 |
| Face | Rollback | ROLLED_BACK, reset PASS | 1e17fc9a-9db7-4fa6-b57a-a6130356a7c4 |
| Face | Promotion | SUCCEEDED, reset PASS | f819f41e-9254-44bf-8e69-d605b2f6e7c6 |
| Voice | Rollback | ROLLED_BACK, reset PASS | 1187a0ca-45cb-4ff0-a251-a5aeb088c626 |

`simulation-verification.json` ghi status PASS, synthetic=true và production_policies_unchanged=true. Đây là phép đối chiếu đã lưu của bốn run ngày 04/10, không khẳng định runtime ở mọi thời điểm đều không thay đổi. Reports local được gitignore nên clone mới không mặc nhiên chứa chúng [S17].

## 15 Simulation và minh họa kết quả

### 15.1 Cách dựng và tính cách ly

Simulation nhận yêu cầu từ platform portal, dùng SQLite, file-backed MLflow và volume riêng. Nó không nhận production DB/MinIO credentials hoặc model weights. Airflow, Prometheus, Alertmanager và host được dùng chung nên vẫn có thể tranh chấp CPU/RAM. Synthetic artifacts ở simulation volume, không lưu vào production MinIO.

Generator tạo vector unit 201 chiều và genuine/impostor truth tổng hợp; không chạy raw ảnh/WAV qua encoder. Nó dựng ba cửa sổ drift mới với chất lượng ổn định, embedding/score shift và performance degradation ở nhiều age cohorts. Baseline threshold là 0,8. Sau khi nhận alert thật của đúng run từ Alertmanager, pipeline mới calibration và đăng ký candidate. Ngưỡng mới là kết quả thuật toán, không gán cứng làm outcome promotion.

Demo dùng gates rút ngắn: 200 HTTP requests/stage, minimum 5 giây theo mặc định, 20 labels/class và disagreement allowance 0,6. Runtime preview có thể tăng thời gian stage; cần đọc limits của run. Production giữ 1.000 observations, 3.600 giây, 30 labels/class và disagreement 0,1. Không lấy thời gian hoàn tất demo để suy thời gian rollout production.

### 15.2 Promotion Face trên dữ liệu tổng hợp

Run Face promotion `f819f41e-9254-44bf-8e69-d605b2f6e7c6` có threshold candidate xấp xỉ 0,401. Paired offline holdout gồm 30 genuine và 45 impostor comparisons: champion FMR 0, FNMR 1; candidate FMR 0, FNMR 0. EER của cả hai bằng 0 vì scores vẫn phân tách được; champion chỉ dùng ngưỡng quá cao đối với phân phối được dựng. Kết quả này minh họa threshold adaptation, không phải encoder đã học tốt hơn.

| Stage | Tổng HTTP requests | Requests dùng challenger |
|---|---:|---:|
| Shadow | 200 | 0 |
| Canary 5% | 200 | 12 |
| Canary 10% | 200 | 20 |
| Canary 25% | 200 | 58 |
| Canary 50% | 200 | 113 |
| Canary 100% | 200 | 200 |

Không có response_mismatches trong các stage đã lưu. Sau promotion, 200 probes dùng version 2. Routed counts là bằng chứng request thực chọn policy; chúng có thể khác tỷ lệ cấu hình do cohort/hash và cỡ mẫu. Không yêu cầu một run khác tái tạo đúng các số 12/20/58/113.

### 15.3 Rollback Voice khi tăng nhận nhầm

Run Voice rollback `1187a0ca-45cb-4ff0-a251-a5aeb088c626` qua offline/shadow và canary đầu, sau đó chủ động tiêm impostor score cao ở 25%. Challenger FMR trên evaluation của stage tăng lên 1, trong khi champion FMR bằng 0. Gate dừng challenger; rollback probe ghi 200 samples, served_candidate=0 và chỉ version 1. Outcome ROLLED_BACK là thành công của kịch bản kiểm tra chặn lỗi, không phải model mới được promote.

Baseline được dựng để minh họa drift nên champion có thể có FNMR xấu trên dữ liệu shifted ngay cả khi được giữ lại vì an toàn FMR. Rollback giảm rủi ro update mới, không tự chữa nguyên nhân dữ liệu hoặc chứng minh incumbent hoàn hảo. Đây là điểm phải giải thích khi trình diễn.

### 15.4 Ba thao tác demo và điều kiện hoàn tất

Nút thứ nhất chạy drift dẫn tới promotion; nút thứ hai tiêm lỗi canary để rollback; nút thứ ba cancel/reset routing và aliases simulation về baseline, giữ audit. Reset không xóa tenant/checks đã tạo ở phần demo sản phẩm. Sau mỗi run, cần xuất JSON, đối chiếu run ID giữa portal/Airflow, xem model simulation tại MLflow :15031 và xác nhận reset hoàn tất.

Buổi bảo vệ tổ chức 15 phút trình bày, 10–15 phút demo và 10 phút Q&A. Khi scheduler chậm hoặc alert chưa đến, trình bày đúng trạng thái đang chờ; có thể dùng evidence đã lưu và nói rõ ngày/run. Không hạ gate, relabel synthetic thành human hoặc sửa production alias để buổi demo trông thành công [S17, S18].

## 16 Responsible AI và bảo vệ dữ liệu

### 16.1 Fairness và chất lượng bằng chứng

RAI report đo accuracy/FAR/FRR theo các quality slices thấp, trung bình, cao. So sánh human slices cần ít nhất 20 labels/slice, gồm ít nhất 5 genuine và 5 impostor. Accuracy gap lớn hơn 10 điểm phần trăm được flag; Wilson 95% intervals thể hiện bất định của error rates. Quality slice là proxy cho điều kiện capture, không phải demographic fairness theo giới, tuổi hoặc nhóm dân số.

DAG sinh RAI report trước offline gate, nhưng endpoint candidate của lifecycle modality hiện chưa enforce `REQUIRE_HUMAN_FAIRNESS`. Cờ đó áp dụng cho gate bundle legacy. Vì vậy chưa được tuyên bố fairness là gate tự động đã chặn promotion trong luồng mới. Cần bổ sung enforcement và benchmark consented phù hợp trước pilot.

### 16.2 Explainability và human oversight

Responses có scores, thresholds, versions, reasons và margins. Đường policy explanation hỗ trợ sensitivity quanh ngưỡng ±0,05 và counterfactual một modality trong khi giữ các điều kiện khác. Đây là giải thích quy tắc quyết định, không phải SHAP/LIME hoặc giải thích nhân quả bên trong encoder. Risk score không được diễn giải thành xác suất nhân viên gian lận đã hiệu chuẩn.

Human review phải tách identity truth của Face/Voice khỏi phán xét gian lận tổng thể. Random audit giảm bias so với chỉ review suspicious, nhưng không loại hết bias. Dịch vụ trả tín hiệu hỗ trợ; quy trình recapture, appeal và quyết định ảnh hưởng nhân viên cần do khách hàng thiết kế. Hosted compatibility có manual review nhưng chưa có đầy đủ case-management/appeal cho khách hàng.

### 16.3 Privacy và security

Biometric embeddings là dữ liệu nhạy cảm, không phải dữ liệu vô danh. Consent assertions và tenant scoping là kiểm soát kỹ thuật; khách hàng còn phải xác định lawful basis, mục đích và thời gian lưu. API keys được hash; webhook có HMAC; evidence download cần quyền phù hợp; secrets không đưa vào source, image hoặc report.

Hệ thống cần hoàn thiện TLS, SSO/RBAC, chính sách mã hóa/KMS, audit truy cập và xóa dữ liệu xuyên PostgreSQL/MinIO/backups trước rollout thật. Deactivation không tương đương erasure. Research detectors chưa đủ benchmark cho physical replay, unseen deepfakes, accent/disability effects hoặc mọi nhóm người dùng. Không mở rộng dữ liệu sang surveillance hay identification 1:N ngoài mục đích đã thống nhất [S6, S9].

## 17 Vận hành phục hồi và quy mô

### 17.1 Cài đặt và readiness

Chuẩn bị Docker Desktop Linux containers/WSL2 và Compose v2; Python 3.11 cho scripts/tests host nếu cần. Clone repository FSB ngoài OneDrive, tạo `.env` từ example chỉ khi chưa có, đổi credentials phù hợp và chạy `docker compose up -d --build --wait --wait-timeout 900`. Model-init tải pinned weights; kiểm tra logs nếu lần đầu chậm. Compose dùng Dockerfile theo service, không có Dockerfile tổng tại root.

Installation rỗng chưa có quy trình một lệnh đánh giá/khởi tạo champion thật. `/health` có thể pass trong khi `/ready` trả 503. Runtime demo đã bàn giao cần giữ hoặc phục hồi backup được phép gồm DB/artifacts/config tương ứng. Simulation tự tạo baseline tổng hợp riêng và không cần thay champion production để chạy demo.

| Trang | Địa chỉ local |
|---|---|
| Portal / employee example | http://localhost:18501 / http://localhost:18600 |
| API docs | http://localhost:18100/docs |
| Airflow | http://localhost:18081 |
| MLflow production / simulation | http://localhost:15030 / http://localhost:15031 |
| Grafana overview | http://localhost:13000/d/biometric-overview |
| Grafana simulation | http://localhost:13000/d/biometric-simulation |
| Prometheus / Alertmanager | http://localhost:19090 / http://localhost:19093 |
| MinIO console | http://localhost:19101 |

Private overlay hiện tắt endpoint simulation legacy, yêu cầu callback HTTPS và đưa legacy-demo vào profile riêng; nó chưa loại bỏ mọi service/DAG simulation kế thừa từ Compose. Vì vậy không gọi overlay này là bản hardening production hoàn chỉnh [S7].

### 17.2 Sự cố và rollback

| Tình huống | Xử lý | Bằng chứng sau xử lý |
|---|---|---|
| Canary regression | Dừng traffic challenger, giữ champion | Failure audit, Registry và routed response |
| Rollback sau promotion | Dùng lifecycle rollback endpoint theo modality | DB champion và MLflow previous/current khớp |
| Template có vấn đề | Operator dùng template rollback endpoint | ActiveTemplate pointer và audit |
| Webhook lỗi | Giữ outbox, retry; receiver deduplicate | Delivery status và canonical check |
| Registry/DB gián đoạn | Phục hồi dependency, reconcile intent | Readiness/state/versions đúng; không suy từ health đơn lẻ |
| App release lỗi | Triển khai release trước phù hợp schema | Health, smoke check, data/volumes được giữ |

Backup phải bao gồm PostgreSQL, MinIO artifacts/evidence cần giữ, weights và config/secrets ở kho riêng. Test restore vào môi trường mới trước khi dùng như kế hoạch phục hồi. Không restore đè lên installation đang phục vụ hoặc dùng `down -v` để reset demo. Code rollback không tự rollback schema/dữ liệu. Automatic application rollback chưa được triển khai như policy gate rollback.

### 17.3 Capacity và cost

50.000 nhân viên được ghi danh khác 50.000 người gửi request đồng thời. Nếu N người đang thi và gửi mỗi 30 giây, arrival rate xấp xỉ N/30 checks/giây. Với 1.000 người đồng thời là 33,3 checks/giây; với 50.000 là 1.666,7 checks/giây. Chưa có load test chứng minh stack local đáp ứng các mức này.

Công thức sizing sơ bộ là workers >= ceil(arrival_rate × CPU_service_time / 0,65), với CPU_service_time phải được đo cho full check gồm encoders và inspectors. Đây chỉ là ước lượng, cần kiểm tra concurrency locks, DB contention, media upload, memory mỗi model cache, p95 và bursts. Một phép đo verify identity đơn lẻ không đại diện full batch latency.

Chi phí tháng gồm compute API/worker/control-plane, DB, storage/requests, network, backup và thời gian human review. Raw media mặc định bỏ giúp giảm dung lượng, nhưng evidence, templates và versioned datasets vẫn tăng. Cửa sổ drift 100 mẫu và overlap 80% có thể không phù hợp population 50.000; cần chọn cohort/window đại diện, không chỉ tăng số replica. Chưa có ROI hoặc cloud bill đã đo [S19].

## 18 Tổ chức nhóm và bàn giao

| Thành viên | Trách nhiệm | Sản phẩm bàn giao cần kiểm tra |
|---|---|---|
| Trịnh Đức Dương | Project lead, kiến trúc và core biometric/lifecycle | Service boundary, Face/Voice policy, tenant contract, integration review |
| Đỗ Quang Hiệp | QA, evaluation validation, reproducibility | Regression tests, holdout checks, monitoring evidence, demo validation |
| Tô Thanh Hải | Platform, containers, CI/CD và vận hành | Runner/Compose, exact-SHA deploy, recovery và portal integration |
| Ngô Anh Đức | Báo cáo, slide, sơ đồ và tài liệu | Final report, architecture explanation, demo runbook và Q&A |

Đây là phân công trách nhiệm hiện hành trong CONTRIBUTING, không phải thống kê công sức được đo. Bằng chứng meaningful contribution cần gồm công việc thực tế, PR/review, deliverables và khả năng giải thích/demo. Metadata Git, đặc biệt sau rewrite, không tự chứng minh ai thực hiện phần việc ban đầu; báo cáo không gán số commit giả cho thành viên.

Quy trình đề xuất dùng branch feat/fix/test/docs theo chủ đề, commit mô tả thay đổi cụ thể, PR vào main và reviewer từ mảng khác. CI phù hợp phải pass; deployment chỉ từ trusted main. Khi bàn giao cần chỉ rõ revision, cấu hình runtime, nơi giữ secrets/backup, dữ liệu được phép demo và bằng chứng của đúng run. Không chuyển API keys, media hoặc database dump vào repository [S20].

## 19 Giới hạn hướng phát triển và kết luận

| Ưu tiên | Việc cần hoàn thiện | Điều kiện nghiệm thu |
|---|---|---|
| Trước pilot | Dataset consented, trusted labels và customer risk budgets | Holdout/cohort metrics, class counts và uncertainty được review |
| Trước pilot | Fairness enforcement trong candidate path thực tế | Test chứng minh insufficient/rejected evidence chặn rollout |
| Trước pilot | Initial evaluated champion và retention/erasure xuyên kho | Installation mới có quy trình đánh giá; deletion/restore drill có evidence |
| Pilot vận hành | Capacity, concurrency, TLS/SSO và application recovery | Load test theo lịch thi và sự cố có đo recovery |
| Sau pilot | Customer training scope và template post-activation monitoring | Consent/isolation enforcement, không tự lấy tenant khác làm data train |
| Theo nhu cầu | Fine-tune encoder và đánh giá anti-spoof | Raw dataset/trainer/compute và benchmark độc lập trước serving |

Các trade-off chính là dùng pretrained encoder để tập trung lifecycle trong phạm vi dữ liệu/compute hiện có; dùng PostgreSQL cho verification 1:1 để tránh thêm hạ tầng chưa cần; và dùng Compose một host để demo dễ tái lập nhưng chấp nhận giới hạn HA/capacity. Stateful shadow/canary tăng khả năng audit và rollback, đồng thời đòi labels, thời gian và consistency giữa nhiều thành phần.

Dự án đã hiện thực luồng xác minh theo batch và cơ chế kiểm soát cập nhật threshold policy có bằng chứng. Điểm mạnh nằm ở tách trách nhiệm sản phẩm, dữ liệu và vận hành; giữ Face/Voice độc lập; phân biệt statistical drift với reviewed degradation; và giữ đường quay lại khi candidate gây regression. Simulation và CI cho thấy các cơ chế đó có thể được kiểm tra, nhưng không thay thế benchmark người dùng thật, fairness hoặc chứng minh production readiness.

Hướng tiếp theo là biến các gate hiện có thành quy trình pilot dựa trên dữ liệu đại diện, quyền sử dụng rõ ràng và phép đo vận hành thực tế. Champion là phiên bản được chấp nhận theo bằng chứng hiện có; việc tiếp tục giám sát và lưu lịch sử là điều kiện để duy trì sự tin cậy sau triển khai.

## Phụ lục A Nguồn kiểm chứng

Mọi đường dẫn dưới đây tính từ root repository FSB. Tài liệu được đối chiếu ngày 05/10/2026 trên checkout có thay đổi local. Artifact trong reports là bằng chứng local được gitignore; khi cần tái kiểm chứng phải dùng đúng runtime/dữ liệu và ghi lại timestamp mới. Hai report dự án khác chỉ dùng tham khảo cấu trúc, không cung cấp thuật toán, số liệu hay kết quả cho dự án này.

| Mã | Nguồn trong dự án | Nội dung đối chiếu |
|---|---|---|
| S1 | README.md, PROJECT_REQUIREMENTS.md | Scope, setup và boundaries |
| S2 | ARCHITECTURE.md, docs/ARCHITECTURE_OVERVIEW.md | Components, flows và trade-offs |
| S3 | docs/MODALITY_LIFECYCLE.md, pipeline/lifecycle_config.json | Methods, defaults và gates |
| S4 | docs/EVIDENCE.md | Dated CI/local evidence |
| S5 | SAAS_INTEGRATION.md, api/app/checks.py | API, tenant, idempotency và webhook |
| S6 | RESPONSIBLE_AI.md, pipeline/responsible_ai_report.py | Fairness, privacy và enforcement gap |
| S7 | DEPLOYMENT.md, OPERATIONS.md, docker-compose.yml | Deployment, readiness, recovery |
| S8 | pipeline/bootstrap_demo.py, data_snapshot.py, dataset_ledger.py; reports/data-quality.json | Data source, lineage và snapshot counts |
| S9 | api/app/biometrics.py, api/app/vendor/README.md, pipeline/download_models.py | Encoders, detectors, pinned provenance |
| S10 | pipeline/evaluation.py, pipeline/modality_training.py | Identity split, calibration và artifacts |
| S11 | airflow/dags/ | Ba DAG và bảy model tasks |
| S12 | pipeline/drift_decision.py, api/app/lifecycle_service.py | Drift, persistence và trigger |
| S13 | api/app/template_lifecycle.py | Template safeguard và rollback |
| S14 | api/app/model_lifecycle.py, observation.py, lifecycle_api.py | Policy routing và transitions |
| S15 | MONITORING_MAPPING.md, monitoring/ và dashboard builders | Metrics, reports và alerting |
| S16 | .github/workflows/ci.yml, tests/test_deploy_local.py | CI jobs và preflight |
| S17 | docs/SIMULATION.md; reports/simulation-verification.json, simulation-promotion-face.json, simulation-rollback-voice.json | Run IDs, offline, routed counts và probes |
| S18 | docs/presentation/DEMO_RUNBOOK.md, QA_GUIDE.md | Live demo và xử lý sự cố |
| S19 | SCALABILITY_COST.md | Capacity/cost assumptions |
| S20 | CONTRIBUTING.md, RUBRIC_MAPPING.md | Team process và assignment mapping |

**GitHub Actions của mốc CI:** https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring/actions/runs/37176107308

**Nguồn pretrained và dataset:** OpenCV Zoo cho YuNet/SFace; SpeechBrain `spkrec-ecapa-voxceleb`; LFW tại `marcelohaps/lfw`; Speech Commands tại `mteb/speech-commands-mini`; AASIST từ `clovaai/aasist`; MiniFASNetV2 theo attribution và revision trong vendor README. Các model/dataset này thuộc upstream tương ứng; nhóm không tuyên bố phát minh hoặc tự train các encoder đó.

## Phụ lục B Thuật ngữ

| Thuật ngữ | Ý nghĩa trong báo cáo |
|---|---|
| Enrollment / template | Ghi danh / các vector tham chiếu gắn với person |
| Embedding | Biểu diễn vector do encoder tạo từ ảnh hoặc giọng nói |
| Genuine / impostor | Cùng danh tính / khác danh tính theo nhãn độc lập |
| FMR / FNMR | Nhận nhầm impostor / từ chối nhầm genuine |
| PSI / MMD² | So phân phối scalar / khoảng cách kernel giữa vector distributions |
| Candidate / challenger | Policy mới đăng ký / policy đủ điều kiện thử có kiểm soát |
| Champion | Policy được chấp nhận đang phục vụ theo lifecycle |
| Shadow / canary | Quan sát không đổi response / cho cohort dùng policy mới |
| DAG | Đồ thị task có hướng không chu trình để Airflow điều phối |
| Lineage / fingerprint | Quan hệ truy vết dữ liệu và model / hash nhận dạng nội dung |
| RAI | Responsible AI, gồm fairness, explainability, privacy và human oversight |
| Synthetic evidence | Bằng chứng từ dữ liệu dựng, không tương đương benchmark người thật |
