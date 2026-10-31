import { createContext, createElement, useContext, type ReactNode } from "react";
import { useMatch } from "react-router-dom";

/*
 * Two kinds of call site, kept deliberately different:
 *  - The CURRENT client (a client page and its cards): use useClientScope(), so a future
 *    global client switcher only has to set ClientScopeProvider.
 *  - Rows or links naming some OTHER, explicit client (lists, search results, a ticket's own
 *    organization, receivables rows): call clientRoute(id) / clientApiPath(id, ...) directly.
 *    These must never follow the switcher.
 */

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

/** Active client: the :id of an /organizations/:id[/*] route (a client page always shows its own client), else the provider value. */
export function useClientScope(): { orgId: number | null; apiPath: (...parts: Part[]) => string; route: (...parts: Part[]) => string } {
  const fromProvider = useContext(ScopeContext);
  const rawId = useMatch("/organizations/:id/*")?.params.id;
  const fromRoute = rawId !== undefined && /^\d+$/.test(rawId) && Number(rawId) > 0 ? Number(rawId) : null;
  const orgId = fromRoute ?? fromProvider;
  const need = () => {
    if (orgId === null) throw new Error("No client in scope");
    return orgId;
  };
  return {
    orgId,
    apiPath: (...parts) => clientApiPath(need(), ...parts),
    route: (...parts) => clientRoute(need(), ...parts),
  };
}
