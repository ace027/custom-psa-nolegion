import { NavLink, Outlet } from "react-router-dom";
import { useMe } from "../auth";
import { visibleItems } from "./navConfig";

/** /admin/*: a sub-nav of the Admin pages this person may open, beside the page. */
export default function AdminLayout() {
  const { data: me } = useMe();
  const items = visibleItems(me).filter((i) => i.section === "admin");
  const link = ({ isActive }: { isActive: boolean }) =>
    `block rounded-lg px-3 py-1.5 text-sm ${isActive ? "bg-blue-50 font-semibold text-blue-700" : "text-slate-600 hover:bg-slate-100"}`;
  return (
    <div className="space-y-4 md:flex md:gap-6 md:space-y-0">
      {items.length > 0 && (
        <nav aria-label="Admin" className="md:w-44 md:shrink-0">
          <ul className="flex flex-wrap gap-1 md:flex-col">
            {items.map((i) => (
              <li key={i.id}>
                <NavLink to={i.route} className={link}>{i.label}</NavLink>
              </li>
            ))}
          </ul>
        </nav>
      )}
      <div className="min-w-0 flex-1">
        <Outlet />
      </div>
    </div>
  );
}
