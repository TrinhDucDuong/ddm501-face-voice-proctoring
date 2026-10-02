"""Render the versioned business/technical project report with Unicode text."""
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'api'))
from app.company_reports import pdf_font  # noqa: E402


def main():
    font = pdf_font()
    normal = ParagraphStyle('normal', fontName=font, fontSize=10.5, leading=16, spaceAfter=8)
    title = ParagraphStyle('title', parent=normal, fontSize=20, leading=27, spaceAfter=15, keepWithNext=True)
    heading = ParagraphStyle('heading', parent=normal, fontSize=14, leading=20, spaceBefore=14, spaceAfter=8, keepWithNext=True)
    story = []
    for line in (ROOT/'PROJECT_REPORT.md').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        if line.startswith('# '):
            story.append(Paragraph(escape(line[2:]), title))
        elif line.startswith('## '):
            story.append(Paragraph(escape(line[3:]), heading))
        else:
            story.append(Paragraph(escape(line), normal))
    story.append(Spacer(1, .3*cm))
    destination = ROOT/'docs/DDM501_Project_Report.pdf'
    doc = SimpleDocTemplate(str(destination), title='DDM501 Face & Voice Integrity Service',
                            author='DDM501 project', leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    def footer(canvas, document):
        canvas.setFont(font, 8)
        canvas.drawString(2*cm, cm, 'DDM501 | MVP tích hợp doanh nghiệp | 29/09/2026')
        canvas.drawRightString(document.pagesize[0]-2*cm, cm, str(document.page))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(destination)


if __name__ == '__main__':
    main()
