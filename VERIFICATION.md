# Kiểm chứng MLOps và company service (Asia/Saigon)

## Deploy GitHub Actions 02/10/2026, đối chiếu ngày 03/10/2026

- Repository hiện dùng để đối chiếu CI/deploy: [FSB-MSA36HN/DDM501-face-voice-proctoring](https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring). Các link repo cá nhân ở những mục baseline bên dưới là bằng chứng lịch sử.
- [Run 37032729559](https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring/actions/runs/37032729559), commit `dfd1faa460cc9cb153bcf059cbe2d9fc3ecdcd42`, **success**. GitHub API xác nhận cả `quality`, `containers`, `deploy-demo` thành công; [job deploy-demo](https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring/actions/runs/37032729559/job/110924788849) hoàn tất lúc **23:21:33 ngày 02/10/2026** (Asia/Saigon).
- Deployment chạy qua runner **self-hosted Linux/WSL** và gọi PowerShell trên Windows để stage đúng SHA ngoài OneDrive, Compose rollout, chờ readiness rồi kiểm chứng monitoring. Đây là bằng chứng deploy tự động đã vượt trở ngại runner Windows ghi trong mục 01/10; không phải deploy cloud.
- Đã tải và đọc artifact `deployment-monitoring-evidence`: report lúc `2026-10-02T16:21:19.252512+00:00`, `status=pass`; cả `all_dashboard_queries`, `collector_and_container_freshness`, `protected_reports_and_sources` đều pass. Bản đối chiếu local: `reports/prior-deployment-monitoring-verification.json` (gitignored).
- Đã đọc JUnit/coverage trong artifact `quality-evidence`: **103 test được thu thập = 101 passed + 2 skipped**, không failure/error; coverage **81,02%**. Hai test bị skip là `test_deployment_preflight_stages_exact_checkout` và `test_deployment_rejects_other_revision_before_staging`. Vì vậy job quality xanh của run này **không chứng minh hai test preflight đã chạy**; bằng chứng triển khai thật là job `deploy-demo` và artifact monitoring riêng.

## Sửa kiểm chứng ngày 03/10/2026

- `verify_stack.py` kiểm tra tập tên đầy đủ của 7 task training (gồm `publish_versioned_dataset`), không cho phép task trùng/thiếu/lạ và yêu cầu mọi task `success`. Test hồi quy tái hiện verifier cũ từ chối 7 task hợp lệ nhưng chấp nhận 6 task thiếu; sau sửa, cả 9 tình huống pass, gồm empty/failed/running/skipped/state chưa có.
- Chạy thật `python pipeline/verify_stack.py --dag-run continuous_training_20261002_b`: **7/7 nhóm kiểm chứng pass**, trong đó Airflow có **7/7 task success**. Report: `reports/verification.json`. Lần kiểm tra này đọc lại training run đã có; không trigger training, không gửi inference hoặc Telegram mới.
- Hai test deployment nay dùng checkout Git, `.env` mẫu, Python runtime và release directory tạm; không phụ thuộc `DDM501_RUNTIME_ROOT` hay dữ liệu demo. Trên Windows local, **2 passed, 0 skipped**; kiểm tra staging từ đúng commit dù working tree đã sửa, từ chối SHA khác trước staging và giữ nguyên `.env` runtime.
- Workflow thêm job bắt buộc `deployment-preflight` trên `windows-latest`, upload `deployment-preflight-evidence` và fail nếu JUnit thiếu test, có skip/failure/error. `containers` phụ thuộc cả `quality` và `deployment-preflight`; Ubuntu vẫn skip hai test Windows một cách minh bạch.
- Đã push commit `71d624df8eeecc9f1b63df6e20cf20219acb01c9` lên `main` của repo tổ chức. [Job Windows deployment-preflight](https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring/actions/runs/37097498074/job/111130318175) trong [run 37097498074](https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring/actions/runs/37097498074) **success**. Đã tải và đọc artifact `deployment-preflight-evidence`: **2 passed, 0 skipped, 0 failures/errors**, thời gian pytest 9,698 giây. Cả `test_deployment_preflight_stages_exact_checkout` và `test_deployment_rejects_other_revision_before_staging` thực sự chạy trên GitHub Windows. Bản JUnit đối chiếu local: `reports/github-windows-preflight-tests.xml` (gitignored).
- Bộ test local theo scope coverage CI: **112 passed, 0 skipped**, coverage **81,06%** (ngưỡng 80%); JUnit `reports/tests-review.xml`, `coverage.xml`. Có 13 warning từ dependencies, không có test failure/error. Ruff, compile và kiểm tra cấu hình Compose pass.
- Artifact `quality-evidence` của run `37097498074` xác nhận Ubuntu **110 passed + 2 skipped** trên 112 test, không failure/error, coverage **81,02%**. Hai test Windows được chứng minh bằng artifact của job riêng ở trên, không cộng nhầm skipped thành passed.
- Run `37097498074` hoàn tất **success** cho cả bốn job: `quality`, `deployment-preflight`, `containers`, `deploy-demo`. [Job deploy-demo](https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring/actions/runs/37097498074/job/111130883520) deploy commit `71d624d` thành công. Đã đọc artifact `deployment-monitoring-evidence`, report lúc `2026-10-03T04:48:47.316448+00:00`: `status=pass`, cả dashboard queries, collector/container freshness và protected reports/sources đều pass. Bản đối chiếu local: `reports/github-review-deployment-monitoring.json` (gitignored).

## Continuous MLOps local 02/10/2026

- Checkpoint trước thay đổi: branch `checkpoint/2026-10-02-before-mlops-continuous`, commit `4913b7b`; dump PostgreSQL `data/backups/ddm501_restore_drill_20261001_184709.dump` đã được restore thử vào database tạm. Runtime MinIO/DB phát sinh sau checkpoint cần sao lưu riêng nếu rollback.
- `biometric_monitoring_pipeline` run `continuous_monitor_20261002_a` và `continuous_monitor_20261002_b` thành công. Training DAG run `continuous_training_20261002_a` thành công **7/7 task**. MinIO có training manifest cho 282 embedding, SHA-256 snapshot đối chiếu đúng; monitoring đã ghi input không nhãn, nhãn review tách riêng và report theo cửa sổ.
- Sau đợt rà soát retry/provenance, monitoring run `continuous_monitor_20261002_c` cũng thành công: collect/branch/no-op success, task trigger được skip vì chưa đủ mẫu. Training snapshot cũ được publish lại với timestamp khác mà SHA-256 bất biến vẫn khớp. API/monitoring được build lại từ source mới.
- Training run `continuous_training_20261002_b` trên dataset không đổi thành công **7/7 task**; publish dataset lặp không lỗi. MLflow vẫn giữ `champion=10`, candidate/challenger mới `12`; task rollout ghi `status=skipped`, `challenger_was_not_promoted` thay vì reload champion cũ. Bộ kiểm chứng hiện tại: **101 pytest pass**, coverage đúng scope CI **81,06%** (ngưỡng 80%), Ruff/compile/Compose config/DAG import/diff check pass, `verify_monitoring_centre.py` pass.
- MLflow `champion=10`, `candidate=12`, `challenger=12`; API `/ready` phục vụ version 10. Version 11 và 12 không vượt paired holdout (`no_measured_gain`) và chưa đủ random audit human, vì vậy không được promote. Monitoring hiện báo `insufficient_data`: mỗi tenant/model mới chỉ có vài check, không có human label; không coi đây là drift hoặc accuracy tốt/xấu.
- `verify_employee_demo.py` chạy lại qua hai công ty, mỗi người ghi danh một lần với 2 ảnh + 2 WAV, check `verified`, cross-tenant bị chặn. Đây là media bootstrap để thử luồng, không phải ground truth human. API review queue lấy cohort 10% độc lập với trạng thái dự đoán và chặn khai khống `random_audit`.
- `verify_monitoring_centre.py` pass: mọi truy vấn dashboard, collector/freshness và protected reports. Prometheus scrape trạng thái monitoring DAG, retrain recommendation theo tenant/model; ba alert drift/retrain/staleness được nạp và hiện inactive. Phiên này không gửi alert Telegram thử để tránh thông báo dư.
- Giới hạn triển khai: chưa có nhãn human đủ để tự đánh giá FAR/FRR production hoặc đổi champion; chưa có canary phân tuyến request thực. Code/image CI/CD vẫn qua GitHub Actions, còn lần deploy local này được build bằng Docker Compose; runner Windows đã có giới hạn Code Integrity ghi ở phần 01/10.

## Demo nhân viên đa công ty 01/10/2026

- Commit `8dc4863` đã được push lên `main`; local Compose đã deploy đúng source commit này và health API, portal, trang thi, Grafana đều trả HTTP 200.
- **69/69** pytest pass; Ruff, compile và JavaScript syntax check pass. Lời mời nhân viên ràng buộc tenant/người, hết hạn 24 giờ và dùng một lần. Test bao phủ thiếu consent, thiếu/trùng mẫu, hết hạn, subscription dừng và cách ly tenant.
- `pipeline/verify_employee_demo.py` đã chạy qua trang thi local với hai công ty: mỗi người tự ghi danh 2 ảnh + 2 WAV trong một request, replay bị từ chối, check qua simulator cho kết quả `verified`, cross-tenant bị chặn. Bằng chứng: `reports/employee-demo-verification.json` (gitignored).
- `pipeline/verify_company_service.py` có `verified` và `suspicious`, bằng chứng MinIO, cách ly check/evidence, CSV/PDF và webhook có chữ ký đều pass. Bằng chứng: `reports/company-verification.json`.
- DAG `biometric_model_pipeline` run `employee_demo_20261001` thành công 6/6 tác vụ. `verify_stack.py --dag-run employee_demo_20261001 --inference` pass serving/Registry/Airflow/Prometheus/Evidently/Grafana/alerts/inference. `verify_monitoring_centre.py --send-alert` pass truy vấn dashboard, collector, protected reports và Alertmanager → Telegram.
- GitHub Actions của commit cuối: jobs `quality` và `containers` pass. `deploy-demo` bị kẹt vì Windows Code Integrity chặn `Runner.Worker.dll` chưa đạt Enterprise signing policy (`0x800711C7`); đã yêu cầu hủy job kẹt. Local deploy đã thực hiện thủ công, không thay đổi policy bảo mật. Runner cần được IT cho phép hoặc thay bằng runner tương thích trước khi CI/CD tự deploy được.
- Browser camera/microphone chưa được kiểm tra trên thiết bị thật trong phiên này vì không có browser điều khiển khả dụng; HTML/JS đã kiểm tra cú pháp, endpoint và luồng upload chạy qua simulator. Media bootstrap không phải benchmark độ chính xác người thật/deepfake.

## Maintenance 29/09/2026

| Hạng mục | Bằng chứng mới |
|---|---|
| Quality | **65 tests pass, coverage 86,50%**; Ruff, compile, generated-dashboard diff và Compose config pass |
| Company batch | Hai tenant đăng ký, cùng mã nhân viên, SFace/ECAPA + MiniFASNet/AASIST thật; same identity verified, other identity suspicious |
| API consistency | Retry cùng request/payload trả cùng check; thay payload 409; kết quả/check/event/outbox cùng transaction |
| Isolation/storage | Check/evidence/export khác tenant 404; thiếu key 401; suspicious image/WAV lưu MinIO; ordinary check không giữ raw |
| Business reports | JSON/PDF/CSV theo nhân viên/phiên/ngày; first/last check ranges, labels và evidence status; không có điểm thi |
| Callbacks | Signed customer webhooks delivered, receiver HTTP 200; verifier poll kiểm tra ACK cho từng check |
| Multi-capture | Ảnh ghép hai mặt và audio ghép hai người có `multiple_faces`, `multiple_speakers_suspected`; chỉ là scenario inference |
| Portal | Streamlit AppTest chạy sáu trang của cả hai tenant, đăng ký anonymous và inline CSV export với API thật |
| Monitoring | 62 panels, 67 queries; dashboard queries, freshness, protected reports/sources pass; short/multi-face capture không bị coi là detector outage |
| GitHub CI/CD | [Run 36562882154](https://github.com/TrinhDucDuong/ddm501-face-voice-proctoring/actions/runs/36562882154) success: quality, containers, deploy-demo; remote 65 tests, coverage 86,45% |
| Deployed code | Release `8b720fc1a30ba16754c785020325e40de27c02e4` ngoài OneDrive; company/callback/isolation/evidence/export và monitoring kiểm tra lại sau deploy pass |

Artifacts mới: `reports/company-verification.json`, `multiple-capture-verification.json`, `company-demo.pdf/csv`, `ui-verification.log`, `coverage-maintenance.json`, `tests-maintenance.xml`, `monitoring-verification.json`. Không đưa credentials/media/runtime artifacts lên GitHub. Camera/mic, browser playback/download và anti-spoof customer benchmark chưa được xác thực bằng những checks này.

## Baseline full pipeline 28/09/2026

Bằng chứng runtime tại `reports/verification.json`, `monitoring-verification.json`, `coverage.json`, `saas-verification.json`, `paas-verification.json`, `recovery-verification.json`, `github-actions.json`. Các file này/data/models/backups chứa dữ liệu runtime, được gitignore. Tài liệu ghi kết quả thực chạy; không thay thế điểm do giảng viên chấm.

## Pipeline, serving và chất lượng

| Hạng mục | Kết quả thực tế |
|---|---|
| Airflow | Run `isolated_holdout_20260928`: 6/6 tasks success, RAI trước promotion và reload API |
| Snapshot/validation | 282 feature rows, training tenant demo; snapshot SHA-256 cố định theo run, validation trước calibration |
| MLflow | Champion **9**, run `4068c96a6c13401bae5f91ab250cfdcb`; params/metrics/snapshot/validation/evaluation/signature và nested objective runs |
| Evaluation | Identity-disjoint max-template cosine giống serving; năm partitions, holdout riêng + bốn folds CV nội bộ; margin chọn bằng CV, không dùng holdout |
| Gates | Calibration/CV/holdout FAR và FRR ≤20%, holdout sample counts và dataset fingerprint; reject invalid/NaN metrics, CLI không bypass |
| API | Backend `pretrained`, loaded champion 9, readiness pass; giữ model trước nếu reload thất bại |
| Ảnh/WAV thật | Cùng danh tính ALLOW, score 1/1; khác danh tính REVIEW, face 0,19485 và voice 0,10871; reasons/margins/sensitivity/counterfactual theo policy |
| Tests | **52 passed**, coverage **88,76%**, Ruff/diff checks pass |
| Phạm vi coverage | Toàn `app`, toàn `monitoring`, `pipeline.evaluation`, `data_snapshot`, `validate_data`, `promotion_gate`, `responsible_ai_report`; không phải toàn repository |
| Live SaaS | **19 checks pass**: tenant isolation, consent, expiry/one-time session, genuine/impostor upload, operator review, HMAC callbacks, single exam admission |

### FAR/FRR của champion 9

| Modality | Threshold | Calibration FAR / FRR | Internal CV FAR / FRR | Reserved holdout FAR / FRR | Holdout genuine / impostor |
|---|---:|---:|---:|---:|---:|
| Face | 0,374 | 0% / 0% | 0,56% / 0% | 0% / 0% | 27 / 55 |
| Voice | 0,221 | 14,73% / 16,39% | 19,60% / 16,47% | 18,18% / 16,67% | 30 / 55 |

Margin ứng viên cố định: 0; 0,002; 0,005; 0,01; 0,02. Chọn margin nhỏ nhất đạt gate bằng internal CV; face 0, voice 0,002. Holdout không nằm trong train/test của bất kỳ inner fold nào. Regression test thay riêng embeddings holdout chứng minh threshold/CV không đổi. Nếu không có margin đạt, giữ kết quả fail để promotion từ chối.

## Grafana và Telegram

| Hạng mục | Kết quả |
|---|---|
| Dashboard | **59 panels gồm 7 row headers**, **64 truy vấn** PromQL/SQL/LogQL đã thực thi không lỗi |
| Monitoring coverage | Readiness/latency/errors, training quality, PSI/Evidently, human/synthetic classification, Registry/calibration/CV/holdout, sessions/review SLA, webhooks, DAG/tasks, RAI, CPU/RAM/network/IO, logs |
| Metrics/collectors | API/drift/webhook/ops scrape UP; DB/Registry/Airflow/Docker collectors thành công và freshness hợp lệ |
| Logs/resources | Alloy v1.20.0 → Loki; Docker stats qua read-only socket proxy; theo Compose project |
| Reports | Tám report HTML/JSON cùng origin Grafana; anonymous 401, authenticated 200 |
| Human evidence | Report `waiting_for_feedback`, fairness `insufficient_data`; synthetic là nguồn/report/alert riêng |
| Alert delivery | Alertmanager → ops-monitor → **Telegram đã gửi thành công**, cả kiểm thử trực tiếp và webhook; bot `@ddm501_face_voice_proctoring_bot` |

Truy vấn không lỗi không đồng nghĩa mọi series có dữ liệu: human labels, empty review queue và rates khi thiếu traffic có thể No data/NaN. Simulation cố tình tạo drift/performance degradation, được đánh dấu synthetic. Dashboard là quyền quản trị nền tảng; tenant filter áp dụng SQL.

## Recovery và deployment

- Restore drill 28/09: `data/backups/ddm501_restore_drill_20260928_102822.dump`, **563.959 bytes**. Restore vào DB tạm riêng, đối chiếu số dòng của tám bảng, xóa DB tạm; không restore đè dữ liệu gốc.
- Rollback rehearsal thành công **8 → 7 → 8**, readiness được kiểm tra. Đây là bằng chứng trước khi champion 9 đăng ký, không gọi nhầm là rollback version 9.
- Portable serving image đã kiểm chứng local không có bind mount model, 19 integration checks pass, dùng chung local DB/MLflow/MinIO. Private overlay đã validate config. Chưa phải deployment cloud/customer thực tế.
- Load smoke trước đó: 20 requests, concurrency 2, 0 lỗi, p95 0,244s trên CPU warm; không suy ra SLA hoặc capacity production.

## CI/CD baseline 28/09/2026

Run [36430718832](https://github.com/TrinhDucDuong/ddm501-face-voice-proctoring/actions/runs/36430718832) **success**, commit `3e98c770c913b84f30e68e541d044551f966503c`, ngày 28/09/2026. Cả ba jobs **quality, containers, deploy-demo** thành công, gồm kiểm chứng dashboard/protected reports/freshness và upload artifacts. Remote: **52 passed, coverage 88,69%**; local: **52 passed, coverage 88,76%**. Deploy thực tế trên Docker Desktop qua runner Windows, source release ngoài OneDrive, dữ liệu/secrets giữ nguyên; chưa phải public cloud deployment.

Quality: Ruff → compile → dashboard consistency → pytest/coverage ≥80% → Compose config. Containers: build API/UI/drift/ops/Airflow/webhook/legacy trên GitHub Ubuntu. Deploy: trusted-main runner Windows, giữ dữ liệu/secrets/weights → Compose rollout → readiness/monitoring smoke → dashboard queries/protected reports/freshness. Artifacts: `quality-evidence` (JUnit/coverage XML), `deployment-monitoring-evidence`.

Các lỗi thực tế đã sửa: Ruff mới thay đổi defaults (pin phiên bản/cấu hình rules); Windows execution policy chặn Python setup và scripts (runtime Python + process-scoped bypass); Docker Desktop không đọc được file bind từ checkout OneDrive (Git archive đúng SHA sang release ngoài OneDrive, probe file config đọc thành công). Không thay policy toàn máy. Runner chạy theo phiên, cần khởi động lại sau reboot; xem [OPERATIONS.md](OPERATIONS.md).

## Giới hạn còn mở

Evaluation đã identity-disjoint trong tập demo, nhưng face/voice bootstrap ghép tổng hợp; genuine inference dùng lại media enroll. Chưa chứng minh chất lượng trên người dùng mới, fairness demographic, liveness hay audio anti-spoof. Cần consented real data/human labels; không dùng synthetic để đạt human gate. Camera/mic cần browser acceptance thực tế. Team contribution/demo/Q&A cần người thật. Repo đã xác minh public qua GitHub API ngày 28/09. Cloud/TLS/SSO/customer deployment chưa triển khai.

## Xem trực tiếp

- [Grafana Monitoring Centre](http://localhost:13000/d/biometric-overview)
- [Portal](http://localhost:18501), [legacy exam](http://localhost:18600), [API docs](http://localhost:18100/docs)
- [Airflow](http://localhost:18081), [MLflow](http://localhost:15030), [MinIO](http://localhost:19101)
- [Prometheus targets](http://localhost:19090/targets), [alerts](http://localhost:19090/alerts), [Alertmanager](http://localhost:19093)
- [Telegram bot](https://t.me/ddm501_face_voice_proctoring_bot)
- Đầy đủ URL report/exporters/health và trạng thái runtime: [PROJECT_STATE.md](PROJECT_STATE.md).
