import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";
import { Page, Ticket, api } from "../api";
import { inputCls } from "../ui";

const label = (t: Ticket) => `#${t.number} — ${t.subject.length > 60 ? `${t.subject.slice(0, 60)}…` : t.subject}`;

/** Searchable ticket combobox. Server-side search (q = subject text or number), debounced 250 ms, 20 results. */
export default function TicketPicker({ exclude, value, onChange }: { exclude: number[]; value: Ticket | null; onChange: (t: Ticket | null) => void }) {
  const uid = useId();
  const listId = `${uid}-list`;
  const [text, setText] = useState("");
  const [term, setTerm] = useState("");
  const [open, setOpen] = useState(false);
  const [closed, setClosed] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    const h = setTimeout(() => setTerm(text.trim()), 250);
    return () => clearTimeout(h);
  }, [text]);

  const params = new URLSearchParams({ limit: "20", sort: "number" });
  if (!closed) params.set("open_only", "true");
  if (term && !value) params.set("q", term);
  const res = useQuery({
    queryKey: ["ticket-picker", closed, value ? "" : term],
    enabled: open,
    queryFn: () => api<Page<Ticket>>(`/tickets?${params}`),
  });
  const options = (res.data?.items ?? []).filter((t) => !exclude.includes(t.id));

  const choose = (t: Ticket) => { onChange(t); setText(label(t)); setOpen(false); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, options.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === "Enter" && open && options[active]) { e.preventDefault(); choose(options[active]); }
    else if (e.key === "Escape" && open) { e.stopPropagation(); setOpen(false); }
  };

  return (
    <div className="relative min-w-72">
      <input
        className={inputCls}
        role="combobox"
        aria-label="Search tickets by number or title"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && options[active] ? `${uid}-opt-${options[active].id}` : undefined}
        autoComplete="off"
        placeholder="Search by number or title"
        value={text}
        onChange={(e) => { setText(e.target.value); onChange(null); setOpen(true); setActive(0); }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKey}
      />
      <label className="mt-1 flex items-center gap-1 text-xs text-slate-600">
        <input type="checkbox" checked={closed} onChange={(e) => { setClosed(e.target.checked); setActive(0); }} /> Show closed tickets
      </label>
      {open && (
        <ul id={listId} role="listbox" aria-label="Matching tickets" className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded border border-slate-200 bg-white text-sm shadow">
          {res.isLoading ? (
            <li className="px-2 py-1.5 text-slate-500" role="presentation">Loading…</li>
          ) : options.length === 0 ? (
            <li className="px-2 py-1.5 text-slate-500" role="presentation">No matching tickets</li>
          ) : (
            options.map((t, i) => (
              <li
                key={t.id}
                id={`${uid}-opt-${t.id}`}
                role="option"
                aria-selected={i === active}
                className={`cursor-pointer px-2 py-1.5 ${i === active ? "bg-blue-50" : ""}`}
                onMouseDown={(e) => { e.preventDefault(); choose(t); }}
              >
                {label(t)}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
