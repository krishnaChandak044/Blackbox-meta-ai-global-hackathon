"use client";

import { useMemo, useState } from "react";
import * as THREE from "three";
import { Html, Line } from "@react-three/drei";
import type { SceneSample } from "@/lib/api";

interface TrajectoryMeshProps {
  samples: SceneSample[];
  color: string;
  dashed?: boolean;
  lineWidth?: number;
  label?: string;
  isIllustrative?: boolean;
  onSelectSample?: (sample: SceneSample) => void;
  selectedSample?: SceneSample | null;
}

export default function TrajectoryMesh({
  samples,
  color,
  dashed = false,
  lineWidth = 3,
  label,
  isIllustrative = false,
  onSelectSample,
  selectedSample,
}: TrajectoryMeshProps) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const validSamples = useMemo(() => {
    return samples.filter(
      (s) =>
        Number.isFinite(s.position_m.x) &&
        Number.isFinite(s.position_m.y)
    );
  }, [samples]);

  const points3D = useMemo<[number, number, number][]>(() => {
    return validSamples.map((s) => [
      s.position_m.x,
      s.position_m.z ?? 0,
      s.position_m.y,
    ]);
  }, [validSamples]);

  const midPoint = useMemo<[number, number, number] | null>(() => {
    if (points3D.length < 2) return null;
    const midIdx = Math.floor(points3D.length / 2);
    const p = points3D[midIdx];
    return [p[0], p[1] + 0.4, p[2]];
  }, [points3D]);

  if (points3D.length < 2) return null;

  const firstPt = points3D[0];
  const lastPt = points3D[points3D.length - 1];

  return (
    <group>
      {/* 3D Path Line */}
      <Line
        points={points3D}
        color={color}
        lineWidth={lineWidth}
        dashed={dashed}
        dashSize={0.6}
        gapSize={0.4}
      />

      {/* Origin & Terminal Point Spheres */}
      <mesh position={firstPt}>
        <sphereGeometry args={[0.16, 16, 16]} />
        <meshStandardMaterial color={color} roughness={0.3} />
      </mesh>
      <mesh position={lastPt}>
        <sphereGeometry args={[0.16, 16, 16]} />
        <meshStandardMaterial color={color} roughness={0.3} />
      </mesh>

      {/* Floating illustrative badge for simulated/counterfactual/rival trajectories */}
      {isIllustrative && midPoint && (
        <Html position={midPoint} center distanceFactor={15}>
          <div
            style={{
              background: "rgba(24, 37, 42, 0.88)",
              color: "#f59e0b",
              border: "1px solid rgba(245, 158, 11, 0.4)",
              borderRadius: "4px",
              padding: "2px 6px",
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.05em",
              pointerEvents: "none",
              whiteSpace: "nowrap",
              boxShadow: "0 2px 6px rgba(0,0,0,0.25)",
            }}
          >
            ILLUSTRATIVE
          </div>
        </Html>
      )}

      {/* Clickable interactive waypoint markers */}
      {validSamples.map((s, idx) => {
        const isSelected =
          selectedSample &&
          selectedSample.frame_index === s.frame_index &&
          Math.abs(selectedSample.presentation_ts_s - s.presentation_ts_s) < 1e-4;
        const isHovered = hoveredIdx === idx;
        const pt = points3D[idx];

        return (
          <mesh
            key={`pt-${s.frame_index}-${idx}`}
            position={pt}
            onClick={(e) => {
              e.stopPropagation();
              onSelectSample?.(s);
            }}
            onPointerOver={(e) => {
              e.stopPropagation();
              setHoveredIdx(idx);
            }}
            onPointerOut={() => setHoveredIdx(null)}
          >
            <sphereGeometry args={[isSelected ? 0.24 : isHovered ? 0.18 : 0.08, 12, 12]} />
            <meshStandardMaterial
              color={isSelected ? "#10b981" : isHovered ? "#38bdf8" : color}
              emissive={isSelected ? "#059669" : isHovered ? "#0284c7" : "#000000"}
              emissiveIntensity={isSelected || isHovered ? 0.6 : 0}
            />
            {(isHovered || isSelected) && (
              <Html distanceFactor={12} position={[0, 0.35, 0]} center>
                <div
                  style={{
                    background: "#0f172a",
                    color: "#f8fafc",
                    padding: "3px 8px",
                    borderRadius: "4px",
                    fontSize: "11px",
                    whiteSpace: "nowrap",
                    boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                    pointerEvents: "none",
                  }}
                >
                  Frame {s.frame_index} · {s.presentation_ts_s.toFixed(3)}s
                </div>
              </Html>
            )}
          </mesh>
        );
      })}
    </group>
  );
}

