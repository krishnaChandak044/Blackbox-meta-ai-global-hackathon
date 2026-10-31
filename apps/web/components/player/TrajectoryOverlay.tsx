"use client";

/**
 * TrajectoryOverlay — SVG layer rendered on top of VideoPlayer.
 *
 * Renders:
 *   - Bounding boxes for all tracks at the current frame
 *   - Ground-contact point (bottom-centre of bbox)
 *   - Historical path polyline (last N frames)
 *   - Uncertainty circle (1-sigma radius projected to pixels)
 *   - Human-confirmed badge
 */

import type { TrackDetail, TrackPointOut } from "@/lib/api";

const CATEGORY_COLOR: Record<string, string> = {
  vehicle:    "#7BAE7F",   // sage
  pedestrian: "#6BA3BF",   // sky
  cyclist:    "#C9A96E",   // sand
  unknown:    "#9B8EC4",   // lavender
};

const HISTORY_FRAMES = 60;  // how many past frames to draw the path

interface Props {
  tracks: TrackDetail[];
  currentFrame: number;
  videoWidth: number;
  videoHeight: number;
  /** pixels per world unit — used to render sigma circles when world data exists */
  pixelsPerMetre?: number;
}

export default function TrajectoryOverlay({
  tracks,
  currentFrame,
  videoWidth,
  videoHeight,
  pixelsPerMetre,
}: Props) {
  if (!videoWidth || !videoHeight) return null;

  return (
    <svg
      viewBox={`0 0 ${videoWidth} ${videoHeight}`}
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
      aria-label="Trajectory overlay"
    >
      <defs>
        <marker id="arrow" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
          <path d="M0,0 L0,6 L6,3 z" fill="rgba(255,255,255,0.6)" />
        </marker>
      </defs>

      {tracks.map((track) => {
        const color = CATEGORY_COLOR[track.category] ?? CATEGORY_COLOR.unknown;

        // Collect historical points for path
        const historyPoints = track.points.filter(
          (p) => p.frame_index >= currentFrame - HISTORY_FRAMES && p.frame_index <= currentFrame
        );

        // Current frame point
        const current = track.points.find((p) => p.frame_index === currentFrame);

        return (
          <g key={track.id}>
            {/* ── History path ──────────────────────────────────────────────── */}
            {historyPoints.length > 1 && (
              <polyline
                points={historyPoints
                  .map((p) => `${p.gc_pixel_x},${p.gc_pixel_y}`)
                  .join(" ")}
                fill="none"
                stroke={color}
                strokeWidth={1.5}
                strokeOpacity={0.5}
                strokeDasharray="4 3"
              />
            )}

            {/* ── Ground contact dots (history) ─────────────────────────────── */}
            {historyPoints.map((p) => (
              <circle
                key={p.frame_index}
                cx={p.gc_pixel_x}
                cy={p.gc_pixel_y}
                r={2}
                fill={color}
                fillOpacity={0.3 + 0.7 * ((p.frame_index - (currentFrame - HISTORY_FRAMES)) / HISTORY_FRAMES)}
              />
            ))}

            {/* ── Current frame bbox + annotations ──────────────────────────── */}
            {current && (
              <>
                {/* Bounding box */}
                <rect
                  x={current.bbox_x_min}
                  y={current.bbox_y_min}
                  width={current.bbox_x_max - current.bbox_x_min}
                  height={current.bbox_y_max - current.bbox_y_min}
                  fill="none"
                  stroke={color}
                  strokeWidth={current.is_human_corrected ? 2.5 : 1.5}
                  strokeDasharray={current.is_interpolated ? "6 3" : undefined}
                  rx={3}
                />

                {/* Category label */}
                <rect
                  x={current.bbox_x_min}
                  y={current.bbox_y_min - 18}
                  width={72}
                  height={16}
                  fill={color}
                  fillOpacity={0.85}
                  rx={3}
                />
                <text
                  x={current.bbox_x_min + 4}
                  y={current.bbox_y_min - 5}
                  fontSize={10}
                  fill="white"
                  fontFamily="Inter, sans-serif"
                  fontWeight={500}
                >
                  {track.category} {(current.detection_confidence * 100).toFixed(0)}%
                </text>

                {/* Ground contact */}
                <circle
                  cx={current.gc_pixel_x}
                  cy={current.gc_pixel_y}
                  r={4}
                  fill={color}
                  stroke="white"
                  strokeWidth={1.5}
                />

                {/* Uncertainty circle (if world data + pixel scale available) */}
                {current.sigma_m != null && pixelsPerMetre != null && (
                  <circle
                    cx={current.gc_pixel_x}
                    cy={current.gc_pixel_y}
                    r={current.sigma_m * pixelsPerMetre}
                    fill="none"
                    stroke={color}
                    strokeWidth={1}
                    strokeOpacity={0.4}
                    strokeDasharray="3 2"
                  />
                )}

                {/* Human-confirmed checkmark */}
                {track.is_human_confirmed && (
                  <text
                    x={current.bbox_x_max - 14}
                    y={current.bbox_y_min - 4}
                    fontSize={12}
                    aria-label="Human confirmed"
                  >
                    ✓
                  </text>
                )}

                {/* Human-corrected indicator */}
                {current.is_human_corrected && (
                  <text
                    x={current.bbox_x_min + 2}
                    y={current.bbox_y_max + 12}
                    fontSize={9}
                    fill={color}
                    fontFamily="Inter, sans-serif"
                  >
                    ✎ corrected
                  </text>
                )}
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}
