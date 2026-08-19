import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, formatWhen, pollUntilIdle } from "../api";
import Copyable from "../components/Copyable";
import { StatusBadge } from "../components/StatusBadge";
import type { StatusPayload } from "../types";

export default function Dashboard() {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setStatus(await api.status());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load status");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function syncNow() {
    setBusy(true);
    setError(null);
    try {
      await api.trigger();
      const next = await pollUntilIdle();
      setStatus(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
      await load();
    } finally {
      setBusy(false);
    }
  }

  if (!status && !error) {
    return <p className="text-ink/60">Loading…</p>;
  }

  const last = status?.last_run;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-serif text-4xl">Today’s paper, when you want it</h1>
        <p className="mt-2 max-w-2xl text-ink/70">
          This service keeps the latest digest ready. Your reader pulls it over OPDS — nothing is pushed to a sleeping
          device.
        </p>
      </div>

      {error && <Banner tone="error">{error}</Banner>}
      {status && !status.source_configured && (
        <Banner tone="warn">
          The active source is not fully configured.{" "}
          <Link to="/sources" className="underline">
            Add an API key
          </Link>{" "}
          before the first sync.
        </Banner>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Active source">
          <p className="font-serif text-2xl">{status?.active_source_name ?? "—"}</p>
          <p className="mt-1 text-sm text-ink/60">{status?.source_configured ? "Configured" : "Needs setup"}</p>
        </Card>
        <Card title="Last run">
          {last ? (
            <>
              <div className="flex items-center gap-2">
                <StatusBadge status={last.status} />
                <span className="text-sm text-ink/70">{formatWhen(last.started_at)}</span>
              </div>
              <p className="mt-2 text-sm">
                {last.articles_fetched} fetched
                {last.articles_failed ? ` · ${last.articles_failed} failed` : ""}
              </p>
              {last.error_message && <p className="mt-2 text-sm text-rust">{last.error_message}</p>}
            </>
          ) : (
            <p className="text-ink/60">No runs yet</p>
          )}
        </Card>
        <Card title="Next scheduled">
          <p className="font-serif text-2xl">{formatWhen(status?.next_run_at)}</p>
          <p className="mt-1 text-sm text-ink/60">Local server time</p>
        </Card>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void syncNow()}
          disabled={busy || status?.run_in_progress}
          className="rounded-full bg-ink px-5 py-2 text-sm text-paper disabled:opacity-50"
        >
          {busy || status?.run_in_progress ? "Syncing…" : "Sync now"}
        </button>
        {status?.latest_digest && (
          <a className="rounded-full border border-ink px-5 py-2 text-sm" href={`/download/${status.latest_digest}`}>
            Latest digest
          </a>
        )}
        <Link to="/runs" className="text-sm underline">
          Run history
        </Link>
      </div>

      {status && (
        <Card title="On your LAN">
          <div className="space-y-4">
            <Copyable label="Local IP" value={status.lan_ip ?? "Not detected"} />
            <Copyable label="Site URL" value={status.site_url} />
            <Copyable label="OPDS catalog" value={status.opds_url} />
            {status.lan_ips.length > 1 && (
              <p className="text-sm text-ink/60">Other addresses: {status.lan_ips.filter((ip) => ip !== status.lan_ip).join(", ")}</p>
            )}
            <p className="text-sm text-ink/60">Paste the OPDS URL into the Xteink X3 (CrossPoint) OPDS client. Use the local IP, not 127.0.0.1 — that only works on this computer.</p>
          </div>
        </Card>
      )}
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-rule bg-white/50 p-5">
      <h2 className="text-xs uppercase tracking-[0.16em] text-ink/50">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Banner({ tone, children }: { tone: "error" | "warn"; children: ReactNode }) {
  const cls = tone === "error" ? "bg-rust/10 text-rust" : "bg-amber/10 text-amber";
  return <div className={`rounded-xl px-4 py-3 text-sm ${cls}`}>{children}</div>;
}
