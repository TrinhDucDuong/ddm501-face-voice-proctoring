"""Pinned research detectors and explicitly limited capture-integrity signals."""
import json
import threading
from pathlib import Path

import cv2
import numpy as np
from prometheus_client import Gauge

from .biometrics import BiometricError, _decode_audio, _decode_image, cosine

CAPABILITY = Gauge('biometric_integrity_capability_ready', 'Last detector execution had no operational failure', ['capability'])


def speaker_consistency(embeddings, threshold=.35):
    result = {'method': 'ecapa_segment_consistency',
              'limitation': 'Heuristic for consecutive speaker changes, not overlap diarization or an exact speaker count.'}
    if len(embeddings) < 2:
        return {**result, 'status': 'not_assessed', 'reason': 'Insufficient voiced segments'}
    minimum = min(cosine(a, b) for a, b in zip(embeddings, embeddings[1:], strict=False))
    return {**result, 'status': 'failed' if minimum < threshold else 'passed',
            'minimum_similarity': minimum, 'threshold': threshold, 'segments': len(embeddings)}


class IntegrityInspector:
    def __init__(self, settings, biometric_engine):
        self.settings, self.engine = settings, biometric_engine
        self.model_dir = Path(settings.model_dir)
        self.pad_model, self.audio_model = None, None
        self.lock = threading.Lock()

    def inspect(self, face, voice):
        if self.settings.model_backend != 'pretrained':
            return {key: {'status': 'not_assessed', 'reason': 'Test embedding backend has no integrity detector'}
                    for key in ('face_pad', 'audio_spoof', 'speaker_consistency')}
        results = {}
        # Serialize the detector runtimes, independent of the biometric engine lock.
        with self.lock:
            for key, method, payload in [('face_pad', self.face_pad, face), ('audio_spoof', self.audio_spoof, voice),
                                         ('speaker_consistency', self.speakers, voice)]:
                try:
                    results[key] = method(payload)
                    # A healthy detector may decline a multi-face or short-audio capture.
                    CAPABILITY.labels(capability=key).set(1)
                except BiometricError:
                    # Invalid customer media is not a platform outage; preserve the last readiness value.
                    results[key] = {'status': 'not_assessed', 'reason': 'Invalid capture'}
                except Exception as exc:
                    CAPABILITY.labels(capability=key).set(0)
                    results[key] = {'status': 'unavailable', 'reason': type(exc).__name__}
        return results

    def face_pad(self, payload):
        path = self.model_dir/'minifasnet_v2.onnx'
        if not path.exists():
            raise FileNotFoundError('MiniFASNet weights missing')
        image = _decode_image(payload)
        with self.engine._lock:
            if self.engine._face_detector is None:
                self.engine._load_sface()
            height, width = image.shape[:2]
            self.engine._face_detector.setInputSize((width, height))
            _, faces = self.engine._face_detector.detect(image)
        if faces is None or len(faces) != 1:
            return {'status': 'not_assessed', 'reason': 'Exactly one face is required for PAD'}
        x, y, w, h = faces[0][:4]
        scale = min(2.7, (width-1)/w, (height-1)/h)
        cw, ch = w*scale, h*scale
        left, top = int(max(0, min(x+w/2-cw/2, width-cw))), int(max(0, min(y+h/2-ch/2, height-ch)))
        crop = image[top:int(top+ch), left:int(left+cw)]
        # Upstream functional.to_tensor uses BGR float [0,255]; upstream test.py defines class 1 as live.
        tensor = cv2.resize(crop, (80, 80)).astype(np.float32).transpose(2, 0, 1)[None]
        if self.pad_model is None:
            import onnxruntime as ort
            options = ort.SessionOptions()
            options.intra_op_num_threads = 1
            self.pad_model = ort.InferenceSession(str(path), options, providers=['CPUExecutionProvider'])
        scores = np.asarray(self.pad_model.run(None, {self.pad_model.get_inputs()[0].name: tensor})[0]).reshape(-1)
        probabilities = np.exp(scores-scores.max())
        probabilities /= probabilities.sum()
        spoof_score = float(1-probabilities[1])
        return {'status': 'failed' if spoof_score >= self.settings.face_spoof_threshold else 'passed',
                'score': spoof_score, 'threshold': self.settings.face_spoof_threshold, 'model': 'MiniFASNetV2-2.7',
                'revision': 'd29c87568ca9b5662da803b10f217c4db20b142b',
                'limitation': 'Single-image print/screen PAD signal; unseen video deepfakes are not validated.'}

    def audio_spoof(self, payload):
        path = self.model_dir/'aasist.pth'
        if not path.exists():
            raise FileNotFoundError('AASIST weights missing')
        import torch

        from .vendor.aasist import Model
        config = json.loads((Path(__file__).parent/'vendor/aasist_config.json').read_text())['model_config']
        if self.audio_model is None:
            torch.set_num_threads(2)
            self.audio_model = Model(config).cpu()
            self.audio_model.load_state_dict(torch.load(path, map_location='cpu', weights_only=True))
            self.audio_model.eval()
        _, signal = _decode_audio(payload, normalize_peak=False)
        length = config['nb_samp']
        # Evaluate consecutive 4.04s windows, including a repeated short last window, as upstream pads short input.
        scores = []
        with torch.inference_mode():
            for offset in range(0, len(signal), length):
                chunk = signal[offset:offset+length]
                chunk = np.tile(chunk, int(np.ceil(length/len(chunk))))[:length]
                _, logits = self.audio_model(torch.from_numpy(chunk.copy()).unsqueeze(0))
                scores.append(float(torch.softmax(logits, dim=1)[0, 0]))  # ASVspoof: 0 spoof, 1 bona fide
        spoof_score = max(scores)
        return {'status': 'failed' if spoof_score >= self.settings.audio_spoof_threshold else 'passed',
                'score': spoof_score, 'threshold': self.settings.audio_spoof_threshold, 'model': 'AASIST-ASVspoof2019-LA',
                'revision': 'a04c9863f63d44471dde8a6abcb3b082b07cd1d1',
                'limitation': 'Research synthetic/converted-speech detector; physical playback and unseen generators are not validated.'}

    def speakers(self, payload):
        rate, signal = _decode_audio(payload)
        size = int(2*rate)
        embeddings = []
        for offset in range(0, len(signal)-size+1, size):
            segment = signal[offset:offset+size]
            if float(np.sqrt(np.mean(segment**2))) < .03:
                continue
            embeddings.append(self.engine._ecapa(segment))
        return speaker_consistency(embeddings, self.settings.speaker_change_threshold)
