import os
import uuid

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:18100").rstrip("/")
API_KEY = os.getenv("API_KEY", "demo-internal-key")
HEADERS = {"X-API-Key": API_KEY}

st.set_page_config(page_title="Face + Voice Integrity", page_icon="🛡️", layout="wide")
st.title("🛡️ Face + Voice Integrity")
st.caption("MVP nội bộ — xác minh 1:1, quyết định REVIEW cần người kiểm tra")


def api(method: str, path: str, **kwargs):
    response = requests.request(method, f"{API_URL}{path}", headers=HEADERS, timeout=120, **kwargs)
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"HTTP {response.status_code}: {detail}")
    return response.json()


try:
    health = api("GET", "/health")
    st.sidebar.success(f"API healthy · {health['backend']} · model {health['model_version']}")
except Exception as exc:
    st.sidebar.error(f"API chưa sẵn sàng: {exc}")

page = st.sidebar.radio("Chức năng", ["Tổng quan", "Thêm hồ sơ", "Ghi danh sinh trắc", "Xác minh", "Sự kiện"])

if page == "Tổng quan":
    st.subheader("Luồng demo")
    st.markdown("1. Tạo hồ sơ → 2. Ghi danh ít nhất 2 ảnh và 2 audio WAV → 3. Xác minh → 4. Kiểm tra event/Grafana.")
    try:
        people = api("GET", "/v1/people")
        c1, c2, c3 = st.columns(3)
        c1.metric("Hồ sơ", len(people))
        c2.metric("Sẵn sàng", sum(person["ready"] for person in people))
        c3.metric("Cần bổ sung mẫu", sum(not person["ready"] for person in people))
        if people:
            st.dataframe(pd.DataFrame(people), use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(str(exc))

elif page == "Thêm hồ sơ":
    with st.form("create-person", clear_on_submit=True):
        external_id = st.text_input("Mã nhân viên / thí sinh", placeholder="EMP-0001")
        display_name = st.text_input("Tên hiển thị", placeholder="Nguyễn Văn A")
        submitted = st.form_submit_button("Tạo hồ sơ", type="primary")
    if submitted:
        try:
            created = api("POST", "/v1/people", json={"external_id": external_id, "display_name": display_name})
            st.success(f"Đã tạo {created['display_name']} · ID {created['id']}")
        except Exception as exc:
            st.error(str(exc))

elif page == "Ghi danh sinh trắc":
    try:
        people = api("GET", "/v1/people")
    except Exception as exc:
        people = []
        st.error(str(exc))
    if not people:
        st.info("Hãy tạo hồ sơ trước.")
    else:
        labels = {f"{p['external_id']} — {p['display_name']} ({p['face_samples']}F/{p['voice_samples']}V)": p for p in people}
        selected = labels[st.selectbox("Hồ sơ", labels)]
        st.info("Cần ≥2 ảnh ở góc/ánh sáng hơi khác nhau và ≥2 đoạn WAV, mỗi đoạn 2–10 giây.")
        camera = st.camera_input("Chụp ảnh trực tiếp")
        face_uploads = st.file_uploader("Hoặc tải nhiều ảnh", type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)
        voice_recording = st.audio_input("Thu giọng nói: đọc một câu tiếng Anh")
        voice_uploads = st.file_uploader("Hoặc tải nhiều audio WAV", type=["wav"], accept_multiple_files=True)
        if st.button("Ghi danh các mẫu", type="primary"):
            files = []
            for item in ([camera] if camera else []) + face_uploads:
                files.append(("face_files", (item.name, item.getvalue(), item.type or "image/jpeg")))
            for item in ([voice_recording] if voice_recording else []) + voice_uploads:
                files.append(("voice_files", (item.name, item.getvalue(), "audio/wav")))
            try:
                result = api("POST", f"/v1/people/{selected['id']}/enroll", files=files)
                st.success(f"Đã thêm {result['face_added']} ảnh, {result['voice_added']} audio. Ready={result['ready']}")
                if result["rejected"]:
                    st.warning("\n".join(result["rejected"]))
            except Exception as exc:
                st.error(str(exc))

elif page == "Xác minh":
    try:
        people = [person for person in api("GET", "/v1/people") if person["ready"]]
    except Exception as exc:
        people = []
        st.error(str(exc))
    if not people:
        st.info("Chưa có hồ sơ đủ mẫu.")
    else:
        labels = {f"{p['external_id']} — {p['display_name']}": p for p in people}
        selected = labels[st.selectbox("Danh tính khai báo", labels)]
        session_id = st.text_input("Session ID", value=f"exam-{uuid.uuid4().hex[:8]}")
        face = st.camera_input("Ảnh xác minh")
        voice = st.audio_input("Audio xác minh")
        if st.button("Xác minh", type="primary"):
            files = {}
            if face:
                files["face_file"] = (face.name, face.getvalue(), face.type or "image/jpeg")
            if voice:
                files["voice_file"] = (voice.name, voice.getvalue(), "audio/wav")
            try:
                result = api("POST", "/v1/verify", data={"person_id": selected["id"], "session_id": session_id}, files=files)
                if result["accepted"]:
                    st.success("ALLOW — hai tín hiệu khớp ngưỡng")
                else:
                    st.warning("REVIEW — chuyển kiểm tra thủ công")
                st.json(result)
            except Exception as exc:
                st.error(str(exc))

else:
    try:
        events = api("GET", "/v1/events?limit=200")
        if events:
            frame = pd.DataFrame(events)
            st.dataframe(frame, use_container_width=True, hide_index=True)
            st.download_button("Tải CSV", frame.to_csv(index=False), "verification-events.csv", "text/csv")
        else:
            st.info("Chưa có sự kiện.")
    except Exception as exc:
        st.error(str(exc))

