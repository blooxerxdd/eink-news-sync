import type { FetchStatus, RunStatus } from "../types";

const runStyles: Record<RunStatus, string> = {
  success: "bg-moss/15 text-moss",
  error: "bg-rust/15 text-rust",
  partial: "bg-amber/15 text-amber",
  running: "bg-forest/10 text-forest",
};

const fetchStyles: Record<FetchStatus, string> = {
  ok: "bg-moss/15 text-moss",
  skipped_paywall: "bg-amber/15 text-amber",
  failed: "bg-rust/15 text-rust",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${runStyles[status]}`}>
      {status}
    </span>
  );
}

export function FetchBadge({ status }: { status: FetchStatus }) {
  const label = status === "skipped_paywall" ? "skipped" : status;
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${fetchStyles[status]}`}>
      {label}
    </span>
  );
}
