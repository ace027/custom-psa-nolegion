"""Background worker: polls the support mailbox and sends queued outbound mail.

python -m app.worker           # loop forever
python -m app.worker --once    # a single cycle (cron / debugging)
"""

import logging
import os
import signal
import sys
import time

from app.config import get_settings
from app.mail.graph import GraphClient
from app.mail.ingest import heartbeat, run_cycle

log = logging.getLogger("psa.worker")
_stop = False
BUSY_EVERY = 300  # seconds between free/busy refreshes
_last_busy: float | None = None
RETENTION_EVERY = 86400  # seconds between retention purges
_last_retention: float | None = None


def _handle(*_):
    global _stop
    _stop = True


def billing_jobs() -> None:
    """Prepare due reminders and the monthly statement batch (idempotent; never sends anything)."""
    from app import db as dbmod
    from app.deps import Ctx
    from app.notices import run_scheduled
    from app.scope import Scope

    try:
        with dbmod.new_session() as db:
            dbmod.set_org_scope(db, "all")
            result = run_scheduled(Ctx(db=db, user=None, scope=Scope.all()))
            db.commit()
        if any(result.values()):
            log.info("prepared billing notices for review: %s", result)
    except Exception:
        log.exception("billing jobs failed")

    try:
        from app import renewals
        from app.billing import today

        with dbmod.new_session() as db:
            dbmod.set_org_scope(db, "all")
            ctx = Ctx(db=db, user=None, scope=Scope.all())
            counts = renewals.scan(ctx, today(ctx))
            db.commit()
        if any(counts.values()):
            log.info("renewal reminders: %s", counts)
    except Exception:
        log.exception("renewal reminder jobs failed")


def notify_jobs() -> None:
    """Email assignees whose tickets reached SLA at-risk or breached (once per state)."""
    from app import db as dbmod
    from app.deps import Ctx
    from app.notifications import scan_sla
    from app.scope import Scope

    try:
        with dbmod.new_session() as db:
            dbmod.set_org_scope(db, "all")
            queued = scan_sla(Ctx(db=db, user=None, scope=Scope.all()))
            db.commit()
        if queued:
            log.info("queued %d SLA notification(s)", queued)
    except Exception:
        log.exception("notification jobs failed")


def client_notice_jobs() -> None:
    """Turn due appointment notices into outbound client emails (before send_pending runs)."""
    from datetime import UTC, datetime

    from app import client_notices
    from app import db as dbmod

    try:
        with dbmod.new_session() as db:
            n = client_notices.send_due(db, datetime.now(UTC))
        if n:
            log.info("queued %d client appointment email(s)", n)
    except Exception:
        log.exception("client notice jobs failed")


def integration_jobs() -> None:
    """Sync vendor integrations that are due (or were asked to sync now). Read-only toward vendors;
    a failure is recorded on the run and never raises."""
    from app import db as dbmod
    from app.asset_sync import due, sync_integration
    from app.deps import Ctx
    from app.scope import Scope

    try:
        with dbmod.new_session() as db:
            dbmod.set_org_scope(db, "all")
            ctx = Ctx(db=db, user=None, scope=Scope.all())
            for integration in due(ctx):
                run = sync_integration(ctx, integration)
                db.commit()  # one commit per vendor so a later failure keeps earlier runs
                log.info(
                    "synced %s: %s (+%d ~%d -%d, %d client(s) failed)",
                    integration.name,
                    run.status,
                    run.added,
                    run.changed,
                    run.retired,
                    run.clients_failed,
                )
    except Exception:
        log.exception("integration jobs failed")


def alert_jobs() -> None:
    """Poll NinjaOne for alerts on integrations that are due (or were asked to poll now) and turn
    them into tickets. A vendor failure is recorded on the integration and never raises."""
    from datetime import UTC, datetime

    from app import db as dbmod
    from app.deps import Ctx
    from app.rmm_alerts import due, poll
    from app.scope import Scope

    try:
        with dbmod.new_session() as db:
            dbmod.set_org_scope(db, "all")
            ctx = Ctx(db=db, user=None, scope=Scope.all())
            for integration in due(ctx, datetime.now(UTC)):
                name = integration.name
                try:
                    result = poll(ctx, integration)
                    db.commit()  # one commit per integration so a later failure keeps earlier polls
                    log.info("polled alerts for %s: %s", name, result)
                except Exception:
                    db.rollback()
                    log.exception("alert poll for %s failed", name)
    except Exception:
        log.exception("alert jobs failed")


def webhook_jobs() -> None:
    """Send due webhook deliveries (signed, with retries). A failure never raises."""
    from app import db as dbmod
    from app.webhooks import deliver_due

    try:
        with dbmod.new_session() as db:
            dbmod.set_org_scope(db, "all")
            counts = deliver_due(db)
        if any(counts.values()):
            log.info("webhook deliveries: %s", counts)
    except Exception:
        log.exception("webhook jobs failed")


def retention_jobs() -> None:
    """Purge old automation runs and webhook deliveries, at most once every RETENTION_EVERY
    seconds. Windows come from AUTOMATION_RUNS_RETENTION_DAYS (30) and
    WEBHOOK_DELIVERIES_RETENTION_DAYS (90). A failure never raises."""
    global _last_retention
    from app import automation
    from app import db as dbmod
    from app.deps import Ctx
    from app.scope import Scope

    mono = time.monotonic()
    if _last_retention is not None and mono - _last_retention < RETENTION_EVERY:
        return
    _last_retention = mono
    try:
        runs_days = int(os.environ.get("AUTOMATION_RUNS_RETENTION_DAYS", "30"))
        deliveries_days = int(os.environ.get("WEBHOOK_DELIVERIES_RETENTION_DAYS", "90"))
        with dbmod.new_session() as db:
            dbmod.set_org_scope(db, "all")
            runs, deliveries = automation.purge_old(
                Ctx(db=db, user=None, scope=Scope.all()), runs_days, deliveries_days
            )
            db.commit()
        log.info(
            "retention purge: %d automation run(s), %d webhook delivery(ies)", runs, deliveries
        )
    except Exception:
        log.exception("retention jobs failed")


def calendar_jobs(client) -> None:
    """Push pending appointment changes to Outlook (idempotent; a failure never raises)."""
    from datetime import UTC, datetime

    from app import db as dbmod
    from app.calendar_sync import push_pending

    try:
        with dbmod.new_session() as db:
            dbmod.set_org_scope(db, "all")
            n = push_pending(db, client, now=datetime.now(UTC))
        if n:
            log.info("processed %d calendar sync row(s)", n)
    except Exception:
        log.exception("calendar jobs failed")
    busy_job(client)


def busy_job(client) -> None:
    """Refresh the Outlook free/busy cache, at most once every BUSY_EVERY seconds."""
    global _last_busy
    from datetime import UTC, datetime

    from app import db as dbmod
    from app.calendar_sync import refresh_busy

    mono = time.monotonic()
    if _last_busy is not None and mono - _last_busy < BUSY_EVERY:
        return
    _last_busy = mono
    try:
        with dbmod.new_session() as db:
            n = refresh_busy(db, client, now=datetime.now(UTC))
        if n:
            log.info("refreshed Outlook busy time for %d user(s)", n)
    except Exception:
        log.exception("busy refresh failed")


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


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    s = get_settings()
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request is noise
    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    if not s.mail_configured:
        log.warning(
            "Mail is not configured (GRAPH_* / MAIL_MAILBOX); worker is idle. "
            "See docs/MAIL_SETUP.md"
        )
        while not _stop:
            heartbeat(None)
            billing_jobs()
            notify_jobs()
            integration_jobs()
            alert_jobs()
            webhook_jobs()
            retention_jobs()
            if "--once" in argv:
                break
            for _ in range(60):
                if _stop:
                    break
                time.sleep(1)
        return 0
    client = build_client()
    log.info("mail worker started for %s (every %ss)", s.mail_mailbox, s.mail_poll_seconds)
    while not _stop:
        client_notice_jobs()
        run_cycle(client, s.mail_mailbox)
        calendar_jobs(client)
        billing_jobs()
        notify_jobs()
        integration_jobs()
        alert_jobs()
        webhook_jobs()
        retention_jobs()
        if "--once" in argv:
            break
        for _ in range(s.mail_poll_seconds):
            if _stop:
                break
            time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
