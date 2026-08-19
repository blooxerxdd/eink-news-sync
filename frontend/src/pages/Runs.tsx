import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, durationLabel, formatWhen } from "../api";
import { StatusBadge } from "../components/StatusBadge";
import type { RunSummary } from "../types";

export default function Runs() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .runs()
      .then(setRuns)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load runs"));
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="font-serif text-4xl">Run history</h1>
      {error && <p className="text-rust">{error}</p>}
      <div className="overflow-x-auto rounded-2xl border border-rule bg-white/50">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b border-rule text-xs uppercase tracking-[0.14em] text-ink/50">
            <tr>
              <th className="px-4 py-3">When</th>
              <th className="px-4 py-3">Source</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Fetched</th>
              <th className="px-4 py-3">Failed</th>
              <th className="px-4 py-3">Duration</th>
              <th className="px-4 py-3">Digest</th>
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 && (
              <tr>
                <td className="px-4 py-8 text-ink/60" colSpan={7}>
                  No runs yet. Trigger a sync from the dashboard.
                </td>
              </tr>
            )}
            {runs.map((run) => (
              <tr key={run.id} className="border-b border-rule/70 last:border-0">
                <td className="px-4 py-3">
                  <Link to={`/runs/${run.id}`} className="underline">
                    {formatWhen(run.started_at)}
                  </Link>
                </td>
                <td className="px-4 py-3">{run.source_id}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={run.status} />
                </td>
                <td className="px-4 py-3">{run.articles_fetched}</td>
                <td className="px-4 py-3">{run.articles_failed}</td>
                <td className="px-4 py-3">{durationLabel(run.duration_seconds)}</td>
                <td className="px-4 py-3">{run.digest_filename ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
