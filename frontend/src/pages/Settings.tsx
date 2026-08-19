import { FormEvent, useEffect, useState } from "react";
import { api } from "../api";
import type { SettingsPayload } from "../types";

export default function Settings() {
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .settings()
      .then(setSettings)
      .catch((err: unknown) => setMessage(err instanceof Error ? err.message : "Failed to load settings"));
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setBusy(true);
    try {
      const saved = await api.saveSettings(settings);
      setSettings(saved);
      setMessage("Saved. The daily schedule now uses these values.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  if (!settings) return <p className="text-ink/60">Loading…</p>;

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="font-serif text-4xl">Settings</h1>
      <form onSubmit={(event) => void onSubmit(event)} className="space-y-4 rounded-2xl border border-rule bg-white/50 p-5">
        <div className="grid grid-cols-2 gap-3">
          <NumberField
            label="Sync hour"
            value={settings.sync_hour}
            min={0}
            max={23}
            onChange={(sync_hour) => setSettings({ ...settings, sync_hour })}
          />
          <NumberField
            label="Sync minute"
            value={settings.sync_minute}
            min={0}
            max={59}
            onChange={(sync_minute) => setSettings({ ...settings, sync_minute })}
          />
        </div>
        <NumberField
          label="Max articles per source digest"
          value={settings.max_articles}
          min={1}
          max={200}
          onChange={(max_articles) => setSettings({ ...settings, max_articles })}
        />
        <NumberField
          label="Digest retention (per source)"
          value={settings.digest_retention}
          min={1}
          max={365}
          onChange={(digest_retention) => setSettings({ ...settings, digest_retention })}
        />
        <label className="block text-sm">
          <span className="font-medium">OPDS catalog title</span>
          <input
            className="mt-1 w-full rounded-xl border border-rule bg-white px-3 py-2"
            value={settings.opds_title}
            onChange={(event) => setSettings({ ...settings, opds_title: event.target.value })}
          />
        </label>
        <button type="submit" disabled={busy} className="rounded-full bg-ink px-4 py-2 text-sm text-paper disabled:opacity-50">
          Save settings
        </button>
      </form>
      {message && <p className="text-sm">{message}</p>}
      <p className="text-sm text-ink/60">
        Schedule times are in the server’s local timezone. Only hour and minute are used — the job runs once per day.
      </p>
    </div>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block text-sm">
      <span className="font-medium">{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        className="mt-1 w-full rounded-xl border border-rule bg-white px-3 py-2"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}
