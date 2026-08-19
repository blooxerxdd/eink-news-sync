import { useEffect, useState } from "react";
import { api, formatBytes, formatWhen } from "../api";
import Copyable from "../components/Copyable";
import type { DigestInfo, StatusPayload } from "../types";

export default function Digests() {
  const [digests, setDigests] = useState<DigestInfo[]>([]);
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.digests(), api.status()])
      .then(([files, payload]) => {
        setDigests(files);
        setStatus(payload);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load digests"));
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="font-serif text-4xl">Digests</h1>
      {error && <p className="text-rust">{error}</p>}
      {status && (
        <section className="space-y-4 rounded-2xl border border-rule bg-white/50 p-5">
          <Copyable label="Local IP" value={status.lan_ip ?? "Not detected"} />
          <Copyable label="OPDS URL for the e-reader" value={status.opds_url} />
        </section>
      )}
      <div className="overflow-x-auto rounded-2xl border border-rule bg-white/50">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="border-b border-rule text-xs uppercase tracking-[0.14em] text-ink/50">
            <tr>
              <th className="px-4 py-3">File</th>
              <th className="px-4 py-3">Modified</th>
              <th className="px-4 py-3">Size</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {digests.length === 0 && (
              <tr>
                <td className="px-4 py-8 text-ink/60" colSpan={4}>
                  No EPUB files yet. Run a sync after configuring a source.
                </td>
              </tr>
            )}
            {digests.map((digest) => (
              <tr key={digest.filename} className="border-b border-rule/70 last:border-0">
                <td className="px-4 py-3 font-mono text-xs">{digest.filename}</td>
                <td className="px-4 py-3">{formatWhen(digest.modified_at)}</td>
                <td className="px-4 py-3">{formatBytes(digest.size_bytes)}</td>
                <td className="px-4 py-3">
                  <a className="underline" href={digest.download_url}>
                    Download
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
