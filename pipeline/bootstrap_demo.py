"""Build and optionally enroll a reproducible 50–100 identity technical demo set.

Face and voice subjects are paired synthetically by row; they are not the same real person.
Therefore this dataset validates plumbing only, never biometric accuracy.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

import requests
import fsspec
from datasets import Audio, Image, load_dataset

FACE_DATASET = "marcelohaps/lfw"
FACE_REVISION = "12a61458b56d0433d07269dc1d64368abf4f6b4d"
VOICE_DATASET = "mteb/speech-commands-mini"
VOICE_REVISION = "3ac713aa0829eeadda73182f38bbbd788d21254b"


def bytes_from_asset(asset: dict) -> bytes:
    if asset.get("bytes") is not None:
        return asset["bytes"]
    if str(asset["path"]).startswith("hf://"):
        with fsspec.open(asset["path"], "rb") as handle:
            return handle.read()
    return Path(asset["path"]).read_bytes()


def collect_faces(limit: int, per_person: int) -> dict[str, list[bytes]]:
    dataset = load_dataset(FACE_DATASET, split="train", revision=FACE_REVISION, streaming=True)
    dataset = dataset.cast_column("image", Image(decode=False))
    found: dict[str, list[dict]] = defaultdict(list)
    complete: set[str] = set()
    for row in dataset:
        identity = str(row.get("identity") or row.get("label_name") or row["label"])
        if len(found[identity]) < per_person:
            # Keep lightweight references while scanning LFW. Downloading here would
            # fetch thousands of one-shot identities that can never be enrolled.
            found[identity].append(row["image"])
            if len(found[identity]) == per_person:
                complete.add(identity)
        if len(complete) >= limit:
            break
    return {
        key: [bytes_from_asset(asset) for asset in found[key]]
        for key in sorted(complete)[:limit]
    }


def collect_voices(limit: int, per_person: int) -> dict[str, list[bytes]]:
    found: dict[str, list[dict]] = defaultdict(list)
    complete: set[str] = set()
    for split in ("train", "validation", "test"):
        dataset = load_dataset(VOICE_DATASET, split=split, revision=VOICE_REVISION, streaming=True)
        dataset = dataset.cast_column("audio", Audio(decode=False))
        for row in dataset:
            speaker = str(row.get("speaker_id"))
            if speaker in {"None", "", "nan"}:
                continue
            if len(found[speaker]) < per_person:
                found[speaker].append(row["audio"])
                if len(found[speaker]) == per_person:
                    complete.add(speaker)
            if len(complete) >= limit:
                break
        if len(complete) >= limit:
            break
    return {
        key: [bytes_from_asset(asset) for asset in found[key]]
        for key in sorted(complete)[:limit]
    }


def enroll_row(row: dict, index: int) -> None:
    base = os.getenv("PUBLIC_API_URL", "http://localhost:18100")
    headers = {"X-API-Key": os.getenv("API_KEY", "demo-internal-key")}
    response = requests.post(
        f"{base}/v1/people", headers=headers,
        json={"external_id": row["external_id"], "display_name": f"Demo User {index:03d}"}, timeout=30,
    )
    if response.status_code == 409:
        people = requests.get(f"{base}/v1/people", headers=headers, timeout=30).json()
        person = next(person for person in people if person["external_id"] == row["external_id"])
        if person["ready"]:
            print(f"{row['external_id']} already ready; skipped")
            return
    else:
        response.raise_for_status()
        person = response.json()
    face_paths = [Path(path) for path in row["faces"]]
    voice_paths = [Path(path) for path in row["voices"]]
    files = [("face_files", (path.name, path.read_bytes(), "image/jpeg")) for path in face_paths]
    files += [("voice_files", (path.name, path.read_bytes(), "audio/wav")) for path in voice_paths]
    enrolled = requests.post(f"{base}/v1/people/{person['id']}/enroll", headers=headers, files=files, timeout=300)
    enrolled.raise_for_status()
    print(row["external_id"], json.dumps(enrolled.json(), ensure_ascii=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identities", type=int, default=50, choices=range(10, 101))
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("data/bootstrap"))
    parser.add_argument("--enroll-api", action="store_true")
    parser.add_argument("--enroll-existing", action="store_true", help="Enroll the existing manifest without downloading again")
    args = parser.parse_args()
    if args.enroll_existing:
        manifest = json.loads((args.output / "manifest.json").read_text(encoding="utf-8"))
        for index, row in enumerate(manifest, 1):
            enroll_row(row, index)
        print(f"enrolled {len(manifest)} identities from {args.output / 'manifest.json'}")
        return
    faces = collect_faces(args.identities, args.samples)
    voices = collect_voices(args.identities, args.samples)
    count = min(len(faces), len(voices), args.identities)
    if count < args.identities:
        raise RuntimeError(f"Chỉ tìm được {count}/{args.identities} identities đủ mẫu")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, ((face_name, face_items), (voice_name, voice_items)) in enumerate(zip(faces.items(), voices.items()), 1):
        demo_id = f"DEMO-{index:03d}"
        folder = args.output / demo_id
        folder.mkdir(exist_ok=True)
        face_paths, voice_paths = [], []
        for sample_index, payload in enumerate(face_items, 1):
            path = folder / f"face-{sample_index}.jpg"
            path.write_bytes(payload)
            face_paths.append(path)
        for sample_index, payload in enumerate(voice_items, 1):
            path = folder / f"voice-{sample_index}.wav"
            path.write_bytes(payload)
            voice_paths.append(path)
        row = {"external_id": demo_id, "face_source": face_name, "voice_source": voice_name,
               "faces": [str(path) for path in face_paths], "voices": [str(path) for path in voice_paths]}
        manifest.append(row)
        if args.enroll_api:
            enroll_row(row, index)
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"created {count} synthetic face/voice pairings at {args.output}")


if __name__ == "__main__":
    main()
