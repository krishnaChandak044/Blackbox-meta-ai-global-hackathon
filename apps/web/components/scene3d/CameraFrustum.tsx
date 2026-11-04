"use client";

import { useMemo } from "react";
import * as THREE from "three";

interface CameraPose {
  status: string;
  reason?: string;
  position_m?: { x: number; y: number; z: number };
  direction?: { x: number; y: number; z: number };
  fov_deg?: number;
  near_m?: number;
  far_m?: number;
}

interface CameraFrustumProps {
  pose?: CameraPose | null;
}

/**
 * Renders a camera frustum pyramid ONLY when camera pose is verified and available.
 * If camera pose is unknown, returns null (ensuring no misleading frustum is displayed).
 */
export default function CameraFrustum({ pose }: CameraFrustumProps) {
  const lineGeometry = useMemo(() => {
    if (!pose || pose.status !== "available" || !pose.position_m) {
      return null;
    }

    const eye = new THREE.Vector3(pose.position_m.x, pose.position_m.z ?? 1.5, pose.position_m.y);
    const dir = new THREE.Vector3(
      pose.direction?.x ?? 0,
      pose.direction?.z ?? 0,
      pose.direction?.y ?? 1
    ).normalize();

    const far = pose.far_m ?? 15.0;
    const fov = ((pose.fov_deg ?? 60) * Math.PI) / 180;
    const halfH = far * Math.tan(fov / 2);
    const halfW = halfH * (16 / 9);

    const right = new THREE.Vector3().crossVectors(dir, new THREE.Vector3(0, 1, 0)).normalize();
    const up = new THREE.Vector3().crossVectors(right, dir).normalize();

    const centerFar = eye.clone().addScaledVector(dir, far);
    const c1 = centerFar.clone().addScaledVector(right, -halfW).addScaledVector(up, halfH);
    const c2 = centerFar.clone().addScaledVector(right, halfW).addScaledVector(up, halfH);
    const c3 = centerFar.clone().addScaledVector(right, halfW).addScaledVector(up, -halfH);
    const c4 = centerFar.clone().addScaledVector(right, -halfW).addScaledVector(up, -halfH);

    // Wireframe pyramid edges
    const points = [
      eye, c1, eye, c2, eye, c3, eye, c4,
      c1, c2, c2, c3, c3, c4, c4, c1,
    ];

    return new THREE.BufferGeometry().setFromPoints(points);
  }, [pose]);

  if (!lineGeometry) return null;

  return (
    <lineSegments geometry={lineGeometry}>
      <lineBasicMaterial color="#3b82f6" linewidth={1.5} transparent opacity={0.6} />
    </lineSegments>
  );
}

