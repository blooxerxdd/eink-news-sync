import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { ConfigField, SourceInfo } from "../types";

export default function Sources() {
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [secretsSet, setSecretsSet] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const current = useMemo(
    () => sources.find((source) => source.source_id === selected) ?? sources[0],
    [sources, selected],
  );

  async function load(sourceId?: string) {
    const list = await api.sources();
    setSources(list);
    const id = sourceId || list.find((s) => s.is_active)?.source_id || list[0]?.source_id;
    if (!id) return;
    setSelected(id);
    const cfg = await api.sourceConfig(id);
    setValues(cfg.config);
    setSecretsSet(cfg.secrets_set);
    setLoaded(true);
  }

  useEffect(() => {
    void load().catch((err: unknown) => setMessage(err instanceof Error ? err.message : "Failed to load"));
  }, []);

  function setField(key: string, value: unknown) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  async function onSave(event: FormEvent) {
    event.preventDefault();
    if (!current) return;
    setBusy(true);
    setMessage(null);
    try {
      const saved = await api.saveSourceConfig(current.source_id, values);
      setValues(saved.config);
      setProblems(saved.problems ?? []);
      setMessage("Saved.");
      await load(current.source_id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function onValidate() {
    if (!current) return;
    setBusy(true);
    try {
      const result = await api.validateSource(current.source_id, values);
      setProblems(result.problems);
      setMessage(result.ok ? "Configuration looks valid." : "Configuration has problems.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Validate failed");
    } finally {
      setBusy(false);
    }
  }

  async function onActivate() {
    if (!current) return;
    setBusy(true);
    try {
      await api.activateSource(current.source_id);
      setMessage(`${current.display_name} will be included in the next sync.`);
      await load(current.source_id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not include source");
    } finally {
      setBusy(false);
    }
  }

  async function onDeactivate() {
    if (!current) return;
    setBusy(true);
    try {
      await api.deactivateSource(current.source_id);
      setMessage(`${current.display_name} will be skipped on the next sync.`);
      await load(current.source_id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not exclude source");
    } finally {
      setBusy(false);
    }
  }

  if (!current || !loaded) return <p className="text-ink/60">Loading…</p>;

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="font-serif text-4xl">Source configuration</h1>
      <p className="text-ink/70">
        Include each source you want in the daily sync. A run builds one EPUB per included source; they all appear in
        the same OPDS catalog.
      </p>
      <label className="block text-sm">
        <span className="text-xs uppercase tracking-[0.14em] text-ink/50">Source</span>
        <select
          className="mt-1 w-full rounded-xl border border-rule bg-white px-3 py-2"
          value={current.source_id}
          onChange={(event) => void load(event.target.value)}
        >
          {sources.map((source) => (
            <option key={source.source_id} value={source.source_id}>
              {source.display_name}
              {source.is_active ? " (in sync)" : ""}
            </option>
          ))}
        </select>
      </label>

      <form onSubmit={(event) => void onSave(event)} className="space-y-4 rounded-2xl border border-rule bg-white/50 p-5">
        {current.config_fields.map((field) => (
          <FieldInput
            key={field.key}
            field={field}
            value={values[field.key]}
            secretIsSet={secretsSet.includes(field.key)}
            onChange={(value) => setField(field.key, value)}
          />
        ))}
        <div className="flex flex-wrap gap-2 pt-2">
          <button type="submit" disabled={busy} className="rounded-full bg-ink px-4 py-2 text-sm text-paper disabled:opacity-50">
            Save
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void onValidate()}
            className="rounded-full border border-ink px-4 py-2 text-sm disabled:opacity-50"
          >
            Test configuration
          </button>
          {!current.is_active ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void onActivate()}
              className="rounded-full border border-ink px-4 py-2 text-sm disabled:opacity-50"
            >
              Include in sync
            </button>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={() => void onDeactivate()}
              className="rounded-full border border-ink px-4 py-2 text-sm disabled:opacity-50"
            >
              Exclude from sync
            </button>
          )}
        </div>
      </form>

      {message && <p className="text-sm">{message}</p>}
      {problems.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-sm text-rust">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FieldInput({
  field,
  value,
  secretIsSet,
  onChange,
}: {
  field: ConfigField;
  value: unknown;
  secretIsSet: boolean;
  onChange: (value: unknown) => void;
}) {
  if (field.type === "secret") {
    return (
      <label className="block text-sm">
        <span className="font-medium">{field.label}</span>
        <input
          type="password"
          autoComplete="off"
          placeholder={secretIsSet ? "Saved — leave unchanged to keep" : "Required"}
          className="mt-1 w-full rounded-xl border border-rule bg-white px-3 py-2"
          value={typeof value === "string" && !value.includes("•") ? value : ""}
          onChange={(event) => onChange(event.target.value)}
        />
        {field.help && <p className="mt-1 text-xs text-ink/50">{field.help}</p>}
      </label>
    );
  }

  if (field.type === "number") {
    return (
      <label className="block text-sm">
        <span className="font-medium">{field.label}</span>
        <input
          type="number"
          className="mt-1 w-full rounded-xl border border-rule bg-white px-3 py-2"
          value={value == null ? "" : String(value)}
          onChange={(event) => onChange(event.target.value === "" ? field.default : Number(event.target.value))}
        />
        {field.help && <p className="mt-1 text-xs text-ink/50">{field.help}</p>}
      </label>
    );
  }

  if (field.type === "tags") {
    const tags = Array.isArray(value) ? (value as string[]) : [];
    return (
      <label className="block text-sm">
        <span className="font-medium">{field.label}</span>
        <input
          type="text"
          className="mt-1 w-full rounded-xl border border-rule bg-white px-3 py-2"
          defaultValue={tags.join(", ")}
          placeholder="world, business, technology"
          onBlur={(event) =>
            onChange(
              event.target.value
                .split(",")
                .map((part) => part.trim())
                .filter(Boolean),
            )
          }
        />
        {field.help && <p className="mt-1 text-xs text-ink/50">{field.help}</p>}
      </label>
    );
  }

  return (
    <label className="block text-sm">
      <span className="font-medium">{field.label}</span>
      <input
        type="text"
        className="mt-1 w-full rounded-xl border border-rule bg-white px-3 py-2"
        value={value == null ? "" : String(value)}
        onChange={(event) => onChange(event.target.value)}
      />
      {field.help && <p className="mt-1 text-xs text-ink/50">{field.help}</p>}
    </label>
  );
}
