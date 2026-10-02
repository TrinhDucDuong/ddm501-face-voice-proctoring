"""Provision a local customer and enroll demo media; credentials stay in gitignored data/."""
import json
from pathlib import Path

import requests
from dotenv import dotenv_values


def main():
    base = "http://127.0.0.1:18100"
    config_path = Path("data/local-saas.json")
    platform_key = dotenv_values(".env").get("API_KEY", "demo-internal-key")
    session = requests.Session()

    def call(method, path, key, **kwargs):
        response = session.request(method, base + path, headers={"X-API-Key": key}, timeout=180, **kwargs)
        response.raise_for_status()
        return response.json()

    if config_path.exists():
        config = json.loads(config_path.read_text())
        call("GET", "/v1/me", config["integration_key"])
    else:
        tenant = call("POST", "/v1/admin/tenants", platform_key, json={
            "name": "Local English Exam", "webhook_url": "http://legacy-demo:8000/webhooks/verification",
            "return_url": "http://localhost:18600/",
        })
        config = {"tenant_id": tenant["id"], "webhook_secret": tenant["webhook_secret"]}
        for role in ("operator", "integration"):
            key = call("POST", f"/v1/admin/tenants/{tenant['id']}/keys", platform_key, json={"role": role})
            config[role + "_key"] = key["api_key"]
        config_path.parent.mkdir(exist_ok=True)
        config_path.write_text(json.dumps(config, indent=2))
        config_path.chmod(0o600)
    people = call("GET", "/v1/people", config["operator_key"])
    manifest = json.loads(Path("data/bootstrap/manifest.json").read_text(encoding="utf-8"))
    for row in manifest[:2]:
        person = next((p for p in people if p["external_id"] == row["external_id"]), None)
        if person is None:
            person = call("POST", "/v1/people", config["operator_key"], json={
                "external_id": row["external_id"], "display_name": "Candidate " + row["external_id"],
            })
        if not person["ready"]:
            files = []
            for field, values, mime in (("face_files", row["faces"], "image/jpeg"), ("voice_files", row["voices"], "audio/wav")):
                for value in values:
                    path = Path(value.replace("\\", "/"))
                    files.append((field, (path.name, path.read_bytes(), mime)))
            result = call("POST", f"/v1/people/{person['id']}/enroll", config["operator_key"], files=files)
            if not result["ready"]:
                raise RuntimeError("Enrollment not ready: " + str(result["rejected"]))
    print("Local tenant ready; credentials saved only to data/local-saas.json. Legacy UI: http://localhost:18600")


if __name__ == "__main__":
    main()
