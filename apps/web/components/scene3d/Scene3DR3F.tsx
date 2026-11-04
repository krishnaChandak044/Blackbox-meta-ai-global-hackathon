"use client";

import { Suspense, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Html } from "@react-three/drei";
import type { Scene3D as SceneData, SceneSample } from "@/lib/api";
import TrajectoryMesh from "./TrajectoryMesh";
import UncertaintyTube from "./UncertaintyTube";
import CameraFrustum from "./CameraFrustum";

interface Scene3DR3FProps {
  scene: SceneData;
  onToggle2DFallback?: () => void;
}

const COLORS = {
  observed: "#0284c7",
  fitted: "#8b5cf6",
  counterfactual: "#d97706",
  rival: "#e11d48",
};

interface PathLayer {
  key: string;
  label: string;
  color: string;
  dashed: boolean;
  isIllustrative: boolean;
  samples: SceneSample[];
}

export default function Scene3DR3F({ scene, onToggle2DFallback }: Scene3DR3FProps) {
  const [showFitted, setShowFitted] = useState(true);
  const [showCounterfactual, setShowCounterfactual] = useState(true);
  const [showRivals, setShowRivals] = useState(true);
  const [showUncertainty, setShowUncertainty] = useState(true);
  const [sampleIndex, setSampleIndex] = useState(0);
  const controlsRef = useRef<any>(null);

  // Group layers identically to the data contract
  const layers = useMemo<PathLayer[]>(() => {
    const result: PathLayer[] = scene.objects.map((obj) => ({
      key: `track:${obj.track_id}`,
      label: `Observed · ${obj.class} ${obj.track_id.slice(0, 6)}`,
      color: COLORS.observed,
      dashed: false,
      isIllustrative: false,
      samples: obj.samples,
    }));

    if (showFitted) {
      result.push(
        ...scene.fitted_paths.map((path) => ({
          key: `fit:${path.run_id ?? "fit"}`,
          label: `Fitted · ${path.run_id?.slice(0, 6) ?? "model"}`,
          color: COLORS.fitted,
          dashed: false,
          isIllustrative: false,
          samples: path.samples,
        }))
      );
    }

    if (showCounterfactual) {
      result.push(
        ...scene.counterfactual_paths.map((path) => ({
          key: `cf:${path.run_id ?? "cf"}`,
          label: "Counterfactual · illustrative",
          color: COLORS.counterfactual,
          dashed: true,
          isIllustrative: true,
          samples: path.samples,
        }))
      );
    }

    if (showRivals) {
      for (const search of scene.rival_paths) {
        for (const hyp of search.hypotheses) {
          result.push({
            key: `rival:${search.search_id}:${hyp.rank}`,
            label: `Rival ${hyp.rank} · ${hyp.disambiguation_status.replaceAll("_", " ")}`,
            color: COLORS.rival,
            dashed: true,
            isIllustrative: true,
            samples: hyp.samples,
          });
        }
      }
    }

    return result;
  }, [scene, showFitted, showCounterfactual, showRivals]);

  // Unified chronological timeline
  const timeline = useMemo(() => {
    const map = new Map<string, SceneSample>();
    for (const obj of scene.objects) {
      for (const s of obj.samples) {
        map.set(`${s.frame_index}:${s.presentation_ts_s}`, s);
      }
    }
    return [...map.values()].sort((a, b) => a.presentation_ts_s - b.presentation_ts_s);
  }, [scene]);

  const selectedSample = timeline[Math.min(sampleIndex, Math.max(0, timeline.length - 1))];

  // Calculate bounding box and centering
  const bounds = useMemo(() => {
    const all = layers
      .flatMap((l) => l.samples)
      .filter((s) => Number.isFinite(s.position_m.x) && Number.isFinite(s.position_m.y));

    if (!all.length) {
      return { centerX: 0, centerY: 0, extent: 15 };
    }

    const xs = all.map((s) => s.position_m.x);
    const ys = all.map((s) => s.position_m.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);

    return {
      centerX: (minX + maxX) / 2,
      centerY: (minY + maxY) / 2,
      extent: Math.max(maxX - minX, maxY - minY, 10),
    };
  }, [layers]);

  const handleResetView = () => {
    if (controlsRef.current) {
      controlsRef.current.target.set(bounds.centerX, 0, bounds.centerY);
      controlsRef.current.object.position.set(
        bounds.centerX,
        bounds.extent * 1.2,
        bounds.centerY + bounds.extent * 1.4
      );
      controlsRef.current.update();
    }
  };

  const handleSelectSample = (sample: SceneSample) => {
    const idx = timeline.findIndex(
      (s) => s.frame_index === sample.frame_index && Math.abs(s.presentation_ts_s - sample.presentation_ts_s) < 1e-4
    );
    if (idx !== -1) {
      setSampleIndex(idx);
    }
  };

  return (
    <div className="scene3d-shell" style={{ display: "flex", flexDirection: "column", width: "100%", position: "relative" }}>
      {/* Synthetic Banner */}
      <div className="scene3d-banner" role="note" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>{scene.synthetic_view_label}</span>
        <span style={{ fontSize: "11px", opacity: 0.85, fontWeight: 500 }}>
          WebGL 3D Accelerated
        </span>
      </div>

      {/* Toolbar */}
      <div className="scene3d-toolbar" aria-label="Scene controls">
        <button className="btn btn-secondary btn-sm" onClick={handleResetView}>
          Reset 3D camera
        </button>
        <label className="scene-toggle">
          <input
            type="checkbox"
            checked={showFitted}
            onChange={(e) => setShowFitted(e.target.checked)}
          />{" "}
          Fitted paths
        </label>
        <label className="scene-toggle">
          <input
            type="checkbox"
            checked={showCounterfactual}
            onChange={(e) => setShowCounterfactual(e.target.checked)}
          />{" "}
          Counterfactuals
        </label>
        <label className="scene-toggle">
          <input
            type="checkbox"
            checked={showRivals}
            onChange={(e) => setShowRivals(e.target.checked)}
          />{" "}
          Rivals
        </label>
        <label className="scene-toggle">
          <input
            type="checkbox"
            checked={showUncertainty}
            onChange={(e) => setShowUncertainty(e.target.checked)}
          />{" "}
          Uncertainty tubes
        </label>

        {onToggle2DFallback && (
          <button
            className="btn btn-outline btn-sm"
            onClick={onToggle2DFallback}
            style={{ marginLeft: "auto", fontSize: "11px" }}
            title="Switch to 2D Canvas fallback projection"
          >
            Switch to 2D Fallback
          </button>
        )}
      </div>

      {/* 3D WebGL Canvas Container */}
      <div
        className="scene3d-canvas-wrap"
        style={{
          width: "100%",
          height: "520px",
          position: "relative",
          background: "#f8fafc",
          borderRadius: "6px",
          overflow: "hidden",
        }}
      >
        <Canvas
          camera={{
            position: [bounds.centerX, bounds.extent * 1.2, bounds.centerY + bounds.extent * 1.4],
            fov: 42,
            near: 0.1,
            far: Math.max(500, bounds.extent * 20),
          }}
          style={{ width: "100%", height: "100%" }}
        >
          <ambientLight intensity={0.9} />
          <directionalLight position={[bounds.centerX + 20, 40, bounds.centerY + 30]} intensity={1.1} />
          <directionalLight position={[bounds.centerX - 20, 20, bounds.centerY - 20]} intensity={0.4} />

          {/* Calibrated Ground Plane Grid */}
          <gridHelper
            args={[
              Math.max(30, Math.ceil(bounds.extent * 2.5)),
              Math.max(20, Math.ceil(bounds.extent / 2)),
              "#94a3b8",
              "#e2e8f0",
            ]}
            position={[bounds.centerX, 0, bounds.centerY]}
          />

          {/* Coordinate Axes at Origin: X=Red, Y=Green (Height), Z=Blue (Lateral) */}
          <axesHelper args={[Math.max(3, bounds.extent * 0.15)]} position={[0, 0.01, 0]} />

          <Suspense fallback={null}>
            {/* Trajectory Layers */}
            {layers.map((layer) => (
              <group key={layer.key}>
                <TrajectoryMesh
                  samples={layer.samples}
                  color={layer.color}
                  dashed={layer.dashed}
                  lineWidth={layer.key.startsWith("track:") ? 3.5 : 2.5}
                  label={layer.label}
                  isIllustrative={layer.isIllustrative}
                  onSelectSample={handleSelectSample}
                  selectedSample={selectedSample}
                />
                {showUncertainty && (
                  <UncertaintyTube
                    samples={layer.samples}
                    color={layer.color}
                  />
                )}
              </group>
            ))}

            {/* Selected Sample Current Frame Vehicle Marker */}
            {selectedSample && (
              <group
                position={[
                  selectedSample.position_m.x,
                  (selectedSample.position_m.z ?? 0) + 0.12,
                  selectedSample.position_m.y,
                ]}
              >
                {/* 3D Vehicle representation cursor */}
                <mesh>
                  <boxGeometry args={[1.8, 0.7, 0.9]} />
                  <meshStandardMaterial color="#0f172a" roughness={0.2} metalness={0.5} />
                </mesh>
                <mesh position={[0, -0.1, 0]}>
                  <ringGeometry args={[0.8, 1.1, 24]} />
                  <meshBasicMaterial color="#10b981" side={THREE.DoubleSide} transparent opacity={0.8} />
                </mesh>
                <Html position={[0, 1.0, 0]} center distanceFactor={14}>
                  <div
                    style={{
                      background: "rgba(15, 23, 42, 0.92)",
                      color: "#38bdf8",
                      border: "1px solid #0284c7",
                      borderRadius: "4px",
                      padding: "2px 6px",
                      fontSize: "11px",
                      fontWeight: 600,
                      whiteSpace: "nowrap",
                      pointerEvents: "none",
                    }}
                  >
                    Vehicle · {selectedSample.presentation_ts_s.toFixed(3)}s
                  </div>
                </Html>
              </group>
            )}

            {/* Camera Frustum (only rendered if pose is verified and available) */}
            <CameraFrustum pose={scene.camera_pose as any} />
          </Suspense>

          <OrbitControls
            ref={controlsRef}
            target={[bounds.centerX, 0, bounds.centerY]}
            makeDefault
            enableDamping
            dampingFactor={0.05}
            maxPolarAngle={Math.PI / 2 - 0.02} // Restrict camera from going underneath ground plane
            minDistance={1.0}
            maxDistance={bounds.extent * 15}
          />
        </Canvas>

        {/* Forensic Camera Pose unknown badge */}
        {scene.camera_pose.status !== "available" && (
          <div
            className="scene3d-camera-unknown"
            style={{
              position: "absolute",
              bottom: "12px",
              right: "12px",
              background: "rgba(15, 23, 42, 0.8)",
              color: "#cbd5e1",
              fontSize: "11px",
              padding: "4px 8px",
              borderRadius: "4px",
              pointerEvents: "none",
            }}
          >
            Camera pose unknown · no camera frustum shown
          </div>
        )}

        {/* Orbit / Pan UX Helper */}
        <div
          style={{
            position: "absolute",
            top: "12px",
            right: "12px",
            background: "rgba(255, 255, 255, 0.85)",
            color: "#475569",
            fontSize: "10px",
            padding: "3px 7px",
            borderRadius: "4px",
            pointerEvents: "none",
            border: "1px solid #e2e8f0",
          }}
        >
          Left-drag: Orbit · Right-drag: Pan · Scroll: Zoom
        </div>

        {/* Ground Plane Annotation */}
        <div
          style={{
            position: "absolute",
            bottom: "12px",
            left: "12px",
            background: "rgba(255, 255, 255, 0.85)",
            color: "#64748b",
            fontSize: "11px",
            padding: "2px 6px",
            borderRadius: "4px",
            pointerEvents: "none",
          }}
        >
          Ground plane · z = 0 m (SI Metres)
        </div>
      </div>

      {/* Trajectory Legend */}
      <div className="scene3d-legend" style={{ marginTop: "12px" }}>
        {layers.map((layer) => (
          <span key={layer.key}>
            <i style={{ background: layer.color }} />
            {layer.label}
          </span>
        ))}
      </div>

      {/* Timeline Scrubber */}
      {timeline.length > 0 && (
        <div className="scene3d-timebar" style={{ marginTop: "12px" }}>
          <label htmlFor="scene-time">Source track time</label>
          <input
            id="scene-time"
            type="range"
            min="0"
            max={timeline.length - 1}
            value={Math.min(sampleIndex, timeline.length - 1)}
            onChange={(e) => setSampleIndex(Number(e.target.value))}
          />
          <span>
            Frame {selectedSample?.frame_index} · {selectedSample?.presentation_ts_s.toFixed(3)} s
          </span>
        </div>
      )}

      {/* Forensic Provenance Details */}
      <div className="scene3d-provenance" style={{ marginTop: "12px" }}>
        <span>Calibration: {scene.coordinate_system.calibration_fit_id ?? "unavailable"}</span>
        <span>Units: {scene.coordinate_system.units}</span>
        <span>Origin: {scene.coordinate_system.origin}</span>
        <span>Source SHA-256: {scene.media_sha256.slice(0, 14)}…</span>
      </div>

      {/* Limitations Disclosures */}
      <ul className="scene3d-limitations" style={{ marginTop: "12px" }}>
        {scene.limitations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
