"""Background worker: polls the support mailbox and sends queued outbound mail.

python -m app.worker           # loop forever
python -m app.worker --once    # a single cycle (cron / debugging)
"""

import logging
import signal
import sys
import time

from app.config import get_settings
from app.mail.graph import GraphClient
from app.mail.ingest import heartbeat, run_cycle

log = logging.getLogger("psa.worker")
_stop = False


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
        run_cycle(client, s.mail_mailbox)
        billing_jobs()
        notify_jobs()
        if "--once" in argv:
            break
        for _ in range(s.mail_poll_seconds):
            if _stop:
                break
            time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
