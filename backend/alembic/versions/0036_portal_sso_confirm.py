"""Portal SSO: confirm the first Microsoft sign-in through an emailed one-time link

Revision ID: 0036
Revises: 0035

Entra does not verify the email / preferred_username claims, so a first sign-in that matched a
contact only by email no longer binds the oid. It issues a portal sign-in link instead, and the
pending binding travels with that link:

- portal_login_tokens.bind_entra_oid, bind_entra_tenant_id: nullable; NULL on plain links.
- portal_login_tokens.bind_browser_hash: sha256 of a secret held in an httponly cookie by the browser
  that completed the Microsoft sign-in. The oid is bound only when the link is opened in that same
  browser, so a tenant member cannot get the real contact to link the member's Microsoft account by
  clicking the confirm email (account-linking CSRF).

Grants: portal_login_tokens has table-wide SELECT, INSERT, UPDATE for the app role (0008), which
covers the new columns; no column-level grants exist on it.
"""

import sqlalchemy as sa

from alembic import op

revision = "0036"
down_revision = "0035"


def upgrade() -> None:
    op.add_column("portal_login_tokens", sa.Column("bind_entra_oid", sa.String(64)))
    op.add_column("portal_login_tokens", sa.Column("bind_entra_tenant_id", sa.String(64)))
    op.add_column("portal_login_tokens", sa.Column("bind_browser_hash", sa.String(64)))


def downgrade() -> None:
    # Pending confirmations are short-lived (portal_link_minutes); dropping them only means the
    # contact signs in without binding and must use Sign in with Microsoft again.
    op.drop_column("portal_login_tokens", "bind_browser_hash")
    op.drop_column("portal_login_tokens", "bind_entra_tenant_id")
    op.drop_column("portal_login_tokens", "bind_entra_oid")
