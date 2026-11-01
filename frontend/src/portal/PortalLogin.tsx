import { useMutation, useQuery } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PortalLoginOptions, api } from "../api";
import { Button, Card, ErrorMsg, Field, inputCls } from "../ui";

export default function PortalLogin() {
  const [email, setEmail] = useState("");
  const [params] = useSearchParams();
  const options = useQuery({ queryKey: ["portal", "login-options"], retry: false, queryFn: () => api<PortalLoginOptions>("/portal/login-options") });
  const ask = useMutation({ mutationFn: () => api<{ detail: string }>("/portal/login-link", { method: "POST", json: { email } }) });
  const sso = options.data?.sso === true;
  return (
    <Card title="Sign in">
      {params.get("sso") === "denied" && (
        <p role="alert" className="mb-3 rounded bg-red-50 p-2 text-sm text-red-800">
          We could not sign you in with Microsoft. Ask your IT contact to check your account, or use an email link.
        </p>
      )}
      {params.get("sso") === "confirm" && (
        <p role="status" className="mb-3 rounded bg-blue-50 p-2 text-sm text-blue-800">
          Check your email: we sent a link to confirm your Microsoft account. It works once.
        </p>
      )}
      {sso && (
        <>
          <Button type="button" onClick={() => window.location.assign("/api/v1/portal/sso/login")}>Sign in with Microsoft</Button>
          <div className="my-4 flex items-center gap-3 text-xs text-slate-500" aria-hidden>
            <span className="h-px flex-1 bg-slate-200" />or<span className="h-px flex-1 bg-slate-200" />
          </div>
        </>
      )}
      <p className="mb-3 text-sm text-slate-600">Enter your email address and we will send you a one-time sign-in link. There is no password.</p>
      <form className="space-y-3" onSubmit={(e: FormEvent) => { e.preventDefault(); ask.mutate(); }}>
        <Field label="Email address"><input className={inputCls} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Button type="submit" disabled={ask.isPending}>Email me a link</Button>
      </form>
      <ErrorMsg error={ask.error} />
      {ask.data && <p role="status" className="mt-3 rounded bg-green-50 p-2 text-sm text-green-800">{ask.data.detail} Check your inbox; the link expires in a few minutes.</p>}
    </Card>
  );
}
