import { createContext, createElement, useContext, type ReactNode } from "react";
import { useParams } from "react-router-dom";

type Part = string | number;

/** API path for a client-scoped resource: /organizations/<id>[/parts]. */
export function clientApiPath(orgId: number, ...parts: Part[]): string {
  return ["/organizations", orgId, ...parts].join("/");
}

/** UI route for a client page. */
export function clientRoute(orgId: number, ...parts: Part[]): string {
  return clientApiPath(orgId, ...parts);
}

const ScopeContext = createContext<number | null>(null);

export function ClientScopeProvider({ value = null, children }: { value?: number | null; children: ReactNode }) {
  return createElement(ScopeContext.Provider, { value }, children);
}

/** Active client: the provider value, else the :id route param on client pages. */
export function useClientScope(): { orgId: number | null; apiPath: (...parts: Part[]) => string } {
  const fromProvider = useContext(ScopeContext);
  const param = Number(useParams().id);
  const orgId = fromProvider ?? (Number.isFinite(param) && param > 0 ? param : null);
  return {
    orgId,
    apiPath: (...parts) => {
      if (orgId === null) throw new Error("No client in scope");
      return clientApiPath(orgId, ...parts);
    },
  };
}
