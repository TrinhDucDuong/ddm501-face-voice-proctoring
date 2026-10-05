# Kịch bản demo toàn diện: 10–15 phút

**Vị trí trong buổi bảo vệ:** sau 15 phút trình bày, trước 10 phút Q&A.
**Bản chuẩn:** 13 phút, slide 19–26 theo `deck-content.json` hiện hành. Các bản xuất trong archive có thể đã đổi thứ tự slide; mở theo tiêu đề nếu dùng bản cũ. **Người dẫn:** Đức. **Thao tác:** Hải.
Dương giải thích lifecycle; Hiệp đọc metric/gate và kiểm chứng kết quả.

Mục tiêu là đi từ pain point “ai thực sự làm bài?” tới bằng chứng xác minh, rồi
chứng minh hệ thống biết kiểm soát việc cập nhật policy. Không cố chứng minh mọi
loại cheating trong một buổi demo.

## 1. Ranh giới dữ liệu cần nói trước

- **Demo sản phẩm:** tạo nhân viên/checks/callbacks/evidence trong tenant demo trên
  ứng dụng chính. Những thao tác này có ghi dữ liệu. Dùng tenant riêng của buổi học,
  không dùng tenant khách hàng. Reset simulation không xóa dữ liệu phần này.
- **Demo simulation:** dùng vector/nhãn tổng hợp, SQLite/MLflow/volume riêng, không
  thay đổi production policy. Dùng chung host và Airflow nên vẫn có thể tranh chấp
  CPU/RAM. Không nói “không có bất kỳ tác động nào tới production”.
- **Evidence lịch sử:** số liệu trên slide 23/25 là lượt ngày 03/10/2026. Nếu mở
  report lịch sử, nói rõ là report đã lưu. Run mới phải được đánh giá bằng run ID mới.

## 2. Chuẩn bị trước giờ học

Thực hiện trước khi chia sẻ màn hình. Không đưa credentials hoặc biometric media
lên GitHub. Đây là checklist chuẩn bị, không có nghĩa các bước đã được chạy lại
trong lần biên soạn tài liệu này.

### Trước 30–60 phút

1. Kiểm tra Docker Desktop, API, portal, Airflow scheduler, Grafana và hai MLflow
   services hoạt động. Runtime phải có champion đã đánh giá và data/artifacts tương
   ứng nếu demo luồng sản phẩm. Registry rỗng có thể `/health` = 200 nhưng `/ready`
   = 503; không chữa bằng cách tùy tiện đổi alias hoặc hạ gate.
2. Chuẩn bị hai tenant **DEMO-CLASS-A**, **DEMO-CLASS-B** từ trước. Đăng nhập operator
   A, operator B và platform bằng ba browser profile/session riêng. Hai tab trong
   cùng profile có thể chia sẻ trạng thái; kiểm tra lại tên tenant trên giao diện.
   Gói đăng ký chỉ là giả lập, không có thanh toán thật.
3. Chuẩn bị người A và người B với media có quyền sử dụng. Mỗi người có hai ảnh
   và hai WAV ghi danh khác nhau; thêm một cặp ảnh/WAV để query. Audio khoảng 10 giây
   phù hợp phần nói, không dùng WAV quá ngắn rồi coi capability unavailable là lỗi.
4. Test trước media trên cùng runtime. Ghi lại expected identity match, inspector
   capabilities và reasons thực tế. Không cam kết “đúng người luôn verified” nếu
   detector anti-spoof hoặc chất lượng có thể trả suspicious/inconclusive.
5. Có nhân viên **A-READY** đã ghi danh để dự phòng và một mã mới, ví dụ
   `CLASS-YYYYMMDD-01`, để tạo live. Không ghi danh lại cùng file vào một người đã
   có mẫu rồi gọi lỗi duplicate là bug.
6. Dùng bộ media query mới cho mỗi lượt trong một session. Nếu dùng lại file trong
   lần tập dượt, đổi session sang `CLASS-YYYYMMDD-HHMM`. Không dùng thủ thuật đó để
   phủ nhận tín hiệu capture reuse; nói rõ đây là cách tách hai phiên demo.
7. Cấu hình webhook trước giờ: receiver thật được allowlist và sẵn sàng ACK.
   Receiver demo tại `http://legacy-demo:8000/webhooks/verification` phải nhận biết
   đúng tenant và signing secret của tenant đó. Chỉ đặt URL chưa đủ để đảm bảo
   delivery. Tập thử và kiểm tra `delivered`, HTTP 200 trước buổi học.
8. Chuẩn bị tùy chọn request trong API client với secrets nằm trong biến môi trường
   cục bộ: retry cùng payload và cross-tenant GET. Không chiếu request headers,
   terminal history hoặc environment có key. Chỉ mở response/status đã lọc.
9. Chạy thử cả hai scenario simulation một lần, xuất JSON và ghi lại thời gian.
   Dùng nút **3. Khôi phục baseline demo**, xác nhận reset đã hoàn tất. Không reset
   bằng `docker compose down -v`, xóa database hoặc xóa model.
10. Chuẩn bị report đã lọc của promotion/rollback và screenshot kết quả của chính
    lần tập dượt để dự phòng. Giữ timestamp/run ID, không sửa số liệu để khớp slide.

### Các cửa sổ mở sẵn

| Cửa sổ | URL / nơi mở | Nội dung cần thấy |
|---|---|---|
| Operator công ty A | `http://localhost:18501` | Nhân viên, ghi danh, checks, lịch sử |
| Operator công ty B | Profile riêng, cùng URL | Roster/lịch sử của B |
| Platform | Profile riêng, cùng URL | Simulation MLOps |
| Nhân viên, tùy chọn | `http://localhost:18600` | Self-enrollment qua lời mời dùng một lần |
| Grafana overview | `http://localhost:13000/d/biometric-overview` | 10 panel service/drift/freshness |
| Grafana simulation | `http://localhost:13000/d/biometric-simulation` | Chọn Scenario/Modality, xem synthetic gate/routing/reset |
| Airflow | `http://localhost:18081/dags/biometric_simulation/grid` | Run của chính simulation đang demo |
| MLflow simulation | `http://localhost:15031` | Model `simulation-<run-id>-<modality>` |
| MLflow production | `http://localhost:15030` | Face/Voice registry độc lập, chỉ đọc |
| GitHub Actions FSB | `https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring/actions` | Run cụ thể, job và artifacts |

Mở GitHub FSB trực tiếp hoặc link **CI/CD** trong trang **Vận hành MLOps**.
Trong buổi demo không dùng nút **Reload champion model** để thay
cho lifecycle rollback, vì đó là thao tác bundle legacy.

## 3. Timeline chuẩn 13 phút

| Thời gian demo | Slide | Thao tác chính | Điểm cần chứng minh |
|---|---:|---|---|
| 00:00–02:00 | 19 | Tạo nhân viên, ghi danh | Mẫu và identity được gắn với đúng tenant/người |
| 02:00–05:00 | 20 | Same-person, other-person, history/evidence/webhook | Kết quả có reason, version và bằng chứng truy xuất |
| 05:00–06:00 | 21 | Grafana, bắt đầu simulation Voice | Tách monitoring nghiệp vụ và nền tảng |
| 06:00–09:00 | 22 | Theo dõi promotion | Alert, offline, shadow, canary và champion |
| 09:00–09:30 | 23 | Đọc routed counts | Phân biệt traffic live với bảng evidence lịch sử |
| 09:30–12:00 | 24 | Reset, scenario Face rollback | Fail gate dừng rollout |
| 12:00–12:30 | 25 | Kiểm tra probes/version | Traffic thực quay về champion |
| 12:30–13:00 | 26 | Reset, lưu evidence, chuyển Q&A | Kết thúc có trạng thái và audit rõ ràng |

### Bước A. Ghi danh: 00:00–02:00

**Đức nói:** “Em mở công ty demo A. Phần này minh họa dữ liệu thực sự được ghi vào
tenant demo của ứng dụng. Chúng ta tạo một nhân viên và gắn mẫu Face/Voice với người
đó trước khi có thể xác minh.”

**Hải thao tác:**

1. Trên operator A, vào **Nhân viên**, nhập mã mới và tên hiển thị, bấm **Thêm nhân viên**.
2. Vào **Ghi danh face & voice**, chọn đúng người. Upload đúng hai ảnh và hai WAV
   đã chuẩn bị; checkbox consent chỉ chọn khi thực sự có sự đồng ý/quyền sử dụng.
3. Bấm **Ghi danh** một lần. Đọc kết quả và kiểm tra **Đủ mẫu** trong danh sách.
4. Nếu muốn self-enrollment, thay bước 2–3 bằng **Tạo liên kết ghi danh**, mở :18600,
   **Kiểm tra lời mời**, gửi bốn mẫu. Chọn một đường, không demo cả hai trong bản 13 phút.

**Kết quả cần đọc:** nhân viên đúng tenant, `ready=true` hoặc nhãn Đủ mẫu. Nếu thiếu
mẫu, đọc `rejected` và lý do. Sau 30 giây điều tra không xong, chuyển sang A-READY
và nói rõ đó là nhân viên đã chuẩn bị trước, không giả vờ lượt enrollment live thành công.

**Lời nối:** “Chúng ta đã có reference của người A. Bây giờ xem điều gì xảy ra khi
capture đúng người và khi tài khoản A nhận media của người khác.”

### Bước B. Xác minh và bằng chứng: 02:00–05:00

1. **Kiểm tra tích hợp**: chọn A, nhập session mới, upload query của A, xác nhận
   consent và bấm **Gửi check**. UI sinh request ID mới mỗi lần bấm.
2. Mở JSON kỹ thuật vừa đủ để chỉ `check_id`, face/voice scores và match,
   `reason_codes`, `capabilities`, `model_versions` / `model_version` và
   `evidence_status`. Không đọc toàn JSON.
3. Giữ khai báo người A, gửi ảnh/WAV của B đã được phép dùng. Kỳ vọng identity
   mismatch trong bộ fixture đã tập thử. Chỉ nói kết quả thật đang thấy; không
   tuyên bố anti-spoof accuracy từ một ví dụ.
4. **Lịch sử & báo cáo**: lọc người A và session vừa nhập, chọn check nghi vấn,
   bấm **Mở bằng chứng** khi `stored` hoặc `partial`. Chỉ phát 2–3 giây audio nếu
   phù hợp quyền sử dụng. Xuất CSV hoặc PDF, không cần xuất cả hai trong bản chuẩn.
5. **API & Webhook**: xem bảng delivery của check vừa gửi, chỉ status/HTTP code.
   Không chọn **Hiển thị secret xác thực webhook**, không cấp hoặc thu hồi key live.
6. Nếu còn 20–30 giây, chuyển operator B để thấy dữ liệu B. Đây là bằng chứng giao
   diện được scope, chưa đủ chứng minh chặn direct API. Muốn chứng minh mạnh hơn,
   dùng request đã chuẩn bị `GET /v1/checks/{check_A}` với key B, response 404.

**Đức nói:** “Một score thấp chưa phải kết luận gian lận. Chúng ta xem identity,
capture quality, capability và reason trước. Lịch sử chỉ thể hiện các capture đã
nhận, không chứng minh giám sát liên tục ở khoảng giữa hai lượt.”

**Hiệp bổ sung:** “Review labels phải có căn cứ độc lập. Em chỉ mở form để chỉ ra
Face/Voice labels riêng, không lưu dữ liệu synthetic thành human ground truth để
kích hoạt retrain.”

**Tùy chọn mở rộng 30–45 giây:** trong API client đã chuẩn bị, gửi lại đúng
`request_id` và payload để thấy cùng `check_id`. Đổi payload nhưng giữ request ID
thì 409. **Bấm Gửi check hai lần trên UI không phải test idempotency**, vì mỗi lần
UI tạo UUID mới và có thể kích hoạt capture reuse.

### Bước C. Vận hành và chuyển ranh giới: 05:00–06:00

Mở Grafana: chỉ một panel service/latency, freshness và một panel lifecycle theo
modality. Không cuộn qua toàn dashboard. `No data` do thiếu reviewed labels không
có nghĩa performance khỏe. Sau đó sang platform **Simulation MLOps**, chọn Voice,
ghi nhận champion simulation ban đầu và bấm **1. Drift → nâng cấp champion** một lần.

**Đức nói:** “Các check vừa rồi đi qua ứng dụng chính. Từ bước này, demo dùng vector
và nhãn tổng hợp trong vùng simulation riêng. Chúng ta dùng dữ liệu được dựng để
kiểm tra cơ chế xử lý drift, không dùng nó để công bố accuracy.”

Mở dashboard **Simulation**, chọn đúng scenario/modality. Đọc drift evidence, alert receipt, offline, routed samples và outcome; snapshot còn sau reset là lịch sử, không phải traffic mới.

Trong lúc Airflow chờ nhận job, có thể mở GitHub FSB run đã chọn sẵn tối đa 20 giây:
chỉ Windows `deployment-preflight`, build và `deploy-demo`, phân biệt preflight với
deploy thật. Chỉ gọi job success khi run thực tế hiển thị success. Không bấm rerun
hoặc deploy để phục vụ màn trình diễn.

### Bước D. Promotion: 06:00–09:30

Không tạo run thứ hai: run đã bắt đầu ở bước C. Đối chiếu cùng run ID giữa portal
và Airflow. Mở **Quyết định drift, gate và lịch sử chuyển trạng thái**.

| Quan sát | Ý nghĩa cần nói | Tiêu chí đọc kết quả |
|---|---|---|
| Drift report | Ba cửa sổ mới, score/embedding drift và reviewed degradation | `RETRAIN_REQUIRED` của modality được chọn |
| Alert receipt | Prometheus/Alertmanager đã giao alert | Receipt có đúng run ID trước training |
| Offline | So cùng holdout | FMR/FNMR candidate không vi phạm gate |
| Shadow | Challenger quan sát, champion trả lời | Served candidate = 0 ở shadow |
| Canary | Request thật dùng policy theo cohort | Stage và served_candidate tăng theo traffic |
| Promotion | Chỉ sau stage cuối | Version champion mới, probe đúng version |

**Dương nói:** “Training ở đây chọn threshold bằng calibration. Candidate phải
được so với incumbent trên cùng dữ liệu holdout. Trong shadow, đáp án người dùng
vẫn thuộc champion. Tới canary mới có request dùng challenger, nên cần nhìn routed
counts, không chỉ nhìn phần trăm cấu hình.”

Mở MLflow **:15031**, chọn model có đúng run ID/modality. Đọc `champion` và version;
không mở :15030 rồi đổi production aliases. Chuẩn bị tải evidence JSON cho đúng run
sau khi hoàn tất. Nếu tiếp tục chạy tới quá demo 09:00, dùng slide 23 và báo rõ đó là
evidence lịch sử. Muốn bắt đầu scenario rollback phải reset/cancel run trước và
đợi reset hoàn tất; nếu không đủ thời gian, dùng evidence lịch sử cho rollback.

Bảng slide 23 ngày 03/10: shadow 0/200, canary 13/22/57/99/200 trên 200 request mỗi
stage. Đây là một lượt cụ thể, không phải số bắt buộc mọi seed/run phải giống hệt.

### Bước E. Rollback: 09:30–12:30

1. Bấm **3. Khôi phục baseline demo**, chờ xác nhận. Chọn Face.
2. Bấm **2. Canary lỗi → rollback** một lần. Theo dõi cùng run, không bấm lại khi
   đang chờ alert hoặc scheduler.
3. Đọc failure tại canary 25%, `failed metric`, observed value, limit, stage/version.
   Kịch bản chủ động tiêm impostor score cao; không gọi đây là lỗi tự phát đã phát hiện
   trên dữ liệu nhân viên thật.
4. Đối chiếu traffic về 0 và rollback probes dùng incumbent. Trong lượt lịch sử,
   200/200 probe dùng version 1. Run mới đọc số thực tế của nó.

**Hiệp nói:** “Một candidate giảm từ chối nhầm vẫn có thể nguy hiểm nếu tăng chấp
nhận sai. Gate FMR chặn trường hợp đó. Trạng thái FAILED_CANARY ở kịch bản này là
kết quả đúng: challenger bị dừng, champion được giữ và evidence vẫn còn.”

**Phân biệt:** workflow hoàn tất kịch bản rollback không có nghĩa model được promote.
Một exception do network/database cũng không phải bằng chứng gate rollback hoạt động.

### Bước F. Reset và kết thúc: 12:30–13:00

1. Lưu report cho đúng hai run, dùng **Chuẩn bị báo cáo evidence JSON** rồi tải file.
2. Bấm **3. Khôi phục baseline demo**. Đợi UI xác nhận phục hồi baseline. Reports
   drift cũ vẫn còn là history; đừng gọi history đó là trạng thái drift mới.
3. Nếu đã chuẩn bị snapshot trước/sau `GET /v1/admin/lifecycle/state` với platform
   credential, đối chiếu **modality, state, traffic_percent, champion_version,
   challenger_version**. Không so toàn JSON byte-for-byte vì samples/timestamps có
   thể thay đổi. Các check của bước B có thể làm counters tăng.
4. Nếu chưa có snapshot, chỉ nói “thiết kế cách ly và evidence lịch sử ghi nhận
   production policies không đổi”, không khẳng định đã kiểm chứng trước/sau buổi live.

**Đức kết:** “Nhóm đã đi qua xác minh danh tính, xem lại bằng chứng, quan sát hệ thống,
đưa policy mới qua gate và chủ động chặn một policy gây regression. Xin mời thầy cô
và các bạn đặt câu hỏi trong mười phút tiếp theo.”

## 4. Điều chỉnh theo thời gian thực tế

| Bản demo | Sản phẩm | Vận hành | Promotion | Rollback | Reset/kết |
|---|---:|---:|---:|---:|---:|
| 10 phút | 3:00 | 0:45 | 3:00 | 2:45 | 0:30 |
| 13 phút chuẩn | 5:00 | 1:00 | 3:30 | 3:00 | 0:30 |
| 15 phút tối đa | 6:00 | 1:30 | 3:30 | 3:00 | 1:00 |

Bản 10 phút dùng A-READY để giới thiệu enrollment đã chuẩn bị, chỉ mở một export,
và có thể dùng report lịch sử cho scenario thứ hai nếu chưa hoàn tất. Bản 15 phút
thêm self-enrollment **hoặc** idempotency/cross-tenant direct API, không cố thêm tất
cả. Hai kịch bản simulation chạy nối tiếp vì service chỉ nhận một run active.

## 5. Kịch bản xử lý sự cố

| Sự cố | Hành động | Câu nói trung thực |
|---|---|---|
| Camera/mic không cấp quyền | Dùng upload được chuẩn bị và quyền sử dụng hợp lệ | “Em chuyển sang media fixture để tiếp tục kiểm tra luồng.” |
| Capture đúng người nhưng suspicious | Xem inspector reasons và chất lượng | “Identity và integrity là hai loại tín hiệu, đây là kết quả thực tế của capture này.” |
| Webhook pending / failed | Xem delivery status, không sửa secret trên màn chiếu | “Callback chưa được receiver xác nhận; em giữ đúng trạng thái này và dùng evidence trước để giải thích retry.” |
| Airflow queue chờ | Xem scheduler/run, dùng evidence lịch sử theo timebox | “Run hiện tại chưa hoàn tất, bảng tiếp theo thuộc lượt đã lưu.” |
| Alert chưa tới | Xem receipt, không bỏ điều kiện chờ hoặc hạ ngưỡng | “Training chưa được phép bắt đầu vì chưa có alert receipt đúng run.” |
| Reset đang chờ | Đợi bước active dừng, không xóa volumes | “Reset đang chờ bước đang chạy kết thúc.” |
| Model gate thật sự reject | Trình bày failure reason | “Candidate không đạt gate nên champion được giữ nguyên.” |

## 6. Tiêu chí một buổi demo hoàn tất

- Có ít nhất một request sản phẩm live, đọc đúng kết quả và đúng tenant/session.
- Mở được lịch sử và evidence phù hợp hoặc nói rõ lý do chưa có evidence.
- Phân biệt alert nền tảng với business webhook của công ty.
- Với từng scenario, chỉ ra run ID, nguồn live/lịch sử, gate và outcome đúng.
- Đã yêu cầu reset simulation và xác nhận outcome thực tế, giữ audit.
- Không thay đổi gate, production alias hoặc gắn synthetic data thành human labels.
- Không kết luận human accuracy, fairness hoặc capacity từ demo này.
