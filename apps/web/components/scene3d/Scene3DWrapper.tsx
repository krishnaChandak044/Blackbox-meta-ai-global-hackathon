"use client";

import { Component, type ReactNode, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import type { Scene3D as SceneData } from "@/lib/api";
import Scene3DCanvasFallback from "./Scene3D";

// Dynamically import Scene3DR3F to avoid SSR issues with WebGL / window objects
const Scene3DR3F = dynamic(() => import("./Scene3DR3F"), {
  ssr: false,
  loading: () => (
    <div className="scene3d-shell" style={{ minHeight: "480px", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div className="card card-body flex items-center gap-3">
        <div className="spinner" />
        <span>Initializing 3D WebGL renderer…</span>
      </div>
    </div>
  ),
});

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback: ReactNode;
  onError?: (error: Error) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

class WebGLErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error) {
    this.props.onError?.(error);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

function detectWebGL(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    const gl =
      canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl");
    return Boolean(gl);
  } catch {
    return false;
  }
}

export default function Scene3DWrapper({ scene }: { scene: SceneData }) {
  const [mounted, setMounted] = useState(false);
  const [webglSupported, setWebglSupported] = useState(true);
  const [force2D, setForce2D] = useState(false);

  useEffect(() => {
    setMounted(true);
    const supported = detectWebGL();
    setWebglSupported(supported);
  }, []);

  if (!mounted) {
    return (
      <div className="scene3d-shell" style={{ minHeight: "480px", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div className="card card-body flex items-center gap-3">
          <div className="spinner" />
          <span>Loading scene view…</span>
        </div>
      </div>
    );
  }

  // If WebGL is unavailable or user explicitly chose 2D Canvas fallback
  if (!webglSupported || force2D) {
    return (
      <div>
        {!webglSupported && (
          <div className="alert alert-info mb-3" style={{ fontSize: "12px", padding: "6px 12px" }}>
            <strong>2D Fallback Active:</strong> WebGL hardware acceleration was not detected in this browser environment. The scene is rendered using the certified 2D ground-plane projection.
          </div>
        )}
        {webglSupported && force2D && (
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "8px" }}>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => setForce2D(false)}
              style={{ fontSize: "11px" }}
            >
              Switch back to 3D WebGL
            </button>
          </div>
        )}
        <Scene3DCanvasFallback scene={scene} />
      </div>
    );
  }

  return (
    <WebGLErrorBoundary
      onError={(err) => {
        console.warn("WebGL runtime error encountered, falling back to 2D Canvas:", err);
        setWebglSupported(false);
      }}
      fallback={
        <div>
          <div className="alert alert-warning mb-3" style={{ fontSize: "12px", padding: "6px 12px" }}>
            <strong>WebGL Context Notice:</strong> The 3D view encountered a GPU rendering issue and automatically degraded to the 2D ground-plane projection.
          </div>
          <Scene3DCanvasFallback scene={scene} />
        </div>
      }
    >
      <Scene3DR3F scene={scene} onToggle2DFallback={() => setForce2D(true)} />
    </WebGLErrorBoundary>
  );
}

