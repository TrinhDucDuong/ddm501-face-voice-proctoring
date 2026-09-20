import io

import cv2
import numpy as np
from scipy.io import wavfile

from app.biometrics import BiometricEngine, cosine
from app.config import Settings


def test_demo_face_is_deterministic(tmp_path):
    engine = BiometricEngine(Settings(model_backend="demo", model_dir=str(tmp_path)))
    image = np.zeros((160, 160, 3), dtype=np.uint8)
    image[::8, :] = 255
    image[:, ::8] = 255
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    first = engine.face(encoded.tobytes())
    second = engine.face(encoded.tobytes())
    assert cosine(first.embedding, second.embedding) > 0.999
    assert first.quality >= 0.12


def test_demo_voice_is_deterministic(tmp_path):
    engine = BiometricEngine(Settings(model_backend="demo", model_dir=str(tmp_path)))
    rate = 16000
    seconds = 2
    signal = (0.6 * np.sin(2 * np.pi * 220 * np.arange(rate * seconds) / rate) * 32767).astype(np.int16)
    stream = io.BytesIO()
    wavfile.write(stream, rate, signal)
    first = engine.voice(stream.getvalue())
    second = engine.voice(stream.getvalue())
    assert cosine(first.embedding, second.embedding) > 0.999
    assert first.quality >= 0.15

