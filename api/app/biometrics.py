from __future__ import annotations

import io
import math
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

from .config import Settings


class BiometricError(ValueError):
    pass


@dataclass
class EmbeddingResult:
    embedding: np.ndarray
    quality: float
    backend: str


def normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if norm < 1e-8:
        raise BiometricError("Không tạo được embedding hợp lệ")
    return vector / norm


def cosine(a: np.ndarray | list[float], b: np.ndarray | list[float]) -> float:
    return float(np.clip(np.dot(normalize(np.asarray(a)), normalize(np.asarray(b))), -1.0, 1.0))


def _decode_image(payload: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise BiometricError("Ảnh không đọc được")
    if min(image.shape[:2]) < 80:
        raise BiometricError("Ảnh quá nhỏ; cần tối thiểu 80x80")
    return image


def _face_quality(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    exposure = max(0.0, 1.0 - abs(brightness - 127.5) / 127.5)
    sharpness = min(1.0, float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 500.0)
    return round(0.45 * exposure + 0.55 * sharpness, 4)


def _decode_audio(payload: bytes) -> tuple[int, np.ndarray]:
    try:
        rate, signal = wavfile.read(io.BytesIO(payload))
    except Exception as exc:
        raise BiometricError("Audio phải là WAV PCM") from exc
    if signal.ndim == 2:
        signal = signal.mean(axis=1)
    if np.issubdtype(signal.dtype, np.integer):
        signal = signal.astype(np.float32) / max(abs(np.iinfo(signal.dtype).min), np.iinfo(signal.dtype).max)
    else:
        signal = signal.astype(np.float32)
    if rate != 16000:
        divisor = math.gcd(rate, 16000)
        signal = resample_poly(signal, 16000 // divisor, rate // divisor).astype(np.float32)
        rate = 16000
    duration = len(signal) / rate
    if duration < 0.8 or duration > 30:
        raise BiometricError("Audio cần dài từ 0.8 đến 30 giây")
    peak = float(np.max(np.abs(signal)))
    if peak < 0.005:
        raise BiometricError("Audio quá nhỏ hoặc im lặng")
    return rate, signal / max(peak, 1e-8)


def _voice_quality(signal: np.ndarray, rate: int) -> float:
    rms = float(np.sqrt(np.mean(signal**2)))
    clipping = float(np.mean(np.abs(signal) > 0.99))
    duration_score = min(1.0, len(signal) / (3.0 * rate))
    level_score = min(1.0, rms / 0.18)
    return round(max(0.0, 0.45 * duration_score + 0.55 * level_score - 2.0 * clipping), 4)


class BiometricEngine:
    """Lazy biometric extractors. `demo` is deterministic and intended only for tests."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.backend = settings.model_backend.lower()
        self.model_dir = Path(settings.model_dir)
        self._face_detector = None
        self._face_recognizer = None
        self._speaker = None
        self._lock = threading.Lock()

    def face(self, payload: bytes) -> EmbeddingResult:
        image = _decode_image(payload)
        quality = _face_quality(image)
        if quality < 0.12:
            raise BiometricError("Ảnh quá tối, sáng hoặc mờ")
        if self.backend == "pretrained":
            embedding = self._sface(image)
            backend = "opencv-sface-2021dec"
        else:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
            embedding = cv2.dct(resized)[:16, :16].reshape(-1)
            backend = "demo-dct"
        return EmbeddingResult(normalize(embedding), quality, backend)

    def voice(self, payload: bytes) -> EmbeddingResult:
        rate, signal = _decode_audio(payload)
        quality = _voice_quality(signal, rate)
        if quality < 0.15:
            raise BiometricError("Audio không đủ chất lượng")
        if self.backend == "pretrained":
            embedding = self._ecapa(signal)
            backend = "speechbrain-ecapa-voxceleb"
        else:
            frames = np.array_split(signal, 24)
            features = []
            for frame in frames:
                spectrum = np.log1p(np.abs(np.fft.rfft(frame, n=512)))
                features.extend([float(np.mean(spectrum)), float(np.std(spectrum)), float(np.max(spectrum))])
            embedding = np.asarray(features, dtype=np.float32)
            backend = "demo-spectrum"
        return EmbeddingResult(normalize(embedding), quality, backend)

    def _load_sface(self) -> None:
        detector_path = self.model_dir / "face_detection_yunet_2023mar.onnx"
        recognizer_path = self.model_dir / "face_recognition_sface_2021dec.onnx"
        if not detector_path.exists() or not recognizer_path.exists():
            raise BiometricError("Thiếu weights SFace/YuNet; chạy `python pipeline/download_models.py`")
        self._face_detector = cv2.FaceDetectorYN.create(str(detector_path), "", (320, 320), 0.8, 0.3, 5000)
        self._face_recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), "")

    def _sface(self, image: np.ndarray) -> np.ndarray:
        with self._lock:
            if self._face_detector is None:
                self._load_sface()
            height, width = image.shape[:2]
            self._face_detector.setInputSize((width, height))
            _, faces = self._face_detector.detect(image)
            if faces is None or len(faces) != 1:
                raise BiometricError(f"Cần đúng một khuôn mặt; phát hiện {0 if faces is None else len(faces)}")
            aligned = self._face_recognizer.alignCrop(image, faces[0])
            return self._face_recognizer.feature(aligned).reshape(-1)

    def _ecapa(self, signal: np.ndarray) -> np.ndarray:
        with self._lock:
            if self._speaker is None:
                try:
                    from speechbrain.inference.speaker import EncoderClassifier
                except ImportError as exc:
                    raise BiometricError("Backend pretrained cần cài requirements-models.txt") from exc
                local_source = self.model_dir / "speechbrain-ecapa"
                if not (local_source / "hyperparams.yaml").exists():
                    raise BiometricError("Thiếu weights ECAPA; chạy `python pipeline/download_models.py`")
                self._speaker = EncoderClassifier.from_hparams(source=str(local_source), run_opts={"device": "cpu"})
            import torch

            with torch.inference_mode():
                tensor = torch.from_numpy(signal).unsqueeze(0)
                return self._speaker.encode_batch(tensor).squeeze().cpu().numpy()
