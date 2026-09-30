import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Me, api } from "../api";
import { useMe } from "../auth";
import { Card, ErrorMsg } from "../ui";

const OPTIONS: { key: "notify_assigned" | "notify_sla" | "notify_reply"; label: string; help: string }[] = [
  { key: "notify_assigned", label: "A ticket is assigned to me", help: "Not sent when you assign a ticket to yourself." },
  { key: "notify_sla", label: "My ticket is at risk of breaching its SLA, or has breached", help: "Once for each state." },
  { key: "notify_reply", label: "A customer replies on my ticket", help: "The email has a link, not the customer's message." },
];

export default function Profile() {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: (patch: Partial<Pick<Me, "notify_assigned" | "notify_sla" | "notify_reply">>) => api("/auth/me/notifications", { method: "PATCH", json: patch }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
  if (!me) return null;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Your settings</h1>
      <Card title="Email me when…">
        <p className="mb-2 text-sm text-slate-600">Sent to {me.email} from the support mailbox, only about tickets assigned to you.</p>
        <ul className="space-y-2 text-sm">
          {OPTIONS.map((o) => (
            <li key={o.key}>
              <label className="flex items-start gap-2">
                <input type="checkbox" className="mt-1" checked={me[o.key]} onChange={(e) => save.mutate({ [o.key]: e.target.checked })} />
                <span>{o.label}<span className="block text-xs text-slate-500">{o.help}</span></span>
              </label>
            </li>
          ))}
        </ul>
        <ErrorMsg error={save.error} />
      </Card>
    </div>
  );
}
