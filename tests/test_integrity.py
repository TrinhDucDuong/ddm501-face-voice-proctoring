from app.config import Settings


def test_unavailable_detectors_do_not_report_passed(tmp_path):
    from app.biometrics import BiometricEngine
    from app.integrity import IntegrityInspector
    settings = Settings(model_backend='pretrained', model_dir=str(tmp_path), _env_file=None)
    inspector = IntegrityInspector(settings, BiometricEngine(settings))
    result = inspector.inspect(b'not-an-image', b'not-a-wav')
    assert result['face_pad']['status'] == 'unavailable'
    assert result['audio_spoof']['status'] == 'unavailable'
    assert result['speaker_consistency']['status'] == 'not_assessed'


def test_demo_backend_is_explicitly_not_an_anti_spoof_model():
    from app.biometrics import BiometricEngine
    from app.integrity import IntegrityInspector
    settings = Settings(model_backend='demo', _env_file=None)
    result = IntegrityInspector(settings, BiometricEngine(settings)).inspect(b'', b'')
    assert all(value['status'] == 'not_assessed' for value in result.values())


def test_speaker_change_requires_multiple_segments_and_reports_heuristic():
    from app.integrity import speaker_consistency
    assert speaker_consistency([[1., 0.]])['status'] == 'not_assessed'
    assert speaker_consistency([[1., 0.], [.99, .01], [1., 0.]])['status'] == 'passed'
    result = speaker_consistency([[1., 0.], [1., 0.], [0., 1.], [0., 1.]])
    assert result['status'] == 'failed'
    assert result['method'] == 'ecapa_segment_consistency'
    assert 'overlap' in result['limitation']


def test_unassessable_capture_is_not_platform_detector_outage(monkeypatch):
    from app.integrity import CAPABILITY, IntegrityInspector
    inspector = IntegrityInspector(Settings(model_backend='pretrained', _env_file=None), None)
    for name in ('face_pad', 'audio_spoof', 'speakers'):
        monkeypatch.setattr(inspector, name, lambda payload: {'status': 'not_assessed', 'reason': 'Insufficient capture'})
    result = inspector.inspect(b'', b'')
    assert result['face_pad']['status'] == 'not_assessed'
    assert CAPABILITY.labels(capability='face_pad')._value.get() == 1
