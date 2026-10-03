"""Company portal. Technical monitoring is reserved for platform administrators."""
import base64
import os
import time as clock
import uuid
from datetime import datetime, time, timezone

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv('API_URL', 'http://localhost:18100').rstrip('/')
st.set_page_config(page_title='Face & Voice Integrity', layout='wide')
st.title('Face & Voice Integrity')
st.caption('Xác minh danh tính cho kỳ đánh giá ngoại ngữ của doanh nghiệp')
COLUMNS = {'employee_code': 'Mã nhân viên', 'employee_name': 'Họ tên', 'session_id': 'Phiên công ty',
           'check_id': 'Mã lượt kiểm tra', 'checked_at': 'Thời điểm kiểm tra', 'status_label': 'Kết quả',
           'reason_labels': 'Dấu hiệu', 'evidence_status': 'Bằng chứng', 'checks': 'Số lượt',
           'suspicious': 'Lượt nghi vấn', 'first_check_at': 'Bắt đầu nhận check', 'last_check_at': 'Lần check cuối'}


def logout():
    for state_key in list(st.session_state):
        del st.session_state[state_key]
    st.query_params.clear()
    st.query_params['page'] = 'login'


def api(method, path, raw=False, api_key=None, **kwargs):
    headers = {'X-API-Key': api_key if api_key is not None else st.session_state.get('auth_key', '')}
    r = requests.request(method, API_URL+path, headers=headers, timeout=180, **kwargs)
    if r.status_code == 401 and api_key is None and st.session_state.get('auth_key'):
        logout()
        st.rerun()
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.json().get('detail', 'Dịch vụ tạm thời chưa sẵn sàng')}")
    return r.content if raw else r.json()


def login():
    key = st.session_state.pop('login_key', '').strip()
    try:
        identity = api('GET', '/v1/me', api_key=key)
        if identity['role'] not in {'operator', 'platform'}:
            raise RuntimeError('Hãy dùng key quản trị công ty hoặc quản trị hệ thống.')
    except Exception as exc:
        st.session_state['login_error'] = str(exc)
        return
    logout()
    st.session_state['auth_key'] = key
    st.session_state['auth_expires_at'] = clock.time() + 3600
    st.query_params['page'] = 'portal'


def select_person(people):
    return st.selectbox('Nhân viên', people, format_func=lambda p: f"{p['external_id']} - {p['display_name']}")


def media_inputs(enrollment=False):
    camera = st.camera_input('Chụp ảnh 1' if enrollment else 'Chụp ảnh')
    second_camera = st.camera_input('Chụp ảnh 2') if enrollment else None
    faces = st.file_uploader('Hoặc tải ảnh', type=['jpg', 'jpeg', 'png', 'webp'], accept_multiple_files=enrollment)
    recording = st.audio_input('Thu audio 1' if enrollment else 'Thu audio')
    second_recording = st.audio_input('Thu audio 2') if enrollment else None
    voices = st.file_uploader('Hoặc tải WAV', type=['wav'], accept_multiple_files=enrollment)
    face_items = [item for item in (camera, second_camera) if item] + (faces if enrollment else [faces] if faces else [])
    voice_items = [item for item in (recording, second_recording) if item] + (voices if enrollment else [voices] if voices else [])
    return face_items, voice_items


def download_link(content, extension):
    mime = 'text/csv' if extension == 'csv' else 'application/pdf'
    encoded = base64.b64encode(content).decode()
    # Inline data avoids publishing tenant reports through Streamlit's shared static media URLs.
    st.markdown(f'<a download="integrity-report.{extension}" href="data:{mime};base64,{encoded}">Tải báo cáo {extension.upper()}</a>', unsafe_allow_html=True)


if st.session_state.get('auth_key') and clock.time() >= st.session_state.get('auth_expires_at', 0):
    logout()

if not st.session_state.get('auth_key'):
    st.query_params['page'] = 'login'
    st.subheader('Đăng nhập quản trị')
    st.info('Nhập key được cấp để mở không gian quản trị công ty hoặc hệ thống.')
    with st.form('login', clear_on_submit=True):
        st.text_input('API key quản trị công ty / nền tảng', type='password', key='login_key')
        st.form_submit_button('Đăng nhập', type='primary', on_click=login)
    if st.session_state.get('login_error'):
        st.error(st.session_state['login_error'])
    with st.expander('Đăng ký công ty - gói dùng thử giả lập'):
        with st.form('register'):
            name = st.text_input('Tên công ty')
            submit = st.form_submit_button('Đăng ký dùng thử', type='primary')
        if submit:
            try:
                row = api('POST', '/v1/registrations', json={'name': name})
                st.success(f"Đã tạo {row['name']}")
                st.warning('Lưu key quản trị dưới đây. Key chỉ hiển thị một lần; dùng để đăng nhập tại biểu mẫu phía trên.')
                st.code(row['operator_key'])
            except Exception as exc:
                st.error(str(exc))
    st.stop()

st.query_params['page'] = 'portal'
st.sidebar.button('Đăng xuất', on_click=logout)

try:
    identity = api('GET', '/v1/me')
    if st.session_state.get('enrollment_link_tenant') != identity['tenant_id']:
        st.session_state.pop('enrollment_link', None)
        st.session_state.pop('enrollment_name', None)
        st.session_state['enrollment_link_tenant'] = identity['tenant_id']
    platform = identity['role'] == 'platform'
    operator = identity['role'] in {'operator', 'platform'}
    pages = ['Công ty & đăng ký', 'Vận hành MLOps'] if platform else ['Tổng quan', 'Nhân viên', 'Kiểm tra tích hợp', 'Lịch sử & báo cáo']
    if operator and not platform:
        pages += ['Ghi danh face & voice', 'API & Webhook']
    st.sidebar.caption('Quản trị nền tảng' if platform else 'Dữ liệu của công ty bạn')
    page = st.sidebar.radio('Chức năng', pages)

    if page == 'Tổng quan':
        people = api('GET', '/v1/people')
        rows = api('GET', '/v1/checks')
        if operator:
            st.subheader(api('GET', '/v1/company')['name'])
        a, b, c = st.columns(3)
        a.metric('Nhân viên', len(people))
        b.metric('Đủ mẫu ghi danh', sum(p['ready'] for p in people))
        c.metric('Lượt kiểm tra đã nhận', rows['total'])
        st.markdown('Đăng ký nhân viên → ghi danh → cấu hình webhook → hệ thống công ty gửi các lượt check.')
        st.caption('Công ty tự quyết định thời điểm kiểm tra, điểm thi và xử lý nghiệp vụ.')

    elif page == 'Nhân viên':
        with st.form('employee', clear_on_submit=True):
            code = st.text_input('Mã nhân viên', placeholder='EMP-001')
            name = st.text_input('Họ tên')
            if st.form_submit_button('Thêm nhân viên', type='primary'):
                api('POST', '/v1/people', json={'external_id': code, 'display_name': name})
                st.success('Đã thêm nhân viên.')
        employees = api('GET', '/v1/people')
        st.dataframe(pd.DataFrame([{'Mã nhân viên': p['external_id'], 'Họ tên': p['display_name'],
                                   'Ghi danh': 'Đủ mẫu' if p['ready'] else 'Cần ghi danh'} for p in employees]),
                     use_container_width=True, hide_index=True)
        if employees:
            st.subheader('Gửi lời mời ghi danh cho nhân viên')
            invited = st.selectbox('Chọn nhân viên nhận lời mời', employees,
                                   format_func=lambda p: f"{p['display_name']} · {p['external_id']}")
            st.caption('Liên kết chỉ dùng một lần trong 24 giờ. Nhân viên tự gửi hai ảnh và hai WAV; không cần key quản trị.')
            if st.button('Tạo liên kết ghi danh', type='primary'):
                invitation = api('POST', f"/v1/people/{invited['id']}/enrollment-invitations")
                st.session_state['enrollment_link'] = 'http://localhost:18600/#enroll=' + invitation['token']
                st.session_state['enrollment_name'] = invited['display_name']
            if st.session_state.get('enrollment_link'):
                st.success(f"Sao chép liên kết cho {st.session_state['enrollment_name']}. Chỉ hiển thị trong phiên quản trị này.")
                st.code(st.session_state['enrollment_link'])

    elif page in {'Ghi danh face & voice', 'Kiểm tra tích hợp'}:
        enrollment = page == 'Ghi danh face & voice'
        people = api('GET', '/v1/people')
        if not people:
            st.info('Thêm nhân viên trước.')
        else:
            person = select_person(people)
            st.info('Ghi danh ít nhất 2 ảnh và 2 WAV; hệ thống giữ embedding, không giữ file ghi danh gốc.' if enrollment else
                    'Backend công ty gọi POST /v1/checks. Nhịp batch, ví dụ 30 giây và WAV 10 giây, do công ty cấu hình.')
            session = None if enrollment else st.text_input('Mã phiên nghiệp vụ', value='ANNUAL-ENGLISH-2026')
            faces, voices = media_inputs(enrollment)
            consent = st.checkbox('Công ty xác nhận có sự đồng ý của nhân viên để xử lý sinh trắc.')
            if st.button('Ghi danh' if enrollment else 'Gửi check', type='primary', disabled=not consent):
                if (enrollment and (len(faces) != 2 or len(voices) != 2)) or (not enrollment and (not faces or not voices)):
                    st.error('Cần cả ảnh và WAV.')
                else:
                    with st.spinner('Đang xử lý…'):
                        if enrollment:
                            files = [('face_files', (f.name, f.getvalue(), f.type or 'image/jpeg')) for f in faces]
                            files += [('voice_files', (f.name, f.getvalue(), 'audio/wav')) for f in voices]
                            result = api('POST', f"/v1/people/{person['id']}/enroll", files=files)
                        else:
                            result = api('POST', '/v1/checks', data={'person_id': person['id'], 'session_id': session,
                                         'request_id': str(uuid.uuid4()), 'consent': 'true'}, files={
                                'face_file': (faces[0].name, faces[0].getvalue(), faces[0].type or 'image/jpeg'),
                                'voice_file': (voices[0].name, voices[0].getvalue(), 'audio/wav')})
                    if not enrollment:
                        (st.success if result['integrity_status'] == 'verified' else st.warning)(result['status_label'])
                    else:
                        (st.success if result['ready'] else st.warning)('Đã ghi danh đủ mẫu.' if result['ready'] else 'Cần bổ sung mẫu ghi danh.')
                    with st.expander('Xem dữ liệu kỹ thuật (JSON)'):
                        st.json(result)

    elif page == 'Lịch sử & báo cáo':
        review_suggestions = {}
        if operator:
            queue = api('GET', '/v1/reviews/queue')
            review_suggestions = {item['check_id']: item['selection_reason'] for item in queue['items']}
            st.subheader('Các lượt cần kiểm duyệt')
            st.caption('Bao gồm lượt nghi vấn và một mẫu kiểm tra ngẫu nhiên từ mỗi 10 lượt bình thường gần đây.')
            if queue['items']:
                st.dataframe(pd.DataFrame(queue['items']), use_container_width=True, hide_index=True,
                             column_config=COLUMNS)
            else:
                st.info('Hiện không có lượt chờ kiểm duyệt.')
        people = api('GET', '/v1/people')
        person = st.selectbox('Phạm vi nhân viên', [None]+people, format_func=lambda p:
                              'Tất cả' if p is None else f"{p['external_id']} - {p['display_name']}")
        session = st.text_input('Mã phiên nghiệp vụ (để trống xem tất cả)')
        params = {k: v for k, v in {'person_id': person['id'] if person else None, 'session_id': session}.items() if v}
        if st.checkbox('Lọc khoảng ngày'):
            a, b = st.columns(2)
            start, end = a.date_input('Từ ngày'), b.date_input('Đến ngày')
            params.update(start=datetime.combine(start, time.min, timezone.utc).isoformat(), end=datetime.combine(end, time.max, timezone.utc).isoformat())
        if operator:
            report = api('GET', '/v1/company/report', params=params)
            st.caption(report['coverage_note'])
            st.subheader('Khoảng thời gian đã nhận check theo nhân viên / phiên')
            st.dataframe(pd.DataFrame(report['employees']), use_container_width=True, hide_index=True, column_config=COLUMNS)
            a, b = st.columns(2)
            for column, extension in [(a, 'csv'), (b, 'pdf')]:
                if column.button('Xuất '+extension.upper()):
                    download_link(api('GET', '/v1/company/report.'+extension, raw=True, params=params), extension)
            rows = report['checks']
        else:
            rows = api('GET', '/v1/checks', params=params)['items']
        fields = ['employee_code', 'employee_name', 'session_id', 'checked_at', 'status_label', 'reason_labels', 'evidence_status']
        st.dataframe(pd.DataFrame([{k: r[k] for k in fields} for r in rows]), use_container_width=True, hide_index=True, column_config=COLUMNS)
        if rows:
            r = st.selectbox('Chi tiết lượt kiểm tra', rows, format_func=lambda r:
                             f"{r['employee_name']} · {r['checked_at']} · {r['status_label']}")
            st.info(f"{r['employee_name']}: {r['status_label']}. {r['reason_labels'] or 'Không có dấu hiệu cần chú ý.'}")
            with st.expander('Xem dữ liệu kỹ thuật (JSON)'):
                st.json(r)
            if operator and r['evidence_status'] in {'stored', 'partial'} and st.button('Mở bằng chứng'):
                for modality in ('face', 'voice'):
                    try:
                        blob = api('GET', f"/v1/checks/{r['check_id']}/evidence/{modality}", raw=True)
                        encoded = base64.b64encode(blob).decode()
                        mime = 'audio/wav' if modality == 'voice' else 'image/png' if blob.startswith(b'\x89PNG') else 'image/webp' if blob.startswith(b'RIFF') else 'image/jpeg'
                        html = f'<img alt="Ảnh bằng chứng" style="max-width:100%;max-height:400px" src="data:{mime};base64,{encoded}">' if modality == 'face' else f'<audio controls aria-label="Audio bằng chứng" src="data:{mime};base64,{encoded}"></audio>'
                        st.markdown(html, unsafe_allow_html=True)
                    except Exception as exc:
                        st.warning(str(exc))
            if operator:
                with st.expander('Kiểm duyệt kết quả và gắn nhãn'):
                    st.caption('Nhãn của người quản trị tách khỏi kết quả model. Hãy kiểm tra ngẫu nhiên cả lượt bình thường để đo tỷ lệ sai lệch.')
                    identity_labels = {'Chưa xác định': 'unknown', 'Đúng người': 'genuine', 'Khác người': 'impostor'}
                    cheating_labels = {'Chưa đủ căn cứ': 'undetermined', 'Xác nhận có gian lận': 'confirmed',
                                       'Không xác nhận gian lận': 'dismissed'}
                    reason_labels = {'Hệ thống báo nghi vấn': 'suspicious', 'Kiểm tra ngẫu nhiên': 'random_audit',
                                     'Điểm gần ngưỡng': 'near_threshold', 'Kiểm tra thủ công': 'manual'}
                    saved_review = api('GET', f"/v1/checks/{r['check_id']}/review")
                    with st.form('review-'+r['check_id']):
                        identity_label = st.selectbox('Danh tính thực tế', list(identity_labels),
                            index=list(identity_labels.values()).index(saved_review.get('identity_truth', 'unknown')))
                        face_identity_label = st.selectbox('Danh tính trong ảnh khuôn mặt', list(identity_labels),
                            index=list(identity_labels.values()).index(saved_review.get('face_identity_truth', 'unknown')),
                            help='Chọn Chưa xác định nếu chưa có căn cứ độc lập để xác minh ảnh.')
                        voice_identity_label = st.selectbox('Danh tính trong bản ghi giọng nói', list(identity_labels),
                            index=list(identity_labels.values()).index(saved_review.get('voice_identity_truth', 'unknown')),
                            help='Đánh giá riêng giọng nói; không suy ra từ kết quả nhận diện khuôn mặt.')
                        cheating_label = st.selectbox('Kết luận về gian lận', list(cheating_labels),
                            index=list(cheating_labels.values()).index(saved_review.get('cheating_judgement', 'undetermined')))
                        selection_label = st.selectbox('Vì sao chọn lượt này để kiểm duyệt', list(reason_labels),
                                                       index=list(reason_labels.values()).index(
                                                           saved_review.get('selection_reason', review_suggestions.get(r['check_id'], 'manual'))))
                        review_notes = st.text_area('Ghi chú và căn cứ', value=saved_review.get('notes') or '')
                        if st.form_submit_button('Lưu kết quả kiểm duyệt', type='primary'):
                            review = api('PUT', f"/v1/checks/{r['check_id']}/review", json={
                                'identity_truth': identity_labels[identity_label],
                                'face_identity_truth': identity_labels[face_identity_label],
                                'voice_identity_truth': identity_labels[voice_identity_label],
                                'cheating_judgement': cheating_labels[cheating_label],
                                'selection_reason': reason_labels[selection_label], 'notes': review_notes or None})
                            st.success('Đã lưu kết quả kiểm duyệt riêng với dự đoán của model.')
                            with st.expander('Xem dữ liệu kỹ thuật (JSON)'):
                                st.json(review)

    elif page == 'API & Webhook':
        config = api('GET', '/v1/company')
        st.code('POST /v1/checks\nX-API-Key: <integration key>\nMultipart: person_id, session_id, request_id, consent, face_file, voice_file')
        st.caption('Giữ request_id khi retry. session_id nối các lượt của một lần đánh giá. Secret chỉ đặt trên backend công ty.')
        with st.form('webhook'):
            url = st.text_input('Webhook URL thuộc host được nền tảng duyệt', value=config['webhook_url'] or '')
            if st.form_submit_button('Lưu webhook'):
                api('PATCH', '/v1/company', json={'webhook_url': url or None})
                st.success('Đã cập nhật webhook.')
        if st.checkbox('Hiển thị secret xác thực webhook'):
            st.code(config['webhook_secret'])
        if st.button('Cấp integration key mới'):
            st.warning('Key chỉ hiển thị một lần. Lưu trên backend công ty.')
            st.code(api('POST', '/v1/company/keys')['api_key'])
        keys = api('GET', '/v1/company/keys')
        st.dataframe(pd.DataFrame(keys), use_container_width=True, hide_index=True)
        active = [k['id'] for k in keys if k['active']]
        if active:
            selected = st.selectbox('Key cần thu hồi', active)
            if st.button('Thu hồi key'):
                api('DELETE', '/v1/company/keys/'+selected)
                st.rerun()
        deliveries = api('GET', '/v1/webhooks')
        st.subheader('Kết quả gửi webhook')
        st.dataframe(pd.DataFrame(deliveries), use_container_width=True, hide_index=True)
        failed = [r['id'] for r in deliveries if r['status'] == 'failed']
        if failed:
            selected = st.selectbox('Webhook lỗi', failed)
            if st.button('Gửi lại webhook lỗi'):
                api('POST', '/v1/webhooks/'+selected+'/retry')
                st.success('Đã đưa vào hàng đợi.')

    elif page == 'Công ty & đăng ký':
        tenants = api('GET', '/v1/admin/tenants')
        st.dataframe(pd.DataFrame(tenants), use_container_width=True, hide_index=True)
        st.caption('Công ty tự đăng ký gói giả lập tại màn hình chưa đăng nhập.')
        tenant = st.selectbox('Công ty', tenants, format_func=lambda r: r['name'])
        role = st.selectbox('Quyền key', ['operator', 'integration'])
        if st.button('Cấp key cho công ty'):
            st.code(api('POST', f"/v1/admin/tenants/{tenant['id']}/keys", json={'role': role})['api_key'])
        active = st.checkbox('Đăng ký đang hoạt động', value=tenant['active'])
        if st.button('Cập nhật đăng ký'):
            api('PATCH', f"/v1/admin/tenants/{tenant['id']}/subscription", json={'active': active})
            st.success('Đã cập nhật; dữ liệu lịch sử được giữ nguyên.')

    elif page == 'Vận hành MLOps':
        st.link_button('Grafana Monitoring Centre', 'http://localhost:13000/d/biometric-overview', type='primary')
        st.caption('Grafana/Evidently/Telegram phục vụ đội vận hành nền tảng. Công ty nhận kết quả nghiệp vụ qua API/webhook.')
        for label, url in {'Airflow': 'http://localhost:18081', 'MLflow': 'http://localhost:15030', 'MinIO': 'http://localhost:19101',
                            'API docs': 'http://localhost:18100/docs', 'Customer demo': 'http://localhost:18600',
                            'CI/CD': 'https://github.com/TrinhDucDuong/ddm501-face-voice-proctoring/actions'}.items():
            st.link_button(label, url)
        if st.button('Reload champion model'):
            result = api('POST', '/v1/admin/reload-model')
            st.success('Đã gửi yêu cầu tải model hiện hành.')
            with st.expander('Xem dữ liệu kỹ thuật (JSON)'):
                st.json(result)
except Exception as exc:
    st.error(str(exc))
