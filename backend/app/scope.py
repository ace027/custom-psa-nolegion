"""App-layer client isolation. Every repository query goes through Scope; Postgres RLS is the
independent backstop if a query ever forgets to."""

from dataclasses import dataclass

from sqlalchemy import Select
from sqlalchemy.orm import InstrumentedAttribute


@dataclass(frozen=True)
class Scope:
    org_ids: frozenset[int] | None  # None = all organizations (staff)

    @classmethod
    def all(cls) -> "Scope":
        return cls(None)

    @classmethod
    def orgs(cls, *ids: int) -> "Scope":
        return cls(frozenset(ids))

    def allows(self, org_id: int) -> bool:
        return self.org_ids is None or org_id in self.org_ids

    def apply(self, stmt: Select, column: InstrumentedAttribute) -> Select:
        if self.org_ids is None:
            return stmt
        return stmt.where(column.in_(self.org_ids))

    def rls_value(self) -> str:
        return "all" if self.org_ids is None else ",".join(str(i) for i in sorted(self.org_ids))
