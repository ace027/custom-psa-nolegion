import { KeyboardEvent, RefObject, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import type { Me } from "../api";
import { BRAND } from "../branding";
import { ThemeToggle } from "../ui";
import { ICON_PATHS, IconName, NavItem, itemForPath } from "./navConfig";
import { BookmarksApi } from "./useBookmarks";

export function Icon({ name, className = "h-5 w-5", filled = false }: { name: IconName; className?: string; filled?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      className={`shrink-0 ${className}`}
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

const ritem =
  "flex w-full flex-col items-center gap-0.5 rounded-xl px-0.5 pb-1.5 pt-2 text-center text-[10px] leading-tight text-slate-600 hover:bg-slate-100";
const ritemOn = "bg-blue-50 font-semibold text-blue-700 hover:bg-blue-50";

interface Props {
  me: Me;
  bookmarks: BookmarksApi;
  allOpen: boolean;
  onToggleAll: () => void;
  allButtonRef: RefObject<HTMLButtonElement | null>;
  /** Placeholder until the command palette (16-04): focuses the header search. */
  onGoTo: () => void;
}

/** Mockup C: an 80px rail on wide screens, a bottom tab bar under 768px. */
export default function Rail({ me, bookmarks, allOpen, onToggleAll, allButtonRef, onGoTo }: Props) {
  const { pathname } = useLocation();
  const current = itemForPath(pathname);
  const { items } = bookmarks;
  const links = useRef(new Map<string, HTMLAnchorElement>());
  const focusAfterMove = useRef<string | null>(null);
  const dragId = useRef<string | null>(null);
  const [drop, setDrop] = useState<{ index: number; after: boolean } | null>(null);
  const [menu, setMenu] = useState<{ id: string; style: React.CSSProperties } | null>(null);

  // The moved bookmark keeps focus after a keyboard or menu move (React may re-insert its node).
  useLayoutEffect(() => {
    if (!focusAfterMove.current) return;
    links.current.get(focusAfterMove.current)?.focus();
    focusAfterMove.current = null;
  });

  function moveAndFocus(id: string, to: number) {
    focusAfterMove.current = id;
    bookmarks.move(id, to);
  }

  function onLinkKey(e: KeyboardEvent, id: string, index: number) {
    if (!e.altKey || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
    e.preventDefault();
    moveAndFocus(id, e.key === "ArrowUp" ? index - 1 : index + 1);
  }

  function openMenu(id: string, button: HTMLButtonElement) {
    const r = button.getBoundingClientRect();
    const phone = window.innerWidth < 768;
    const style: React.CSSProperties = phone
      ? { bottom: window.innerHeight - r.top + 4, left: Math.max(4, Math.min(r.left - 120, window.innerWidth - 180)) }
      : { top: r.top, left: r.right + 4 };
    setMenu({ id, style });
  }

  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-30 flex h-16 items-stretch gap-1 border-t border-slate-200 bg-surface p-1 md:sticky md:top-0 md:h-screen md:w-20 md:shrink-0 md:flex-col md:overflow-y-auto md:border-r md:border-t-0 md:px-1.5 md:py-2.5"
    >
      <Link to="/dashboard" aria-label={`${BRAND.name} home`} className="mx-auto mb-2 hidden md:block">
        {BRAND.logoUrl ? (
          <img src={BRAND.logoUrl} alt="" className="h-8 w-auto" />
        ) : (
          <span aria-hidden className="grid h-8 w-8 place-items-center rounded-lg bg-blue-600 text-sm font-bold text-on-accent">{BRAND.mark}</span>
        )}
      </Link>
      <ul className="flex md:flex-col">
        <li className="flex flex-1">
          <button type="button" className={ritem} onClick={onGoTo} aria-keyshortcuts="Control+K Meta+K">
            <Icon name="search" />
            <span>Go to</span>
          </button>
        </li>
      </ul>
      <div className="mx-2 my-1.5 hidden border-t border-slate-200 md:block" />
      <ul aria-label="Bookmarks" className="flex min-w-0 flex-1 md:flex-none md:flex-col md:gap-0.5">
        {items.map((it, index) => (
          <li
            key={it.id}
            draggable
            data-testid={`bookmark-${it.id}`}
            className={`group relative flex-1 ${index >= 4 ? "hidden md:block" : ""}`}
            onDragStart={(e) => {
              dragId.current = it.id;
              e.dataTransfer?.setData("text/plain", it.id);
              if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
            }}
            onDragOver={(e) => {
              if (!dragId.current) return;
              e.preventDefault();
              const from = items.findIndex((x) => x.id === dragId.current);
              setDrop(from === index ? null : { index, after: from < index });
            }}
            onDragLeave={() => setDrop((d) => (d?.index === index ? null : d))}
            onDrop={(e) => {
              e.preventDefault();
              const id = dragId.current;
              dragId.current = null;
              setDrop(null);
              if (id) bookmarks.move(id, index);
            }}
            onDragEnd={() => {
              dragId.current = null;
              setDrop(null);
            }}
          >
            {drop?.index === index && (
              <span aria-hidden className={`absolute inset-x-1 h-0.5 rounded bg-blue-600 ${drop.after ? "-bottom-px" : "-top-px"}`} />
            )}
            <Link
              to={it.route}
              ref={(el) => {
                if (el) links.current.set(it.id, el);
                else links.current.delete(it.id);
              }}
              aria-label={it.short !== it.label ? it.label : undefined}
              aria-current={current?.id === it.id ? "page" : undefined}
              title={`${it.label} (Alt+Up or Alt+Down to move)`}
              className={`${ritem} ${current?.id === it.id ? ritemOn : ""}`}
              onKeyDown={(e) => onLinkKey(e, it.id, index)}
            >
              <Icon name={it.icon} />
              <span className="line-clamp-2 max-w-full break-words">{it.short}</span>
            </Link>
            <button
              type="button"
              aria-label={`Options for ${it.label}`}
              aria-haspopup="menu"
              aria-expanded={menu?.id === it.id}
              className="absolute right-0 top-0 rounded-md p-0.5 text-slate-500 hover:bg-slate-200 focus:opacity-100 group-hover:opacity-100 [@media(hover:hover)]:opacity-0"
              onClick={(e) => (menu?.id === it.id ? setMenu(null) : openMenu(it.id, e.currentTarget))}
            >
              <Icon name="more" className="h-3.5 w-3.5" />
            </button>
            {menu?.id === it.id && (
              <BookmarkMenu
                item={it}
                index={index}
                count={items.length}
                style={menu.style}
                onClose={(refocus) => {
                  setMenu(null);
                  if (refocus) links.current.get(it.id)?.parentElement?.querySelector<HTMLButtonElement>("button")?.focus();
                }}
                onMove={(to) => {
                  setMenu(null);
                  moveAndFocus(it.id, to);
                }}
                onRemove={() => {
                  setMenu(null);
                  bookmarks.remove(it.id);
                  allButtonRef.current?.focus();
                }}
              />
            )}
          </li>
        ))}
        {items.length === 0 && <li className="hidden px-1 py-1 text-center text-[10.5px] text-slate-400 md:block">Star pages to bookmark them</li>}
      </ul>
      <ul className="flex md:flex-col">
        <li className="flex flex-1">
          <button
            type="button"
            ref={allButtonRef}
            className={`${ritem} ${allOpen ? ritemOn : ""}`}
            aria-expanded={allOpen}
            aria-controls="all-pages"
            onClick={onToggleAll}
          >
            <Icon name="grid" />
            <span>All pages</span>
          </button>
        </li>
      </ul>
      <div className="hidden flex-1 md:block" />
      <Link
        to="/profile"
        aria-label={`Profile and notifications: ${me.display_name}`}
        title="Your profile and notification settings"
        aria-current={pathname === "/profile" ? "page" : undefined}
        className={`${ritem} hidden md:flex`}
      >
        <Icon name="user" />
        <span className="line-clamp-2 max-w-full break-words">{me.display_name.split(" ")[0]}</span>
      </Link>
      <ThemeToggle className="mt-1 hidden px-1 md:block" />
      <p
        role="status"
        className={
          bookmarks.status
            ? "fixed bottom-20 left-3 right-3 z-50 rounded-lg bg-slate-900 px-3 py-2 text-sm text-slate-50 shadow-card md:bottom-4 md:left-24 md:right-auto md:max-w-sm"
            : "sr-only"
        }
      >
        {bookmarks.status}
      </p>
    </nav>
  );
}

function BookmarkMenu({
  item,
  index,
  count,
  style,
  onClose,
  onMove,
  onRemove,
}: {
  item: NavItem;
  index: number;
  count: number;
  style: React.CSSProperties;
  onClose: (refocus: boolean) => void;
  onMove: (to: number) => void;
  onRemove: () => void;
}) {
  const ref = useRef<HTMLUListElement>(null);
  const enabled = () => [...(ref.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [])];
  useEffect(() => {
    enabled()[0]?.focus();
    const outside = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose(false);
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, []);
  function onKey(e: KeyboardEvent) {
    const list = enabled();
    const at = list.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "Escape") {
      e.preventDefault();
      onClose(true);
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      list[(at + (e.key === "ArrowDown" ? 1 : list.length - 1)) % list.length]?.focus();
    } else if (e.key === "Tab") {
      onClose(false);
    }
  }
  const cls = "block w-full rounded-md px-3 py-1.5 text-left text-sm hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40";
  return (
    <ul
      ref={ref}
      role="menu"
      aria-label={`Options for ${item.label}`}
      style={style}
      className="fixed z-50 w-44 rounded-lg border border-slate-200 bg-surface p-1 text-slate-700 shadow-card"
      onKeyDown={onKey}
    >
      <li role="none">
        <button type="button" role="menuitem" className={cls} disabled={index === 0} onClick={() => onMove(index - 1)}>Move up</button>
      </li>
      <li role="none">
        <button type="button" role="menuitem" className={cls} disabled={index === count - 1} onClick={() => onMove(index + 1)}>Move down</button>
      </li>
      <li role="none">
        <button type="button" role="menuitem" className={`${cls} text-red-700`} onClick={onRemove}>Remove bookmark</button>
      </li>
    </ul>
  );
}
