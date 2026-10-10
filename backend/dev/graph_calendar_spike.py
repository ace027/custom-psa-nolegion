"""Real-tenant spike for the Graph calendar calls. Run from backend/:

    python dev/graph_calendar_spike.py --mailbox tech@example.com
    python dev/graph_calendar_spike.py --mailbox tech@example.com --write
    python dev/graph_calendar_spike.py --mailbox tech@example.com --outside other@example.com

Read-only by default. Paste the final PASS/FAIL block back to the owner.
The client secret and token are never printed.
"""

import argparse
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.mail.graph import GraphClient, GraphError, event_payload  # noqa: E402


def build_client() -> GraphClient:
    s = get_settings()
    return GraphClient(
        s.graph_tenant_id,
        s.graph_client_id,
        s.graph_client_secret,
        s.mail_mailbox,
        base_url=s.graph_base_url,
        login_url=s.graph_login_url,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Graph calendar spike against the real tenant.")
    ap.add_argument("--mailbox", required=True, help="technician mailbox to read/write")
    ap.add_argument(
        "--outside",
        help="a mailbox OUTSIDE the RBAC scope; getSchedule as this caller must be denied",
    )
    ap.add_argument(
        "--write",
        action="store_true",
        help="also create, re-create (idempotency), update and delete a test event",
    )
    args = ap.parse_args(argv)

    s = get_settings()
    client = build_client()
    results: list[tuple[str, str, str]] = []  # (PASS|FAIL|WARN, step, detail)

    def record(state: str, step: str, detail: str = "") -> None:
        results.append((state, step, detail))
        print(f"{state} {step} {detail}".rstrip())

    now = datetime.now(UTC)
    try:
        sched = client.get_schedule(args.mailbox, [args.mailbox], now, now + timedelta(hours=24))
        items = sched.get(args.mailbox.lower(), [])
        record("PASS", "getSchedule read", f"{len(items)} busy items")
        for it in items:
            print(f"  {it.status} {it.starts_at.isoformat()} -> {it.ends_at.isoformat()}")
    except GraphError as e:
        record("FAIL", "getSchedule read", f"status={e.status} transient={e.transient}")

    if args.write:
        start = now + timedelta(hours=1)
        payload = event_payload(0, start, start + timedelta(minutes=30), s.public_url)
        txn = f"psa-spike-{int(time.time())}"
        event_id = None
        try:
            event_id = client.create_event(args.mailbox, payload, txn)
            record("PASS", "create_event", f"id={event_id}")
        except GraphError as e:
            record("FAIL", "create_event", f"status={e.status} transient={e.transient}")
        if event_id:
            try:
                again = client.create_event(args.mailbox, payload, txn)
                if again == event_id:
                    record("PASS", "idempotent create", "same id returned")
                else:
                    record("FAIL", "idempotent create", f"different id {again}")
                    try:
                        client.delete_event(args.mailbox, again)
                    except GraphError:
                        pass
            except GraphError as e:
                record("FAIL", "idempotent create", f"status={e.status}")
            try:
                moved = event_payload(
                    0,
                    start + timedelta(minutes=30),
                    start + timedelta(minutes=60),
                    s.public_url,
                )
                client.update_event(
                    args.mailbox, event_id, {"start": moved["start"], "end": moved["end"]}
                )
                record("PASS", "update_event", "moved by 30 minutes")
            except GraphError as e:
                record("FAIL", "update_event", f"status={e.status}")
            try:
                client.delete_event(args.mailbox, event_id)
                record("PASS", "delete_event")
            except GraphError as e:
                record("FAIL", "delete_event", f"status={e.status}")
            try:
                client.delete_event(args.mailbox, event_id)
                record("PASS", "delete again tolerated (404)")
            except GraphError as e:
                record("FAIL", "delete again tolerated (404)", f"status={e.status}")

    if args.outside:
        try:
            client.get_schedule(args.outside, [args.outside], now, now + timedelta(hours=24))
            record("WARN", "RBAC boundary", f"{args.outside} was readable; scope not enforced")
        except GraphError as e:
            if e.status in (401, 403):
                record("PASS", "RBAC boundary", f"denied with {e.status}")
            else:
                record("WARN", "RBAC boundary", f"unexpected status={e.status}")

    print("\n== SPIKE SUMMARY ==")
    for state, step, detail in results:
        print(f"{state}: {step} {detail}".rstrip())
    return 1 if any(r[0] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
