import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { WARRANTY_LABEL, ApiError, PortalAssets, PortalInvoice, PortalInvoiceDetail, PortalMe, PortalTicket, PortalTicketDetail, api } from "../api";
import { money } from "../money";
import { Button, Card, ErrorMsg, Field, StatTile, ThemeToggle, WarrantyBadge, fmt, inputCls } from "../ui";

function usePortalMe() {
  return useQuery({
    queryKey: ["portal", "me"],
    retry: false,
    queryFn: async (): Promise<PortalMe | null> => {
      try {
        return await api<PortalMe>("/portal/me");
      } catch (e) {
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return null;
        throw e;
      }
    },
  });
}

export default function PortalApp() {
  return (
    <Routes>
      <Route path="/portal/verify" element={<Verify />} />
      <Route path="/portal/*" element={<Gate />} />
    </Routes>
  );
}

function Shell({ title, right, children }: { title?: string; right?: React.ReactNode; children: React.ReactNode }) {
  const name = title ?? "Client portal";
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-surface">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <div className="flex items-center gap-2.5 font-bold text-slate-900">
            <span aria-hidden className="grid h-7 w-7 place-items-center rounded-lg bg-blue-600 text-sm text-on-accent">{name[0]?.toUpperCase()}</span>
            {name}
          </div>
          <div className="ml-auto flex flex-wrap items-center justify-end gap-x-3 gap-y-1 text-sm text-slate-500 [&_button]:whitespace-nowrap">{right}<ThemeToggle /></div>
        </div>
      </header>
      <div className="mx-auto max-w-4xl p-4 sm:py-6">{children}</div>
    </div>
  );
}

function Gate() {
  const me = usePortalMe();
  if (me.isLoading) return <Shell><p>Loading…</p></Shell>;
  if (me.error) return <Shell><ErrorMsg error={me.error} /></Shell>;
  if (!me.data) return <SignIn />;
  return <Signed me={me.data} />;
}

function SignIn() {
  const [email, setEmail] = useState("");
  const ask = useMutation({ mutationFn: () => api<{ detail: string }>("/portal/login-link", { method: "POST", json: { email } }) });
  return (
    <Shell>
      <Card title="Sign in">
        <p className="mb-3 text-sm text-slate-600">Enter your email address and we will send you a one-time sign-in link. There is no password.</p>
        <form className="space-y-3" onSubmit={(e: FormEvent) => { e.preventDefault(); ask.mutate(); }}>
          <Field label="Email address"><input className={inputCls} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Button type="submit" disabled={ask.isPending}>Email me a link</Button>
        </form>
        <ErrorMsg error={ask.error} />
        {ask.data && <p role="status" className="mt-3 rounded bg-green-50 p-2 text-sm text-green-800">{ask.data.detail} Check your inbox; the link expires in a few minutes.</p>}
      </Card>
    </Shell>
  );
}

function Verify() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const redeem = useMutation({
    mutationFn: (token: string) => api<PortalMe>("/portal/verify", { method: "POST", json: { token } }),
    onSuccess: (me) => { qc.setQueryData(["portal", "me"], me); nav("/portal", { replace: true }); },
  });
  useEffect(() => {
    // The token travels in the URL fragment so it is never sent to a server, log or referrer.
    const token = new URLSearchParams(window.location.hash.replace(/^#/, "")).get("token");
    window.history.replaceState(null, "", window.location.pathname);
    if (token) redeem.mutate(token);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <Shell>
      {redeem.isError ? (
        <Card title="This link cannot be used"><p className="text-sm">It has expired or was already used. <Link className="text-blue-700 underline" to="/portal">Ask for a new one</Link>.</p></Card>
      ) : <p>Signing you in…</p>}
    </Shell>
  );
}

function Signed({ me }: { me: PortalMe }) {
  const qc = useQueryClient();
  const logout = useMutation({
    mutationFn: () => api("/portal/logout", { method: "POST" }),
    onSuccess: () => { qc.clear(); qc.setQueryData(["portal", "me"], null); },
  });
  const tab = ({ isActive }: { isActive: boolean }) => `rounded-lg px-3.5 py-1.5 text-sm ${isActive ? "bg-blue-50 font-semibold text-blue-700" : "text-slate-500 hover:bg-slate-100"}`;
  return (
    <Shell
      title={me.company_name ? `${me.company_name} client portal` : undefined}
      right={<><span>{me.contact_name} · {me.organization_name}</span><button className="text-blue-700 hover:underline" onClick={() => logout.mutate()}>Sign out</button></>}
    >
      <nav className="mb-5 flex gap-1">
        <NavLink to="/portal/tickets" className={tab}>Tickets</NavLink>
        {me.can_see_billing && <NavLink to="/portal/invoices" className={tab}>Invoices</NavLink>}
        {me.can_see_devices && <NavLink to="/portal/devices" className={tab}>Devices</NavLink>}
      </nav>
      <Routes>
        <Route index element={<Navigate to="/portal/tickets" replace />} />
        <Route path="tickets" element={<Tickets />} />
        <Route path="tickets/:id" element={<TicketPage />} />
        {me.can_see_billing && <Route path="invoices" element={<Invoices />} />}
        {me.can_see_billing && <Route path="invoices/:id" element={<InvoicePage />} />}
        {me.can_see_devices && <Route path="devices" element={<Devices />} />}
        <Route path="*" element={<Navigate to="/portal/tickets" replace />} />
      </Routes>
    </Shell>
  );
}

function Tickets() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["portal", "tickets"], queryFn: () => api<PortalTicket[]>("/portal/tickets") });
  const [f, setF] = useState({ subject: "", description: "" });
  const nav = useNavigate();
  const open = useMutation({
    mutationFn: () => api<PortalTicket>("/portal/tickets", { method: "POST", json: f }),
    onSuccess: (t) => { setF({ subject: "", description: "" }); qc.invalidateQueries({ queryKey: ["portal", "tickets"] }); nav(`/portal/tickets/${t.id}`); },
  });
  return (
    <div className="space-y-4">
      <Card title="Open a new ticket">
        <form className="space-y-2" onSubmit={(e: FormEvent) => { e.preventDefault(); open.mutate(); }}>
          <Field label="Subject"><input className={inputCls} required minLength={3} maxLength={200} value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} /></Field>
          <Field label="What is happening?"><textarea className={inputCls} required rows={5} maxLength={10000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <Button type="submit" disabled={open.isPending}>Send</Button>
        </form>
        <ErrorMsg error={open.error} />
      </Card>
      <Card title="Your tickets">
        <ErrorMsg error={list.error} />
        <ul className="divide-y divide-slate-100 text-sm">
          {list.data?.map((t) => (
            <li key={t.id} className="flex items-center justify-between py-2">
              <Link className="text-blue-700 hover:underline" to={`/portal/tickets/${t.id}`}>#{t.number} {t.subject}</Link>
              <span className="text-slate-500">{t.status_name ?? t.status.replace(/_/g, " ")} · {fmt(t.updated_at)}</span>
            </li>
          ))}
          {list.data?.length === 0 && <li className="py-2 text-slate-500">No tickets yet.</li>}
        </ul>
      </Card>
    </div>
  );
}

function TicketPage() {
  const { id } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["portal", "ticket", id], queryFn: () => api<PortalTicketDetail>(`/portal/tickets/${id}`) });
  const [body, setBody] = useState("");
  const reply = useMutation({
    mutationFn: () => api<PortalTicketDetail>(`/portal/tickets/${id}/reply`, { method: "POST", json: { body } }),
    onSuccess: (d) => { setBody(""); qc.setQueryData(["portal", "ticket", id], d); qc.invalidateQueries({ queryKey: ["portal", "tickets"] }); },
  });
  const t = q.data;
  return (
    <div className="space-y-4">
      <Link className="text-sm text-blue-700 hover:underline" to="/portal/tickets">← All tickets</Link>
      <ErrorMsg error={q.error} />
      {t && (
        <>
          <h2 className="text-lg font-semibold">#{t.number} {t.subject} <span className="ml-2 rounded bg-slate-100 px-2 py-0.5 text-xs font-normal">{t.status_name ?? t.status.replace(/_/g, " ")}</span></h2>
          {t.description && <Card title="Original request"><p className="whitespace-pre-wrap text-sm">{t.description}</p></Card>}
          {t.notes.map((n) => (
            <div key={n.id} className={`rounded-lg border p-3 text-sm ${n.from_support ? "border-blue-200 bg-blue-50" : "border-slate-200 bg-surface"}`}>
              <div className="mb-1 text-xs text-slate-500">{n.author} · {fmt(n.created_at)}</div>
              <p className="whitespace-pre-wrap">{n.body}</p>
            </div>
          ))}
          <form className="space-y-2" onSubmit={(e: FormEvent) => { e.preventDefault(); reply.mutate(); }}>
            <Field label="Add a reply"><textarea className={inputCls} required rows={4} maxLength={10000} value={body} onChange={(e) => setBody(e.target.value)} /></Field>
            <Button type="submit" disabled={reply.isPending || !body.trim()}>Send reply</Button>
          </form>
          <ErrorMsg error={reply.error} />
        </>
      )}
    </div>
  );
}

const STATUS: Record<PortalInvoice["status"], string> = { paid: "Paid", partial: "Partly paid", unpaid: "Unpaid", written_off: "Closed" };

function Invoices() {
  const q = useQuery({ queryKey: ["portal", "invoices"], queryFn: () => api<PortalInvoice[]>("/portal/invoices") });
  return (
    <Card title="Invoices" actions={<a className="text-sm text-blue-700 hover:underline" href="/api/portal/statement/pdf">Download account statement</a>}>
      <ErrorMsg error={q.error} />
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-1">Invoice</th><th>Date</th><th>Due</th><th className="text-right">Total</th><th className="text-right">Balance</th><th /></tr></thead>
        <tbody>
          {q.data?.map((i) => (
            <tr key={i.id} className="border-b border-slate-100">
              <td className="p-1"><Link className="text-blue-700 hover:underline" to={`/portal/invoices/${i.id}`}>{i.number}</Link></td>
              <td>{i.invoice_date}</td><td>{i.due_date}</td>
              <td className="text-right">{money(i.total_cents)}</td><td className="text-right">{money(i.balance_cents)}</td>
              <td className="pl-3"><span className={i.is_overdue ? "font-medium text-red-700" : ""}>{i.is_overdue ? `${i.days_past_due} days overdue` : STATUS[i.status]}</span></td>
            </tr>
          ))}
          {q.data?.length === 0 && <tr><td colSpan={6} className="p-2 text-slate-500">No invoices yet.</td></tr>}
        </tbody>
      </table>
    </Card>
  );
}

function InvoicePage() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["portal", "invoice", id], queryFn: () => api<PortalInvoiceDetail>(`/portal/invoices/${id}`) });
  const i = q.data;
  return (
    <div className="space-y-4">
      <Link className="text-sm text-blue-700 hover:underline" to="/portal/invoices">← All invoices</Link>
      <ErrorMsg error={q.error} />
      {i && (
        <Card title={i.number} actions={<a className="text-sm text-blue-700 hover:underline" href={`/api/portal/invoices/${i.id}/pdf`}>Download PDF</a>}>
          <p className="mb-2 text-sm text-slate-600">Dated {i.invoice_date}, due {i.due_date}. {STATUS[i.status]}{i.balance_cents > 0 ? `, balance ${money(i.balance_cents)}` : ""}.</p>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-1">Description</th><th className="text-right">Qty</th><th className="text-right">Price</th><th className="text-right">Amount</th></tr></thead>
            <tbody>{i.lines.map((l, n) => <tr key={n} className="border-b border-slate-100"><td className="p-1">{l.description}</td><td className="text-right">{l.quantity.replace(/\.?0+$/, "")}</td><td className="text-right">{money(l.unit_price_cents)}</td><td className="text-right">{money(l.amount_cents)}</td></tr>)}</tbody>
            <tfoot><tr><td colSpan={3} className="p-1 text-right text-slate-500">Tax</td><td className="text-right">{money(i.tax_cents)}</td></tr><tr className="font-semibold"><td colSpan={3} className="p-1 text-right">Total</td><td className="text-right">{money(i.total_cents)}</td></tr></tfoot>
          </table>
        </Card>
      )}
    </div>
  );
}

function Devices() {
  const q = useQuery({ queryKey: ["portal", "assets"], queryFn: () => api<PortalAssets>("/portal/assets") });
  const d = q.data;
  const soon = d ? d.counts.expiring_30 + d.counts.expiring_60 + d.counts.expiring_90 : 0;
  const pct = (n: number) => (d && d.total ? `${(n / d.total) * 100}%` : "0%");
  return (
    <div className="space-y-4">
      <ErrorMsg error={q.error} />
      {d && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile value={d.total} label="Devices" />
            <StatTile value={soon} label="Expiring in 90 days" tone="text-amber-800" />
            <StatTile value={d.counts.expired} label="Out of warranty" tone="text-red-700" />
            <StatTile value={d.counts.unknown} label="Unknown date" tone="text-slate-500" />
          </div>
          {d.total > 0 && (
            <Card title="Warranty coverage" actions={<span className="text-sm text-slate-500">as of {d.as_of}</span>}>
              <div role="img" aria-label={`${d.counts.expired} expired, ${soon} expiring within 90 days, ${d.counts.in_warranty} in warranty, ${d.counts.unknown} unknown`} className="flex h-2 overflow-hidden rounded-full bg-slate-100">
                <i style={{ width: pct(d.counts.expired) }} className="bg-red-700" />
                <i style={{ width: pct(soon) }} className="bg-amber-700" />
                <i style={{ width: pct(d.counts.in_warranty) }} className="bg-green-700" />
                <i style={{ width: pct(d.counts.unknown) }} className="bg-slate-400" />
              </div>
              <p className="mt-2 text-xs text-slate-500">Devices without a warranty date are shown as unknown, never guessed.</p>
            </Card>
          )}
          <Card title="Devices and warranty">
            <p className="mb-3 text-sm text-slate-600">
              {d.total} device(s) as of {d.as_of}: <b>{soon}</b> with warranty ending in the next 90 days and <b>{d.counts.expired}</b> out of warranty.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[34rem] text-left text-sm">
                <thead className="border-b border-slate-200 text-slate-500"><tr><th className="p-2">Device</th><th>Type</th><th>Make / model</th><th>Warranty ends</th></tr></thead>
                <tbody>
                  {d.devices.map((x) => (
                    <tr key={`${x.name}-${x.warranty_end}`} className="border-b border-slate-100 last:border-0">
                      <td className="p-2 font-semibold">{x.name}</td><td className="px-2 text-slate-500">{x.kind}</td>
                      <td className="px-2">{[x.manufacturer, x.model].filter(Boolean).join(" ") || "—"}</td>
                      <td className="px-2">{x.warranty_end ?? "—"} <WarrantyBadge state={x.warranty_status} label={WARRANTY_LABEL[x.warranty_status]} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
