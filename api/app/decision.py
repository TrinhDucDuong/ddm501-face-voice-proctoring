"""Pure decision policy shared by real and simulated inference paths."""
from __future__ import annotations

import numpy as np


def decide(
    scores: dict[str, float | None],
    qualities: dict[str, float | None],
    thresholds: dict[str, float],
    require_both: bool = True,
) -> tuple[bool, float, list[str]]:
    reasons: list[str] = []
    for modality in ("face", "voice"):
        score = scores.get(modality)
        quality = qualities.get(modality)
        if score is None:
            if require_both:
                reasons.append(f"missing_{modality}")
            continue
        if not -1.0 <= score <= 1.0:
            raise ValueError(f"{modality}_score must be between -1 and 1")
        if score < thresholds[modality]:
            reasons.append(f"{modality}_mismatch")
        if quality is not None:
            if not 0.0 <= quality <= 1.0:
                raise ValueError(f"{modality}_quality must be between 0 and 1")
            if quality < 0.25:
                reasons.append(f"low_{modality}_quality")

    available_risks = [1.0 - float(scores[m]) for m in ("face", "voice") if scores.get(m) is not None]
    risk = float(np.mean(available_risks)) if available_risks else 1.0
    risk = min(1.0, risk + 0.18 * sum(reason.startswith("missing_") for reason in reasons))
    accepted = not reasons and bool(available_risks)
    return accepted, risk, reasons
