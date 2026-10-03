"""Platform-only classroom controls backed by durable simulation evidence."""
import json

import pandas as pd
import streamlit as st


def render(api):
    st.subheader('Simulation lifecycle Face / Voice')
    st.warning('Dữ liệu giả lập — cấu hình demo tăng tốc. Database và MLflow riêng; không đổi champion đang phục vụ.')
    st.caption('Demo bắt đầu từ embedding tổng hợp, không chạy camera/microphone hoặc fine-tune encoder. '
               'Các gate drift, calibration, shadow và canary dùng chung code với hệ thống chính.')
    state = api('GET', '/v1/admin/simulation/state')
    current = state.get('current') or {}
    active = current.get('status') in {'QUEUED', 'RUNNING'}
    needs_reset = bool(current) and current.get('status') != 'RESET'
    modality = st.selectbox('Modality giả lập', ['voice', 'face'], disabled=active)
    seed = st.number_input('Seed tái lập dữ liệu', min_value=0, max_value=1000000, value=501, disabled=active)
    a, b, c = st.columns(3)
    if a.button('1. Drift → nâng cấp champion', disabled=needs_reset, use_container_width=True, type='primary'):
        api('POST', '/v1/admin/simulation/runs', json={'scenario': 'promotion', 'modality': modality, 'seed': seed})
        st.rerun()
    if b.button('2. Canary lỗi → rollback', disabled=needs_reset, use_container_width=True):
        api('POST', '/v1/admin/simulation/runs', json={'scenario': 'rollback', 'modality': modality, 'seed': seed})
        st.rerun()
    if c.button('3. Khôi phục baseline demo', disabled=not needs_reset, use_container_width=True):
        with st.spinner('Dừng lượt chạy và phục hồi baseline simulation…'):
            api('POST', '/v1/admin/simulation/reset')
        st.rerun()
    st.caption('Airflow nhận job trong khoảng một phút. Trước lượt mới, khôi phục baseline; lịch sử vẫn được giữ.')
    left, right = st.columns(2)
    left.link_button('Airflow simulation DAG', 'http://localhost:18081/dags/biometric_simulation/grid')
    right.link_button('MLflow simulation riêng', 'http://localhost:15031')

    @st.fragment(run_every='5s')
    def progress():
        evidence = api('GET', '/v1/admin/simulation/state')
        run = evidence.get('current')
        if not run:
            st.info('Chưa có lượt simulation. Chọn một trong hai kịch bản để bắt đầu.')
            return
        st.write(f"Lượt `{run['id']}` · {run['modality'].upper()} · **{run['status']}** · {run.get('phase', '')}")
        st.progress(min(1., len(run.get('completed', [])) / 6))
        st.caption('Giới hạn demo: 200 request/stage, tối thiểu 5 giây/stage, 20 nhãn/lớp, '
                   'disagreement ≤60%; FMR ≤1%, FNMR ≤5%. Nhãn là synthetic truth, không phải review người thật.')
        if run.get('error'):
            st.error(run['error'])
        if run['status'] == 'SUCCEEDED':
            st.success('Challenger đã vượt các gate và trở thành champion của simulation.')
        elif run['status'] == 'ROLLED_BACK':
            st.success('Gate đã chặn challenger ở canary; probe xác nhận traffic trở lại champion ban đầu.')
        elif run['status'] == 'RESET':
            st.success('Baseline simulation đã được phục hồi. Có thể chạy lại kịch bản.')
            st.caption('Các metric drift/offline/canary bên dưới là bằng chứng lịch sử của lượt vừa khôi phục.')
        deployment = run.get('deployment', {})
        a, b, c = st.columns(3)
        a.metric('Champion simulation', deployment.get('champion_version', '—'))
        b.metric('Challenger simulation', deployment.get('challenger_version') or '—')
        c.metric('Canary traffic', f"{deployment.get('traffic_percent', 0):g}%")
        if run.get('offline'):
            st.write('So sánh offline trên cùng holdout')
            st.dataframe(pd.DataFrame([{'policy': k, **run['offline'][k]} for k in ('champion', 'candidate')]),
                hide_index=True, use_container_width=True)
        if run.get('stages'):
            st.write('Request thực qua endpoint simulation và kết quả routing')
            st.dataframe(pd.DataFrame([{k: s[k] for k in ('stage', 'traffic_percent', 'samples',
                'served_candidate', 'response_mismatches', 'fault_injected')} for s in run['stages']]),
                hide_index=True, use_container_width=True)
        alerts = [a for a in evidence.get('alerts', []) if a.get('run_id') == run['id']]
        st.write('Alert Prometheus → Alertmanager → simulation:', len(alerts), 'thông báo đã nhận')
        with st.expander('Quyết định drift, gate và lịch sử chuyển trạng thái'):
            st.json({'drift': run.get('drift'), 'deployment': deployment, 'audit': run.get('audit'),
                     'alerts': alerts, 'rollback_probe': run.get('rollback_probe'), 'champion_probe': run.get('champion_probe')})
        st.dataframe(pd.DataFrame(evidence.get('history', [])), hide_index=True, use_container_width=True)
    progress()
    history = state.get('history', [])
    selected_run = st.selectbox('Lượt cần tải evidence', history,
        format_func=lambda r: f"{r['scenario']} · {r['modality']} · {r['id']}") if history else None
    if selected_run and st.button('Chuẩn bị báo cáo evidence JSON'):
        report = api('GET', '/v1/admin/simulation/evidence/' + selected_run['id'])
        st.download_button('Tải báo cáo simulation', json.dumps(report, ensure_ascii=False, indent=2),
                           file_name=f"simulation-{selected_run['id']}.json", mime='application/json')
