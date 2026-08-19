export type RunStatus = "running" | "success" | "error" | "partial";
export type FetchStatus = "ok" | "skipped_paywall" | "failed";

export interface RunSummary {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: RunStatus;
  source_id: string;
  articles_fetched: number;
  articles_failed: number;
  error_message: string | null;
  digest_filename: string | null;
  duration_seconds: number | null;
}

export interface ArticleRow {
  id: number;
  source_id: string;
  external_id: string;
  title: string;
  url: string;
  section: string | null;
  published_at: string | null;
  byline: string | null;
  fetch_status: FetchStatus;
  word_count: number | null;
}

export interface RunDetail extends RunSummary {
  articles: ArticleRow[];
}

export interface StatusPayload {
  ok: boolean;
  warning: string;
  active_source_id: string | null;
  active_source_name: string | null;
  active_sources: { source_id: string; display_name: string; configured: boolean }[];
  source_configured: boolean;
  run_in_progress: boolean;
  last_run: RunSummary | null;
  next_run_at: string | null;
  opds_url: string;
  lan_ip: string | null;
  lan_ips: string[];
  site_url: string;
  latest_digest: string | null;
  latest_digests: { source_id: string; filename: string; title: string }[];
}

export interface ConfigField {
  key: string;
  label: string;
  type: "secret" | "text" | "number" | "tags" | string;
  required: boolean;
  default: unknown;
  help: string | null;
}

export interface SourceInfo {
  source_id: string;
  display_name: string;
  is_active: boolean;
  configured: boolean;
  config_fields: ConfigField[];
}

export interface SourceConfigPayload {
  source_id: string;
  is_active: boolean;
  config: Record<string, unknown>;
  updated_at?: string | null;
  secrets_set: string[];
  problems?: string[];
}

export interface SettingsPayload {
  sync_hour: number;
  sync_minute: number;
  max_articles: number;
  opds_title: string;
  digest_retention: number;
  active_source_id: string;
}

export interface DigestInfo {
  filename: string;
  title: string;
  source_id: string | null;
  size_bytes: number;
  modified_at: string;
  download_url: string;
  opds_download_url: string;
}

export interface DeviceSummary {
  client_ip: string;
  user_agent: string | null;
  first_seen_at: string;
  last_seen_at: string;
  last_path: string;
  last_status: number;
  request_count: number;
  recent: boolean;
}

export interface AccessEvent {
  id: number;
  seen_at: string;
  client_ip: string;
  user_agent: string | null;
  method: string;
  path: string;
  status_code: number;
}
