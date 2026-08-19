import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, durationLabel, formatWhen } from "../api";
import { FetchBadge, StatusBadge } from "../components/StatusBadge";
import type { RunDetail } from "../types";

export default function RunDetailPage() {
  const { id } = useParams();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .run(Number(id))
      .then(setRun)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load run"));
  }, [id]);

  if (error) return <p className="text-rust">{error}</p>;
  if (!run) return <p className="text-ink/60">Loading…</p>;

  return (
    <div className="space-y-6">
      <p>
        <Link to="/runs" className="text-sm underline">
          ← All runs
        </Link>
      </p>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-4xl">Run #{run.id}</h1>
          <p className="mt-1 text-ink/70">
            {run.source_id} · {formatWhen(run.started_at)} · {durationLabel(run.duration_seconds)}
          </p>
        </div>
        <StatusBadge status={run.status} />
      </div>
      {run.error_message && <p className="rounded-xl bg-rust/10 px-4 py-3 text-sm text-rust">{run.error_message}</p>}
      {run.digest_filename && (
        <a className="inline-block text-sm underline" href={`/download/${run.digest_filename}`}>
          Download {run.digest_filename}
        </a>
      )}
      <div className="overflow-x-auto rounded-2xl border border-rule bg-white/50">
        <table className="w-full min-w-[800px] text-left text-sm">
          <thead className="border-b border-rule text-xs uppercase tracking-[0.14em] text-ink/50">
            <tr>
              <th className="px-4 py-3">Title</th>
              <th className="px-4 py-3">Section</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Words</th>
            </tr>
          </thead>
          <tbody>
            {(run.articles ?? []).length === 0 && (
              <tr>
                <td className="px-4 py-8 text-ink/60" colSpan={4}>
                  No articles recorded for this run.
                </td>
              </tr>
            )}
            {(run.articles ?? []).map((article) => (
              <tr key={article.id} className="border-b border-rule/70 last:border-0">
                <td className="px-4 py-3">
                  <a href={article.url} target="_blank" rel="noreferrer" className="underline">
                    {article.title}
                  </a>
                  {article.byline && <div className="text-xs text-ink/50">{article.byline}</div>}
                </td>
                <td className="px-4 py-3">{article.section ?? "—"}</td>
                <td className="px-4 py-3">
                  <FetchBadge status={article.fetch_status} />
                </td>
                <td className="px-4 py-3">{article.word_count ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
