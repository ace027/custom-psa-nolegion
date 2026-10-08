"""Re-encrypt every stored vendor credential with the primary CREDENTIALS_KEY.

Rotation: put the NEW key first and the old one second in CREDENTIALS_KEY ("new,old"), restart,
run `python -m app.rekey`, then remove the old key. See docs/INTEGRATIONS.md.
"""

import sys

from sqlalchemy import select

from app import crypto
from app import db as dbmod
from app.models import Integration


def main() -> int:
    n = 0
    with dbmod.new_session() as db:
        dbmod.set_org_scope(db, "all")
        for i in db.scalars(select(Integration).where(Integration.credentials.is_not(None))):
            i.credentials = crypto.reencrypt(i.credentials)
            n += 1
        db.commit()
    print(f"re-encrypted {n} credential set(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
