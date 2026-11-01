import { useState } from "react";

/** Fetches a file the same way api() does (same-origin cookies + CSRF header) and saves it, or sets an inline error. */
export function useDownload(what: string) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const run = async (url: string, fallbackName: string) => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const res = await fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "psa" } });
      if (!res.ok) {
        let detail = "";
        try {
          const body = await res.json();
          if (typeof body.detail === "string") detail = body.detail;
        } catch {
          /* not JSON */
        }
        const why = res.status === 401 || res.status === 403 ? "your session may have expired. Sign in again and retry." : "please try again.";
        setError(`${what} failed: ${why}${detail ? ` (${detail})` : ""}`);
        return;
      }
      const name = /filename="?([^";]+)"?/i.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? fallbackName;
      const href = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = href;
      a.download = name;
      a.click();
      URL.revokeObjectURL(href);
      if (res.headers.get("X-Export-Truncated") === "true") setNote("Only the first 10,000 rows were exported.");
    } catch {
      setError(`${what} failed: could not reach the server. Check your connection and retry.`);
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, note, run };
}

export function DownloadStatus({ error, note }: { error: string | null; note?: string | null }) {
  if (error) return <p role="alert" className="text-sm text-red-700">{error}</p>;
  return note ? <p role="status" className="text-sm text-slate-600">{note}</p> : null;
}

export default function ExportButton({ kind, label }: { kind: "tickets" | "invoices" | "devices"; label: string }) {
  const d = useDownload("Export");
  return (
    <span>
      <button
        type="button"
        className="text-sm text-blue-700 hover:underline disabled:opacity-60"
        disabled={d.busy}
        onClick={() => d.run(`/api/v1/portal/export/${kind}.csv`, `${kind}.csv`)}
      >
        {d.busy ? "Exporting…" : label}
      </button>
      <DownloadStatus error={d.error} note={d.note} />
    </span>
  );
}
