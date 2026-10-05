# Bộ trình bày và demo DDM501

Kế hoạch hiện hành: **15 phút trình bày + 10–15 phút demo + 10 phút Q&A**.
Bản chuẩn dùng demo 13 phút, tổng 38 phút. Nguồn được rà soát ngày 05/10/2026.

## Nguồn hiện hành

- [Nội dung slide](docs/presentation/deck-content.json): 18 slide present, 8 slide
  dẫn demo, 1 slide Q&A và 6 phụ lục. Đây là nguồn cho builder và lời thoại.
- [SPEAKER_SCRIPT](docs/presentation/SPEAKER_SCRIPT.md): lời thoại, phân vai, mốc
  thời gian và nguồn đối chiếu; sinh từ cùng JSON.
- [DEMO_RUNBOOK](docs/presentation/DEMO_RUNBOOK.md): thao tác sản phẩm, monitoring,
  simulation promotion/rollback/reset, điều kiện chuẩn bị và phương án khi demo chậm.
- [QA_GUIDE](docs/presentation/QA_GUIDE.md): 23 câu hỏi luyện tập, giới hạn và người trả lời.

Câu chuyện mở đầu là giả định về thi hộ trong kỳ đánh giá ngoại ngữ doanh nghiệp.
Không trình bày nó như sự cố khách hàng đã ghi nhận. Phần kỹ thuật phân biệt
encoder pretrained, threshold retraining, template update, policy canary và
application Compose deployment. Demo dùng tenant riêng và simulation có labels
tổng hợp; xem [SIMULATION](docs/SIMULATION.md) và [EVIDENCE](docs/EVIDENCE.md).

## Các bản xuất cũ

[PowerPoint](docs/archive/presentation-2026-10-04/DDM501_Defense_15p_Demo13p_QA10p.pptx),
[PDF slide](docs/archive/presentation-2026-10-04/DDM501_Defense_15p_Demo13p_QA10p.pdf)
và [PDF kịch bản](docs/archive/presentation-2026-10-04/DDM501_Script_Demo_QA.pdf)
được giữ nguyên trong archive. PPTX đã có chỉnh sửa thủ công/reorder sau export,
nên PDF, số thứ tự và speaker script cũ không hoàn toàn khớp nhau. Bản cũ còn dẫn
nguồn đã gỡ và chứa số liệu lịch sử. Không dùng chúng như tài liệu đã cập nhật hôm nay.

## Tạo bản xuất mới

Trên Windows có PowerPoint, cài `requirements-docs.txt` vào venv rồi chạy từ root:

```powershell
.venv/Scripts/python.exe pipeline/build_presentation_script.py
powershell -NoProfile -ExecutionPolicy Bypass -File pipeline/build_classroom_presentation.ps1
.venv/Scripts/python.exe pipeline/build_rehearsal_pdf.py
```

Builder slide dùng COM PowerPoint, tạo PPTX/PDF và PNG previews. Nó từ chối ghi đè
PPTX đã tồn tại; dùng `-Output` với tên mới khi cần. Builder PDF kịch bản dùng
ReportLab và Segoe UI. Xem lại từng slide/page, Unicode, tràn chữ, thứ tự và Notes
trước khi dùng bản xuất làm tài liệu nộp. Đợt rà soát này cập nhật nguồn và lời
thoại, không tạo lại hoặc gắn nhãn mới cho binary lịch sử.

`pipeline/build_presentation.py` (generator 12 slide cũ) đã được bỏ; chỉ duy trì
một nguồn JSON và builder lớp học. PDF báo cáo dự án là bản xuất tùy chọn từ
`pipeline/build_project_report.py`, ghi vào `reports/`; nguồn là PROJECT_REPORT.md.

Số liệu 03/10 trên các slide evidence vẫn là số liệu lịch sử. Muốn thay chúng bằng
run mới, giữ đúng run ID/timestamp và kiểm tra report thực tế; không chỉ đổi ngày.
Trước khi demo, diễn tập trên runtime thật và đọc chính xác kết quả đang thấy.
