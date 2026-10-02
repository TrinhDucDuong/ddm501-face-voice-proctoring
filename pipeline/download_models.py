"""Download immutable model revisions from Hugging Face Hub."""
import hashlib
import os
import sys
from pathlib import Path

import requests
from huggingface_hub import hf_hub_download, snapshot_download

MODEL_DIR = Path(os.getenv("MODEL_DIR", str(Path(__file__).resolve().parents[1] / "models")))
MODEL_DIR.mkdir(parents=True, exist_ok=True)

if os.getenv("OFFLINE_MODE", "false").lower() == "true":
    required = ["face_recognition_sface_2021dec.onnx", "face_detection_yunet_2023mar.onnx"]
    required += ["speechbrain-ecapa/" + name for name in (
        "hyperparams.yaml", "embedding_model.ckpt", "classifier.ckpt", "mean_var_norm_emb.ckpt", "label_encoder.txt",
    )]
    required += ["minifasnet_v2.onnx", "aasist.pth"]
    missing = [name for name in required if not (MODEL_DIR / name).is_file()]
    if missing:
        raise RuntimeError("Offline model files missing: " + ", ".join(missing))
    print("Offline mode: using pre-provisioned local weights")
    sys.exit(0)

FILES = [
    ("opencv/face_recognition_sface", "face_recognition_sface_2021dec.onnx", "3d7082438a6e4551e840c9b2bb60b71e8da4b524"),
    ("opencv/face_detection_yunet", "face_detection_yunet_2023mar.onnx", "3cc26e7f1014a5ee5d74a42acee58bafc9d0a310"),
    ("garciafido/minifasnet-v2-anti-spoofing-onnx", "minifasnet_v2.onnx", "d29c87568ca9b5662da803b10f217c4db20b142b"),
]

for repo_id, filename, revision in FILES:
    path = hf_hub_download(repo_id=repo_id, filename=filename, revision=revision, local_dir=MODEL_DIR)
    print(f"downloaded {repo_id}@{revision}: {path}")

voice_dir = snapshot_download(
    repo_id="speechbrain/spkrec-ecapa-voxceleb",
    revision="0f99f2d0ebe89ac095bcc5903c4dd8f72b367286",
    local_dir=MODEL_DIR / "speechbrain-ecapa",
    allow_patterns=["*.yaml", "*.ckpt", "*.txt", "*.json"],
)
print(f"downloaded SpeechBrain ECAPA: {voice_dir}")

aasist_revision = "a04c9863f63d44471dde8a6abcb3b082b07cd1d1"
aasist_file = MODEL_DIR / "aasist.pth"
if not aasist_file.exists():
    response = requests.get(f"https://raw.githubusercontent.com/clovaai/aasist/{aasist_revision}/models/weights/AASIST.pth", timeout=120)
    response.raise_for_status()
    aasist_file.write_bytes(response.content)
pad_hash = hashlib.sha256((MODEL_DIR / "minifasnet_v2.onnx").read_bytes()).hexdigest()
if pad_hash != "d7b3cd9ba8a7ceb13baa8c4720902e27ca3112eff52f926c08804af6b6eecc7b":
    raise RuntimeError("MiniFASNet checksum mismatch")
aasist_hash = hashlib.sha256(aasist_file.read_bytes()).hexdigest()
if aasist_hash != "51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0":
    raise RuntimeError("AASIST checksum mismatch")
print("Pinned AASIST checkpoint SHA256:", aasist_hash)
