import { useEffect, useState } from "react";
import { api, formatWhen } from "../api";
import type { AccessEvent, DeviceSummary } from "../types";

export default function Devices() {
  const [devices, setDevices] = useState<DeviceSummary[]>([]);
  const [events, setEvents] = useState<AccessEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const [nextDevices, nextEvents] = await Promise.all([api.devices(), api.deviceEvents(100)]);
      setDevices(nextDevices);
      setEvents(nextEvents);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load device log");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-serif text-4xl">Devices</h1>
        <p className="mt-2 max-w-2xl text-ink/70">
          Hits to the OPDS catalog and EPUB downloads. HTTP does not stay connected — “recent” means a request in the
          last five minutes.
        </p>
      </div>
      {error && <p className="text-rust">{error}</p>}
      <div className="flex items-center gap-3">
        <button type="button" onClick={() => void load()} className="rounded-full border border-ink px-4 py-1.5 text-sm">
          Refresh
        </button>
        <span className="text-sm text-ink/60">{devices.length} device{devices.length === 1 ? "" : "s"}</span>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-rule bg-white/50">
        <table className="w-full min-w-[800px] text-left text-sm">
          <thead className="border-b border-rule text-xs uppercase tracking-[0.14em] text-ink/50">
            <tr>
              <th className="px-4 py-3">IP</th>
              <th className="px-4 py-3">Client</th>
              <th className="px-4 py-3">Last seen</th>
              <th className="px-4 py-3">Hits</th>
              <th className="px-4 py-3">Last path</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {devices.length === 0 && (
              <tr>
                <td className="px-4 py-8 text-ink/60" colSpan={6}>
                  No OPDS or download requests yet. Open the catalog from the e-reader to appear here.
                </td>
              </tr>
            )}
            {devices.map((device) => (
              <tr key={`${device.client_ip}-${device.user_agent ?? ""}`} className="border-b border-rule/70 last:border-0">
                <td className="px-4 py-3 font-mono text-xs">{device.client_ip}</td>
                <td className="max-w-xs truncate px-4 py-3" title={device.user_agent ?? ""}>
                  {shortAgent(device.user_agent)}
                </td>
                <td className="px-4 py-3">{formatWhen(device.last_seen_at)}</td>
                <td className="px-4 py-3">{device.request_count}</td>
                <td className="px-4 py-3 font-mono text-xs">{device.last_path}</td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      device.recent ? "bg-moss/15 text-moss" : "bg-rule text-ink/70"
                    }`}
                  >
                    {device.recent ? "recent" : "idle"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <h2 className="font-serif text-2xl">Request log</h2>
        <div className="mt-4 overflow-x-auto rounded-2xl border border-rule bg-white/50">
          <table className="w-full min-w-[800px] text-left text-sm">
            <thead className="border-b border-rule text-xs uppercase tracking-[0.14em] text-ink/50">
              <tr>
                <th className="px-4 py-3">When</th>
                <th className="px-4 py-3">IP</th>
                <th className="px-4 py-3">Path</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Client</th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 && (
                <tr>
                  <td className="px-4 py-8 text-ink/60" colSpan={5}>
                    No events recorded.
                  </td>
                </tr>
              )}
              {events.map((event) => (
                <tr key={event.id} className="border-b border-rule/70 last:border-0">
                  <td className="px-4 py-3">{formatWhen(event.seen_at)}</td>
                  <td className="px-4 py-3 font-mono text-xs">{event.client_ip}</td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {event.method} {event.path}
                  </td>
                  <td className="px-4 py-3">{event.status_code}</td>
                  <td className="max-w-xs truncate px-4 py-3" title={event.user_agent ?? ""}>
                    {shortAgent(event.user_agent)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function shortAgent(value: string | null): string {
  if (!value) return "—";
  if (value.length <= 48) return value;
  return `${value.slice(0, 45)}…`;
}
