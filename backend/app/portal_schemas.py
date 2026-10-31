"""Schemas for the Phase 14 client-portal additions (SSO, and later attachments and exports)."""

from pydantic import BaseModel


class PortalLoginOptionsOut(BaseModel):
    sso: bool  # "Sign in with Microsoft" is configured and the portal is turned on
