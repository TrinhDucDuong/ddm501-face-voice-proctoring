# Bằng chứng và cách đối chiếu

Danh mục rà soát ngày **05/10/2026**. Các mốc dưới đây được ghi nhận trong các phiên
kiểm chứng trước; đợt cập nhật tài liệu này không chạy lại deploy, retrain hoặc simulation.

## CI/CD trên FSB

Repository: [FSB-MSA36HN/DDM501-face-voice-proctoring](https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring).

Mốc đã ghi nhận ngày 04/10/2026:
[run 37176107308](https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring/actions/runs/37176107308),
revision `22f64daa7f31181130d5b1355c97eb62eeac5ab6`.
`quality`, Windows `deployment-preflight`, `containers` và `deploy-demo` thành công.
Ubuntu ghi nhận 161 test cases với 2 skip; Windows thực thi 2 test deployment không
skip. Deploy kiểm tra dashboard tổng quan với 20 truy vấn. Đây là bằng chứng của
revision đó, không tự chứng minh các thay đổi chưa commit hoặc chưa deploy đã chạy trên GitHub.

Khi cần kết quả mới, mở [Actions](https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring/actions),
đối chiếu SHA, từng job và artifacts `quality-evidence`,
`deployment-preflight-evidence`, `deployment-monitoring-evidence`.
JUnit/coverage có thể hết hạn lưu trên GitHub; nếu không còn artifact, ghi rõ thiếu
bằng chứng chi tiết. Push chỉ sửa Markdown/`docs/**` không tự kích hoạt workflow;
PR hoặc workflow dispatch có thể chạy CI theo [DEPLOYMENT](../DEPLOYMENT.md).

## Simulation local ngày 04/10/2026

| Modality | Kịch bản | Run ID |
|---|---|---|
| Voice | Promotion | `06dcd24d-0bfe-4667-9791-924456653862` |
| Face | Rollback tại canary 25% | `1e17fc9a-9db7-4fa6-b57a-a6130356a7c4` |
| Face | Promotion | `f819f41e-9254-44bf-8e69-d605b2f6e7c6` |
| Voice | Rollback tại canary 25% | `1187a0ca-45cb-4ff0-a251-a5aeb088c626` |

Đã ghi nhận bốn DAG run hoàn tất, reset PASS và policy production không đổi trong
phép đối chiếu trước/sau. Simulation dùng vector/nhãn tổng hợp, DB và MLflow riêng,
HTTP policy routing và alert receipt thật. Rollback là outcome đúng của scenario
tiêm lỗi; không phải candidate được promote. Chi tiết nằm trong [SIMULATION](SIMULATION.md).

Đợt local này ghi nhận 163 tests pass, dashboard simulation 10 panel/17 truy vấn
có giá trị hữu hạn và browser không có lỗi JavaScript. Source simulation lúc đó
có thay đổi local ngoài revision CI nêu trên. Các JSON/screenshots trong `reports/`
là artifacts gitignored, không bảo đảm có trên clone mới. Không biến những số này
thành coverage, accuracy hoặc kết quả CI hiện tại.

## Những điều các bằng chứng này chưa xác nhận

- Accuracy, demographic fairness và anti-spoof trên nhân viên thật.
- Shadow/canary production với lượng nhãn và thời gian theo cấu hình production.
- Capacity/concurrency 50.000 nhân viên hoặc disaster recovery trên cloud.
- Tự tạo champion production đã đánh giá từ registry rỗng.
- Fairness gate tự động trong endpoint candidate của lifecycle modality.

## Ghi nhận một lần kiểm chứng mới

Lưu timestamp, source SHA/dirty state, loại môi trường, command hoặc DAG/run ID,
nguồn dữ liệu/labels, kết quả thực tế và đường dẫn artifact đã lọc secrets.
Phân biệt checks chỉ đọc với verifier tạo tenant/events, gửi Telegram, hoặc chạy
simulation. Xem [OPERATIONS](../OPERATIONS.md) trước khi chạy.

Checkpoint 28–29/09 nằm trong [archive](archive/PROJECT_STATE_2026-09-29.md).
Run ID từ repository cá nhân giai đoạn đó không được gắn sang URL Actions FSB.
