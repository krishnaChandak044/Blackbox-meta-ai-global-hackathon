"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Scene3D as SceneData, SceneSample } from "@/lib/api";

type PathLayer = { key: string; label: string; color: string; dashed: boolean; samples: SceneSample[] };

const COLORS = { observed: "#327f93", fitted: "#8c78b8", counterfactual: "#bd8a3b", rival: "#bc6565" };

export default function Scene3D({ scene }: { scene: SceneData }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [azimuth, setAzimuth] = useState(-0.55);
  const [elevation, setElevation] = useState(0.48);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [showFitted, setShowFitted] = useState(true);
  const [showCounterfactual, setShowCounterfactual] = useState(true);
  const [showRivals, setShowRivals] = useState(true);
  const [sampleIndex, setSampleIndex] = useState(0);
  const drag = useRef<{ x: number; y: number; azimuth: number; elevation: number; panX: number; panY: number; mode: "orbit" | "pan" } | null>(null);

  const layers = useMemo<PathLayer[]>(() => {
    const result: PathLayer[] = scene.objects.map((object) => ({ key: `track:${object.track_id}`, label: `Observed · ${object.class} ${object.track_id.slice(0, 6)}`, color: COLORS.observed, dashed: false, samples: object.samples }));
    if (showFitted) result.push(...scene.fitted_paths.map((path) => ({ key: `fit:${path.run_id}`, label: `Fitted · ${path.run_id?.slice(0, 6)}`, color: COLORS.fitted, dashed: false, samples: path.samples })));
    if (showCounterfactual) result.push(...scene.counterfactual_paths.map((path) => ({ key: `cf:${path.run_id}`, label: "Counterfactual · illustrative", color: COLORS.counterfactual, dashed: true, samples: path.samples })));
    if (showRivals) for (const search of scene.rival_paths) for (const hypothesis of search.hypotheses) {
      result.push({ key: `rival:${search.search_id}:${hypothesis.rank}`, label: `Rival ${hypothesis.rank} · ${hypothesis.disambiguation_status.replaceAll("_", " ")}`, color: COLORS.rival, dashed: true, samples: hypothesis.samples });
    }
    return result;
  }, [scene, showFitted, showCounterfactual, showRivals]);

  const timeline = useMemo(() => {
    const unique = new Map<string, SceneSample>();
    for (const object of scene.objects) for (const sample of object.samples) unique.set(`${sample.frame_index}:${sample.presentation_ts_s}`, sample);
    return [...unique.values()].sort((a, b) => a.presentation_ts_s - b.presentation_ts_s);
  }, [scene]);
  const selected = timeline[Math.min(sampleIndex, Math.max(0, timeline.length - 1))];

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const parent = canvas.parentElement;
    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      const width = rect.width, height = rect.height;
      context.clearRect(0, 0, width, height);
      context.fillStyle = "#f7f8f8";
      context.fillRect(0, 0, width, height);

      const all = layers.flatMap((layer) => layer.samples).filter((sample) => Number.isFinite(sample.position_m.x) && Number.isFinite(sample.position_m.y));
      if (!all.length) {
        context.fillStyle = "#64748b"; context.font = "14px sans-serif"; context.textAlign = "center";
        context.fillText("No calibrated trajectory samples are available for this scene.", width / 2, height / 2);
        return;
      }
      const xs = all.map((item) => item.position_m.x), ys = all.map((item) => item.position_m.y);
      const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
      const centerX = (minX + maxX) / 2, centerY = (minY + maxY) / 2;
      const extent = Math.max(maxX - minX, maxY - minY, 5);
      const scale = Math.min(width, height) * 0.72 / extent * zoom;
      const cosine = Math.cos(azimuth), sine = Math.sin(azimuth), pitch = Math.max(0.18, Math.min(1.2, elevation));
      const project = (x: number, y: number, z = 0) => {
        const dx = x - centerX, dy = y - centerY;
        const rotatedX = dx * cosine - dy * sine;
        const rotatedY = dx * sine + dy * cosine;
        return { x: width / 2 + pan.x + rotatedX * scale, y: height / 2 + pan.y - (rotatedY * Math.sin(pitch) - z * Math.cos(pitch)) * scale };
      };

      // Ground plane guide; these are scene coordinates, not inferred road geometry.
      context.strokeStyle = "#e2e8e9"; context.lineWidth = 1;
      const gridStep = Math.pow(10, Math.floor(Math.log10(extent / 5 || 1)));
      for (let offset = -2; offset <= 2; offset++) {
        const delta = offset * gridStep * 2;
        const a = project(centerX - extent, centerY + delta), b = project(centerX + extent, centerY + delta);
        const c = project(centerX + delta, centerY - extent), d = project(centerX + delta, centerY + extent);
        context.beginPath(); context.moveTo(a.x, a.y); context.lineTo(b.x, b.y); context.stroke();
        context.beginPath(); context.moveTo(c.x, c.y); context.lineTo(d.x, d.y); context.stroke();
      }

      for (const layer of layers) {
        if (layer.samples.length < 1) continue;
        context.strokeStyle = layer.color; context.lineWidth = layer.key.startsWith("track:") ? 3 : 2.2;
        context.setLineDash(layer.dashed ? [7, 6] : []);
        context.beginPath();
        layer.samples.forEach((sample, index) => {
          const point = project(sample.position_m.x, sample.position_m.y, sample.position_m.z);
          if (!index) context.moveTo(point.x, point.y); else context.lineTo(point.x, point.y);
        });
        context.stroke(); context.setLineDash([]);
        const first = project(layer.samples[0].position_m.x, layer.samples[0].position_m.y, layer.samples[0].position_m.z);
        const lastSample = layer.samples[layer.samples.length - 1];
        const last = project(lastSample.position_m.x, lastSample.position_m.y, lastSample.position_m.z);
        context.fillStyle = layer.color;
        for (const point of [first, last]) { context.beginPath(); context.arc(point.x, point.y, 4, 0, Math.PI * 2); context.fill(); }
      }

      if (selected) {
        const point = project(selected.position_m.x, selected.position_m.y, selected.position_m.z);
        context.beginPath(); context.arc(point.x, point.y, 9, 0, Math.PI * 2);
        context.strokeStyle = "#18252a"; context.lineWidth = 2; context.stroke();
      }
      context.fillStyle = "#64748b"; context.font = "12px sans-serif"; context.textAlign = "left";
      context.fillText("Ground plane · z = 0 m", 16, height - 18);
    };
    draw();
    const observer = parent ? new ResizeObserver(draw) : null;
    if (parent && observer) observer.observe(parent);
    return () => observer?.disconnect();
  }, [layers, azimuth, elevation, zoom, pan, selected]);

  const onPointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    drag.current = { x: event.clientX, y: event.clientY, azimuth, elevation, panX: pan.x, panY: pan.y, mode: event.shiftKey || event.button === 2 ? "pan" : "orbit" };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const onPointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drag.current) return;
    if (drag.current.mode === "pan") {
      setPan({ x: drag.current.panX + event.clientX - drag.current.x, y: drag.current.panY + event.clientY - drag.current.y });
    } else {
      setAzimuth(drag.current.azimuth + (event.clientX - drag.current.x) * 0.009);
      setElevation(Math.max(0.18, Math.min(1.2, drag.current.elevation - (event.clientY - drag.current.y) * 0.006)));
    }
  };

  return (
    <div className="scene3d-shell">
      <div className="scene3d-banner" role="note">{scene.synthetic_view_label}</div>
      <div className="scene3d-toolbar" aria-label="Scene controls">
        <button className="btn btn-secondary btn-sm" onClick={() => { setAzimuth(-0.55); setElevation(0.48); setZoom(1); setPan({ x: 0, y: 0 }); }}>Reset view</button>
        <label className="scene-toggle"><input type="checkbox" checked={showFitted} onChange={(e) => setShowFitted(e.target.checked)} /> Fitted paths</label>
        <label className="scene-toggle"><input type="checkbox" checked={showCounterfactual} onChange={(e) => setShowCounterfactual(e.target.checked)} /> Counterfactuals</label>
        <label className="scene-toggle"><input type="checkbox" checked={showRivals} onChange={(e) => setShowRivals(e.target.checked)} /> Rivals</label>
        <label className="scene-zoom">Zoom <input type="range" min="0.5" max="2.5" step="0.05" value={zoom} onChange={(e) => setZoom(Number(e.target.value))} /></label>
      </div>
      <div className="scene3d-canvas-wrap">
        <canvas ref={canvasRef} className="scene3d-canvas" role="img" aria-label="Orbitable ground-plane replay. Drag to orbit; hold Shift or right-drag to pan." onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }} onContextMenu={(event) => event.preventDefault()} />
        <div className="scene3d-camera-unknown">Camera pose unknown · no camera frustum shown</div>
      </div>
      <div className="scene3d-legend">{layers.map((layer) => <span key={layer.key}><i style={{ background: layer.color }} />{layer.label}</span>)}</div>
      {timeline.length > 0 && <div className="scene3d-timebar"><label htmlFor="scene-time">Source track time</label><input id="scene-time" type="range" min="0" max={timeline.length - 1} value={Math.min(sampleIndex, timeline.length - 1)} onChange={(e) => setSampleIndex(Number(e.target.value))} /><span>Frame {selected?.frame_index} · {selected?.presentation_ts_s.toFixed(3)} s</span></div>}
      <div className="scene3d-provenance"><span>Calibration: {scene.coordinate_system.calibration_fit_id ?? "unavailable"}</span><span>Units: {scene.coordinate_system.units}</span><span>Origin: {scene.coordinate_system.origin}</span><span>Source SHA-256: {scene.media_sha256.slice(0, 14)}…</span></div>
      <ul className="scene3d-limitations">{scene.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
    </div>
  );
}
