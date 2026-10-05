"""Create a printable rehearsal packet from the presentation Markdown sources."""
import json
import re
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'docs/presentation'


def inline(value):
    value = escape(value)
    value = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', value)
    value = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', value)
    return re.sub(r'`([^`]+)`', r'<font color="#176E68">\1</font>', value)


def build():
    source_date = json.loads((FOLDER / 'deck-content.json').read_text(encoding='utf-8'))['date']
    for name, file in [('Segoe', 'segoeui.ttf'), ('Segoe-Bold', 'segoeuib.ttf'),
                       ('Segoe-Italic', 'segoeuii.ttf')]:
        pdfmetrics.registerFont(TTFont(name, str(Path('C:/Windows/Fonts') / file)))
    pdfmetrics.registerFontFamily('Segoe', normal='Segoe', bold='Segoe-Bold',
                                  italic='Segoe-Italic', boldItalic='Segoe-Bold')
    styles = getSampleStyleSheet()
    for key in ['Normal', 'BodyText', 'Heading1', 'Heading2', 'Heading3']:
        styles[key].fontName = 'Segoe'
        styles[key].textColor = colors.HexColor('#172F3C')
    styles['BodyText'].fontSize = 10.2
    styles['BodyText'].leading = 15.5
    styles['BodyText'].spaceAfter = 7
    styles.add(ParagraphStyle('AttachedLabel', parent=styles['BodyText'], keepWithNext=True))
    for key, size in [('Heading1', 22), ('Heading2', 16), ('Heading3', 12.5)]:
        styles[key].fontName = 'Segoe-Bold'
        styles[key].fontSize = size
        styles[key].leading = size * 1.3
        styles[key].spaceBefore = 13
        styles[key].spaceAfter = 8
        styles[key].keepWithNext = True
    styles.add(ParagraphStyle('Cell', fontName='Segoe', fontSize=8.7, leading=12,
                              textColor=colors.HexColor('#172F3C'), alignment=TA_LEFT))
    styles.add(ParagraphStyle('CellHead', parent=styles['Cell'], fontName='Segoe-Bold',
                              textColor=colors.white))
    styles.add(ParagraphStyle('Cover', parent=styles['Heading1'], fontSize=28, leading=36))
    output = FOLDER / 'DDM501_Script_Demo_QA.pdf'
    doc = SimpleDocTemplate(str(output), pagesize=(210*mm, 297*mm),
                            leftMargin=19*mm, rightMargin=19*mm,
                            topMargin=20*mm, bottomMargin=18*mm,
                            title='DDM501 - Kịch bản trình bày, demo và Q&A',
                            author='DDM501 FSB-MSA36HN')
    story = [Spacer(1, 22*mm), Paragraph('Face + Voice Integrity', styles['Cover']),
             Spacer(1, 9*mm), Paragraph('Kịch bản bảo vệ dự án', styles['Heading1']),
             Paragraph('15 phút trình bày<br/>10–15 phút demo<br/>10 phút Q&A', styles['Heading2']),
             Spacer(1, 12*mm), HRFlowable(width='100%', color=colors.HexColor('#176E68')),
             Spacer(1, 6*mm), Paragraph('Trịnh Đức Dương<br/>Do Quang Hiep<br/>To Thanh Hai<br/>Ngo Anh Duc', styles['BodyText']),
             Spacer(1, 8*mm), Paragraph(f'Bản hướng dẫn tập nói và điều khiển demo, ngày {source_date}. '
             'Câu chuyện mở đầu là tình huống giả định. Các số liệu lịch sử luôn được ghi rõ nguồn và thời điểm.', styles['BodyText']),
             Spacer(1, 8*mm), Paragraph('Nội dung: lời thoại từng slide, runbook demo 13 phút, '
             'phương án 10/15 phút và ngân hàng 23 câu hỏi phản biện.', styles['BodyText'])]

    for filename in ['SPEAKER_SCRIPT.md', 'DEMO_RUNBOOK.md', 'QA_GUIDE.md']:
        story.append(PageBreak())
        lines = (FOLDER/filename).read_text(encoding='utf-8').splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.startswith('|'):
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith('|'):
                    raw = lines[i].strip()
                    if not re.fullmatch(r'[|:\- ]+', raw):
                        table_lines.append([cell.strip() for cell in raw.strip('|').split('|')])
                    i += 1
                columns = len(table_lines[0])
                rows = [[Paragraph(inline(cell), styles['CellHead' if r == 0 else 'Cell'])
                         for cell in row] for r, row in enumerate(table_lines)]
                width = doc.width / columns
                widths = [width] * columns
                if columns == 3:
                    widths = [doc.width*.22, doc.width*.36, doc.width*.42]
                table = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT',
                              rowSplitRange=(3, -1) if len(rows) > 3 else None)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#176E68')),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#E4EEEA'), colors.white]),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('TOPPADDING', (0,0), (-1,-1), 6),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                    ('LINEBELOW', (0,0), (-1,0), .5, colors.white),
                ]))
                story += [table, Spacer(1, 9)]
                continue
            match = re.match(r'^(#{1,3})\s+(.+)', line)
            if match:
                story.append(Paragraph(inline(match[2]), styles[f'Heading{len(match[1])}']))
                i += 1
                continue
            chunk = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r'^(#|\||- |\d+\.)', lines[i].strip()):
                chunk.append(lines[i].strip())
                i += 1
            text = ' '.join(chunk)
            if text.startswith('- '):
                text = '• ' + text[2:]
            attached = text.startswith(('**Người nói:**', '**Mốc thời gian:**',
                                        '**Lời thoại**', '**Thao tác / chuyển lời**'))
            story.append(Paragraph(inline(text), styles['AttachedLabel' if attached else 'BodyText']))

    def page(canvas, document):
        canvas.setFont('Segoe', 8)
        canvas.setFillColor(colors.HexColor('#526673'))
        canvas.drawString(19*mm, 285*mm, 'DDM501 / Face + Voice Integrity / 15 + 13 + 10 phút')
        canvas.drawRightString(191*mm, 10*mm, str(document.page))
    doc.build(story, onFirstPage=page, onLaterPages=page)
    print(output)


if __name__ == '__main__':
    build()
