"""Tenant-scoped integrity reports. No exam scores or admission decisions."""
import csv
import io
import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .auth import Principal, get_person, operator
from .checks import check_query
from .db import get_db
from .models import IntegrityCheck, Tenant

router = APIRouter()


def report_data(db, principal, person_id=None, session_id=None, start=None, end=None):
    if person_id:
        get_person(db, person_id, principal)
    if start and end and start > end:
        raise HTTPException(422, 'start must precede end')
    rows = db.scalars(check_query(principal, person_id, session_id, start, end)
                      .order_by(IntegrityCheck.created_at, IntegrityCheck.id)).all()
    employees = {}
    results = [row.result for row in rows]
    for result in results:
        key = (result['employee_id'], result['session_id'])
        if key not in employees:
            employees[key] = {k: result[k] for k in ('employee_id', 'employee_code', 'employee_name', 'session_id')}
            employees[key].update(first_check_at=result['checked_at'], last_check_at=result['checked_at'], checks=0, suspicious=0)
        item = employees[key]
        item['last_check_at'] = result['checked_at']
        item['checks'] += 1
        item['suspicious'] += result['integrity_status'] == 'suspicious'
    return {'company': db.get(Tenant, principal.tenant_id).name, 'employees': list(employees.values()),
            'checks': results, 'coverage_note': 'Khoảng thời gian phản ánh các lượt check đã nhận, không chứng minh giám sát liên tục.'}


def csv_cell(value):
    value = str(value) if value is not None else ''
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value


def csv_report(data):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    fields = ['check_id', 'employee_code', 'employee_name', 'session_id', 'checked_at',
              'integrity_status', 'face_match', 'voice_match', 'reason_labels', 'evidence_status', 'model_version']
    writer.writerow(fields)
    for row in data['checks']:
        writer.writerow([csv_cell('; '.join(row[key]) if isinstance(row[key], list) else row[key]) for key in fields])
    return stream.getvalue().encode('utf-8-sig')


def pdf_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if 'IntegritySans' in pdfmetrics.getRegisteredFontNames():
        return 'IntegritySans'
    candidates = [os.getenv('PDF_FONT_PATH', ''), '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                  'C:/Windows/Fonts/arial.ttf']
    for path in candidates:
        if path and Path(path).is_file():
            pdfmetrics.registerFont(TTFont('IntegritySans', path))
            return 'IntegritySans'
    raise RuntimeError('Unicode PDF font unavailable; install fonts-dejavu-core or set PDF_FONT_PATH')


def pdf_report(data):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    font = pdf_font()
    normal = ParagraphStyle('body', fontName=font, fontSize=10, leading=15, spaceAfter=7)
    heading = ParagraphStyle('heading', parent=normal, fontSize=16, leading=22, spaceAfter=12)
    output = io.BytesIO()
    document = SimpleDocTemplate(output, title='Employee integrity report', leftMargin=2*cm, rightMargin=2*cm,
                                 topMargin=2*cm, bottomMargin=2*cm)
    story = [Paragraph('Báo cáo xác minh danh tính và liêm chính', heading),
             Paragraph(escape(data['company']), normal), Paragraph(escape(data['coverage_note']), normal)]
    for employee in data['employees']:
        story += [Spacer(1, 8), Paragraph(escape(f"{employee['employee_code']} - {employee['employee_name']}"), heading),
                  Paragraph(escape(f"Phiên: {employee['session_id']} | {employee['checks']} lượt check | {employee['suspicious']} nghi vấn"), normal),
                  Paragraph(escape(f"Từ {employee['first_check_at']} đến {employee['last_check_at']}"), normal)]
        for row in data['checks']:
            if (row['employee_id'], row['session_id']) != (employee['employee_id'], employee['session_id']):
                continue
            text = f"{row['checked_at']} | {row['check_id']} | {row['status_label']}"
            story.append(Paragraph(escape(text), normal))
            story.append(Paragraph(escape('Lý do: '+('; '.join(row['reason_labels']) or 'Không có dấu hiệu nghi vấn')), normal))
            story.append(Paragraph(escape(f"Bằng chứng: {row['evidence_status']} | Model: {row['model_version']}"), normal))
    if not data['checks']:
        story.append(Paragraph('Chưa có lượt kiểm tra trong phạm vi đã chọn.', normal))
    def footer(canvas, doc):
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor('#475569'))
        canvas.drawString(2*cm, cm, 'Kết quả model là tín hiệu; khách hàng quyết định nghiệp vụ.')
        canvas.drawRightString(doc.pagesize[0]-2*cm, cm, str(doc.page))
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


@router.get('/v1/company/report')
@router.get('/v1/company/report{extension}')
def report(extension: str = '', person_id: str | None = None, session_id: str | None = None,
           start: datetime | None = None, end: datetime | None = None,
           db: Session = Depends(get_db), principal: Principal = Depends(operator)):
    if extension not in ('', '.csv', '.pdf'):
        raise HTTPException(404, 'Report format not found')
    data = report_data(db, principal, person_id, session_id, start, end)
    if not extension:
        return data
    content = csv_report(data) if extension == '.csv' else pdf_report(data)
    return Response(content, media_type='text/csv' if extension == '.csv' else 'application/pdf',
                    headers={'Content-Disposition': f'attachment; filename="integrity-report{extension}"',
                             'Cache-Control': 'no-store'})
