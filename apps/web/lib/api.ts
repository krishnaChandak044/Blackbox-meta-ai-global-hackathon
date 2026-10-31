/* ─── Blackbox API Client ─────────────────────────────────────────────────── */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const V1 = `${BASE}/api/v1`;

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${V1}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
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
    fetch(`${V1}/cases/${id}`, { method: "DELETE" }),
};

/* ── Media API ────────────────────────────────────────────────────────────── */
export const mediaApi = {
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

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress?.(Math.round((e.loaded / e.total) * 100));
      };

      xhr.onload = () => {
        if (xhr.status === 201) {
          resolve(JSON.parse(xhr.responseText) as SourceMedia);
        } else {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail ?? "Upload failed"));
        }
      };
      xhr.onerror = () => reject(new Error("Network error during upload"));
      xhr.send(fd);
    });
  },

  checkIntegrity: (caseId: string, mediaId: string) =>
    req<IntegrityCheck>(`/cases/${caseId}/media/${mediaId}/integrity`),

  delete: (caseId: string, mediaId: string) =>
    fetch(`${V1}/cases/${caseId}/media/${mediaId}`, { method: "DELETE" }),
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
