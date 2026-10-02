"""Small explicit CPU serving test using demo media, not an accuracy benchmark."""
import argparse
import concurrent.futures
import json
import time
from pathlib import Path

import numpy as np
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.requests <= 100 or not 1 <= args.concurrency <= 8:
        parser.error("demo bounds: 1..100 requests, 1..8 concurrency")
    cfg = json.loads(Path("data/local-saas.json").read_text())
    headers = {"X-API-Key": cfg["operator_key"]}
    base = "http://127.0.0.1:18100"
    response = requests.get(base + "/v1/people", headers=headers, timeout=20)
    response.raise_for_status()
    manifest = json.loads(Path("data/bootstrap/manifest.json").read_text())[0]
    person = next(p for p in response.json() if p["external_id"] == manifest["external_id"])
    files = {}
    for field, values, mime in (("face_file", manifest["faces"], "image/jpeg"), ("voice_file", manifest["voices"], "audio/wav")):
        path = Path(values[0].replace("\\", "/"))
        files[field] = (path.name, path.read_bytes(), mime)

    def request(index):
        started = time.perf_counter()
        result = requests.post(base + "/v1/verify", headers=headers, files=files,
                               data={"person_id": person["id"], "session_id": f"load-demo-{index}"}, timeout=60)
        return {"seconds": time.perf_counter() - started, "status": result.status_code,
                "accepted": result.json().get("accepted") if result.ok else False}

    request("warmup")
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(executor.map(request, range(args.requests)))
    elapsed = time.perf_counter() - started
    report = {"requests": args.requests, "concurrency": args.concurrency, "wall_seconds": elapsed,
              "throughput_rps": args.requests / elapsed,
              "p50_seconds": float(np.percentile([r["seconds"] for r in results], 50)),
              "p95_seconds": float(np.percentile([r["seconds"] for r in results], 95)),
              "errors": sum(r["status"] != 200 for r in results), "results": results,
              "limitation": "Local CPU smoke load only; warm model, reused media; not a capacity or biometric-accuracy claim"}
    Path("reports/load-test.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
