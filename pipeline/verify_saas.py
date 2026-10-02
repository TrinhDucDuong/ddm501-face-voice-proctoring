"""Live SaaS integration acceptance test; creates labelled demo sessions, never logs secrets."""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests
from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:18100")
    parser.add_argument("--output", type=Path, default=Path("reports/saas-verification.json"))
    args = parser.parse_args()
    config = json.loads(Path("data/local-saas.json").read_text())
    api = args.api_url.rstrip("/")
    legacy = "http://127.0.0.1:18600"
    browser = requests.Session()
    operator = {"X-API-Key": config["operator_key"]}
    integration = {"X-API-Key": config["integration_key"]}
    platform = {"X-API-Key": dotenv_values(".env").get("API_KEY", "demo-internal-key")}
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "checks": {}, "tenant_id": config["tenant_id"]}

    def check(name, condition):
        report["checks"][name] = "pass" if condition else "fail"
        if not condition:
            raise AssertionError(name)
        print("PASS " + name, flush=True)

    def call(method, path, **kwargs):
        response = browser.request(method, path, timeout=180, **kwargs)
        response.raise_for_status()
        return response.json()

    def await_webhook(expected):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            status = call("GET", legacy + "/status")
            if status["webhooks_received"] >= expected:
                return status
            time.sleep(1)
        raise AssertionError("Webhook not received within 35 seconds")

    try:
        check("legacy_page", browser.get(legacy, timeout=10).status_code == 200)
        candidates = call("GET", api + "/v1/people", headers=integration)
        manifest = json.loads(Path("data/bootstrap/manifest.json").read_text(encoding="utf-8"))
        person = next(p for p in candidates if p["external_id"] == manifest[0]["external_id"])
        report["sessions"] = []
        for label, media in (("genuine", manifest[0]), ("impostor", manifest[1])):
            created = call("POST", legacy + "/start", json={"person_id": person["id"]})
            check(label + "_blocked_before_verify", browser.post(legacy + "/enter", timeout=10).status_code == 403)
            session_id = created["session_id"]
            token = parse_qs(urlsplit(created["verify_url"]).fragment)["token"][0]
            check(label + "_cross_tenant_hidden", browser.get(api + "/v1/sessions/" + session_id, headers=platform, timeout=10).status_code == 404)
            files = {}
            for field, values, mime in (("face_file", media["faces"], "image/jpeg"), ("voice_file", media["voices"], "audio/wav")):
                path = Path(values[0].replace("\\", "/"))
                files[field] = (path.name, path.read_bytes(), mime)
            url = api + f"/v1/public/sessions/{session_id}/verify"
            headers = {"Authorization": "Bearer " + token}
            outcome = call("POST", url, headers=headers, files=files, data={"consent": "true"})
            check(label + "_decision", outcome["status"] == ("allow" if label == "genuine" else "review"))
            check(label + "_token_consumed", browser.post(url, headers=headers, files=files, data={"consent": "true"}, timeout=10).status_code == 409)
            status = await_webhook(1)
            check(label + "_webhook_delivered", status["webhooks_received"] == 1)
            browser.get(legacy, timeout=10)  # return navigation must preserve browser-to-exam binding
            check(label + "_return_keeps_session", call("GET", legacy + "/status")["session_id"] == session_id)
            if label == "genuine":
                check("genuine_exam_admitted", call("POST", legacy + "/enter")["allowed"])
                check("exam_admission_one_time", browser.post(legacy + "/enter", timeout=10).status_code == 409)
            else:
                check("impostor_exam_blocked", browser.post(legacy + "/enter", timeout=10).status_code == 403)
                result = call("POST", api + f"/v1/sessions/{session_id}/review", headers=operator,
                              json={"approved": False, "notes": "Integration test: known mismatched bootstrap identity"})
                check("operator_rejection", result["status"] == "reject")
                await_webhook(2)
                check("rejected_exam_blocked", browser.post(legacy + "/enter", timeout=10).status_code == 403)
            report["sessions"].append({"id": session_id, "scenario": label})
        deliveries = call("GET", api + "/v1/webhooks", headers=operator)
        ids = {row["id"] for row in report["sessions"]}
        report["deliveries"] = [row for row in deliveries if row["session_id"] in ids]
        check("durable_outbox_delivered", all(row["status"] == "delivered" for row in report["deliveries"]))
        report["status"] = "pass"
    except Exception as exc:
        report["status"], report["error"] = "fail", str(exc)
        raise
    finally:
        Path("reports").mkdir(exist_ok=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
