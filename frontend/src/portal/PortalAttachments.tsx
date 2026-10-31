import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { PORTAL_MAX_UPLOAD_BYTES, PORTAL_UPLOAD_EXTENSIONS, PortalAttachment, api } from "../api";
import { Card, ErrorMsg, fmt } from "../ui";

function readBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).replace(/^data:[^,]*,/, ""));
    r.onerror = () => reject(new Error("Could not read that file"));
    r.readAsDataURL(file);
  });
}

export function checkFile(file: { name: string; size: number }): string | null {
  if (file.size > PORTAL_MAX_UPLOAD_BYTES) return "That file is larger than 10 MB.";
  const ext = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  if (!PORTAL_UPLOAD_EXTENSIONS.includes(ext)) return "That file type is not allowed.";
  return null;
}

export default function PortalAttachments({ ticketId, closed }: { ticketId: number; closed: boolean }) {
  const qc = useQueryClient();
  const key = ["portal", "attachments", ticketId];
  const list = useQuery({ queryKey: key, queryFn: () => api<PortalAttachment[]>(`/portal/tickets/${ticketId}/attachments`) });
  const [problem, setProblem] = useState<string | null>(null);
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const content_base64 = await readBase64(file);
      return api<PortalAttachment>(`/portal/tickets/${ticketId}/attachments`, { method: "POST", json: { filename: file.name, content_base64 } });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
  return (
    <Card title="Attachments">
      <ErrorMsg error={list.error} />
      <ul className="divide-y divide-slate-100 text-sm">
        {list.data?.map((a) => (
          <li key={a.id} className="flex items-center justify-between py-1.5">
            <a className="text-blue-700 hover:underline" href={`/api/v1/portal/attachments/${a.id}/download`}>{a.filename}</a>
            <span className="text-slate-500">{Math.ceil(a.size_bytes / 1024)} KB · {fmt(a.created_at)}</span>
          </li>
        ))}
        {list.data?.length === 0 && <li className="py-1.5 text-slate-500">No files attached.</li>}
      </ul>
      {closed ? (
        <p className="mt-3 text-sm text-slate-500">This ticket is closed, so files can no longer be added.</p>
      ) : (
        <div className="mt-3 space-y-2">
          <label className="block text-sm">
            <span className="mb-1 block text-slate-600">Attach a file (up to 10 MB: {PORTAL_UPLOAD_EXTENSIONS.join(", ")})</span>
            <input
              type="file"
              disabled={upload.isPending}
              onChange={(e) => {
                const input = e.target;
                const file = input.files?.[0];
                upload.reset();
                if (!file) return;
                const bad = checkFile(file);
                setProblem(bad);
                if (!bad) upload.mutate(file);
                input.value = "";
              }}
            />
          </label>
          {upload.isPending && <p role="status" className="text-sm text-slate-600">Uploading…</p>}
          {upload.isSuccess && <p role="status" className="text-sm text-green-800">File attached.</p>}
          {problem && <p role="alert" className="text-sm text-red-700">{problem}</p>}
          <ErrorMsg error={upload.error} />
        </div>
      )}
    </Card>
  );
}
