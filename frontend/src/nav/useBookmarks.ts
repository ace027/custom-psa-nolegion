import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Bookmarks, Me, api } from "../api";
import { DEFAULT_BOOKMARKS, NavItem, canOpen, navItem } from "./navConfig";

export const MAX_BOOKMARKS = 8;
export const CAP_MESSAGE = `You can bookmark up to ${MAX_BOOKMARKS} pages. Remove one first.`;
export const SAVE_ERROR = "Your bookmarks could not be saved, so the previous order is back. Try again.";
// Not under ["me", ...]: sign-out drops every other query, and bookmarks belong to the person.
const KEY = ["bookmarks"];

/** The signed-in person's rail bookmarks, saved on the server.
 *  `items` are the pages to show. The saved list may also hold ids this person can no longer open
 *  (role change) or that no longer exist: they are hidden, but kept in every save. */
export function useBookmarks(me: Me | null | undefined) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: KEY, queryFn: () => api<Bookmarks>("/me/bookmarks"), enabled: !!me, retry: false });
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (!status) return;
    const t = setTimeout(() => setStatus(""), 6000);
    return () => clearTimeout(t);
  }, [status]);

  const defaults = me ? (DEFAULT_BOOKMARKS[me.role] ?? []) : [];
  // Nothing until the server answers (no flash of the defaults); if it cannot answer, the defaults.
  const saved: string[] = q.data ? (q.data.items ?? defaults) : q.isError ? defaults : [];
  const items = saved.map(navItem).filter((i): i is NavItem => !!i && canOpen(me, i));

  const save = useMutation({
    mutationFn: (next: string[]) => api<Bookmarks>("/me/bookmarks", { method: "PUT", json: { items: next } }),
    onMutate: async (next) => {
      await qc.cancelQueries({ queryKey: KEY });
      const prev = qc.getQueryData<Bookmarks>(KEY) ?? { items: null };
      qc.setQueryData<Bookmarks>(KEY, { items: next });
      setError("");
      return { prev };
    },
    // shortcut: rolls back to the list before this save; two quick changes where only the first
    // fails can briefly show the older order until the next load. Fine for a personal preference.
    onError: (_e, _next, ctx) => {
      if (ctx) qc.setQueryData<Bookmarks>(KEY, ctx.prev);
      setStatus("");
      setError(SAVE_ERROR);
    },
  });

  const isBookmarked = (id: string) => items.some((i) => i.id === id);

  function remove(id: string) {
    save.mutate(saved.filter((x) => x !== id));
    setStatus(`${navItem(id)?.label ?? id} removed from bookmarks`);
  }

  function toggle(id: string) {
    if (saved.includes(id)) return remove(id);
    if (saved.length >= MAX_BOOKMARKS) return setStatus(CAP_MESSAGE);
    save.mutate([...saved, id]);
    setStatus(`${navItem(id)?.label ?? id} bookmarked`);
  }

  /** Move a shown bookmark to `toIndex` among the shown ones; hidden ids keep their slots. */
  function move(id: string, toIndex: number) {
    const shown = items.map((i) => i.id);
    const from = shown.indexOf(id);
    const to = Math.max(0, Math.min(shown.length - 1, toIndex));
    if (from < 0 || from === to) return;
    shown.splice(from, 1);
    shown.splice(to, 0, id);
    const slots = new Set(items.map((i) => i.id));
    let k = 0;
    save.mutate(saved.map((x) => (slots.has(x) ? shown[k++] : x)));
    setStatus(`${navItem(id)?.label ?? id} moved to position ${to + 1} of ${shown.length}`);
  }

  return { items, isBookmarked, toggle, move, remove, status, error };
}

export type BookmarksApi = ReturnType<typeof useBookmarks>;
