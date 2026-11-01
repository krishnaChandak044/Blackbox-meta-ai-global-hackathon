"""Deterministic, explainable evidence-needs ranking (no source invention)."""
from __future__ import annotations

from typing import Any

SUGGESTIONS = {
    "scale_calibration": ("measure_scene_distance", "Record one known ground distance", 0.80, 2.0,
                           "A known-distance measurement addresses missing metric scale."),
    "homography_reprojection": ("scene_calibration", "Add reviewed ground-plane anchors", 0.65, 2.5,
                                 "Additional calibration anchors can constrain the ground-plane mapping."),
    "pixel_localisation": ("higher_quality_video", "Request the original higher-resolution clip", 0.35, 2.0,
                           "Original frames may improve ground-contact localisation."),
    "frame_timestamp": ("camera_timing_metadata", "Request camera timing or recording metadata", 0.25, 1.5,
                        "Timing metadata can reduce timestamp uncertainty; camera clock error may remain unknown."),
    "model_assumption": ("expert_measurement", "Request an independent scene or vehicle measurement", 0.25, 3.0,
                         "An independent measurement may constrain model assumptions."),
}


def rank_evidence_needs(certificates: dict[str, Any], *, known_sources: list[dict] | None = None,
                        verified_deadlines: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """Rank suggestions using declared heuristic reduction, effort, and verified urgency.

    Reduction values are prioritization heuristics, not calibrated probabilities.
    Only user-verified deadlines affect urgency; unknown availability stays unknown.
    """
    known_sources = known_sources or []
    verified_deadlines = verified_deadlines or {}
    candidates: dict[str, dict[str, Any]] = {}
    for quantity, cert in certificates.items():
        get = cert.get if isinstance(cert, dict) else lambda key, default=None: getattr(cert, key, default)
        status = get("status")
        if status == "measurable":
            continue
        limiting = get("limiting_source") or "model_assumption"
        key, title, reduction, effort, reason = SUGGESTIONS.get(limiting, SUGGESTIONS["model_assumption"])
        row = candidates.setdefault(key, {
            "need_key": key, "title": title, "evidence_type": key,
            "questions": [], "heuristic_expected_reduction_fraction": reduction,
            "effort_score_1_low_5_high": effort, "privacy_cost_1_low_5_high": 1.0,
            "availability": "unknown", "retention_deadline": None,
            "ranking_basis": reason,
        })
        row["questions"].append(quantity)
        row["ranking_basis"] += f" Affects {quantity} ({status})."
    source_by_key = {item.get("need_key"): item for item in known_sources if item.get("verified") is True}
    for key, row in candidates.items():
        verified = source_by_key.get(key)
        if verified:
            row["availability"] = "human_verified_source"
            deadline_hours = verified_deadlines.get(key)
            if deadline_hours is not None and deadline_hours >= 0:
                row["retention_deadline"] = {"hours_remaining": float(deadline_hours), "basis": "user_verified"}
        urgency = 0.0
        deadline = row["retention_deadline"]
        if deadline:
            urgency = max(0.0, 1.0 - deadline["hours_remaining"] / 168.0)
        row["urgency_score_0_1"] = urgency
        row["priority_score"] = (row["heuristic_expected_reduction_fraction"] / row["effort_score_1_low_5_high"]
                                 + urgency * 0.5)
        row["reduction_metric"] = "heuristic_fraction; not a probability or validated effect"
        row["questions"] = sorted(set(row["questions"]))
    return sorted(candidates.values(), key=lambda item: (-item["priority_score"], item["need_key"]))
