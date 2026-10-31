"""
engine/claims/checker.py
────────────────────────
Checks claim assertions against track data + homography/scale.

Framework-free: no FastAPI / SQLAlchemy / Celery imports.

Key correctness rules:
1. Speed is computed PER-VEHICLE — tracks are never mixed.
   The vehicle whose time window overlaps the assertion is selected first.
2. All unit conversions are made explicit in explanations (km/h).
3. Coverage values describe evidence quantity, not verdict probability.
4. Time-window filtering: only track points whose presentation_ts_s falls
   within [assertion.source_ts_start, assertion.source_ts_end] are used.
   If the window is 0-length, the full track is used (backward compat).
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from engine.claims.models import Claim, ClaimAssertion, ClaimVerdict, TrackDetailLite, TrackPointLite

# ── Tunable thresholds ────────────────────────────────────────────────────────
SPEED_SUPPORT_TOL = 0.20    # ±20% → supported
SPEED_CONTRADICT_TOL = 0.40  # >40% → contradicted; between = inconclusive
STOP_MIN_DURATION_S = 0.5
DIRECTION_TOL_DEG = 45.0    # ±45° of claimed compass bearing

# Minimum number of consecutive world-point pairs to trust a speed estimate
MIN_SPEED_PAIRS = 2

DIRECTION_BEARINGS: dict[str, float] = {
    "north": 0.0, "northbound": 0.0,
    "south": 180.0, "southbound": 180.0,
    "east": 90.0, "eastbound": 90.0,
    "west": 270.0, "westbound": 270.0,
    "straight": 0.0, "forward": 0.0, "straight ahead": 0.0,
    "north-east": 45.0, "northeast": 45.0,
    "south-east": 135.0, "southeast": 135.0,
    "south-west": 225.0, "southwest": 225.0,
    "north-west": 315.0, "northwest": 315.0,
}


# ── Unit conversion ───────────────────────────────────────────────────────────

def _to_kmh(value: float, unit: str | None) -> float:
    """Convert a claimed speed value to km/h for comparison."""
    if unit is None:
        raise ValueError("Speed unit is unknown")
    u = unit.lower().strip()
    if u in ("km/h", "kph", "kmph", "kilometres per hour", "kilometers per hour"):
        return value
    if u in ("mph", "miles per hour", "mile per hour"):
        return value * 1.60934
    if u in ("m/s", "ms", "metres per second", "meters per second"):
        return value * 3.6
    raise ValueError(f"Unsupported speed unit: {unit}")


# ── Time-window filtering ─────────────────────────────────────────────────────

def _filter_by_window(
    points: list[TrackPointLite],
    ts_start: float,
    ts_end: float,
) -> list[TrackPointLite]:
    """
    Return only the points whose timestamp falls within [ts_start, ts_end].
    If the window is zero-length (ts_start == ts_end == 0) the full list is
    returned unchanged — this happens when timestamps were not available in
    the transcript.
    """
    if ts_start == 0.0 and ts_end == 0.0:
        return points  # no window info — use all
    return [p for p in points if ts_start <= p.presentation_ts_s <= ts_end]


# ── Per-vehicle speed computation ─────────────────────────────────────────────

def _speed_for_single_track(
    points: list[TrackPointLite],
) -> tuple[float | None, list[tuple[float, float]], int | None, int | None]:
    """
    Compute the median speed (km/h) for a single vehicle's track.

    Returns (median_kmh, world_positions, first_frame, last_frame).
    Returns (None, [], None, None) when there is insufficient data.
    """
    world_pts = [p for p in points if p.world_x is not None and p.world_y is not None]
    if len(world_pts) < 2:
        return None, [], None, None

    world_pts.sort(key=lambda p: p.presentation_ts_s)

    speeds_ms: list[float] = []
    world_positions = [(p.world_x, p.world_y) for p in world_pts]  # type: ignore[misc]

    for i in range(1, len(world_pts)):
        dt = world_pts[i].presentation_ts_s - world_pts[i - 1].presentation_ts_s
        if dt <= 1e-6:
            continue
        dx = world_pts[i].world_x - world_pts[i - 1].world_x  # type: ignore[operator]
        dy = world_pts[i].world_y - world_pts[i - 1].world_y  # type: ignore[operator]
        dist_m = math.sqrt(dx * dx + dy * dy)
        speeds_ms.append(dist_m / dt)

    if len(speeds_ms) < MIN_SPEED_PAIRS:
        return None, world_positions, world_pts[0].frame_index, world_pts[-1].frame_index

    speeds_ms.sort()
    median_ms = speeds_ms[len(speeds_ms) // 2]
    return median_ms * 3.6, world_positions, world_pts[0].frame_index, world_pts[-1].frame_index


def _best_speed_estimate(
    tracks: list[TrackDetailLite],
    assertion: ClaimAssertion,
) -> tuple[float | None, list[tuple[float, float]], int | None, int | None, str]:
    """
    For a speed assertion, pick the track with the most evidence in the
    assertion's time window and return its speed estimate.

    Returns (median_kmh, world_positions, f_start, f_end, track_id).
    """
    ts_start = assertion.source_ts_start
    ts_end = assertion.source_ts_end
    best: tuple[float | None, list, int | None, int | None, str] = (None, [], None, None, "")
    best_point_count = 0

    for track in tracks:
        window_pts = _filter_by_window(track.points, ts_start, ts_end)
        # Skip tracks with no overlap in the assertion window
        if not window_pts and ts_start != 0.0:
            continue
        pts_to_use = window_pts if window_pts else track.points
        world_count = sum(1 for p in pts_to_use if p.world_x is not None and p.world_y is not None)
        if world_count > best_point_count:
            best_point_count = world_count
            kmh, wpos, f0, f1 = _speed_for_single_track(pts_to_use)
            best = (kmh, wpos, f0, f1, track.id)

    return best


# ── Bearing helpers ───────────────────────────────────────────────────────────

def _angular_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _direction_to_bearing(text: str) -> float | None:
    lower = text.lower().strip()
    for key, deg in DIRECTION_BEARINGS.items():
        if key in lower:
            return deg
    return None


def _bearing_from_track(
    track: TrackDetailLite,
    assertion: ClaimAssertion,
) -> tuple[float | None, list[tuple[float, float]], int | None, int | None]:
    ts_start = assertion.source_ts_start
    ts_end = assertion.source_ts_end
    pts_in_window = _filter_by_window(track.points, ts_start, ts_end)
    pts = pts_in_window if pts_in_window else track.points
    world_pts = [p for p in pts if p.world_x is not None and p.world_y is not None]
    if len(world_pts) < 2:
        return None, [], None, None
    world_pts.sort(key=lambda p: p.presentation_ts_s)
    dx = world_pts[-1].world_x - world_pts[0].world_x  # type: ignore[operator]
    dy = world_pts[-1].world_y - world_pts[0].world_y  # type: ignore[operator]
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None, [], None, None
    bearing = math.degrees(math.atan2(dx, dy)) % 360
    wpos = [(p.world_x, p.world_y) for p in world_pts]  # type: ignore[misc]
    return bearing, wpos, world_pts[0].frame_index, world_pts[-1].frame_index


# ── Evidence confidence ───────────────────────────────────────────────────────

def _data_coverage(n_pairs: int, expected_pairs: int = 15) -> float:
    """Evidence coverage score; this is not a probability of verdict correctness."""
    return min(1.0, max(0.0, n_pairs / expected_pairs))


# ── Main entry point ──────────────────────────────────────────────────────────

def check_claim(
    claim: Claim,
    tracks: list[TrackDetailLite],
    homography=None,
    scale=None,
) -> ClaimVerdict:
    """
    Check a Claim against the available track evidence.

    Parameters
    ----------
    claim      : the structured Claim extracted from a transcript
    tracks     : world-projected track points for the relevant media clip
    homography : HomographyResult (unused here — kept for API symmetry)
    scale      : ScaleResult — required for speed checks; None → insufficient_data
    """
    now = datetime.now(timezone.utc)

    if not claim.assertions:
        return ClaimVerdict(
            claim_id=claim.id,
            verdict="inconclusive",
            confidence=0.5,
            evidence_frame_start=None,
            evidence_frame_end=None,
            evidence_world_positions=None,
            explanation="Claim has no structured assertions to evaluate.",
            checked_at=now,
        )

    if not tracks:
        return ClaimVerdict(
            claim_id=claim.id,
            verdict="inconclusive",
            confidence=0.5,
            evidence_frame_start=None,
            evidence_frame_end=None,
            evidence_world_positions=None,
            explanation=(
                "No object tracks found for this media clip. "
                "Run tracking before checking claims."
            ),
            checked_at=now,
        )

    # Evaluate only the primary (first) assertion.
    # Multiple assertions per claim would require aggregate logic — out of scope for Phase 3.
    primary = claim.assertions[0]
    atype = primary.assertion_type

    # ── Speed ─────────────────────────────────────────────────────────────────
    if atype == "speed":
        if scale is None:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="insufficient_data",
                confidence=0.0,
                evidence_frame_start=None,
                evidence_frame_end=None,
                evidence_world_positions=None,
                explanation=(
                    "Speed cannot be verified: no ground-plane calibration (scale) is available. "
                    "Go to Calibration, place ≥4 anchors, mark a known-distance pair, and fit the homography."
                ),
                checked_at=now,
            )

        if primary.value is None:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="inconclusive",
                confidence=0.0,
                evidence_frame_start=None,
                evidence_frame_end=None,
                evidence_world_positions=None,
                explanation="Speed assertion has no numeric value to compare against track data.",
                checked_at=now,
            )

        # Convert claimed speed to km/h for a consistent comparison
        try:
            claimed_kmh = _to_kmh(primary.value, primary.unit)
        except ValueError as exc:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="insufficient_data",
                confidence=0.0,
                evidence_frame_start=None,
                evidence_frame_end=None,
                evidence_world_positions=None,
                explanation=f"Speed cannot be checked: {exc}. Specify a supported unit.",
                checked_at=now,
            )
        unit_label = primary.unit or "km/h"

        kmh, wpos, f0, f1, track_id = _best_speed_estimate(tracks, primary)

        if kmh is None:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="inconclusive",
                confidence=0.0,
                evidence_frame_start=f0,
                evidence_frame_end=f1,
                evidence_world_positions=wpos or None,
                explanation=(
                    "Insufficient consecutive world positions to compute a reliable speed estimate. "
                    "Ensure camera calibration covers the vehicle's path during the assertion time window."
                ),
                checked_at=now,
            )

        rel_err = abs(kmh - claimed_kmh) / max(claimed_kmh, 1e-6)

        # Count pairs for confidence
        selected_track = next((t for t in tracks if t.id == track_id), None)
        n_pairs = 0
        if selected_track:
            window_pts = _filter_by_window(selected_track.points, primary.source_ts_start, primary.source_ts_end)
            pts_used = window_pts if window_pts else selected_track.points
            world_in_window = [p for p in pts_used if p.world_x is not None]
            n_pairs = max(0, len(world_in_window) - 1)

        conf = _data_coverage(n_pairs)

        if rel_err <= SPEED_SUPPORT_TOL:
            verdict = "supported"
            expl = (
                f"Speed claim of {primary.value:.0f} {unit_label} is supported by the available track data. "
                f"Measured median speed: {kmh:.1f} km/h "
                f"(relative error {rel_err:.0%}, within ±{SPEED_SUPPORT_TOL:.0%} tolerance). "
                f"Evidence from {n_pairs} consecutive frame pairs on track {track_id[:8]}."
            )
        elif rel_err > SPEED_CONTRADICT_TOL:
            verdict = "contradicted"
            expl = (
                f"Speed claim of {primary.value:.0f} {unit_label} conflicts with the available track data. "
                f"Measured median speed: {kmh:.1f} km/h "
                f"(relative error {rel_err:.0%} exceeds ±{SPEED_CONTRADICT_TOL:.0%}). "
                f"Evidence from {n_pairs} consecutive frame pairs on track {track_id[:8]}."
            )
        else:
            verdict = "inconclusive"
            expl = (
                f"Speed comparison is inconclusive. "
                f"Claimed {primary.value:.0f} {unit_label} vs measured {kmh:.1f} km/h "
                f"(relative error {rel_err:.0%}, between thresholds ±{SPEED_SUPPORT_TOL:.0%}–{SPEED_CONTRADICT_TOL:.0%}). "
                f"Evidence from {n_pairs} frame pairs on track {track_id[:8]}."
            )

        return ClaimVerdict(
            claim_id=claim.id,
            verdict=verdict,
            confidence=conf,
            evidence_frame_start=f0,
            evidence_frame_end=f1,
            evidence_world_positions=wpos or None,
            explanation=expl,
            checked_at=now,
        )

    # ── Stop ──────────────────────────────────────────────────────────────────
    elif atype == "stop":
        # Find the track with world points in the assertion window
        best_track = None
        best_count = 0
        for track in tracks:
            wpts = _filter_by_window(track.points, primary.source_ts_start, primary.source_ts_end)
            pts = wpts if wpts else track.points
            c = sum(1 for p in pts if p.world_x is not None)
            if c > best_count:
                best_count = c
                best_track = track

        if best_track is None:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="inconclusive",
                confidence=0.5,
                evidence_frame_start=None,
                evidence_frame_end=None,
                evidence_world_positions=None,
                explanation="No track data with world positions found in this assertion's time window.",
                checked_at=now,
            )

        window_pts = _filter_by_window(best_track.points, primary.source_ts_start, primary.source_ts_end)
        pts = window_pts if window_pts else best_track.points
        world_pts = sorted(
            [p for p in pts if p.world_x is not None and p.world_y is not None],
            key=lambda p: p.presentation_ts_s,
        )

        if len(world_pts) < 2:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="inconclusive",
                confidence=0.5,
                evidence_frame_start=None,
                evidence_frame_end=None,
                evidence_world_positions=None,
                explanation=(
                    "Insufficient world positions to evaluate stop claim. "
                    "At least 2 calibrated points are required."
                ),
                checked_at=now,
            )

        wpos = [(p.world_x, p.world_y) for p in world_pts]  # type: ignore[misc]
        # A stop is a low-speed interval, not zero movement across the whole window.
        stop_intervals: list[float] = []
        interval_start: float | None = None
        interval_end: float | None = None
        for i in range(1, len(world_pts)):
            dt = world_pts[i].presentation_ts_s - world_pts[i - 1].presentation_ts_s
            if dt <= 0:
                continue
            dx = world_pts[i].world_x - world_pts[i - 1].world_x  # type: ignore[operator]
            dy = world_pts[i].world_y - world_pts[i - 1].world_y  # type: ignore[operator]
            if math.hypot(dx, dy) / dt < 0.25:
                if interval_start is None:
                    interval_start = world_pts[i - 1].presentation_ts_s
                interval_end = world_pts[i].presentation_ts_s
            else:
                if interval_start is not None and interval_end is not None:
                    stop_intervals.append(interval_end - interval_start)
                interval_start = interval_end = None
        if interval_start is not None and interval_end is not None:
            stop_intervals.append(interval_end - interval_start)
        is_stopped = max(stop_intervals, default=0.0) >= STOP_MIN_DURATION_S
        f0 = world_pts[0].frame_index
        f1 = world_pts[-1].frame_index

        if is_stopped:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="supported",
                confidence=min(1.0, max(stop_intervals, default=0.0) / 2.0),
                evidence_frame_start=f0,
                evidence_frame_end=f1,
                evidence_world_positions=wpos,
                explanation=(
                f"Stop claim is supported by a low-speed interval lasting "
                f"{max(stop_intervals):.2f} seconds (minimum {STOP_MIN_DURATION_S:.2f} seconds)."
                ),
                checked_at=now,
            )
        else:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="contradicted",
                confidence=min(1.0, len(world_pts) / 15.0),
                evidence_frame_start=f0,
                evidence_frame_end=f1,
                evidence_world_positions=wpos,
                explanation=(
                f"No low-speed interval of at least {STOP_MIN_DURATION_S:.2f} seconds was observed in the available window."
                ),
                checked_at=now,
            )

    # ── Direction ─────────────────────────────────────────────────────────────
    elif atype == "direction":
        # Try to extract the claimed bearing from the raw assertion text
        relative_text = primary.raw_text.lower()
        if re.search(r"\b(left|right)\b", relative_text):
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="inconclusive",
                confidence=0.0,
                evidence_frame_start=None,
                evidence_frame_end=None,
                evidence_world_positions=None,
                explanation="Relative left/right direction needs a defined viewpoint; no compass verdict was produced.",
                checked_at=now,
            )
        claimed_bearing = _direction_to_bearing(primary.raw_text)
        if claimed_bearing is None:
            claimed_bearing = _direction_to_bearing(primary.subject)
        if claimed_bearing is None:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="inconclusive",
                confidence=0.5,
                evidence_frame_start=None,
                evidence_frame_end=None,
                evidence_world_positions=None,
                explanation=(
                    f"Could not map direction assertion '{primary.raw_text}' to a compass bearing. "
                    "Supported keywords: north, south, east, west, straight, northeast, etc."
                ),
                checked_at=now,
            )

        # The direction sentence may concern a particular subject; without a
        # track binding, multiple candidate tracks are ambiguous. Abstain.
        if len(tracks) != 1:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="inconclusive",
                confidence=0.0,
                evidence_frame_start=None,
                evidence_frame_end=None,
                evidence_world_positions=None,
                explanation="Direction cannot be attributed to one vehicle because the claim is not linked to a specific track.",
                checked_at=now,
            )

        # A single track is required until claims can explicitly identify tracks.
        best_bearing = None
        best_wpos: list[tuple[float, float]] = []
        best_f0 = best_f1 = None
        best_count = 0

        for track in tracks[:1]:
            bearing, wpos, f0, f1 = _bearing_from_track(track, primary)
            if bearing is not None:
                c = len(wpos)
                if c > best_count:
                    best_count = c
                    best_bearing = bearing
                    best_wpos = wpos
                    best_f0, best_f1 = f0, f1

        if best_bearing is None:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="inconclusive",
                confidence=0.5,
                evidence_frame_start=None,
                evidence_frame_end=None,
                evidence_world_positions=None,
                explanation=(
                    "Cannot compute travel bearing: no tracks have calibrated world positions "
                    "in the assertion's time window."
                ),
                checked_at=now,
            )

        diff = _angular_diff(best_bearing, claimed_bearing)
        if diff <= DIRECTION_TOL_DEG:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="supported",
                confidence=min(1.0, best_count / 15.0),
                evidence_frame_start=best_f0,
                evidence_frame_end=best_f1,
                evidence_world_positions=best_wpos or None,
                explanation=(
                    f"Direction claim '{primary.raw_text}' is supported: "
                    f"measured bearing {best_bearing:.0f}° differs by {diff:.0f}° "
                    f"from claimed {claimed_bearing:.0f}° (tolerance ±{DIRECTION_TOL_DEG:.0f}°)."
                ),
                checked_at=now,
            )
        else:
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="contradicted",
                confidence=min(1.0, best_count / 15.0),
                evidence_frame_start=best_f0,
                evidence_frame_end=best_f1,
                evidence_world_positions=best_wpos or None,
                explanation=(
                    f"Direction claim '{primary.raw_text}' is contradicted: "
                    f"measured bearing {best_bearing:.0f}° differs by {diff:.0f}° "
                    f"from claimed {claimed_bearing:.0f}° (exceeds ±{DIRECTION_TOL_DEG:.0f}° tolerance)."
                ),
                checked_at=now,
            )

    # ── Timing ────────────────────────────────────────────────────────────────
    elif atype == "timing":
        return ClaimVerdict(
            claim_id=claim.id,
            verdict="inconclusive",
            confidence=0.5,
            evidence_frame_start=None,
            evidence_frame_end=None,
            evidence_world_positions=None,
            explanation=(
                "Timing assertions require synchronised multi-clip evidence and a common time reference. "
                "Single-clip timing cannot be automatically verified in Phase 3."
            ),
            checked_at=now,
        )

    # ── Action / position / other (not automatically verifiable) ─────────────
    else:
        return ClaimVerdict(
            claim_id=claim.id,
            verdict="inconclusive",
            confidence=0.5,
            evidence_frame_start=None,
            evidence_frame_end=None,
            evidence_world_positions=None,
            explanation=(
                f"Assertion type '{atype}' ('{primary.raw_text}') cannot be automatically "
                "verified from trajectory data alone. Manual review of the source footage is required."
            ),
            checked_at=now,
        )
