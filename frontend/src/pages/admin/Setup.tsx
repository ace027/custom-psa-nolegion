import { useMutation, useQuery } from "@tanstack/react-query";
import { ReactNode, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError, OnboardingConnected, OnboardingCreated, OnboardingStatus, OnboardingStep, api } from "../../api";
import { Button, Card, ErrorMsg, Field, inputCls } from "../../ui";

const BASE = "/onboarding";
const LABEL = { ok: "Done", missing: "Needs action", error: "Error", restart_needed: "Restart needed" } as const;
const TONE = { ok: "bg-green-100 text-green-800", missing: "bg-amber-100 text-amber-800", error: "bg-red-100 text-red-800", restart_needed: "bg-blue-100 text-blue-800" } as const;

function Badge({ status }: { status: OnboardingStep["status"] }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TONE[status]}`}>{LABEL[status]}</span>;
}

function Step({ n, title, status, children }: { n: number; title: string; status?: OnboardingStep; children?: ReactNode }) {
  return (
    <Card title={`${n}. ${title}`} actions={status ? <Badge status={status.status} /> : undefined}>
      {status && <p className="mb-2 text-sm text-slate-600">{status.message}</p>}
      <div className="space-y-3">{children}</div>
    </Card>
  );
}

/** Create or connect one registration. A 409 from create carries the existing app id to connect. */
function AppStep({ n, title, kind, status, onChanged }: { n: number; title: string; kind: "portal" | "mail"; status?: OnboardingStep; onChanged: () => void }) {
  const [mailbox, setMailbox] = useState("");
  const [appId, setAppId] = useState("");
  const [existing, setExisting] = useState(false);
  const [powershell, setPowershell] = useState<string | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const mailBody = kind === "mail" ? { mailbox } : {};
  const done = (r: { powershell?: string | null; differences?: string[] }) => {
    setPowershell(r.powershell ?? null);
    setNotes(r.differences ?? []);
    onChanged();
  };
  const create = useMutation({
    mutationFn: () => api<OnboardingCreated>(`${BASE}/${kind}-app`, { method: "POST", json: mailBody }),
    onSuccess: done,
    onError: (e) => {
      // The 409 body is {detail, app_id}; the api helper keeps only the message, so offer connect.
      if (e instanceof ApiError && e.status === 409) setExisting(true);
    },
  });
  const connect = useMutation({
    mutationFn: () => api<OnboardingConnected>(`${BASE}/connect`, { method: "POST", json: { kind, app_id: appId, ...(kind === "mail" ? { mailbox } : {}) } }),
    onSuccess: done,
  });
  const needMailbox = kind === "mail" && !mailbox.trim();
  return (
    <Step n={n} title={title} status={status}>
      {kind === "mail" && (
        <Field label="Shared mailbox address">
          <input className={inputCls} type="email" value={mailbox} onChange={(e) => setMailbox(e.target.value)} />
        </Field>
      )}
      <div className="flex gap-2">
        <Button disabled={create.isPending || needMailbox} onClick={() => create.mutate()}>Create</Button>
        <Button variant="secondary" onClick={() => setExisting(!existing)}>Use an existing app</Button>
      </div>
      {existing && (
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <Field label="Application (client) ID">
              <input className={inputCls} value={appId} onChange={(e) => setAppId(e.target.value)} />
            </Field>
          </div>
          <Button disabled={connect.isPending || !appId.trim() || needMailbox} onClick={() => connect.mutate()}>Connect</Button>
        </div>
      )}
      <ErrorMsg error={create.error} />
      <ErrorMsg error={connect.error} />
      {notes.length > 0 && (
        <ul className="list-disc pl-5 text-sm text-amber-800">
          {notes.map((d) => <li key={d}>{d}</li>)}
        </ul>
      )}
      {powershell && (
        <div className="space-y-2">
          <p className="text-sm">Run these Exchange Online PowerShell commands to limit the app to this mailbox. Exchange access takes 30 minutes to 2 hours to take effect.</p>
          <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">{powershell}</pre>
          <Button variant="secondary" onClick={() => void navigator.clipboard?.writeText(powershell)}>Copy</Button>
        </div>
      )}
    </Step>
  );
}

export default function Setup() {
  const [params] = useSearchParams();
  const consent = params.get("consent");
  const status = useQuery({
    queryKey: ["onboarding-status"],
    queryFn: () => api<OnboardingStatus>(`${BASE}/status`),
    retry: false,
  });
  const consentStart = useMutation({
    mutationFn: () => api<{ url: string }>(`${BASE}/consent/start`),
    onSuccess: (r) => { window.location.assign(r.url); },
  });
  const finish = useMutation({ mutationFn: () => api<{ removed_scopes: string[] }>(`${BASE}/finish`, { method: "POST" }) });

  if (status.error instanceof ApiError && status.error.status === 404) {
    return <p className="p-6 text-sm">Setup is not enabled on this install.</p>;
  }
  const steps = status.data?.steps ?? [];
  const by = (s: OnboardingStep["step"]) => steps.find((x) => x.step === s);
  const restart = steps.some((s) => s.status === "restart_needed");
  const refetch = () => void status.refetch();
  const confirmFinish = () => {
    if (window.confirm("This removes the setup permission from your account. You can grant it again later.")) finish.mutate();
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <h1 className="text-xl font-semibold">Setup</h1>
      <p className="text-sm text-slate-600">Secrets are stored in Azure Key Vault and are never shown.</p>
      <ErrorMsg error={status.error} />
      <Step n={1} title="Staff sign-in" status={by("staff_sso")}>
        <p className="text-sm">You are signed in, so staff sign-in works.</p>
      </Step>
      <Step n={2} title="Allow setup to manage app registrations">
        {consent === "ok" && <p role="status" className="text-sm text-green-800">Microsoft sign-in succeeded.</p>}
        {consent === "error" && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">Microsoft sign-in did not complete. Please try again.</p>}
        <Button disabled={consentStart.isPending} onClick={() => consentStart.mutate()}>Sign in to Microsoft</Button>
        <ErrorMsg error={consentStart.error} />
      </Step>
      <AppStep n={3} title="Client portal sign-in" kind="portal" status={by("portal_sso")} onChanged={refetch} />
      <AppStep n={4} title="Mail & calendar" kind="mail" status={by("mail")} onChanged={refetch} />
      <Step n={5} title="Restart">
        <p className="text-sm">
          {restart
            ? "Restart the app so it picks up the new settings, for example: az containerapp revision restart (see your deployment notes)."
            : "No restart is needed right now."}
        </p>
      </Step>
      <Step n={6} title="Verify">
        <Button variant="secondary" disabled={status.isFetching} onClick={refetch}>Verify</Button>
        <ul className="space-y-1 text-sm">
          {steps.map((s) => (
            <li key={s.step} className="flex items-center gap-2"><Badge status={s.status} /> {s.message}</li>
          ))}
        </ul>
      </Step>
      <Step n={7} title="Finish">
        {finish.isSuccess ? (
          <p role="status" className="text-sm text-green-800">Setup is finished. The setup permission was removed.</p>
        ) : (
          <Button variant="danger" disabled={finish.isPending} onClick={confirmFinish}>Finish</Button>
        )}
        <ErrorMsg error={finish.error} />
      </Step>
    </div>
  );
}
