import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { SearchHit, api } from "../api";
import { ErrorMsg, Field, inputCls } from "../ui";

const GROUPS: { kind: SearchHit["kind"]; label: string }[] = [
  { kind: "ticket", label: "Tickets" },
  { kind: "organization", label: "Clients" },
  { kind: "contact", label: "Contacts" },
  { kind: "asset", label: "Devices" },
];

function href(h: SearchHit): string {
  if (h.kind === "ticket") return `/tickets/${h.id}`;
  return `/organizations/${h.organization_id ?? h.id}`;
}

export default function Search() {
  const [params, setParams] = useSearchParams();
  const q = (params.get("q") ?? "").trim();
  const res = useQuery({
    queryKey: ["search", q],
    enabled: q.length >= 2,
    queryFn: () => api<{ q: string; hits: SearchHit[] }>(`/search?q=${encodeURIComponent(q)}`),
  });
  const hits = res.data?.hits ?? [];
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Search</h1>
      <div className="max-w-md">
        <Field label="Tickets, clients, contacts and devices">
          <input className={inputCls} autoFocus defaultValue={q} onChange={(e) => setParams(e.target.value ? { q: e.target.value } : {})} />
        </Field>
      </div>
      {q.length > 0 && q.length < 2 && <p className="text-sm text-slate-500">Type at least 2 characters.</p>}
      <ErrorMsg error={res.error} />
      {res.data && hits.length === 0 && <p className="text-sm text-slate-500">Nothing found for “{q}”.</p>}
      {GROUPS.map(({ kind, label }) => {
        const rows = hits.filter((h) => h.kind === kind);
        if (rows.length === 0) return null;
        return (
          <section key={kind} className="rounded-lg border border-slate-200 bg-surface p-4">
            <h2 className="mb-2 font-semibold">{label}</h2>
            <ul className="divide-y divide-slate-100 text-sm">
              {rows.map((h) => (
                <li key={h.id} className="py-1.5">
                  <Link to={href(h)} className="font-medium text-blue-700 hover:underline">{h.title}</Link>
                  {h.subtitle && <span className="ml-2 text-slate-500">{h.subtitle}</span>}
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
