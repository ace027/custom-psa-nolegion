import { useQuery } from "@tanstack/react-query";
import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Me, api } from "../api";
import { can } from "../auth";
import { IconName, NavItem, canOpen, itemForPath, navItem, settingsPages, visibleItems } from "./navConfig";
import { Icon } from "./Rail";
import { BookmarksApi } from "./useBookmarks";

const RECENT_KEY = "psa.recent-pages";
const RECENT_MAX = 4;
const HINTS = "Up and Down arrows move, Enter opens, Alt+P bookmarks the highlighted page, Escape closes.";

const readRecent = (): string[] => {
  try {
    const v = JSON.parse(sessionStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
};

/** Quick actions open the page where the thing is done; each needs the permission that page needs. */
const ACTIONS: { id: string; label: string; permission: string; route: string; icon: IconName }[] = [
  { id: "new-ticket", label: "New ticket", permission: "ticket:write", route: "/tickets", icon: "ticket" },
  { id: "start-timer", label: "Start a timer", permission: "time:write", route: "/timesheet", icon: "clock" },
  { id: "book-appointment", label: "Book an appointment", permission: "schedule:write", route: "/dispatch", icon: "calendar" },
  { id: "new-quote", label: "New quote", permission: "quote:write", route: "/quotes", icon: "doc" },
  { id: "record-payment", label: "Record a payment", permission: "payment:write", route: "/billing/payments", icon: "dollar" },
];

interface Row {
  key: string;
  group: string;
  label: string;
  hint?: string;
  icon: IconName;
  /** Nav item id, so Alt+P can bookmark it. */
  navId?: string;
  disabled?: boolean;
  go: () => void;
}

/** Remembers the last pages visited (this tab only). Mounted once, so it also sees every navigation. */
export default function CommandPalette({ me, bookmarks, open, onClose }: { me: Me; bookmarks: BookmarksApi; open: boolean; onClose: () => void }) {
  const { pathname } = useLocation();
  useEffect(() => {
    const id = itemForPath(pathname)?.id;
    if (!id) return;
    try {
      sessionStorage.setItem(RECENT_KEY, JSON.stringify([id, ...readRecent().filter((x) => x !== id)].slice(0, RECENT_MAX)));
    } catch {
      /* storage blocked: Recent just stays empty */
    }
  }, [pathname]);
  return open ? <Dialog me={me} bookmarks={bookmarks} onClose={onClose} /> : null;
}

function Dialog({ me, bookmarks, onClose }: { me: Me; bookmarks: BookmarksApi; onClose: () => void }) {
  const nav = useNavigate();
  const opener = useRef(document.activeElement as HTMLElement | null);
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  useEffect(() => input.current?.focus(), []);

  const q = query.trim();
  const ticketNo = can(me, "ticket:read") ? /^#?(\d{1,9})$/.exec(q)?.[1] : undefined;
  // A ticket the person cannot see is simply absent from the list, the same as one that does not exist.
  const lookup = useQuery({
    queryKey: ["palette-ticket", ticketNo],
    enabled: !!ticketNo,
    retry: false,
    queryFn: async () => {
      const r = await api<{ items: { id: number; number: number; subject: string }[] }>(`/tickets?q=${ticketNo}&limit=5`);
      return r.items.find((t) => t.number === Number(ticketNo)) ?? null;
    },
  });

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    const page = (group: string, it: NavItem): Row => ({
      key: `${group}-${it.id}`, group, label: it.label, hint: it.route, icon: it.icon, navId: it.id, go: () => nav(it.route),
    });
    const actions = ACTIONS.filter((a) => can(me, a.permission)).map<Row>((a) => ({
      key: `action-${a.id}`, group: "Actions", label: a.label, icon: a.icon, go: () => nav(a.route),
    }));
    if (!q) {
      const bookmarked = bookmarks.items;
      const recent = readRecent().map(navItem).filter((i): i is NavItem => !!i && canOpen(me, i) && !bookmarks.isBookmarked(i.id));
      return [...bookmarked.map((i) => page("Bookmarked", i)), ...recent.map((i) => page("Recent", i)), ...actions];
    }
    const tokens = q.toLowerCase().split(/\s+/);
    const matches = (text: string) => tokens.every((t) => text.toLowerCase().includes(t));
    if (ticketNo) {
      const t = lookup.data;
      const failed = lookup.isError || lookup.data === null;
      out.push({
        key: "ticket",
        group: "Tickets",
        label: failed ? `Ticket #${ticketNo} not found` : `Go to ticket #${ticketNo}`,
        hint: t?.subject ?? (lookup.isPending ? "Looking up…" : undefined),
        icon: "ticket",
        disabled: !t,
        go: () => t && nav(`/tickets/${t.id}`),
      });
    }
    const pages = visibleItems(me)
      .filter((i) => matches(`${i.label} ${i.keywords.join(" ")}`))
      .map((i) => page("Pages", i));
    const tabs = settingsPages(me)
      .filter((p) => matches(`settings ${p.label} ${p.about}`))
      .map<Row>((p) => ({ key: `settings-${p.id}`, group: "Pages", label: `Settings: ${p.label}`, hint: p.about, icon: "cog", go: () => nav(`/admin/settings/${p.path}`) }));
    const found = [...pages, ...tabs, ...actions.filter((a) => matches(a.label))];
    out.push(...found, {
      key: "search", group: "Search", label: `Search tickets for "${q}"`, icon: "search", go: () => nav(`/search?q=${encodeURIComponent(q)}`),
    });
    return out;
  }, [q, ticketNo, lookup.data, lookup.isError, lookup.isPending, me, bookmarks.items, bookmarks.isBookmarked, nav]);

  const none = !!q && rows.length === 1 && rows[0].key === "search";
  const at = Math.min(active, rows.length - 1);
  useEffect(() => document.getElementById(`cp-opt-${at}`)?.scrollIntoView?.({ block: "nearest" }), [at]);

  function close() {
    onClose();
    opener.current?.focus?.();
  }
  function choose(row: Row | undefined) {
    if (!row || row.disabled) return;
    row.go();
    close();
  }
  function onKey(e: KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "Tab") {
      e.preventDefault(); // the input is the only stop: keeps focus inside the dialog
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (rows.length) setActive((at + (e.key === "ArrowDown" ? 1 : rows.length - 1)) % rows.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(rows[at]);
    } else if (e.altKey && e.code === "KeyP") {
      e.preventDefault();
      const id = rows[at]?.navId;
      if (id) bookmarks.toggle(id);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/40 p-4 pt-[10vh]" onMouseDown={close}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="cp-title"
        className="w-full max-w-xl overflow-hidden rounded-xl border border-slate-200 bg-surface shadow-card"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKey}
      >
        <h2 id="cp-title" className="sr-only">Go to</h2>
        <div className="flex items-center gap-2 border-b border-slate-200 px-3">
          <Icon name="search" className="h-4 w-4 text-slate-500" />
          <input
            ref={input}
            role="combobox"
            aria-label="Go to a page, ticket number or action"
            aria-expanded="true"
            aria-controls="cp-list"
            aria-autocomplete="list"
            aria-activedescendant={rows.length ? `cp-opt-${at}` : undefined}
            aria-describedby="cp-hints"
            autoComplete="off"
            placeholder="Go to a page, a ticket number or an action…"
            className="w-full bg-transparent py-3 text-sm outline-none"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
          />
        </div>
        {none && <p className="px-4 py-2 text-sm text-slate-600">No matches</p>}
        <ul id="cp-list" role="listbox" aria-label="Results" className="max-h-[50vh] overflow-y-auto p-1.5">
          {rows.map((r, i) => (
            <li key={r.key} role="presentation">
              {r.group !== rows[i - 1]?.group && (
                <p role="presentation" className="px-2 pb-0.5 pt-2 text-xs font-semibold uppercase tracking-wide text-slate-400">{r.group}</p>
              )}
              <div
                id={`cp-opt-${i}`}
                role="option"
                aria-selected={i === at}
                aria-disabled={r.disabled || undefined}
                className={`flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${i === at ? "bg-blue-50 text-blue-700" : "text-slate-700"} ${r.disabled ? "opacity-60" : ""}`}
                onMouseMove={() => setActive(i)}
                onClick={() => choose(r)}
              >
                <Icon name={r.icon} className="h-4 w-4" />
                <span>{r.label}</span>
                {r.hint && <span className="ml-auto truncate text-xs text-slate-500">{r.hint}</span>}
              </div>
            </li>
          ))}
        </ul>
        <p id="cp-hints" className="border-t border-slate-200 px-3 py-1.5 text-xs text-slate-500">{HINTS}</p>
        <p role="status" className="sr-only">{bookmarks.status}</p>
      </div>
    </div>
  );
}
