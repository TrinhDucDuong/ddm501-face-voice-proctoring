import importlib
from datetime import timedelta
from types import SimpleNamespace

import pytest
from app.models import BiometricSample, EnrollmentInvitation, utcnow
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_saas import saas as saas_fixture
from test_saas import tenant


@pytest.fixture
def enrollment_saas(monkeypatch, tmp_path):
    yield from saas_fixture.__wrapped__(monkeypatch, tmp_path)


def media():
    return [
        ("face_files", ("one.jpg", b"face-one", "image/jpeg")),
        ("face_files", ("two.jpg", b"face-two", "image/jpeg")),
        ("voice_files", ("one.wav", b"voice-one", "audio/wav")),
        ("voice_files", ("two.wav", b"voice-two", "audio/wav")),
    ]


def test_employee_invitation_one_submission_and_replay(enrollment_saas, monkeypatch):
    client, engine, _ = enrollment_saas
    owner = tenant(client, "Enrollment Company")
    created = client.post("/v1/people", headers=owner["operator"], json={
        "external_id": "EMP-1", "display_name": "Lan Nguyen"}).json()
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main.biometrics, "face", lambda data: SimpleNamespace(embedding=SimpleNamespace(tolist=lambda: [float(len(data))]), quality=0.9))
    monkeypatch.setattr(main.biometrics, "voice", lambda data: SimpleNamespace(embedding=SimpleNamespace(tolist=lambda: [float(len(data))]), quality=0.9))
    monkeypatch.setattr(main.object_store, "put", lambda *args: None)

    issue = client.post(f"/v1/people/{created['id']}/enrollment-invitations", headers=owner["operator"])
    assert issue.status_code == 201, issue.text
    token = issue.json()["token"]
    assert client.post("/v1/public/enrollment-invitations/inspect", data={"token": token}).json()["display_name"] == "Lan Nguyen"
    invalid = client.post("/v1/public/enroll", data={"token": token, "consent": "true"}, files=media()[:3])
    assert invalid.status_code == 422
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(BiometricSample)) == 0
    done = client.post("/v1/public/enroll", data={"token": token, "consent": "true"}, files=media())
    assert done.status_code == 200, done.text
    assert done.json()["ready"] is True
    assert done.json()["face_added"] == done.json()["voice_added"] == 2
    assert client.post("/v1/public/enroll", data={"token": token, "consent": "true"}, files=media()).status_code in (404, 409)
    assert client.post("/v1/public/enrollment-invitations/inspect", data={"token": token}).status_code in (404, 409)


def test_invitation_tenant_scope_and_duplicate_media(enrollment_saas, monkeypatch):
    client, engine, _ = enrollment_saas
    first, second = tenant(client, "Invitation A"), tenant(client, "Invitation B")
    created = client.post("/v1/people", headers=first["operator"], json={"external_id": "EMP-1", "display_name": "An"}).json()
    assert client.post(f"/v1/people/{created['id']}/enrollment-invitations", headers=second["operator"]).status_code == 404
    assert client.post(f"/v1/people/{created['id']}/enrollment-invitations", headers=first["integration"]).status_code == 403
    token = client.post(f"/v1/people/{created['id']}/enrollment-invitations", headers=first["operator"]).json()["token"]
    duplicated = media()
    duplicated[1] = ("face_files", ("same.jpg", b"face-one", "image/jpeg"))
    response = client.post("/v1/public/enroll", data={"token": token, "consent": "true"}, files=duplicated)
    assert response.status_code == 422
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(BiometricSample)) == 0


def test_invitation_expiry_inactive_subscription_and_consent(enrollment_saas):
    client, engine, _ = enrollment_saas
    owner = tenant(client, 'Invitation Expiry')
    created = client.post('/v1/people', headers=owner['operator'], json={
        'external_id': 'EMP-2', 'display_name': 'Minh'}).json()
    route = f"/v1/people/{created['id']}/enrollment-invitations"
    token = client.post(route, headers=owner['operator']).json()['token']
    assert client.post('/v1/public/enroll', data={'token': token, 'consent': 'false'}, files=media()).status_code == 422
    with Session(engine) as db:
        invitation = db.scalar(select(EnrollmentInvitation).where(EnrollmentInvitation.person_id == created['id']))
        invitation.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.post('/v1/public/enrollment-invitations/inspect', data={'token': token}).status_code == 404
    fresh = client.post(route, headers=owner['operator']).json()['token']
    client.patch(f"/v1/admin/tenants/{owner['id']}/subscription", headers={'X-API-Key': 'platform-test'},
                 json={'active': False})
    assert client.post('/v1/public/enrollment-invitations/inspect', data={'token': fresh}).status_code == 404
