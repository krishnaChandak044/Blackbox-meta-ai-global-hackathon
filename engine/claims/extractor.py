"""
engine/claims/extractor.py
──────────────────────────
Rule-based claim extraction — pure Python regex, no ML / HTTP.
Returns [] for empty/gibberish input without raising.

Timestamp accuracy contract:
- When diarised segments are provided (via extract_claims_from_segments),
  source_ts_start and source_ts_end are the *actual segment timestamps*
  from the ASR output — not estimates.
- When only plain text is available (extract_claims), timestamps are set
  to None (serialised as 0.0 in the DB) to signal "unknown" — they are
  NEVER inferred from character positions, which is not a valid citation.
"""
from __future__ import annotations
import re
import uuid
from engine.claims.models import Claim, ClaimAssertion

_SPEED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("speed", re.compile(r"\b(?:doing|going|travelling|traveling|moving)\s+(?:at\s+)?(?:about|approximately|around|roughly|at\s+least|over|under)?\s*(\d+(?:\.\d+)?)\s*(?:km/h|kph|kmph|kilometres?\s+per\s+hour|kilometers?\s+per\s+hour|mph|miles?\s+per\s+hour)\b", re.IGNORECASE)),
    ("speed", re.compile(r"\b(\d+(?:\.\d+)?)\s*(km/h|kph|kmph|mph|kilometres?\s+per\s+hour|kilometers?\s+per\s+hour|miles?\s+per\s+hour)\b", re.IGNORECASE)),
    ("speed", re.compile(r"\b(?:doing|going|was\s+doing|going\s+at)\s+(\d+(?:\.\d+)?)\b", re.IGNORECASE)),
]
_DIRECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("direction", re.compile(r"\bturned\s+(left|right|sharply\s+left|sharply\s+right|around)\b", re.IGNORECASE)),
    ("direction", re.compile(r"\bgoing\s+(north|south|east|west|straight|straight\s+ahead|forward)\b", re.IGNORECASE)),
    ("direction", re.compile(r"\bswerved\s+(left|right|to\s+avoid)?\b", re.IGNORECASE)),
    ("direction", re.compile(r"\bmoving\s+(north|south|east|west|northbound|southbound|eastbound|westbound)\b", re.IGNORECASE)),
]
_TIMING_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("timing", re.compile(r"\b(\d+(?:\.\d+)?)\s*seconds?\s+(before|after)\b", re.IGNORECASE)),
    ("timing", re.compile(r"\bbefore\s+the\s+impact\b", re.IGNORECASE)),
    ("timing", re.compile(r"\bat\s+the\s+same\s+time\b", re.IGNORECASE)),
    ("timing", re.compile(r"\bjust\s+(before|after)\b", re.IGNORECASE)),
]
_ACTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("action", re.compile(r"\bran\s+a\s+red\s+light\b", re.IGNORECASE)),
    ("action", re.compile(r"\bwas\s+speeding\b", re.IGNORECASE)),
    ("action", re.compile(r"\bdidn'?t\s+stop\b", re.IGNORECASE)),
    ("action", re.compile(r"\bfailed\s+to\s+stop\b", re.IGNORECASE)),
    ("action", re.compile(r"\bbraked\s+(hard|suddenly)?\b", re.IGNORECASE)),
    ("action", re.compile(r"\bovertook\b", re.IGNORECASE)),
    ("action", re.compile(r"\bjumped\s+the\s+signal\b", re.IGNORECASE)),
]
_STOP_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("stop", re.compile(r"\bstopped\b", re.IGNORECASE)),
    ("stop", re.compile(r"\bhad\s+stopped\b", re.IGNORECASE)),
    ("stop", re.compile(r"\bwas\s+stationary\b", re.IGNORECASE)),
    ("stop", re.compile(r"\bcame\s+to\s+a\s+(?:complete\s+)?stop\b", re.IGNORECASE)),
]
_POSITION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("position", re.compile(r"\bon\s+the\s+wrong\s+side\b", re.IGNORECASE)),
    ("position", re.compile(r"\bin\s+the\s+intersection\b", re.IGNORECASE)),
    ("position", re.compile(r"\bon\s+the\s+footpath\b", re.IGNORECASE)),
    ("position", re.compile(r"\bin\s+the\s+middle\s+of\s+the\s+road\b", re.IGNORECASE)),
    ("position", re.compile(r"\bon\s+the\s+pavement\b", re.IGNORECASE)),
    ("position", re.compile(r"\bat\s+the\s+junction\b", re.IGNORECASE)),
]
ALL_PATTERN_GROUPS: list[list[tuple[str, re.Pattern[str]]]] = [_SPEED_PATTERNS, _DIRECTION_PATTERNS, _TIMING_PATTERNS, _ACTION_PATTERNS, _STOP_PATTERNS, _POSITION_PATTERNS]
_UNIT_NORMALISE: dict[str, str] = {"kilometres per hour": "km/h", "kilometers per hour": "km/h", "kilometre per hour": "km/h", "kilometer per hour": "km/h", "kmph": "km/h", "kph": "km/h", "miles per hour": "mph", "mile per hour": "mph"}
_QUALIFIER_RE = re.compile(r"\b(approximately|about|around|roughly|at\s+least|at\s+most|over|under|never|before|after|exactly)\b", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"[.!?]+(?:\s+|$)")
_MIN_TEXT_LEN = 3
def _normalise_unit(raw: str | None) -> str | None:
    if raw is None:
        return None
    return _UNIT_NORMALISE.get(raw.strip().lower(), raw.strip().lower())
def _extract_qualifier(text: str) -> str | None:
    m = _QUALIFIER_RE.search(text)
    return m.group(1).lower() if m else None
def _extract_speed_value(match: re.Match[str]) -> tuple[float | None, str | None]:
    raw_num: str | None = None
    raw_unit: str | None = None
    for idx in range(1, (match.lastindex or 1) + 1):
        g = match.group(idx)
        if g is None:
            continue
        try:
            float(g)
            if raw_num is None:
                raw_num = g
            continue
        except ValueError:
            pass
        if raw_unit is None:
            raw_unit = g
    value: float | None = None
    if raw_num is not None:
        try:
            value = float(raw_num)
        except ValueError:
            pass
    unit = _normalise_unit(raw_unit) if raw_unit else None
    if value is not None and unit is None:
        unit = "km/h"
    return value, unit
def _sentences(text: str) -> list[tuple[str, int, int]]:
    results: list[tuple[str, int, int]] = []
    parts = _SENTENCE_RE.split(text)
    offset = 0
    for part in parts:
        stripped = part.strip()
        if not stripped:
            offset += len(part) + 1
            continue
        start = text.find(stripped, offset)
        if start == -1:
            start = offset
        end = start + len(stripped)
        results.append((stripped, start, end))
        offset = end
    if not results and text.strip():
        results.append((text.strip(), 0, len(text.strip())))
    return results
def _extract_subject(sentence: str) -> str:
    lower = sentence.lower()
    if "vehicle a" in lower or "vehicle-a" in lower:
        return "Vehicle A"
    if "vehicle b" in lower or "vehicle-b" in lower:
        return "Vehicle B"
    if "pedestrian" in lower:
        return "pedestrian"
    if "cyclist" in lower or "biker" in lower:
        return "cyclist"
    if "traffic light" in lower or "signal" in lower:
        return "traffic light"
    if "car" in lower:
        return "Vehicle A"
    if "truck" in lower or "lorry" in lower:
        return "truck"
    if "bus" in lower:
        return "bus"
    return "unknown"
def _compute_confidence(assertions: list[ClaimAssertion]) -> float:
    if not assertions:
        return 0.0
    base = 0.6
    for a in assertions:
        if a.value is not None:
            base += 0.10
        if a.qualifier is not None:
            base += 0.05
    return min(0.95, round(base, 2))
def extract_claims(
    transcript_text: str,
    case_id: str,
    transcript_id: str,
    *,
    speaker: str = "witness_1",
    media_id: str | None = None,
) -> list[Claim]:
    """
    Extract claims from plain transcript text.

    Timestamps are set to 0.0 (unknown) because character-position
    estimation is not a valid way to cite a frame.
    Use extract_claims_from_segments when diarised segments are available.
    """
    if not transcript_text or not isinstance(transcript_text, str):
        return []
    stripped = transcript_text.strip()
    if len(stripped) < _MIN_TEXT_LEN:
        return []

    claims: list[Claim] = []
    seen_spans: set[tuple[str, int, int]] = set()

    for sent_text, _char_start, _char_end in _sentences(stripped):
        # Timestamps are NOT inferred from character position — they are unknown.
        ts_start: float = 0.0
        ts_end: float = 0.0
        _assertions = _extract_assertions_from_sentence(
            sent_text, ts_start, ts_end, seen_spans
        )
        if _assertions:
            claims.append(Claim(
                id=str(uuid.uuid4()),
                case_id=case_id,
                media_id=media_id,
                transcript_id=transcript_id,
                speaker=speaker,
                assertions=_assertions,
                raw_text=sent_text,
                confidence=_compute_confidence(_assertions),
            ))
    return claims


def extract_claims_from_segments(
    segments: list[dict],
    case_id: str,
    transcript_id: str,
    *,
    media_id: str | None = None,
) -> list[Claim]:
    """
    Extract claims from diarised ASR segments.

    Each segment dict must have:
      {"speaker": str, "start": float, "end": float, "text": str}

    source_ts_start and source_ts_end come directly from segment["start"]
    and segment["end"] — the actual ASR timestamps, not estimates.
    """
    claims: list[Claim] = []
    seen_spans: set[tuple[str, int, int]] = set()

    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if len(text) < _MIN_TEXT_LEN:
            continue
        speaker = str(seg.get("speaker", "unknown"))
        ts_start = float(seg.get("start", 0.0))
        ts_end = float(seg.get("end", 0.0))

        for sent_text, _, _ in _sentences(text):
            _assertions = _extract_assertions_from_sentence(
                sent_text, ts_start, ts_end, seen_spans
            )
            if _assertions:
                claims.append(Claim(
                    id=str(uuid.uuid4()),
                    case_id=case_id,
                    media_id=media_id,
                    transcript_id=transcript_id,
                    speaker=speaker,
                    assertions=_assertions,
                    raw_text=sent_text,
                    confidence=_compute_confidence(_assertions),
                ))
    return claims


def _extract_assertions_from_sentence(
    sent_text: str,
    ts_start: float,
    ts_end: float,
    seen_spans: set[tuple[str, int, int]],
) -> list[ClaimAssertion]:
    """
    Run all pattern groups over a single sentence and return deduplicated assertions.
    ts_start/ts_end are passed in directly — not computed inside.
    """
    assertions: list[ClaimAssertion] = []

    for group in ALL_PATTERN_GROUPS:
        for assertion_type, pattern in group:
            for m in pattern.finditer(sent_text):
                key = (assertion_type, m.start(), m.end())
                if key in seen_spans:
                    continue
                raw_excerpt = m.group(0).strip()
                qualifier = _extract_qualifier(m.group(0))
                value: float | None = None
                unit: str | None = None

                if assertion_type == "speed":
                    value, unit = _extract_speed_value(m)
                elif assertion_type == "timing":
                    g1 = m.group(1) if m.lastindex and m.lastindex >= 1 else None
                    if g1 is not None:
                        try:
                            value = float(g1)
                            unit = "seconds"
                        except ValueError:
                            pass
                else:
                    qualifier = _extract_qualifier(sent_text)

                subject = _extract_subject(sent_text)

                # Dedup: skip if overlaps existing assertion of same type by >50%
                _overlap = False
                for ea in assertions:
                    if ea.assertion_type != assertion_type:
                        continue
                    e_start = sent_text.lower().find(ea.raw_text.lower())
                    if e_start == -1:
                        continue
                    e_end = e_start + len(ea.raw_text)
                    overlap = max(0, min(m.end(), e_end) - max(m.start(), e_start))
                    if overlap > 0 and overlap >= min(len(raw_excerpt), len(ea.raw_text)) * 0.5:
                        if ea.unit and not unit:
                            _overlap = True
                            break
                        elif unit and not ea.unit:
                            assertions.remove(ea)
                            break
                        else:
                            _overlap = True
                            break
                if _overlap:
                    continue

                assertions.append(ClaimAssertion(
                    assertion_type=assertion_type,
                    subject=subject,
                    value=value,
                    unit=unit,
                    qualifier=qualifier,
                    raw_text=raw_excerpt,
                    # Use the segment timestamps directly — no interpolation
                    source_ts_start=round(ts_start, 3),
                    source_ts_end=round(ts_end, 3),
                ))
                seen_spans.add(key)

    # Final dedup on raw text
    deduped: list[ClaimAssertion] = []
    seen_raw: set[tuple[str, str]] = set()
    for a in assertions:
        k2 = (a.assertion_type, a.raw_text.lower())
        if k2 in seen_raw:
            continue
        seen_raw.add(k2)
        deduped.append(a)

    return deduped
