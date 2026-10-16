import { useQuery } from "@tanstack/react-query";
import { can, useMe } from "./auth";
import { getOrgTimezone, schedulingKeys } from "./scheduling/api";
import { getOnCallNow, oncallKeys } from "./scheduling/oncall";
import { formatInZone } from "./scheduling/zone";

/** Sidebar block: who is on call now for each active rotation. Hidden with no rotations or without schedule:read. */
export default function OnCallWidget() {
  const { data: me } = useMe();
  const allowed = can(me, "schedule:read");
  const q = useQuery({ queryKey: oncallKeys.now(), queryFn: getOnCallNow, enabled: allowed, retry: false, refetchInterval: 5 * 60_000 });
  const zone = useQuery({ queryKey: schedulingKeys.orgTimezone(), queryFn: getOrgTimezone, enabled: allowed && !!q.data?.length, retry: false });
  if (!allowed || !q.data || q.data.length === 0) return null;
  return (
    <section aria-label="On call now" className="mt-4 rounded-lg border border-slate-200 px-3 py-2 text-sm">
      <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">On call</h2>
      <ul className="space-y-1">
        {q.data.map((n) => (
          <li key={n.rotation_id}>
            <span className="block text-xs text-slate-500">{n.rotation_name}</span>
            {n.user_name ? (
              <span className="font-medium">
                {n.user_name}
                {n.until && zone.data && <span className="block text-xs font-normal text-slate-500">until {formatInZone(n.until, zone.data, "EEE d MMM HH:mm")}</span>}
              </span>
            ) : (
              <span className="text-slate-500">No one on now</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
