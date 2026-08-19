import type {
  DigestInfo,
  RunDetail,
  RunSummary,
  SettingsPayload,
  SourceConfigPayload,
  SourceInfo,
  StatusPayload,
  ArticleRow,
  DeviceSummary,
  AccessEvent,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    const error = new Error(detail) as Error & { status: number };
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  status: () => request<StatusPayload>("/api/status"),
  runs: (limit = 50) => request<RunSummary[]>(`/api/runs?limit=${limit}`),
  run: (id: number) => request<RunDetail>(`/api/runs/${id}`),
  runArticles: (id: number) => request<ArticleRow[]>(`/api/runs/${id}/articles`),
  trigger: () => request<RunSummary>("/api/runs/trigger", { method: "POST" }),
  sources: () => request<SourceInfo[]>("/api/sources"),
  sourceConfig: (id: string) => request<SourceConfigPayload>(`/api/sources/${id}/config`),
  saveSourceConfig: (id: string, config: Record<string, unknown>) =>
    request<SourceConfigPayload>(`/api/sources/${id}/config`, {
      method: "PUT",
      body: JSON.stringify({ config }),
    }),
  activateSource: (id: string) =>
    request<{ source_id: string; is_active: boolean }>(`/api/sources/${id}/activate`, { method: "POST" }),
  validateSource: (id: string, config?: Record<string, unknown>) =>
    request<{ ok: boolean; problems: string[] }>(`/api/sources/${id}/validate`, {
      method: "POST",
      body: JSON.stringify(config ? { config } : {}),
    }),
  settings: () => request<SettingsPayload>("/api/settings"),
  saveSettings: (payload: Partial<SettingsPayload>) =>
    request<SettingsPayload>("/api/settings", { method: "PUT", body: JSON.stringify(payload) }),
  digests: () => request<DigestInfo[]>("/api/digests"),
  devices: () => request<DeviceSummary[]>("/api/devices"),
  deviceEvents: (limit = 100) => request<AccessEvent[]>(`/api/devices/events?limit=${limit}`),
};

export async function pollUntilIdle(timeoutMs = 180_000): Promise<StatusPayload> {
  const start = Date.now();
  let status = await api.status();
  while (status.run_in_progress) {
    if (Date.now() - start > timeoutMs) {
      throw new Error("Sync is still running");
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
    status = await api.status();
  }
  return status;
}

export function formatWhen(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function durationLabel(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${rest}s`;
}
