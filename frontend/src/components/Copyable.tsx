import { useState } from "react";

export default function Copyable({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="text-xs uppercase tracking-[0.16em] text-ink/50">{label}</p>
        <p className="mt-1 break-all font-mono text-sm">{value}</p>
      </div>
      <button type="button" onClick={() => void copy()} className="shrink-0 rounded-full border border-ink px-3 py-1 text-sm">
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
