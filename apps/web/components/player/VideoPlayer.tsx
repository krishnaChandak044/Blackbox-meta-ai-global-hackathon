"use client";

/**
 * VideoPlayer — frame-accurate HTML5 player with trajectory overlay support.
 *
 * Props:
 *   src          — video URL (local blob or server path)
 *   onFrameChange — called every animation frame with the current frame index
 *   fps          — frames per second (from probe metadata)
 *   overlay      — optional SVG element rendered on top of the video
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface VideoPlayerProps {
  src: string;
  fps: number;
  onFrameChange?: (frameIndex: number, tsSeconds: number) => void;
  overlay?: React.ReactNode;
  height?: number;
}

export default function VideoPlayer({
  src,
  fps,
  onFrameChange,
  overlay,
  height = 400,
}: VideoPlayerProps) {
  const videoRef  = useRef<HTMLVideoElement>(null);
  const rafRef    = useRef<number>(0);
  const [playing, setPlaying]   = useState(false);
  const [current, setCurrent]   = useState(0);   // seconds
  const [duration, setDuration] = useState(0);
  const [frame, setFrame]       = useState(0);

  // ── Sync frame counter via requestAnimationFrame ───────────────────────────
  const tick = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    const ts = v.currentTime;
    const fi = Math.round(ts * fps);
    setCurrent(ts);
    setFrame(fi);
    onFrameChange?.(fi, ts);
    if (!v.paused) rafRef.current = requestAnimationFrame(tick);
  }, [fps, onFrameChange]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onLoaded = () => setDuration(v.duration);
    const onPlay   = () => { rafRef.current = requestAnimationFrame(tick); setPlaying(true); };
    const onPause  = () => { cancelAnimationFrame(rafRef.current); setPlaying(false); };
    const onSeeked = () => tick();
    v.addEventListener("loadedmetadata", onLoaded);
    v.addEventListener("play",   onPlay);
    v.addEventListener("pause",  onPause);
    v.addEventListener("seeked", onSeeked);
    return () => {
      v.removeEventListener("loadedmetadata", onLoaded);
      v.removeEventListener("play",   onPlay);
      v.removeEventListener("pause",  onPause);
      v.removeEventListener("seeked", onSeeked);
      cancelAnimationFrame(rafRef.current);
    };
  }, [tick]);

  // ── Seek by clicking the progress bar ─────────────────────────────────────
  const seekTo = (e: React.MouseEvent<HTMLDivElement>) => {
    const v = videoRef.current;
    if (!v || !duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    v.currentTime = frac * duration;
  };

  // ── Step one frame ─────────────────────────────────────────────────────────
  const stepFrame = (dir: -1 | 1) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Math.max(0, Math.min(duration, v.currentTime + dir / fps));
  };

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    v.paused ? v.play() : v.pause();
  };

  const fmtTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = (s % 60).toFixed(2).padStart(5, "0");
    return `${m}:${sec}`;
  };

  return (
    <div className="video-player-root">
      <style>{`
        .video-player-root {
          background: #111;
          border-radius: var(--radius-lg);
          overflow: hidden;
          position: relative;
          user-select: none;
        }
        .video-container {
          position: relative;
          width: 100%;
        }
        .video-container video {
          width: 100%;
          display: block;
        }
        .video-overlay {
          position: absolute;
          inset: 0;
          pointer-events: none;
        }
        .video-controls {
          background: rgba(26,32,44,0.92);
          padding: var(--space-3) var(--space-4);
          display: flex;
          flex-direction: column;
          gap: var(--space-2);
        }
        .progress-track {
          height: 5px;
          background: rgba(255,255,255,0.15);
          border-radius: var(--radius-pill);
          cursor: pointer;
          position: relative;
          transition: height var(--duration-sm);
        }
        .progress-track:hover { height: 7px; }
        .progress-fill {
          height: 100%;
          background: var(--sage-mid);
          border-radius: var(--radius-pill);
          pointer-events: none;
        }
        .ctrl-row {
          display: flex;
          align-items: center;
          gap: var(--space-3);
        }
        .ctrl-btn {
          background: none;
          border: none;
          color: rgba(255,255,255,0.8);
          font-size: 18px;
          cursor: pointer;
          padding: 2px 6px;
          border-radius: var(--radius-sm);
          transition: background var(--duration-sm);
          line-height: 1;
        }
        .ctrl-btn:hover { background: rgba(255,255,255,0.1); color: #fff; }
        .timecode {
          font-family: var(--font-mono);
          font-size: 12px;
          color: rgba(255,255,255,0.6);
          letter-spacing: 0.04em;
        }
        .frame-badge {
          font-family: var(--font-mono);
          font-size: 11px;
          background: rgba(168,197,160,0.2);
          color: var(--sage-mid);
          padding: 1px 7px;
          border-radius: var(--radius-pill);
          margin-left: auto;
        }
      `}</style>

      <div className="video-container" style={{ minHeight: height }}>
        <video
          ref={videoRef}
          src={src}
          crossOrigin="use-credentials"
          style={{ maxHeight: height, objectFit: "contain", width: "100%" }}
          preload="metadata"
        />
        {overlay && (
          <div className="video-overlay">
            {overlay}
          </div>
        )}
      </div>

      <div className="video-controls">
        {/* Progress */}
        <div className="progress-track" onClick={seekTo} role="slider" aria-label="Seek"
          aria-valuemin={0} aria-valuemax={Math.max(0, duration)} aria-valuenow={current}
          tabIndex={0} onKeyDown={e => {
            if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
              e.preventDefault(); stepFrame(e.key === "ArrowLeft" ? -1 : 1);
            }
          }}>
          <div
            className="progress-fill"
            style={{ width: duration ? `${(current / duration) * 100}%` : "0%" }}
          />
        </div>

        {/* Controls row */}
        <div className="ctrl-row">
          <button className="ctrl-btn" onClick={() => stepFrame(-1)} aria-label="Previous frame">◀</button>
          <button className="ctrl-btn" onClick={togglePlay} aria-label={playing ? "Pause" : "Play"} style={{ fontSize: 22 }}>
            {playing ? "⏸" : "▶"}
          </button>
          <button className="ctrl-btn" onClick={() => stepFrame(1)} aria-label="Next frame">▶</button>

          <span className="timecode">{fmtTime(current)} / {fmtTime(duration)}</span>
          <span className="frame-badge">f {frame}</span>
        </div>
      </div>
    </div>
  );
}
