"""Faithful explanations of the actual decision policy; no causal identity claims."""
from .decision import decide


def explain(scores, qualities, thresholds, require_both=True):
    accepted, _, _ = decide(scores, qualities, thresholds, require_both)
    margins = {m: None if scores.get(m) is None else round(scores[m] - thresholds[m], 6)
               for m in ("face", "voice")}
    sensitivity = []
    for change in (-0.05, 0.0, 0.05):
        policy = {m: min(1.0, max(-1.0, t + change)) for m, t in thresholds.items()}
        outcome, _, reasons = decide(scores, qualities, policy, require_both)
        sensitivity.append({"threshold_change": change, "accepted": outcome, "reasons": reasons})
    counterfactuals = {}
    for modality in ("face", "voice"):
        if scores.get(modality) is None:
            counterfactuals[modality] = {"status": "requires_capture"}
            continue
        changed = dict(scores, **{modality: max(scores[modality], thresholds[modality])})
        outcome, _, reasons = decide(changed, qualities, thresholds, require_both)
        counterfactuals[modality] = {"minimum_score_increase": round(max(0, -margins[modality]), 6),
                                   "accepted_after_score_change": outcome, "remaining_reasons": reasons}
    return {"methods": ["decision_boundary_margins", "threshold_sensitivity", "single_modality_counterfactual"],
            "accepted": accepted, "score_margins": margins, "sensitivity": sensitivity,
            "counterfactuals": counterfactuals,
            "limitation": "Score changes explain policy behaviour; they do not prove identity or prescribe media manipulation."}
