import { RefObject, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import type { Me } from "../api";
import { visibleSections } from "./navConfig";
import { Icon } from "./Rail";
import { BookmarksApi, MAX_BOOKMARKS } from "./useBookmarks";

/** Every page this person may open, by section, with a bookmark star per page. Esc closes it and
 *  returns focus to the All pages button. */
export default function AllPages({
  me,
  bookmarks,
  onClose,
  returnFocus,
}: {
  me: Me;
  bookmarks: BookmarksApi;
  onClose: () => void;
  returnFocus: RefObject<HTMLButtonElement | null>;
}) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      onClose();
      returnFocus.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, returnFocus]);

  return (
    <section
      id="all-pages"
      ref={panel}
      tabIndex={-1}
      aria-labelledby="all-pages-title"
      className="fixed inset-x-0 bottom-16 top-0 z-40 overflow-y-auto border-slate-200 bg-surface p-5 shadow-card focus:outline-none md:bottom-0 md:left-20 md:right-auto md:w-[34rem] md:max-w-[calc(100vw-5rem)] md:border-r"
    >
      <h2 id="all-pages-title" className="text-lg font-semibold">All pages</h2>
      <p className="text-sm text-slate-500">Star a page to bookmark it on the rail (up to {MAX_BOOKMARKS}).</p>
      <div className="mt-4 gap-6 sm:columns-2">
        {visibleSections(me).map((s) => (
          <section key={s.id} aria-labelledby={`all-pages-${s.id}`} className="mb-4 break-inside-avoid">
            <h3 id={`all-pages-${s.id}`} className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">{s.label}</h3>
            <ul>
              {s.items.map((it) => {
                const on = bookmarks.isBookmarked(it.id);
                return (
                  <li key={it.id} className="flex items-center gap-1">
                    <Link to={it.route} onClick={onClose} className="flex-1 rounded-md px-1.5 py-1 text-sm text-slate-700 hover:bg-slate-100">
                      {it.label}
                    </Link>
                    <button
                      type="button"
                      aria-pressed={on}
                      aria-label={`Bookmark ${it.label}`}
                      className={`rounded-md p-1 hover:bg-slate-100 ${on ? "text-amber-700" : "text-slate-400"}`}
                      onClick={() => bookmarks.toggle(it.id)}
                    >
                      <Icon name="star" className="h-4 w-4" filled={on} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </section>
  );
}
