import pytest
from app.decision import decide

THRESHOLDS = {"face": 0.5, "voice": 0.4}


def test_decision_allows_good_multimodal_scores():
    accepted, risk, reasons = decide(
        {"face": 0.8, "voice": 0.7}, {"face": 0.9, "voice": 0.8}, THRESHOLDS
    )
    assert accepted is True
    assert risk == pytest.approx(0.25)
    assert reasons == []


def test_negative_cosine_is_valid_mismatch_not_server_error():
    accepted, risk, reasons = decide(
        {"face": -0.2, "voice": -0.1}, {"face": 0.9, "voice": 0.9}, THRESHOLDS,
    )
    assert not accepted
    assert risk == 1
    assert reasons == ["face_mismatch", "voice_mismatch"]


def test_decision_explains_mismatch_quality_and_missing_input():
    accepted, risk, reasons = decide(
        {"face": 0.3, "voice": None}, {"face": 0.1, "voice": None}, THRESHOLDS
    )
    assert accepted is False
    assert risk == pytest.approx(0.88)
    assert reasons == ["face_mismatch", "low_face_quality", "missing_voice"]


@pytest.mark.parametrize("field", ["score", "quality"])
def test_decision_rejects_out_of_range_features(field):
    scores = {"face": 1.1 if field == "score" else 0.8, "voice": 0.8}
    qualities = {"face": -0.1 if field == "quality" else 0.8, "voice": 0.8}
    with pytest.raises(ValueError):
        decide(scores, qualities, THRESHOLDS)
