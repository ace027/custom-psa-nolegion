import { useQuery } from "@tanstack/react-query";
import { AppSettings, Lookup, Priority, Queue, TicketStatusRow, User, api } from "./api";

/** Reference data used by ticket forms. Small tables, so fetch once and cache. */
export function useLookups() {
  const q = <T,>(key: string, path: string) =>
    useQuery({ queryKey: ["lookup", key], staleTime: 60_000, queryFn: () => api<T>(path) });
  const queues = q<Queue[]>("queues", "/queues");
  const categories = q<Lookup[]>("categories", "/categories");
  const priorities = q<Priority[]>("priorities", "/priorities");
  const workTypes = q<Lookup[]>("work-types", "/work-types");
  const users = q<User[]>("users", "/users");
  const settings = q<AppSettings>("settings", "/settings");
  const statuses = q<TicketStatusRow[]>("ticket-statuses", "/ticket-statuses");
  const ticketTypes = q<Lookup[]>("ticket-types", "/ticket-types");
  return {
    ticketTypes: Array.isArray(ticketTypes.data) ? ticketTypes.data : [],
    queues: queues.data ?? [],
    categories: categories.data ?? [],
    priorities: priorities.data ?? [],
    workTypes: workTypes.data ?? [],
    techs: (users.data ?? []).filter((u) => u.is_active && (u.role === "admin" || u.role === "tech")),
    statuses: Array.isArray(statuses.data) ? statuses.data : [],
    settings: settings.data,
  };
}
