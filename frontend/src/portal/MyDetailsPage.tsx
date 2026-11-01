import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { PortalMe, api } from "../api";
import { Button, Card, ErrorMsg, Field, inputCls } from "../ui";

export default function MyDetailsPage({ me }: { me: PortalMe }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ name: me.contact_name, phone: me.phone ?? "", title: me.title ?? "" });
  const save = useMutation({
    mutationFn: () => api<PortalMe>("/portal/me/contact", { method: "PATCH", json: { name: f.name, phone: f.phone || null, title: f.title || null } }),
    onSuccess: (d) => qc.setQueryData(["portal", "me"], d),
  });
  return (
    <Card title="My details">
      <form className="max-w-md space-y-3" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <Field label="Email address">
          <input className={`${inputCls} cursor-not-allowed !bg-slate-100 text-slate-500`} value={me.email ?? ""} readOnly aria-describedby="me-email-note" />
        </Field>
        <p id="me-email-note" className="text-xs text-slate-500">Contact us to change your email</p>
        <Field label="Name"><input className={inputCls} required maxLength={200} value={f.name} onChange={(e) => { save.reset(); setF({ ...f, name: e.target.value }); }} /></Field>
        <Field label="Phone"><input className={inputCls} maxLength={50} autoComplete="tel" value={f.phone} onChange={(e) => { save.reset(); setF({ ...f, phone: e.target.value }); }} /></Field>
        <Field label="Title"><input className={inputCls} maxLength={100} value={f.title} onChange={(e) => { save.reset(); setF({ ...f, title: e.target.value }); }} /></Field>
        <Button type="submit" disabled={save.isPending || !f.name.trim()}>Save</Button>
      </form>
      <ErrorMsg error={save.error} />
      {save.isSuccess && <p role="status" className="mt-3 rounded bg-green-50 p-2 text-sm text-green-800">Saved</p>}
    </Card>
  );
}
