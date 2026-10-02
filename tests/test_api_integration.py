import importlib
import io

import cv2
import numpy as np
from fastapi.testclient import TestClient
from scipy.io import wavfile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_real_upload_enrollment_verification_and_input_failures(monkeypatch, tmp_path):
    from app.biometrics import BiometricEngine
    from app.config import get_settings
    from app.db import get_db
    from app.registry import RuntimeModel
    from app.storage import ObjectStore

    monkeypatch.setenv('API_KEY', 'upload-test')
    monkeypatch.setenv('MODEL_BACKEND', 'demo')
    monkeypatch.setenv('STORE_RAW_BIOMETRICS', 'false')
    get_settings.cache_clear()
    main = importlib.import_module('app.main')
    settings = get_settings()
    engine = create_engine(f"sqlite:///{(tmp_path/'uploads.db').as_posix()}",connect_args={'check_same_thread':False})
    monkeypatch.setattr(main,'engine',engine)
    monkeypatch.setattr(main,'settings',settings)
    monkeypatch.setattr(main,'biometrics',BiometricEngine(settings))
    monkeypatch.setattr(main,'object_store',ObjectStore(settings))
    monkeypatch.setattr(main.registry,'current',RuntimeModel(.45,.25,'test-registered'))
    monkeypatch.setattr(main.registry,'load',lambda:main.registry.current)
    def database():
        with Session(engine) as db:
            yield db
    main.app.dependency_overrides[get_db] = database
    image = np.zeros((160,160,3),dtype=np.uint8)
    image[::8,:] = 255
    image[:,::8] = 255
    _, encoded = cv2.imencode('.png',image)
    stream = io.BytesIO()
    wave = (np.sin(np.arange(48000)*2*np.pi*220/16000)*20000).astype(np.int16)
    wavfile.write(stream,16000,wave)
    face, voice = ('face.png',encoded.tobytes(),'image/png'), ('voice.wav',stream.getvalue(),'audio/wav')
    headers = {'X-API-Key':'upload-test'}
    try:
        with TestClient(main.app) as client:
            body = {'external_id':'UPLOAD-1','display_name':'Upload Candidate'}
            person = client.post('/v1/people',headers=headers,json=body).json()
            assert client.post('/v1/people',headers=headers,json=body).status_code == 409
            enrollment = f"/v1/people/{person['id']}/enroll"
            assert client.post(enrollment,headers=headers).status_code == 400
            result = client.post(enrollment,headers=headers,files=[('face_files',face),('voice_files',voice)]).json()
            assert result['face_added'] == result['voice_added'] == 1
            duplicate = client.post(enrollment,headers=headers,files=[('face_files',face)]).json()
            assert duplicate['face_added'] == 0 and len(duplicate['rejected']) == 1
            data = {'person_id':person['id'],'session_id':'uploaded'}
            verified = client.post('/v1/verify',headers=headers,data=data,files={'face_file':face,'voice_file':voice})
            assert verified.status_code == 200, verified.text
            assert verified.json()['accepted'] and verified.json()['explanations']['accepted']
            assert verified.json()['face_score'] > .99
            missing = client.post('/v1/verify',headers=headers,data=data,files={'face_file':face}).json()
            assert missing['decision'] == 'review' and 'missing_voice' in missing['reasons']
            assert client.post('/v1/verify',headers=headers,data=data,files={'face_file':('bad.png',b'bad','image/png')}).status_code == 422
            assert client.post('/v1/verify',headers=headers,data=data,files={'face_file':('bad.txt',b'bad','text/plain')}).status_code == 415
            assert client.post('/v1/verify',headers=headers,data=data,files={'face_file':('empty.png',b'','image/png')}).status_code == 400
            feedback = f"/v1/events/{verified.json()['event_id']}/feedback"
            for label in (True,False):
                assert client.put(feedback,headers=headers,json={'is_genuine':label,'reviewer':'test'}).status_code == 201
            assert len(client.get('/v1/events',headers=headers).json()) == 2
            monkeypatch.setattr(settings,'max_upload_mb',0)
            assert client.post('/v1/verify',headers=headers,data=data,files={'face_file':face}).status_code == 413
    finally:
        main.app.dependency_overrides.clear()
        engine.dispose()
        get_settings.cache_clear()


def test_people_simulation_feedback_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'api.db').as_posix()}")
    monkeypatch.setenv("MODEL_BACKEND", "demo")
    monkeypatch.setenv("ENABLE_SIMULATION", "true")
    monkeypatch.setenv("API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()
    main = importlib.import_module("app.main")
    from app.db import get_db
    test_engine = create_engine(f"sqlite:///{(tmp_path / 'isolated.db').as_posix()}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(main, "engine", test_engine)
    monkeypatch.setattr(main, "settings", get_settings())
    def database():
        with Session(test_engine) as db:
            yield db
    main.app.dependency_overrides[get_db] = database
    monkeypatch.setattr(main.registry, "load", lambda: main.registry.current)
    headers = {"X-API-Key": "test-key"}
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/v1/people").status_code == 401
        created = client.post(
            "/v1/people", headers=headers,
            json={"external_id": "INT-001", "display_name": "Integration User"},
        )
        assert created.status_code == 201
        person_id = created.json()["id"]
        observed = client.post(
            "/v1/simulation/observations", headers=headers,
            json={
                "person_id": person_id, "session_id": "integration-1",
                "face_score": 0.9, "voice_score": 0.8,
                "face_quality": 0.9, "voice_quality": 0.9,
            },
        )
        assert observed.status_code == 200
        assert observed.json()["decision"] == "allow"
        event_id = observed.json()["event_id"]
        feedback = client.put(
            f"/v1/events/{event_id}/feedback", headers=headers,
            json={"is_genuine": True, "reviewer": "pytest"},
        )
        assert feedback.status_code == 201
        assert client.get("/v1/events", headers=headers).json()[0]["id"] == event_id
    main.app.dependency_overrides.clear()
    test_engine.dispose()
    get_settings.cache_clear()
