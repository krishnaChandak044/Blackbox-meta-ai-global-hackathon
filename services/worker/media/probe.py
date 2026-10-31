"""Probe an original without changing its bytes."""

import json
import subprocess
from pathlib import Path


def ffprobe(path: Path, *, frames: bool = False) -> dict:
    command = ["ffprobe", "-v", "error", "-of", "json"]
    if frames:
        command += [
            "-select_streams",
            "v:0",
            "-show_frames",
            "-show_entries",
            "frame=best_effort_timestamp_time",
        ]
    else:
        command += ["-show_format", "-show_streams"]
    command.append(str(path))
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
    if result.returncode:
        raise ValueError(f"ffprobe failed: {result.stderr[:500]}")
    return json.loads(result.stdout)


def probe_media(path: Path) -> dict:
    data = ffprobe(path)
    streams = data.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError("File has no video stream")
    rate = video.get("avg_frame_rate", "0/1")
    try:
        numerator, denominator = (int(part) for part in rate.split("/"))
        fps = numerator / denominator if denominator else None
    except ValueError:
        fps = None
    return {
        "codec": video.get("codec_name"),
        "container": data.get("format", {}).get("format_name", "").split(",")[0],
        "duration_seconds": float(
            video.get("duration") or data.get("format", {}).get("duration") or 0
        ),
        "fps_nominal": fps,
        "width": video.get("width"),
        "height": video.get("height"),
        "has_audio": any(stream.get("codec_type") == "audio" for stream in streams),
        "device_clock_metadata": json.dumps(
            {
                "format_tags": data.get("format", {}).get("tags", {}),
                "stream_tags": video.get("tags", {}),
            }
        ),
    }
