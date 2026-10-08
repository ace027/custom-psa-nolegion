import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Contact, Organization, Site, api } from "../api";
import { can, useMe } from "../auth";
import { Button, Card, ErrorMsg, Field, inputCls } from "../ui";
import OrgAssetsCard from "./OrgAssetsCard";
import OrgBillingCard from "./OrgBillingCard";

export default function OrganizationDetail() {
  const id = Number(useParams().id);
  const { data: me } = useMe();
  const canWrite = can(me, "org:write");
  const qc = useQueryClient();
  const refresh = () => qc.invalidateQueries();

  const org = useQuery({ queryKey: ["org", id], queryFn: () => api<Organization>(`/organizations/${id}`) });
  const sites = useQuery({
    queryKey: ["sites", id],
    queryFn: () => api<Site[]>(`/organizations/${id}/sites?include_archived=true`),
  });
  const contacts = useQuery({
    queryKey: ["contacts", id],
    queryFn: () => api<Contact[]>(`/organizations/${id}/contacts?include_archived=true`),
  });

  if (org.isLoading) return <p>Loading…</p>;
  if (!org.data) return <ErrorMsg error={org.error ?? "Not found"} />;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">
        {org.data.name}
        {org.data.archived_at && <span className="ml-2 text-sm text-slate-500">(archived)</span>}
      </h1>
      <OrgForm org={org.data} canWrite={canWrite} onDone={refresh} />
      {can(me, "billing:read") && <OrgBillingCard orgId={id} />}
      <OrgAssetsCard org={org.data} />
      <SitesCard orgId={id} sites={sites.data ?? []} canWrite={canWrite} onDone={refresh} />
      <ContactsCard
        orgId={id}
        contacts={contacts.data ?? []}
        sites={sites.data ?? []}
        canWrite={canWrite}
        onDone={refresh}
      />
    </div>
  );
}

function OrgForm({ org, canWrite, onDone }: { org: Organization; canWrite: boolean; onDone: () => void }) {
  const [form, setForm] = useState(org);
  useEffect(() => setForm(org), [org]);
  const save = useMutation({
    mutationFn: () =>
      api(`/organizations/${org.id}`, {
        method: "PATCH",
        json: { name: form.name, status: form.status, billing_address: form.billing_address, notes: form.notes },
      }),
    onSuccess: onDone,
  });
  const archive = useMutation({
    mutationFn: () => api(`/organizations/${org.id}/${org.archived_at ? "unarchive" : "archive"}`, { method: "POST" }),
    onSuccess: onDone,
  });
  return (
    <Card title="Details">
      <form
        className="grid gap-3 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label="Name">
          <input className={inputCls} disabled={!canWrite} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label="Status">
          <select className={inputCls} disabled={!canWrite} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as Organization["status"] })}>
            <option value="active">active</option>
            <option value="inactive">inactive</option>
            <option value="prospect">prospect</option>
          </select>
        </Field>
        <Field label="Billing address">
          <textarea className={inputCls} disabled={!canWrite} value={form.billing_address ?? ""} onChange={(e) => setForm({ ...form, billing_address: e.target.value })} />
        </Field>
        <Field label="Notes">
          <textarea className={inputCls} disabled={!canWrite} value={form.notes ?? ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </Field>
        <div className="col-span-full space-y-2">
          <ErrorMsg error={save.error ?? archive.error} />
          {canWrite && (
            <div className="flex gap-2">
              <Button type="submit" disabled={save.isPending}>Save</Button>
              <Button type="button" variant="danger" onClick={() => archive.mutate()}>
                {org.archived_at ? "Restore" : "Archive"}
              </Button>
            </div>
          )}
        </div>
      </form>
    </Card>
  );
}

function SitesCard({ orgId, sites, canWrite, onDone }: { orgId: number; sites: Site[]; canWrite: boolean; onDone: () => void }) {
  const [name, setName] = useState("");
  const [city, setCity] = useState("");
  const add = useMutation({
    mutationFn: () => api(`/organizations/${orgId}/sites`, { method: "POST", json: { name, city: city || null } }),
    onSuccess: () => {
      setName("");
      setCity("");
      onDone();
    },
  });
  const toggle = useMutation({
    mutationFn: (s: Site) => api(`/sites/${s.id}/${s.archived_at ? "unarchive" : "archive"}`, { method: "POST" }),
    onSuccess: onDone,
  });
  return (
    <Card title="Sites">
      <ul className="divide-y divide-slate-100 text-sm">
        {sites.map((s) => (
          <li key={s.id} className="flex items-center justify-between py-1.5">
            <span className={s.archived_at ? "text-slate-400 line-through" : ""}>
              {s.name}
              {s.city ? ` — ${s.city}` : ""}
            </span>
            {canWrite && (
              <Button variant="secondary" onClick={() => toggle.mutate(s)}>
                {s.archived_at ? "Restore" : "Archive"}
              </Button>
            )}
          </li>
        ))}
      </ul>
      <ErrorMsg error={add.error ?? toggle.error} />
      {canWrite && (
        <form
          className="mt-3 flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <Field label="Site name">
            <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <Field label="City">
            <input className={inputCls} value={city} onChange={(e) => setCity(e.target.value)} />
          </Field>
          <Button type="submit">Add site</Button>
        </form>
      )}
    </Card>
  );
}

function ContactsCard({ orgId, contacts, sites, canWrite, onDone }: { orgId: number; contacts: Contact[]; sites: Site[]; canWrite: boolean; onDone: () => void }) {
  const blank = { name: "", email: "", phone: "", title: "", site_id: "", is_primary: false, is_billing_contact: false };
  const [form, setForm] = useState(blank);
  const add = useMutation({
    mutationFn: () =>
      api(`/organizations/${orgId}/contacts`, {
        method: "POST",
        json: {
          name: form.name,
          email: form.email || null,
          phone: form.phone || null,
          title: form.title || null,
          site_id: form.site_id ? Number(form.site_id) : null,
          is_primary: form.is_primary,
          is_billing_contact: form.is_billing_contact,
        },
      }),
    onSuccess: () => {
      setForm(blank);
      onDone();
    },
  });
  const toggle = useMutation({
    mutationFn: (c: Contact) => api(`/contacts/${c.id}/${c.archived_at ? "unarchive" : "archive"}`, { method: "POST" }),
    onSuccess: onDone,
  });
  const portal = useMutation({
    mutationFn: ({ c, patch }: { c: Contact; patch: Partial<Pick<Contact, "portal_access" | "portal_org_tickets" | "portal_assets">> }) => api(`/contacts/${c.id}`, { method: "PATCH", json: patch }),
    onSuccess: onDone,
  });
  const { data: me } = useMe();
  const isAdmin = can(me, "portal:manage");
  const makePrimary = useMutation({
    mutationFn: (c: Contact) => api(`/contacts/${c.id}`, { method: "PATCH", json: { is_primary: true } }),
    onSuccess: onDone,
  });
  return (
    <Card title="Contacts">
      <ul className="divide-y divide-slate-100 text-sm">
        {contacts.map((c) => (
          <li key={c.id} className="flex items-center justify-between py-1.5">
            <span className={c.archived_at ? "text-slate-400 line-through" : ""}>
              {c.name}
              {c.title ? `, ${c.title}` : ""}
              {c.email ? ` <${c.email}>` : ""}
              {c.is_primary && <b className="ml-2 text-xs text-blue-700">primary</b>}
              {c.is_billing_contact && <b className="ml-2 text-xs text-green-700">billing</b>}
              {c.portal_access && <b className="ml-2 text-xs text-purple-700">portal{c.portal_org_tickets ? " (all company tickets)" : ""}{c.portal_assets ? " (devices)" : ""}</b>}
            </span>
            {canWrite && (
              <span className="flex gap-2">
                {!c.is_primary && !c.archived_at && (
                  <Button variant="secondary" onClick={() => makePrimary.mutate(c)}>Make primary</Button>
                )}
                {!c.archived_at && c.email && !c.portal_access && isAdmin && (
                  <Button variant="secondary" onClick={() => portal.mutate({ c, patch: { portal_access: true } })}>Give portal access</Button>
                )}
                {c.portal_access && (
                  <Button variant="secondary" onClick={() => portal.mutate({ c, patch: { portal_access: false, portal_org_tickets: false, portal_assets: false } })}>Remove portal access</Button>
                )}
                {c.portal_access && isAdmin && (
                  <Button variant="secondary" onClick={() => portal.mutate({ c, patch: { portal_org_tickets: !c.portal_org_tickets } })}>{c.portal_org_tickets ? "Own tickets only" : "See all company tickets"}</Button>
                )}
                {c.portal_access && isAdmin && (
                  <Button variant="secondary" onClick={() => portal.mutate({ c, patch: { portal_assets: !c.portal_assets } })}>{c.portal_assets ? "Hide devices" : "Show devices"}</Button>
                )}
                <Button variant="secondary" onClick={() => toggle.mutate(c)}>
                  {c.archived_at ? "Restore" : "Archive"}
                </Button>
              </span>
            )}
          </li>
        ))}
      </ul>
      <ErrorMsg error={add.error ?? toggle.error ?? makePrimary.error ?? portal.error} />
      {canWrite && (
        <form
          className="mt-3 grid gap-2 sm:grid-cols-3"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <Field label="Name"><input className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field>
          <Field label="Email"><input className={inputCls} type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label="Phone"><input className={inputCls} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
          <Field label="Title"><input className={inputCls} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
          <Field label="Site">
            <select className={inputCls} value={form.site_id} onChange={(e) => setForm({ ...form, site_id: e.target.value })}>
              <option value="">—</option>
              {sites.filter((s) => !s.archived_at).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <div className="flex items-end gap-4 text-sm">
            <label className="flex items-center gap-1"><input type="checkbox" checked={form.is_primary} onChange={(e) => setForm({ ...form, is_primary: e.target.checked })} />Primary</label>
            <label className="flex items-center gap-1"><input type="checkbox" checked={form.is_billing_contact} onChange={(e) => setForm({ ...form, is_billing_contact: e.target.checked })} />Billing</label>
          </div>
          <div className="col-span-full"><Button type="submit">Add contact</Button></div>
        </form>
      )}
    </Card>
  );
}
