import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Statement, api } from "../../api";
import { can, useMe } from "../../auth";
import { Button, ErrorMsg } from "../../ui";

/** Generate a statement (a frozen snapshot), download its PDF, or queue it for review to email. */
export default function StatementActions({ orgId }: { orgId: number }) {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const nav = useNavigate();
  const make = () => api<Statement>(`/organizations/${orgId}/statements`, { method: "POST" });
  const pdf = useMutation({ mutationFn: make, onSuccess: (s) => window.open(`/api/statements/${s.id}/pdf`, "_blank") });
  const email = useMutation({
    mutationFn: async () => {
      const s = await make();
      return api(`/statements/${s.id}/email`, { method: "POST", json: { send: false } });
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["notices"] }); nav("/billing/reminders"); },
  });
  if (!can(me, "billing:write")) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button variant="secondary" onClick={() => pdf.mutate()}>Statement PDF</Button>
      <Button variant="secondary" onClick={() => email.mutate()}>Prepare statement email</Button>
      <ErrorMsg error={pdf.error ?? email.error} />
    </span>
  );
}
