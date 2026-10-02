import io

import cv2
import numpy as np
import pytest
from app.biometrics import (
    BiometricEngine,
    BiometricError,
    _decode_audio,
    _decode_image,
    _face_quality,
    _voice_quality,
    cosine,
    normalize,
)
from app.config import Settings
from scipy.io import wavfile


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


def test_normalization_and_invalid_images():
    assert np.linalg.norm(normalize(np.array([3.0, 4.0]))) == pytest.approx(1)
    assert cosine([1, 0], [1, 0]) == pytest.approx(1)
    with pytest.raises(BiometricError):
        normalize(np.zeros(4))
    with pytest.raises(BiometricError):
        _decode_image(b"not-an-image")
    ok, tiny = cv2.imencode(".png", np.zeros((20, 20, 3), dtype=np.uint8))
    assert ok
    with pytest.raises(BiometricError):
        _decode_image(tiny.tobytes())


def test_audio_validation_resampling_and_quality():
    with pytest.raises(BiometricError):
        _decode_audio(b"bad wav")
    stream = io.BytesIO()
    short = np.ones(100, dtype=np.int16)
    wavfile.write(stream, 8000, short)
    with pytest.raises(BiometricError, match="0.8"):
        _decode_audio(stream.getvalue())
    stream = io.BytesIO()
    stereo = np.column_stack([np.sin(np.arange(16000)), np.sin(np.arange(16000))])
    wavfile.write(stream, 8000, (stereo * 20000).astype(np.int16))
    rate, signal = _decode_audio(stream.getvalue())
    assert rate == 16000
    assert len(signal) == 32000
    assert 0 <= _voice_quality(signal, rate) <= 1


def test_quality_and_pretrained_weights_fail_closed(tmp_path):
    black = np.zeros((160, 160, 3), dtype=np.uint8)
    assert 0 <= _face_quality(black) <= 1
    engine = BiometricEngine(Settings(model_backend="pretrained", model_dir=str(tmp_path)))
    with pytest.raises(BiometricError, match="weights"):
        engine._load_sface()
