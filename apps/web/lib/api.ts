/* ─── Blackbox API Client ─────────────────────────────────────────────────── */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const V1 = `${BASE}/api/v1`;

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${V1}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (res.status === 401 && !path.startsWith("/auth/")) {
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Authentication required");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json() as Promise<T>;
}

/* ── Types ────────────────────────────────────────────────────────────────── */
export type CaseStatus = "draft" | "processing" | "ready" | "exported";
export type MediaStatus = "uploading" | "stored" | "probing" | "indexed" | "failed";
export type JobStatus  = "queued" | "running" | "done" | "failed" | "retrying";
export type JobStage   = "probe" | "frame_index" | "integrity" | "track" | "calibrate" |
                         "transcribe" | "claim_check" | "dynamics" | "counterfactual" | "export";

export interface Case {
  id: string;
  title: string;
  description: string | null;
  jurisdiction: string | null;
  incident_date: string | null;
  incident_location: string | null;
  status: CaseStatus;
  consent_given: boolean;
  owner_id: string;
  created_at: string;
  updated_at: string;
  media_count: number;
}

export interface SourceMedia {
  id: string;
  case_id: string;
  original_filename: string;
  mime_type: string;
  byte_length: number;
  sha256: string;
  status: MediaStatus;
  upload_time: string;
  codec: string | null;
  container: string | null;
  duration_seconds: number | null;
  frame_count: number | null;
  fps_nominal: number | null;
  is_variable_framerate: boolean | null;
  width: number | null;
  height: number | null;
  has_audio: boolean | null;
}

export interface IntegrityCheck {
  media_id: string;
  original_sha256: string;
  verified_sha256: string;
  intact: boolean;
  checked_at: string;
}

export interface Job {
  id: string;
  case_id: string;
  media_id: string | null;
  stage: JobStage;
  status: JobStatus;
  progress: number;
  error_message: string | null;
  queued_at: string;
  started_at: string | null;
  completed_at: string | null;
}

/* ── Cases API ────────────────────────────────────────────────────────────── */
export const casesApi = {
  list: () => req<Case[]>("/cases/"),
  get:  (id: string) => req<Case>(`/cases/${id}`),
  create: (body: {
    title: string;
    description?: string;
    jurisdiction?: string;
    incident_date?: string;
    incident_location?: string;
    consent_given?: boolean;
  }) => req<Case>("/cases/", { method: "POST", body: JSON.stringify(body) }),
  update: (id: string, body: Partial<Case>) =>
    req<Case>(`/cases/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  delete: (id: string) =>
    fetch(`${V1}/cases/${id}`, { method: "DELETE", credentials: "include" }),
};

/* ── Media API ────────────────────────────────────────────────────────────── */
export const mediaApi = {
  streamUrl: (caseId: string, mediaId: string) =>
    `${V1}/cases/${caseId}/media/${mediaId}/stream`,
  list: (caseId: string) => req<SourceMedia[]>(`/cases/${caseId}/media/`),
  get:  (caseId: string, mediaId: string) =>
    req<SourceMedia>(`/cases/${caseId}/media/${mediaId}`),

  upload: async (
    caseId: string,
    file: File,
    onProgress?: (pct: number) => void,
  ): Promise<SourceMedia> => {
    return new Promise((resolve, reject) => {
      const fd = new FormData();
      fd.append("file", file);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${V1}/cases/${caseId}/media/`);
      xhr.withCredentials = true;

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress?.(Math.round((e.loaded / e.total) * 100));
      };

      xhr.onload = () => {
        if (xhr.status === 201) {
          resolve(JSON.parse(xhr.responseText) as SourceMedia);
        } else {
          if (xhr.status === 401) { window.location.href = "/login"; reject(new Error("Authentication required")); return; }
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail ?? "Upload failed"));
        }
      };
      xhr.onerror = () => reject(new Error("Network error during upload"));
      xhr.send(fd);
    });
  },

  downloadOriginal: async (caseId: string, mediaId: string, filename: string) => {
    const res = await fetch(`${V1}/cases/${caseId}/media/${mediaId}/original`, { credentials: "include" });
    if (!res.ok) throw new Error("Original download failed integrity or access check");
    const url = URL.createObjectURL(await res.blob());
    const link = document.createElement("a");
    link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },

  retry: (caseId: string, mediaId: string) => req<{ job_id: string }>(`/cases/${caseId}/media/${mediaId}/retry`, { method: "POST" }),

  checkIntegrity: (caseId: string, mediaId: string) =>
    req<IntegrityCheck>(`/cases/${caseId}/media/${mediaId}/integrity`),

  delete: (caseId: string, mediaId: string) =>
    fetch(`${V1}/cases/${caseId}/media/${mediaId}`, { method: "DELETE", credentials: "include" }),
};

/* ── Jobs API ─────────────────────────────────────────────────────────────── */
export const jobsApi = {
  listForCase: (caseId: string) => req<Job[]>(`/jobs/case/${caseId}`),
  get: (jobId: string) => req<Job>(`/jobs/${jobId}`),
};


/* ── Helpers ──────────────────────────────────────────────────────────────── */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function shortHash(hash: string): string {
  return `${hash.slice(0, 8)}…${hash.slice(-6)}`;
}

export function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60)  return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24)  return `${h}h ago`;
  return new Date(dateStr).toLocaleDateString();
}


export const authApi = {
  login: (password: string) => req<{ authenticated: boolean }>("/auth/session", { method: "POST", body: JSON.stringify({ password }) }),
  session: () => req<{ authenticated: boolean }>("/auth/session"),
  logout: () => req<{ authenticated: boolean }>("/auth/session", { method: "DELETE" }),
};

/* ── Phase 2 Types ────────────────────────────────────────────────────────── */

export interface CalibrationAnchor {
  id: string;
  media_id: string;
  label: string;
  pixel_x: number;
  pixel_y: number;
  world_x: number;
  world_y: number;
  known_distance_m: number | null;
  is_distance_ref_b: boolean;
  reprojection_error_px: number | null;
  created_at: string;
}

export interface HomographyFit {
  id: string;
  media_id: string;
  anchor_count: number;
  reprojection_rmse_px: number;
  condition_number: number;
  scale_metres_per_pixel: number | null;
  scale_relative_error: number | null;
  scale_source: string | null;
  H: number[][];
  fitted_at: string;
  is_active: boolean;
  per_anchor_errors_px: number[];
}

export interface TrackPointOut {
  frame_index: number;
  presentation_ts_s: number;
  bbox_x_min: number;
  bbox_y_min: number;
  bbox_x_max: number;
  bbox_y_max: number;
  gc_pixel_x: number;
  gc_pixel_y: number;
  world_x: number | null;
  world_y: number | null;
  sigma_m: number | null;
  detection_confidence: number;
  is_interpolated: boolean;
  is_human_corrected: boolean;
}

export interface TrackSummary {
  id: string;
  tracker_track_id: string;
  category: string;
  tracker_model: string;
  first_frame: number;
  last_frame: number;
  point_count: number;
  is_complete: boolean;
  is_human_confirmed: boolean;
  created_at: string;
}

export interface TrackDetail extends TrackSummary {
  points: TrackPointOut[];
}

/* ── Calibration API ──────────────────────────────────────────────────────── */
export const calibrationApi = {
  listAnchors: (caseId: string, mediaId: string) =>
    req<CalibrationAnchor[]>(`/cases/${caseId}/media/${mediaId}/calibration/anchors`),

  addAnchor: (
    caseId: string,
    mediaId: string,
    body: {
      label: string;
      pixel_x: number;
      pixel_y: number;
      world_x: number;
      world_y: number;
      known_distance_m?: number;
      is_distance_ref_b?: boolean;
    },
  ) =>
    req<CalibrationAnchor>(
      `/cases/${caseId}/media/${mediaId}/calibration/anchors`,
      { method: "POST", body: JSON.stringify(body) },
    ),

  deleteAnchor: (caseId: string, mediaId: string, anchorId: string) =>
    fetch(`${V1}/cases/${caseId}/media/${mediaId}/calibration/anchors/${anchorId}`, {
      method: "DELETE",
      credentials: "include",
    }),

  fitHomography: (caseId: string, mediaId: string) =>
    req<HomographyFit>(`/cases/${caseId}/media/${mediaId}/calibration/fit`, { method: "POST" }),

  getActiveFit: (caseId: string, mediaId: string) =>
    req<HomographyFit | null>(`/cases/${caseId}/media/${mediaId}/calibration/fit`),
};

/* ── Phase 3 — Transcripts & Claims ──────────────────────────────────────── */
export interface DiarisedSegment { speaker: string; start: number; end: number; text: string; }
export interface Transcript { id: string; case_id: string; media_id: string | null; speaker_count: number; language: string; raw_text: string; diarised_json: string | null; transcription_model: string; word_count: number; duration_seconds: number | null; created_at: string; }
export interface ClaimAssertion { assertion_type: string; subject: string; value: number | null; unit: string | null; qualifier: string | null; raw_text: string; source_ts_start: number; source_ts_end: number; }
export interface TranscriptClaim { id: string; transcript_id: string; case_id: string; speaker: string; raw_text: string; assertions: ClaimAssertion[]; extraction_confidence: number; source_ts_start: number; source_ts_end: number; created_at: string; }
export interface ClaimVerdict { id: string; claim_id: string; case_id: string; verdict: string; confidence: number; evidence_frame_start: number | null; evidence_frame_end: number | null; evidence_json: string | null; explanation: string; homography_fit_id: string | null; checked_at: string; checked_by: string; }
export interface DynamicsRun {
  run_id: string; status: string; track_id: string; calibration_fit_id: string;
  model_name: string; model_version: string; seed: number; interval_type: string;
  entry_speed_kmh: number | null; entry_speed_lo_kmh: number | null; entry_speed_hi_kmh: number | null;
  mean_decel_ms2: number | null; mean_decel_lo_ms2: number | null; mean_decel_hi_ms2: number | null;
  fitted_points_json: string | null; uncertainty_json: string | null; certificates_json: string | null;
  fit_quality_json: string | null; braking_onset_json: string | null; error_message: string | null;
  created_at: string; completed_at: string | null;
}
export interface CounterfactualResponse {
  id: string; baseline_run_id: string; status: string; simulated_points: Array<Record<string, number>>;
  stopping_distance_m: number | null; stopping_time_s: number | null; sensitivity: Array<Record<string, unknown>>;
  extrapolation_outside_support: boolean; illustrative_label: string; assumptions: Record<string, unknown>; created_at: string;
}
export interface RivalResponse {
  id: string; primary_run_id: string; manifest: Record<string, unknown>; rivals: Array<Record<string, unknown>>;
  empty_search_message: string; second_view_used: boolean; second_view_notes: string; created_at: string;
}
export const transcriptsApi = {
  list: (caseId: string) => req<Transcript[]>(`/cases/${caseId}/transcripts/`),
  get: (caseId: string, id: string) => req<Transcript>(`/cases/${caseId}/transcripts/${id}`),
  create: (caseId: string, body: { raw_text: string; language?: string; media_id?: string }) => req<Transcript>(`/cases/${caseId}/transcripts/`, { method: "POST", body: JSON.stringify(body) }),
  delete: (caseId: string, id: string) => fetch(`${V1}/cases/${caseId}/transcripts/${id}`, { method: "DELETE", credentials: "include" }),
  transcribe: (caseId: string, mediaId: string) => req<{ job_id: string }>(`/cases/${caseId}/transcripts/media/${mediaId}/transcribe`, { method: "POST" }),
};
export const claimsApi = {
  list: (caseId: string) => req<TranscriptClaim[]>(`/cases/${caseId}/claims/`),
  get: (caseId: string, claimId: string) => req<TranscriptClaim>(`/cases/${caseId}/claims/${claimId}`),
  extract: (caseId: string, transcriptId: string) => req<{ job_id: string }>(`/cases/${caseId}/claims/extract/${transcriptId}`, { method: "POST" }),
  check: (caseId: string, claimId: string) => req<ClaimVerdict>(`/cases/${caseId}/claims/${claimId}/check`, { method: "POST" }),
  getCheck: (caseId: string, claimId: string) => req<ClaimVerdict | null>(`/cases/${caseId}/claims/${claimId}/check`),
  update: (caseId: string, claimId: string, body: { raw_text?: string; speaker?: string }) => req<TranscriptClaim>(`/cases/${caseId}/claims/${claimId}`, { method: "PATCH", body: JSON.stringify(body) }),
  delete: (caseId: string, claimId: string) => fetch(`${V1}/cases/${caseId}/claims/${claimId}`, { method: "DELETE", credentials: "include" }),
};
export const phase4Api = {
  queueDynamics: (caseId: string, mediaId: string, body: { track_id: string; calibration_fit_id: string; seed?: number }) =>
    req<{ dynamics_run_id: string; job_id: string; status: string }>(`/cases/${caseId}/media/${mediaId}/dynamics`, { method: "POST", body: JSON.stringify(body) }),
  getDynamics: (caseId: string, mediaId: string) =>
    req<DynamicsRun>(`/cases/${caseId}/media/${mediaId}/dynamics`),
  simulate: (caseId: string, mediaId: string, body: { baseline_run_id: string; braking_onset_shift_s: number; entry_speed_override_kmh?: number | null; decel_override_ms2?: number | null }) =>
    req<CounterfactualResponse>(`/cases/${caseId}/media/${mediaId}/simulate`, { method: "POST", body: JSON.stringify(body) }),
  searchRivals: (caseId: string, mediaId: string, body: { primary_run_id: string; seed: number; grid_n?: number; acceptance_threshold_m?: number }) =>
    req<RivalResponse>(`/cases/${caseId}/media/${mediaId}/rivals/search`, { method: "POST", body: JSON.stringify(body) }),
  getRivals: (caseId: string, mediaId: string) =>
    req<RivalResponse>(`/cases/${caseId}/media/${mediaId}/rivals`),
};

/* ── Tracks API ───────────────────────────────────────────────────────────── */
export const tracksApi = {
  list: (caseId: string, mediaId: string) =>
    req<TrackSummary[]>(`/cases/${caseId}/media/${mediaId}/tracks/`),

  get: (caseId: string, mediaId: string, trackId: string) =>
    req<TrackDetail>(`/cases/${caseId}/media/${mediaId}/tracks/${trackId}`),

  run: (caseId: string, mediaId: string) =>
    req<{ job_id: string }>(`/cases/${caseId}/media/${mediaId}/tracks/run`, { method: "POST" }),

  confirm: (caseId: string, mediaId: string, trackId: string) =>
    req<TrackSummary>(
      `/cases/${caseId}/media/${mediaId}/tracks/${trackId}/confirm`,
      { method: "POST" },
    ),

  correctPoint: (
    caseId: string,
    mediaId: string,
    trackId: string,
    frameIndex: number,
    bbox: { bbox_x_min: number; bbox_y_min: number; bbox_x_max: number; bbox_y_max: number },
  ) =>
    req<TrackPointOut>(
      `/cases/${caseId}/media/${mediaId}/tracks/${trackId}/points/${frameIndex}`,
      { method: "PATCH", body: JSON.stringify(bbox) },
    ),

  delete: (caseId: string, mediaId: string, trackId: string) =>
    fetch(`${V1}/cases/${caseId}/media/${mediaId}/tracks/${trackId}`, {
      method: "DELETE",
      credentials: "include",
    }),
};

/* ── Phase 5 — 3D scene, evidence rescue, Atlas, review exports ───────────── */
export interface ScenePosition {
  x: number;
  y: number;
  z: number;
}
export interface SceneSample {
  frame_index: number;
  presentation_ts_s: number;
  position_m: ScenePosition;
  position_2d_m: { x: number; y: number };
  provenance: string;
  uncertainty_sigma_m?: number | null;
  uncertainty_sigma_xy_m?: { x: number; y: number; coverage: string };
  source?: { media_id: string; frame_index: number };
  uncertainty?: string;
}
export interface ScenePath {
  run_id?: string;
  baseline_run_id?: string;
  path_type: string;
  provenance: string;
  interval_type?: string | null;
  illustrative_label?: string;
  samples: SceneSample[];
}
export interface SceneObject {
  track_id: string;
  class: string;
  review_status: string;
  geometry: { source: string; label: string };
  samples: SceneSample[];
}
export interface SceneRivalHypothesis {
  rank: number;
  params: Record<string, number>;
  residual_m: number;
  disambiguation_status: string;
  samples: SceneSample[];
}
export interface SceneRivalPath {
  search_id: string;
  path_type: string;
  provenance: string;
  illustrative_label: string;
  hypotheses: SceneRivalHypothesis[];
}
export interface Scene3D {
  scene_id: string;
  schema_version: string;
  generated_at: string;
  case_id: string;
  media_id: string;
  media_sha256: string;
  coordinate_system: {
    handedness: string;
    units: string;
    ground_plane: string;
    origin: string;
    calibration_fit_id: string | null;
    transform_source: string;
  };
  camera_pose: { status: string; reason: string };
  objects: SceneObject[];
  fitted_paths: ScenePath[];
  counterfactual_paths: ScenePath[];
  rival_paths: SceneRivalPath[];
  synthetic_view_label: string;
  limitations: string[];
}

export interface EvidenceNeed {
  id: string;
  need_key: string;
  title: string;
  evidence_type: string;
  questions: string[];
  heuristic_expected_reduction_fraction: number;
  effort_score_1_low_5_high: number;
  privacy_cost_1_low_5_high: number;
  availability: string;
  retention_deadline: { hours_remaining: number; basis: string } | null;
  ranking_basis: string;
  urgency_score_0_1: number;
  priority_score: number;
  reduction_metric: string;
  state: string;
  verification: Record<string, unknown> | null;
  draft_text: string | null;
}
export interface EvidenceNeedsResponse {
  case_id: string;
  analysis_run_id: string | null;
  media_count: number;
  needs: EvidenceNeed[];
  retention_deadline_default: string;
  ranking_note: string;
}
export interface EvidenceNeedUpdate {
  state: "verified_source" | "drafted" | "requested_by_user" | "received" | "unavailable" | "refused";
  source_description?: string;
  verified?: boolean;
  retention_deadline?: string | null;
  timezone_name?: string;
  contact_name?: string;
  contact_details?: string;
}
export interface EvidenceDraftInput {
  recipient: string;
  source_description: string;
  date_range: string;
  time_range: string;
}
export interface AtlasAggregate {
  coarse_cell: string;
  time_bucket: string;
  conflict_type: string;
  distinct_case_count: number;
  provenance: string;
  synthetic_included: boolean;
  road_user_mix: Record<string, number>;
  mean_metrics: Record<string, number>;
  limitations: string;
}
export interface AtlasResponse {
  minimum_cohort: number;
  private_by_default: boolean;
  access_scope: string;
  suppressed_group_count: number;
  aggregates: AtlasAggregate[];
}
export interface AtlasContributionInput {
  source_run_id: string;
  coarse_cell: string;
  time_bucket: string;
  conflict_type: "crossing" | "rear_end" | "turning" | "merge" | "other";
  road_user_mix: Record<string, number>;
  metrics: Record<string, number>;
  reviewer_confirmed: boolean;
}
export interface CaseExport {
  export_id: string;
  case_id: string;
  status: "queued" | "running" | "complete" | "failed" | "stale";
  job_id: string | null;
  case_revision_hash: string;
  manifest_sha256: string | null;
  pdf_sha256: string | null;
  json_sha256: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export const phase5Api = {
  scene: (caseId: string, mediaId: string) =>
    req<Scene3D>(`/cases/${caseId}/media/${mediaId}/scene3d`),
  evidenceNeeds: (caseId: string) =>
    req<EvidenceNeedsResponse>(`/cases/${caseId}/evidence-needs`),
  updateEvidenceNeed: (caseId: string, needId: string, body: EvidenceNeedUpdate) =>
    req<{ id: string; state: string; verification: Record<string, unknown> }>(
      `/cases/${caseId}/evidence-needs/${needId}/verification`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  draftEvidenceRequest: (caseId: string, needId: string, body: EvidenceDraftInput) =>
    req<{ id: string; state: string; draft: string; sent: false }>(
      `/cases/${caseId}/evidence-needs/${needId}/draft`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  getAtlasConsent: (caseId: string) =>
    req<{ case_id: string; opted_in: boolean; scope_version: string; consented_at: string | null; revoked_at: string | null }>(
      `/atlas/cases/${caseId}/consent`,
    ),
  setAtlasConsent: (caseId: string, optedIn: boolean) =>
    req<{ case_id: string; opted_in: boolean; scope_version: string; consented_at: string | null; revoked_at: string | null }>(
      `/atlas/cases/${caseId}/consent`,
      { method: "POST", body: JSON.stringify({ opted_in: optedIn, scope_version: "atlas-derived-coarse-v1" }) },
    ),
  addAtlasContribution: (caseId: string, body: AtlasContributionInput) =>
    req<{ contribution_id: string; included: boolean; public_or_cross_case_visibility: string }>(
      `/atlas/cases/${caseId}/contributions`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  atlasAggregates: () => req<AtlasResponse>("/atlas"),
  createExport: (caseId: string) =>
    req<{ export_id: string; job_id: string; status: string; case_revision_hash: string }>(
      `/cases/${caseId}/exports`, { method: "POST" },
    ),
  listExports: (caseId: string) => req<CaseExport[]>(`/cases/${caseId}/exports`),
  getExport: (caseId: string, exportId: string) =>
    req<CaseExport>(`/cases/${caseId}/exports/${exportId}`),
  downloadExport: async (caseId: string, exportId: string, kind: "pdf" | "json") => {
    const response = await fetch(
      `${V1}/cases/${caseId}/exports/${exportId}/files/${kind}`,
      { credentials: "include" },
    );
    if (response.status === 401) {
      if (typeof window !== "undefined") window.location.href = "/login";
      throw new Error("Authentication required");
    }
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail ?? "Export download failed");
    }
    const blobUrl = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = blobUrl;
    anchor.download = `blackbox-${exportId}.${kind}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
  },
};

