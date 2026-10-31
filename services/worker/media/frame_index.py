"""Frame index based on presentation timestamps, including variable-frame-rate clips."""

import json
from pathlib import Path

from services.worker.media.probe import ffprobe


def build_frame_index(path: Path, output: Path) -> dict:
    data = ffprobe(path, frames=True)
    timestamps = []
    for frame in data.get("frames", []):
        value = frame.get("best_effort_timestamp_time")
        if value is not None:
            timestamps.append(round(float(value) * 1_000_000))
    if not timestamps:
        raise ValueError("No timestamped video frames found")
    deltas = [b - a for a, b in zip(timestamps, timestamps[1:]) if b > a]
    is_variable = bool(deltas and (max(deltas) - min(deltas)) > max(1000, min(deltas) * 0.05))
    payload = {"schema_version": 1, "unit": "microseconds", "presentation_timestamps": timestamps}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, separators=(",", ":")))
    return {"frame_count": len(timestamps), "is_variable_framerate": is_variable}
