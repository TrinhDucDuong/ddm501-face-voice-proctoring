"""Generate the Vietnamese rehearsal script from the same source as the deck."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/presentation/deck-content.json'
TARGET = ROOT / 'docs/presentation/SPEAKER_SCRIPT.md'


def clock(seconds):
    return f'{seconds // 60:02}:{seconds % 60:02}'


def main():
    data = json.loads(SOURCE.read_text(encoding='utf-8'))
    slides = data['slides']
    total = sum(s['seconds'] for s in slides)
    lines = [
        '# Kịch bản nói: Face + Voice Integrity', '',
        f'Bản bảo vệ DDM501, cập nhật {data["date"]}. Sinh từ deck-content.json; tên PowerPoint khi export: '
        f'`{data["deck_filename"]}` trong cùng thư mục.', '',
        '**Khung thời gian:** trình bày 15 phút, demo mục tiêu 13 phút '
        '(cho phép 10–15 phút), Q&A 10 phút. Tổng buổi bảo vệ 35–40 phút, '
        'bản đầy đủ 38 phút. Có 18 slide trình bày, 8 slide dẫn demo, '
        '1 slide Q&A và 6 slide phụ lục. Notes được tạo khi export PowerPoint từ nguồn này. '
        'Các PPTX/PDF trong archive là bản lịch sử, không đồng bộ tự động với nguồn hiện hành.', '',
        'Kịch bản thao tác toàn diện: [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md). '
        'Câu hỏi phản biện và phân vai: [QA_GUIDE.md](QA_GUIDE.md).', '',
        '## Cách sử dụng', '',
        '- Tập nói theo ý, không đọc nguyên slide. Các đoạn dưới là lời thoại có thể đọc trực tiếp.',
        '- Phần **Thao tác** dành cho người điều khiển máy, không đọc thành tiếng.',
        '- Mốc thời gian là ngân sách cho giải thích và thao tác, không phải cam kết scheduler chạy đúng số giây.',
        '- Câu chuyện mở đầu là tình huống giả định. Không nói nhóm đã phát hiện một vụ gian lận thật.',
        '- Số liệu evidence ngày 03/10 là lịch sử đã lưu. Nếu mở run mới, đọc kết quả của chính run đó.',
        '- Phụ lục được đánh dấu hidden trong trình chiếu. Mở bằng chọn slide khi cần trả lời câu hỏi.', '',
        '## Phân vai đề xuất', '',
        '| Người nói | Slide | Nội dung |', '|---|---|---|',
        '| Trịnh Đức Dương | 1–5, 14–15; điều phối Q&A | Câu chuyện, giải pháp và lifecycle |',
        '| To Thanh Hai | 6–9, 16 | Tích hợp, model I/O, kiến trúc, lưu trữ, CI/CD; điều khiển demo |',
        '| Do Quang Hiep | 10–13; phụ lục khi cần | Drift, decision engine, template và kiểm chứng evaluation |',
        '| Ngo Anh Duc | 17–18, dẫn demo 19–26 | Giới hạn, chuyển phần, bằng chứng và demo |', '',
        'Nếu chỉ một người trình bày, bỏ các câu mời chuyển lời và giữ nguyên mạch nội dung.', '',
        '## Chuẩn bị trước buổi trình bày', '',
        '1. Mở PowerPoint và dùng Presenter View để xem Notes. Đóng cửa sổ chứa key hoặc thông tin riêng.',
        '2. Kiểm tra Docker Desktop và Airflow scheduler hoạt động. Không nâng cấp dependencies hoặc rebuild sát giờ.',
        '3. Đăng nhập platform ở portal :18501 trước khi chiếu màn hình. Không hiển thị hoặc đọc API key.',
        '4. Mở sẵn Airflow DAG `biometric_simulation` tại :18081 và MLflow simulation tại :15031.',
        '5. Dùng nút **3. Khôi phục baseline demo** nếu có run trước đó. Không dùng `docker compose down -v`.',
        '6. Lưu sẵn evidence JSON của một lượt promotion và rollback thành công về mặt kịch bản. Slides 23 và 25 có evidence lịch sử dự phòng.',
        '7. Đo thử thời gian hai kịch bản trên chính máy trình chiếu. Giới hạn demo tối đa 15 phút; nếu cần, dùng evidence lịch sử cho kịch bản thứ hai như DEMO_RUNBOOK hướng dẫn.', '',
        '## Lời thoại theo slide', '',
    ]
    elapsed = {'present': 0, 'demo': 0, 'qa': 0, 'appendix': 0}
    sections = {'present': 'Trình bày', 'demo': 'Demo', 'qa': 'Q&A', 'appendix': 'Phụ lục'}
    for number, slide in enumerate(slides, 1):
        seconds = slide['seconds']
        section = slide['section']
        start = elapsed[section]
        interval = (f'{sections[section]} {clock(start)}–{clock(start + seconds)}'
                    if seconds else 'Mở theo câu hỏi, không tính thêm thời gian')
        lines += [f'### Slide {number:02}: {slide["title"]}', '',
                  f'**Người nói:** {slide["speaker"]}', '', f'**Mốc thời gian:** {interval}', '',
                  '**Lời thoại**', '', slide['notes'], '', '**Thao tác / chuyển lời**', '',
                  slide['cue'], '', '**Nguồn đối chiếu:** ' + '; '.join(slide['sources']), '']
        elapsed[section] += seconds
    lines += [
        '## Khi demo không diễn ra như dự kiến', '',
        '| Tình huống | Xử lý và câu nói |', '|---|---|',
        '| Queue chờ hơn một phút | Kiểm tra scheduler và DAG. Nói: “Job đang chờ Airflow nhận, đây chưa phải kết quả gate.” |',
        '| Chưa nhận alert | Xem Prometheus/Alertmanager và alert receipt. Không bỏ gate chờ alert hoặc bấm lại liên tục. |',
        '| Promotion chưa xong trong khung giờ | Nói: “Lượt hiện tại còn chạy. Em chuyển sang evidence đã lưu ngày 03/10 để giữ thời lượng.” Mở slide 23. |',
        '| FAILED_CANARY trong scenario rollback | Đây là kết quả mong đợi. Chỉ failure metric, traffic zero và probe dùng champion. |',
        '| FAILED do hạ tầng | Nói rõ đây là lỗi hạ tầng, không đổi tên thành rollback thành công. Dùng evidence lịch sử rồi reset khi bước active dừng. |',
        '| Reset đang chờ | Đợi bước đang chạy kết thúc/cancel. Không xóa DB, container volume hoặc giả định trạng thái đã reset. |', '',
        '## Câu hỏi dự kiến và câu trả lời ngắn', '',
        '**Tại sao phải dùng cả Face và Voice?** Hai modality cung cấp bằng chứng danh tính khác nhau cho bối cảnh có ảnh và phần nói. '
        'Nhóm chưa có benchmark để khẳng định một tỷ lệ cải thiện accuracy cụ thể so với chỉ một modality.', '',
        '**Có bắt được mọi cheating không?** Không. Phạm vi là danh tính và tín hiệu integrity trên các capture được gửi. '
        'Đọc tài liệu ngoài màn hình, gợi ý bên ngoài và mọi kiểu deepfake không được bảo đảm phát hiện.', '',
        '**Champion có phải model tốt nhất không?** Là policy được chấp nhận theo gate và bằng chứng hiện có để phục vụ. '
        'Không phải tối ưu tuyệt đối trên mọi dữ liệu tương lai. Challenger vẫn cần offline, shadow và canary.', '',
        '**Vì sao score của champion và challenger bằng nhau?** Encoder và cosine được dùng chung. '
        'Policy hiện khác ở threshold, nên score bằng nhau nhưng decision có thể khác.', '',
        '**Data drift có tự retrain không?** Một tín hiệu thống kê riêng lẻ không đủ. Cần persistence, trusted '
        'performance degradation, đủ dữ liệu mới, nhiều cohort và không chủ yếu do input/template aging.', '',
        '**Embedding được lưu ở đâu?** PostgreSQL dạng JSON. Đây là verification 1:1 theo employee đã khai báo, '
        'không phải nearest-neighbor search toàn bộ nhân viên.', '',
        '**Thiếu nhãn thì làm gì?** Trả INSUFFICIENT_DATA hoặc dừng progression để thu review phù hợp. '
        'Không dùng accept/reject của model làm ground truth.', '',
        '**Simulation có ảnh hưởng hệ thống thật không?** Dữ liệu, DB và MLflow riêng; không đổi production policies. '
        'Host và Airflow dùng chung nên có thể ảnh hưởng tài nguyên/latency. Không khẳng định cách ly phần cứng.', '',
        '**Demo canary thành công chứng minh điều gì?** Chứng minh routing, gates và Registry transitions chạy trên dữ liệu synthetic. '
        'Không chứng minh mức FAR/FNMR trong dân số hoặc accuracy trên người thật.', '',
        '**Tại sao không dùng ngưỡng 20% trong báo cáo cũ?** Đó là gate của bundle demo lịch sử. '
        'Lifecycle mới dùng cấu hình per-modality tại `pipeline/lifecycle_config.json`; cần gắn mọi con số với đúng phiên bản.', '',
        '**50.000 nhân viên đã chạy được chưa?** Chưa có load/concurrency benchmark ở quy mô đó. '
        'Cần xác định lịch thi, số request đồng thời, sizing và retention trước pilot.', '',
        '**Ai quyết định nhân viên gian lận?** Dịch vụ trả tín hiệu, lý do và bằng chứng. '
        'Khách hàng quyết định nghiệp vụ theo quy trình review, không tự động kỷ luật từ nhãn suspicious.', '',
        '## Cách rút ngắn nếu gần hết giờ', '',
        'Giữ câu chuyện, sơ đồ I/O, decision engine, lifecycle và một kịch bản demo. '
        'Rút phần bảng feature/kiến trúc chi tiết, dùng evidence lịch sử thay cho kịch bản live thứ hai. '
        'Không cắt câu phân biệt dữ liệu tổng hợp với benchmark thật hoặc phần giới hạn của dự án.', '',
    ]
    TARGET.write_text('\n'.join(lines), encoding='utf-8')
    print(f'{len(slides)} slide scripts; complete session {clock(total)}; {TARGET}')


if __name__ == '__main__':
    main()
