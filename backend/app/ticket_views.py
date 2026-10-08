"""Turn ORM tickets into API output (adds derived SLA state)."""

from datetime import datetime

from app.models import Ticket
from app.schemas import TicketOut
from app.sla import Calendar, sla_state


def ticket_out(t: Ticket, cal: Calendar, at_risk_percent: int, now: datetime) -> TicketOut:
    return TicketOut(
        id=t.id,
        number=t.number,
        organization_id=t.organization_id,
        organization_name=t.organization.name if t.organization else None,
        contact_id=t.contact_id,
        contact_name=t.contact.name if t.contact else None,
        site_id=t.site_id,
        queue_id=t.queue_id,
        queue_name=t.queue.name,
        category_id=t.category_id,
        category_name=t.category.name if t.category else None,
        priority_id=t.priority_id,
        priority_name=t.priority.name,
        priority_rank=t.priority.rank,
        status=t.status,
        status_id=t.status_id,
        status_name=t.status_ref.name,
        assignee_id=t.assignee_id,
        assignee_name=t.assignee.display_name if t.assignee else None,
        subject=t.subject,
        description=t.description,
        source=t.source,
        requester_email=t.requester_email,
        needs_triage=t.organization_id is None,
        sla_state=sla_state(t, cal, at_risk_percent, now),
        sla_first_response_due=t.sla_first_response_due,
        sla_resolution_due=t.sla_resolution_due,
        first_responded_at=t.first_responded_at,
        resolved_at=t.resolved_at,
        closed_at=t.closed_at,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )
