#!/usr/bin/env python3
"""Generate a synthetic G9 staged clip with known ground-truth geometry.

Produces:
  fixtures/staged/g9_synthetic_v1/clip.mp4   — 10-second synthetic road clip
  fixtures/staged/g9_synthetic_v1/metadata.json — ground truth geometry

The clip shows:
  - A plain grey road surface 3.5 m wide
  - Two white lane markers at x = 0.0 m and x = 3.5 m (known distance = 3.5 m)
  - A moving blue rectangle simulating a vehicle at ~14 m/s (~50 km/h)
  - Frame rate: 25 fps, 1280×720, H.264

Ground-truth calibration parameters embedded in metadata.json:
  - Known distance: 3.5 m between the two marker lines
  - Vehicle speed: 14.0 m/s = 50.4 km/h
  - Braking onset: frame 125 (5.0 s)
  - Final speed: 0.0 m/s (stopped at frame 200 / 8.0 s)

This fixture is SYNTHETIC — it contains no real footage, personal data,
or identifiable individuals. It may be committed to the repository.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

OUTPUT_DIR = Path("fixtures/staged/g9_synthetic_v1")
CLIP_PATH = OUTPUT_DIR / "clip.mp4"
META_PATH = OUTPUT_DIR / "metadata.json"

# Video parameters
WIDTH = 1280
HEIGHT = 720
FPS = 25
DURATION_S = 10
TOTAL_FRAMES = FPS * DURATION_S  # 250 frames

# Scene geometry (metres, ground plane)
LANE_WIDTH_M = 3.5          # known calibration distance (marker A to marker B)
VEHICLE_WIDTH_M = 1.8
VEHICLE_HEIGHT_M = 1.4      # height above ground (for bbox, not 3D)
CAMERA_HEIGHT_M = 1.2       # simulated fixed camera height
CAMERA_PITCH_DEG = 10.0     # slight downward angle

# Vehicle trajectory
ENTRY_SPEED_MS = 14.0       # 50.4 km/h
BRAKE_ONSET_FRAME = 125     # 5.0 s
DECELERATION_MS2 = 7.0      # hard braking

# Pixel layout (road occupies centre band of frame)
ROAD_Y_TOP_PX = int(HEIGHT * 0.45)
ROAD_Y_BOT_PX = int(HEIGHT * 0.95)
MARKER_A_X_PX = int(WIDTH * 0.30)   # left lane marker (world x = 0.0 m)
MARKER_B_X_PX = int(WIDTH * 0.70)   # right lane marker (world x = 3.5 m)
PIXELS_PER_METRE = (MARKER_B_X_PX - MARKER_A_X_PX) / LANE_WIDTH_M

VEHICLE_CENTER_X_PX = (MARKER_A_X_PX + MARKER_B_X_PX) // 2
VEHICLE_W_PX = int(VEHICLE_WIDTH_M * PIXELS_PER_METRE)
VEHICLE_H_PX = int(VEHICLE_HEIGHT_M * PIXELS_PER_METRE)


def vehicle_y_px(frame: int) -> int:
    """World Y position maps to screen Y (vehicle moves toward camera = downward)."""
    t = frame / FPS
    if frame < BRAKE_ONSET_FRAME:
        dist = ENTRY_SPEED_MS * t
    else:
        t_brake = (frame - BRAKE_ONSET_FRAME) / FPS
        v_at_onset = ENTRY_SPEED_MS
        dist = (ENTRY_SPEED_MS * (BRAKE_ONSET_FRAME / FPS)
                + v_at_onset * t_brake
                - 0.5 * DECELERATION_MS2 * t_brake ** 2)
        # clamp when stopped
        t_stop = v_at_onset / DECELERATION_MS2
        if t_brake >= t_stop:
            dist = (ENTRY_SPEED_MS * (BRAKE_ONSET_FRAME / FPS)
                    + v_at_onset * t_stop
                    - 0.5 * DECELERATION_MS2 * t_stop ** 2)
    # Map distance to screen Y: vehicle starts at top, moves down
    screen_fraction = min(dist / 60.0, 1.0)  # 60 m visible range
    return int(ROAD_Y_TOP_PX + screen_fraction * (ROAD_Y_BOT_PX - ROAD_Y_TOP_PX - VEHICLE_H_PX))


def vehicle_speed_ms(frame: int) -> float:
    if frame < BRAKE_ONSET_FRAME:
        return ENTRY_SPEED_MS
    t_brake = (frame - BRAKE_ONSET_FRAME) / FPS
    t_stop = ENTRY_SPEED_MS / DECELERATION_MS2
    return max(0.0, ENTRY_SPEED_MS - DECELERATION_MS2 * t_brake) if t_brake < t_stop else 0.0


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def make_png_frame(frame_index: int) -> bytes:
    """Generate a minimal synthetic PNG frame."""
    px = bytearray(WIDTH * HEIGHT * 3)
    # Road background — grey
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if ROAD_Y_TOP_PX <= y <= ROAD_Y_BOT_PX:
                v = 120
            else:
                v = 60  # sky
            offset = (y * WIDTH + x) * 3
            px[offset] = px[offset + 1] = px[offset + 2] = v
    # Lane markers — white vertical lines
    for y in range(ROAD_Y_TOP_PX, ROAD_Y_BOT_PX + 1):
        for mx in (MARKER_A_X_PX, MARKER_B_X_PX):
            for dx in range(-2, 3):
                if 0 <= mx + dx < WIDTH:
                    offset = (y * WIDTH + (mx + dx)) * 3
                    px[offset] = px[offset + 1] = px[offset + 2] = 255
    # Vehicle — blue rectangle
    vy = vehicle_y_px(frame_index)
    for y in range(max(0, vy), min(HEIGHT, vy + int(VEHICLE_H_PX))):
        for x in range(max(0, VEHICLE_CENTER_X_PX - VEHICLE_W_PX // 2),
                       min(WIDTH, VEHICLE_CENTER_X_PX + VEHICLE_W_PX // 2)):
            offset = (y * WIDTH + x) * 3
            px[offset] = 30
            px[offset + 1] = 80
            px[offset + 2] = 200
    # Build PNG
    raw_rows = bytearray()
    for y in range(HEIGHT):
        raw_rows.append(0)  # filter type None
        raw_rows.extend(px[y * WIDTH * 3:(y + 1) * WIDTH * 3])
    compressed = zlib.compress(bytes(raw_rows), 6)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", compressed)
        + _png_chunk(b"IEND", b"")
    )
    return png


def generate_clip() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frames_dir = OUTPUT_DIR / "_frames"
    frames_dir.mkdir(exist_ok=True)

    print(f"Writing {TOTAL_FRAMES} PNG frames to {frames_dir} ...")
    for f in range(TOTAL_FRAMES):
        if f % 25 == 0:
            print(f"  frame {f}/{TOTAL_FRAMES}", end="\r", flush=True)
        frame_path = frames_dir / f"frame_{f:04d}.png"
        frame_path.write_bytes(make_png_frame(f))
    print(f"\nAll frames written. Encoding → {CLIP_PATH}")

    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "23",
        str(CLIP_PATH),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # Clean up temporary frame files
    shutil.rmtree(frames_dir)
    print(f"✅ Clip written: {CLIP_PATH}")


def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_metadata() -> None:
    """Write ground-truth calibration and trajectory metadata."""
    track_points = []
    for f in range(TOTAL_FRAMES):
        vy = vehicle_y_px(f)
        gc_px_x = float(VEHICLE_CENTER_X_PX)
        gc_px_y = float(vy + int(VEHICLE_H_PX))
        # Ground-plane world coords from pixel inverse (ground truth)
        world_x = 0.0 + (gc_px_x - MARKER_A_X_PX) / PIXELS_PER_METRE  # horizontal position
        # world_y: derive from vehicle position (top of frame = far, bottom = near camera)
        # This is the KNOWN ground truth for the dynamics test.
        t = f / FPS
        if f < BRAKE_ONSET_FRAME:
            world_y = ENTRY_SPEED_MS * t
        else:
            t_b = (f - BRAKE_ONSET_FRAME) / FPS
            t_stop = ENTRY_SPEED_MS / DECELERATION_MS2
            if t_b < t_stop:
                world_y = (ENTRY_SPEED_MS * (BRAKE_ONSET_FRAME / FPS)
                           + ENTRY_SPEED_MS * t_b
                           - 0.5 * DECELERATION_MS2 * t_b ** 2)
            else:
                world_y = (ENTRY_SPEED_MS * (BRAKE_ONSET_FRAME / FPS)
                           + ENTRY_SPEED_MS * t_stop
                           - 0.5 * DECELERATION_MS2 * t_stop ** 2)
        track_points.append({
            "frame_index": f,
            "presentation_ts_s": round(t, 6),
            "gc_pixel_x": round(gc_px_x, 2),
            "gc_pixel_y": round(gc_px_y, 2),
            "world_x_m": round(world_x, 4),
            "world_y_m": round(world_y, 4),
            "speed_ms": round(vehicle_speed_ms(f), 4),
        })

    clip_sha256 = sha256_path(CLIP_PATH) if CLIP_PATH.exists() else "CLIP_NOT_YET_GENERATED"
    metadata = {
        "fixture_id": "g9_synthetic_v1",
        "description": "Synthetic G9 staged clip — straight road, 50 km/h braking to stop",
        "is_synthetic": True,
        "contains_real_footage": False,
        "consent_required": False,
        "clip_file": str(CLIP_PATH),
        "clip_sha256": clip_sha256,
        "video": {
            "width_px": WIDTH,
            "height_px": HEIGHT,
            "fps": FPS,
            "duration_s": DURATION_S,
            "total_frames": TOTAL_FRAMES,
            "codec": "h264",
        },
        "ground_truth_calibration": {
            "marker_a_pixel_x": MARKER_A_X_PX,
            "marker_a_pixel_y": (ROAD_Y_TOP_PX + ROAD_Y_BOT_PX) // 2,
            "marker_a_world_x_m": 0.0,
            "marker_a_world_y_m": 0.0,
            "marker_b_pixel_x": MARKER_B_X_PX,
            "marker_b_pixel_y": (ROAD_Y_TOP_PX + ROAD_Y_BOT_PX) // 2,
            "marker_b_world_x_m": LANE_WIDTH_M,
            "marker_b_world_y_m": 0.0,
            "known_distance_m": LANE_WIDTH_M,
            "pixels_per_metre": round(PIXELS_PER_METRE, 4),
            "note": "Two white lane markers at x=0.0 m and x=3.5 m; known distance = 3.5 m",
        },
        "ground_truth_dynamics": {
            "vehicle_category": "vehicle",
            "entry_speed_ms": ENTRY_SPEED_MS,
            "entry_speed_kmh": round(ENTRY_SPEED_MS * 3.6, 2),
            "brake_onset_frame": BRAKE_ONSET_FRAME,
            "brake_onset_s": round(BRAKE_ONSET_FRAME / FPS, 3),
            "deceleration_ms2": DECELERATION_MS2,
            "final_speed_ms": 0.0,
            "note": "Vehicle brakes at t=5.0 s, stops within 2.0 s. All values are ground truth.",
        },
        "g9_acceptance_thresholds": {
            "speed_estimate_error_max_kmh": 5.0,
            "speed_interval_must_contain_truth": True,
            "calibration_rmse_max_px": 2.0,
            "note": "If SAM credentials are absent, the system must refuse speed estimates (not fabricate them).",
        },
        "track_points_ground_truth": track_points,
    }
    META_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"✅ Metadata written: {META_PATH}")


if __name__ == "__main__":
    generate_clip()
    generate_metadata()
    print("\nG9 fixture ready. Run the full G9 suite with:")
    print("  python evaluation/runners/g9_full_runner.py --fixture fixtures/staged/g9_synthetic_v1/")
