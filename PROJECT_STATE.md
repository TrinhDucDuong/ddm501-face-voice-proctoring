# Trạng thái tiếp tục — DDM501, 29/09/2026

## Maintenance theo scope công ty đã chốt

Airflow điều phối MLOps (dữ liệu → đánh giá → cập nhật model). Công ty giữ hệ thống thi, nhịp capture, điểm và quyết định nghiệp vụ. Dịch vụ nhận batch ảnh/WAV qua `/v1/checks`, trả kết quả tức thời và signed webhook; portal công ty quản lý nhân viên, ghi danh, API/webhook, lịch sử và PDF/CSV. Grafana/Evidently/Telegram dành cho vận hành nền tảng, không gửi Telegram riêng cho công ty.

PostgreSQL quản lý tenant/nhân viên/embedding/metadata; MinIO lưu artifacts và bằng chứng ảnh/audio của check suspicious. Check thường không giữ raw media. Đăng ký thêm công ty, integration keys và subscription deactivation đã có; tenant isolation áp dụng cho check, evidence và exports.

Live ngày 29/09: hai công ty có cùng mã EMP-001; same identity verified, other identity suspicious; evidence lưu và tải có xác thực; cross-tenant 404; retry idempotent và conflict 409; PDF/CSV và first/last check ranges; callbacks acknowledged HTTP 200. Ảnh ghép hai khuôn mặt/audio ghép hai người tạo `multiple_faces` và `multiple_speakers_suspected`. Media bootstrap/tiled là thử vận chuyển/inference, không phải benchmark người dùng thật.

Quality maintenance: **65 tests pass, coverage 86,50%**; Grafana **62 panels, 67 queries**. Portal được kiểm tra bằng Streamlit AppTest với API thật: trang đăng ký, sáu trang cho mỗi công ty và inline CSV export. Camera/mic và trình duyệt download/playback vẫn cần acceptance trên thiết bị thật. Xem [VERIFICATION.md](VERIFICATION.md) và [PROJECT_REPORT.md](PROJECT_REPORT.md) cho kết quả cuối; các mục bên dưới giữ bằng chứng baseline 28/09.

GitHub maintenance [run 36562882154](https://github.com/TrinhDucDuong/ddm501-face-voice-proctoring/actions/runs/36562882154) **success** cho executable commit `8b720fc1a30ba16754c785020325e40de27c02e4`: quality, containers và deploy-demo đều pass. Remote có **65 tests, coverage 86,45%**. Runtime đã đối chiếu đúng release SHA; kiểm tra công ty/callbacks/isolation/evidence/export và monitoring sau deployment pass. Các commit tài liệu bàn giao sau SHA này không thay executable code.

## Phạm vi và quyền đã có

Hoàn thiện dự án theo rubric/full pipeline, monitoring tập trung Grafana, cảnh báo Telegram, CI/CD trên repo hiện tại. Người dùng đã cho phép sửa code, chạy Docker, commit/push `main`, sử dụng GitHub đã auth qua VS Code/Git Credential Manager. Bot Telegram đã được tạo, credentials trong `.env`. Không triển khai cloud có phí hoặc tạo bằng chứng human/team giả. Không dùng subagents.

## Kết quả baseline 28/09

- DAG `isolated_holdout_20260928`: 6/6 tasks success; snapshot → validate → calibrate/register → RAI → gate → reload. Champion/serving version **9**, 282 feature rows thuộc tenant demo.
- Evaluation: max-template scoring giống serving; năm identity partitions, một holdout giữ ngoài toàn bộ tuning, bốn fold CV nội bộ. Chọn margin nhỏ nhất đạt ngân sách CV từ tập ứng viên cố định; gate calibration/CV/holdout FAR/FRR vẫn 20%.
- **52 tests pass; coverage 88,76%** trên toàn API/monitoring và các module evaluation/snapshot/validation/promotion/RAI được khai báo. Ruff/diff checks pass.
- Full pipeline verification: 8 nhóm pass, inference ảnh/WAV thật. SaaS live: 19 checks pass. Portable image đã kiểm chứng local không có bind mount model.
- Grafana: 59 panels gồm 7 row headers, 64 truy vấn PromQL/SQL/LogQL đã chạy; readiness/data/drift/performance/Registry/review/webhook/DAG/RAI/resources/logs. Human thiếu nhãn hiển thị chờ, không giả dữ liệu.
- Reports HTML/JSON cùng origin Grafana: anonymous 401, authenticated 200. Docker stats qua read-only proxy; Alloy → Loki tập trung logs.
- Alertmanager → ops-monitor → Telegram đã gửi thành công tới `@ddm501_face_voice_proctoring_bot`, không log token.
- Restore drill: dump 563.959 bytes, restore vào DB riêng, đối chiếu tám bảng rồi xóa DB tạm; giữ dữ liệu gốc. Rollback rehearsal 8 → 7 → 8, readiness pass. Champion hiện tại là 9.
- Hai mappings, monitoring mapping, operations/capacity-cost và PowerPoint 12 slides có speaker notes đã tạo. Xem [VERIFICATION.md](VERIFICATION.md) để lấy số liệu/bằng chứng mới nhất.

## GitHub và runtime

Repo: https://github.com/TrinhDucDuong/ddm501-face-voice-proctoring, branch `main`.

Run [36430718832](https://github.com/TrinhDucDuong/ddm501-face-voice-proctoring/actions/runs/36430718832) **success**, commit `3e98c770c913b84f30e68e541d044551f966503c`, ngày 28/09/2026. Cả ba jobs **quality, containers, deploy-demo** thành công, gồm kiểm chứng dashboard/protected reports/freshness và upload artifacts. Remote: **52 passed, coverage 88,69%**; local: **52 passed, coverage 88,76%**. Deploy thực tế trên Docker Desktop qua runner Windows, source release ngoài OneDrive, dữ liệu/secrets giữ nguyên; chưa phải public cloud deployment.

Runner Windows `ddm501-local-windows`, labels `self-hosted`, `Windows`, `ddm501-demo`, tại `data/github-runner` (gitignored). Chạy hidden theo phiên người dùng, chưa cài Windows service. Sau reboot khởi động lại theo [OPERATIONS.md](OPERATIONS.md). Quality/build chạy GitHub-hosted Ubuntu; deploy chỉ trusted main, environment `demo` giới hạn main, concurrency một deploy.

`DDM501_RUNTIME_ROOT` trỏ repo ban đầu. Deploy dùng `.venv/Scripts/python.exe` đã có `dotenv`/`requests`, chỉ bypass execution policy ở process script. `prepare_runner_env.py --stage-deployment` dùng Git archive đúng commit SHA, materialize source tại `%LOCALAPPDATA%/DDM501/deployments/<sha>` ngoài OneDrive rồi giữ `.env`/Compose project/named volumes và absolute mounts models/data/reports/Airflow logs. Docker từng không đọc được file bind từ checkout lồng sâu trong OneDrive; đã kiểm chứng Docker đọc được config từ release local. Không xóa release đang chạy. Repo ban đầu tiếp tục giữ dữ liệu và secrets.

## Máy local và RAM

Docker từng OOM khi tutorial cũ và ECAPA/Evidently chạy cùng lúc. Đã tạo `C:\Users\tdd23\.wslconfig` với WSL2 memory 6GB, swap 6GB. MLflow một worker; Airflow một web worker và một LocalExecutor slot, có biến cấu hình trong `.env.example`.

Sáu container tutorial cũ đang **tạm dừng**, volumes/dữ liệu giữ nguyên. Chỉ khởi động khi có đủ RAM:

```powershell
docker start tutorial07-airflow-scheduler tutorial07-airflow-webserver tutorial07-mlflow ddm501-t03-airflow ddm501-t02-02-mlflow ddm501-t02-01-mlflow
```

Không overwrite `.env` bằng `.env.example`, không `down -v`, reset/clean hay xóa models/data/reports/runner. Không print/commit tokens, tenant keys hoặc backup. Runtime reports/data/models được gitignore.

## URLs đầy đủ

- Grafana: http://localhost:13000/d/biometric-overview
- Reports đăng nhập: http://localhost:13000/reports/data-drift.html, http://localhost:13000/reports/model-performance.html, http://localhost:13000/reports/synthetic-performance.html, http://localhost:13000/reports/data-quality.html, http://localhost:13000/reports/model-evaluation.html, http://localhost:13000/reports/pipeline-status.html, http://localhost:13000/reports/responsible-ai.html, http://localhost:13000/reports/alerts.html
- Portal: http://localhost:18501
- Legacy exam simulator: http://localhost:18600
- Hosted verify: link phiên do portal/API tạo, chứa private one-time token; không đưa token vào báo cáo.
- API docs: http://localhost:18100/docs
- Health/readiness: http://localhost:18100/health, http://localhost:18100/ready
- Airflow: http://localhost:18081
- MLflow: http://localhost:15030
- MinIO console: http://localhost:19101; S3 endpoint http://localhost:19100
- PostgreSQL: localhost:15433
- Prometheus: http://localhost:19090/targets, http://localhost:19090/alerts
- Alertmanager: http://localhost:19093
- Drift metrics: http://localhost:18001/metrics
- Webhook metrics: http://localhost:18002/metrics
- Ops metrics: http://localhost:18003/metrics/
- GitHub Actions: https://github.com/TrinhDucDuong/ddm501-face-voice-proctoring/actions
- Telegram: https://t.me/ddm501_face_voice_proctoring_bot

Grafana/Airflow demo `admin/admin`, loopback only. Monitoring là quyền platform admin; tenant selector chỉ lọc SQL, không biến dashboard thành quyền truy cập tenant.

## Còn cần người dùng/dữ liệu ngoài code

1. Camera/microphone browser acceptance và partner backend thật. Upload media/API/legacy simulator đã kiểm chứng.
2. Dữ liệu biometric có consent, nhãn human và demographic evaluation hợp lệ. Human fairness hiện `insufficient_data`; synthetic bootstrap không chứng minh production accuracy. MiniFASNet PAD/AASIST đã có inference; chưa có benchmark anti-spoof khách hàng. Physical audio replay, unseen video deepfake và simultaneous speaker overlap chưa được xác thực.
3. Tên/vai trò/contribution thật, meaningful commits của thành viên, demo/Q&A. Repo đã xác minh public qua GitHub API ngày 28/09, đáp ứng điều kiện truy cập trong rubric. Không tạo bằng chứng giả.
4. Cloud/customer host/domain/TLS/SSO và SLA/capacity pilot nếu muốn rollout ngoài local. Chưa provision cloud trả phí; local restore không chứng minh cloud disaster recovery.

## Tiếp tục an toàn

Đọc file này và [VERIFICATION.md](VERIFICATION.md), kiểm tra git status/nguồn thực tế. Chỉ chạy checks phù hợp thay đổi. Lệnh kiểm chứng: `.venv/Scripts/python.exe pipeline/verify_stack.py --dag-run isolated_holdout_20260928 --inference --require-alerts`, `pipeline/verify_monitoring_centre.py --send-alert`, `pipeline/verify_saas.py`. Inference/SaaS thêm events demo. `pipeline/github_ci.py` lấy Git Credential Manager trong bộ nhớ và chỉ ghi trạng thái đã lọc.
