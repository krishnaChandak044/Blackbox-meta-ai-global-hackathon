"use client";

import { useMemo } from "react";
import * as THREE from "three";
import type { SceneSample } from "@/lib/api";

interface UncertaintyTubeProps {
  samples: SceneSample[];
  color?: string;
  defaultSigmaM?: number;
}

/**
 * Renders an uncertainty tube / envelope around a series of 3D trajectory points.
 * Radius is driven by the sample's localisation uncertainty (sigma).
 */
export default function UncertaintyTube({
  samples,
  color = "#8c78b8",
  defaultSigmaM = 0.3,
}: UncertaintyTubeProps) {
  const geometry = useMemo(() => {
    const valid = samples.filter(
      (s) =>
        Number.isFinite(s.position_m.x) &&
        Number.isFinite(s.position_m.y)
    );

    if (valid.length < 2) return null;

    // Convert samples to 3D vectors: X -> X, Z -> Y (height), Y -> Z
    const points = valid.map(
      (s) => new THREE.Vector3(s.position_m.x, s.position_m.z ?? 0, s.position_m.y)
    );

    // Remove consecutive duplicates which cause NaN in curve tangents
    const filteredPoints: THREE.Vector3[] = [];
    for (const pt of points) {
      if (
        filteredPoints.length === 0 ||
        pt.distanceTo(filteredPoints[filteredPoints.length - 1]) > 1e-4
      ) {
        filteredPoints.push(pt);
      }
    }

    if (filteredPoints.length < 2) return null;

    // Average sigma for tube radius
    const sigmas = valid.map((s) => s.uncertainty_sigma_m ?? defaultSigmaM);
    const avgSigma = sigmas.reduce((a, b) => a + b, 0) / sigmas.length;
    const radius = Math.max(0.08, Math.min(avgSigma * 1.645, 1.5)); // 90% confidence radius bound

    const curve = new THREE.CatmullRomCurve3(filteredPoints, false, "centripetal");
    const segments = Math.max(20, Math.min(filteredPoints.length * 4, 120));
    return new THREE.TubeGeometry(curve, segments, radius, 8, false);
  }, [samples, defaultSigmaM]);

  if (!geometry) return null;

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial
        color={color}
        transparent
        opacity={0.22}
        roughness={0.6}
        metalness={0.1}
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}
