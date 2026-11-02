import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppSettings, api } from "../../../api";
import { Card, ErrorMsg } from "../../../ui";

export default function PortalSettings() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Portal</h1>
      <PortalCard />
    </div>
  );
}

function PortalCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["lookup", "settings"], queryFn: () => api<AppSettings>("/settings") });
  const save = useMutation({
    mutationFn: (portal_enabled: boolean) => api("/settings", { method: "PATCH", json: { portal_enabled } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lookup"] }),
  });
  if (!q.data) return null;
  return (
    <Card title="Client portal">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={q.data.portal_enabled} onChange={(e) => save.mutate(e.target.checked)} />
        Turn the client portal on
      </label>
      <p className="mt-2 text-xs text-slate-500">Clients sign in at /portal with a one-time link emailed to a contact you have given portal access (Organizations &gt; contact). Needs the mailbox configured. Turning this off signs everyone out at once.</p>
      <ErrorMsg error={save.error} />
    </Card>
  );
}
