import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { Button, ErrorMsg, Field, inputCls } from "../ui";

export default function Login() {
  const qc = useQueryClient();
  const [email, setEmail] = useState("admin@example.com");
  const dev = useMutation({
    mutationFn: () => api("/auth/dev-login", { method: "POST", json: { email } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
  return (
    <main className="mx-auto mt-24 max-w-sm space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-xl font-semibold">PSA sign in</h1>
      <a
        href="/api/auth/login"
        className="block rounded bg-blue-600 px-3 py-2 text-center text-sm font-medium text-white hover:bg-blue-700"
      >
        Sign in with Microsoft
      </a>
      {import.meta.env.DEV && (
        <form
          className="space-y-2 border-t border-slate-200 pt-4"
          onSubmit={(e) => {
            e.preventDefault();
            dev.mutate();
          }}
        >
          <p className="text-xs text-amber-700">Development only: sign in without Entra.</p>
          <Field label="Email">
            <input className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <ErrorMsg error={dev.error} />
          <Button type="submit" variant="secondary">
            Dev login
          </Button>
        </form>
      )}
    </main>
  );
}
