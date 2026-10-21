import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { PROJECT_STATUS_LABEL, ProjectSummary, projectsApi } from "../api";
import { money } from "../money";
import { Card, ErrorMsg } from "../ui";

function Remaining({ p }: { p: ProjectSummary }) {
  const b = useQuery({ queryKey: ["project-budget", p.id], queryFn: () => projectsApi.budget(p.id) });
  if (!b.data) return null;
  if (b.data.over_budget) return <span className="text-red-700">over budget</span>;
  if (b.data.remaining_cents === null) return <span className="text-slate-500">fixed fee</span>;
  return <span className="text-slate-600">{money(b.data.remaining_cents)} remaining</span>;
}

export default function OrgProjectsCard({ orgId }: { orgId: number }) {
  const list = useQuery({ queryKey: ["projects", String(orgId), ""], queryFn: () => projectsApi.list({ organization_id: orgId }) });
  return (
    <Card title="Projects">
      <ErrorMsg error={list.error} />
      {list.data && list.data.length === 0 && <p className="text-sm text-slate-500">No projects for this client.</p>}
      <ul className="divide-y divide-slate-100 text-sm">
        {(list.data ?? []).map((p) => (
          <li key={p.id} className="flex items-center justify-between py-1.5">
            <Link className="text-blue-700 hover:underline" to={`/projects/${p.id}`}>{p.name}</Link>
            <span className="flex gap-3 text-slate-600">{PROJECT_STATUS_LABEL[p.status]} <Remaining p={p} /></span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
