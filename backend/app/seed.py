"""Demo/dev seed data. Idempotent: does nothing if any organization already exists.

    python -m app.seed

NEVER run against production: it creates users with known example.com addresses.
"""

from sqlalchemy import func, select

from app import audit, billing
from app import db as dbmod
from app import repositories as repo
from app import ticket_services as tsvc
from app.config import get_settings
from app.deps import Ctx
from app.models import Contact, Organization, Priority, Site, Ticket, User, WorkType
from app.scope import Scope

USERS = [
    ("admin@example.com", "Ada Admin", "admin"),
    ("tech@example.com", "Terry Tech", "tech"),
    ("billing@example.com", "Bo Billing", "billing"),
    ("readonly@example.com", "Riley ReadOnly", "read_only"),
]

ORGS = [
    {
        "name": "Contoso Dental",
        "billing_address": "100 Main St, Springfield",
        "sites": [("Main Office", "100 Main St", "Springfield", "IL", "62701")],
        "contacts": [
            ("Dana Contoso", "dana@contoso-dental.example.com", "Owner", True, True),
            ("Sam Frontdesk", "sam@contoso-dental.example.com", "Office Manager", False, False),
        ],
    },
    {
        "name": "Fabrikam Engineering",
        "billing_address": "42 Industrial Way, Shelbyville",
        "sites": [
            ("HQ", "42 Industrial Way", "Shelbyville", "IL", "62565"),
            ("Field Office", "7 River Rd", "Shelbyville", "IL", "62565"),
        ],
        "contacts": [("Frank Fabrikam", "frank@fabrikam.example.com", "Principal", True, True)],
    },
    {
        "name": "Northwind Legal",
        "billing_address": None,
        "sites": [("Downtown", "1 Court Sq", "Capital City", "IL", "62702")],
        "contacts": [("Nora Northwind", "nora@northwind.example.com", "Partner", True, False)],
    },
]


TICKETS = [
    # (org name, contact email, subject, priority, assignee email, status, customer note)
    (
        "Contoso Dental",
        "dana@contoso-dental.example.com",
        "Front desk printer offline",
        "High",
        "tech@example.com",
        "open",
        "Rebooted the print spooler; testing.",
    ),
    (
        "Contoso Dental",
        "sam@contoso-dental.example.com",
        "New hire needs M365 mailbox",
        "Normal",
        None,
        "new",
        None,
    ),
    (
        "Fabrikam Engineering",
        "frank@fabrikam.example.com",
        "VPN drops every hour",
        "Urgent",
        "tech@example.com",
        "waiting_on_customer",
        "Can you send the VPN client log?",
    ),
    (
        "Northwind Legal",
        "nora@northwind.example.com",
        "Suspicious sign-in alert",
        "Urgent",
        None,
        "new",
        None,
    ),
]


def seed_tickets(db) -> None:
    if db.execute(select(func.count()).select_from(Ticket)).scalar_one():
        return
    admin = repo.get_user_by_email(db, "admin@example.com")
    if admin is None:
        return
    ctx = Ctx(db=db, user=admin, scope=Scope.all())
    priorities = {p.name: p.id for p in repo.list_lookup(db, Priority, False)}
    work_type = next(w for w in repo.list_lookup(db, WorkType, False) if w.name == "Remote")
    orgs = {o.name: o for o in db.execute(select(Organization)).scalars()}
    for org_name, email, subject, priority, assignee, status, note in TICKETS:
        org = orgs[org_name]
        contact = repo.contacts_by_email(db, email)[0]
        assignee_user = repo.get_user_by_email(db, assignee) if assignee else None
        ticket = tsvc.create_ticket(
            ctx,
            {
                "organization_id": org.id,
                "contact_id": contact.id,
                "subject": subject,
                "priority_id": priorities[priority],
                "assignee_id": assignee_user.id if assignee_user else None,
                "description": f"{subject}. Reported by {contact.name}.",
            },
        )
        if note:
            tsvc.add_note(ctx, ticket.id, note, "customer")
        if status != "new" and ticket.status != status:
            tsvc.update_ticket(ctx, ticket.id, {"status": status})
        if assignee_user:
            tech_ctx = Ctx(db=db, user=assignee_user, scope=Scope.all())
            tsvc.add_time(
                tech_ctx,
                ticket.id,
                {
                    "work_type_id": work_type.id,
                    "minutes": 20,
                    "billable": True,
                    "note": "Initial triage",
                },
            )
    # one email from an unknown sender awaiting triage
    tsvc.create_ticket(
        ctx,
        {
            "organization_id": None,
            "subject": "Do you offer web hosting?",
            "description": "Hi, are you able to host our website?",
        },
        source="email",
        requester_email="lead@unknown-company.example.com",
    )


def seed_billing(db) -> None:
    """Demo rates, agreements and a product sale so a billing run has something to show."""
    from datetime import date

    from app.models import Agreement, Settings

    if db.execute(select(func.count()).select_from(Agreement)).scalar_one():
        return
    admin = repo.get_user_by_email(db, "admin@example.com")
    if admin is None:
        return
    ctx = Ctx(db=db, user=admin, scope=Scope.all())
    settings = db.get(Settings, 1)
    settings.company_name = settings.company_name or "Example MSP LLC"
    settings.company_address = (
        settings.company_address or "100 Technology Dr\nSpringfield, IL 62701"
    )
    settings.invoice_footer = (
        settings.invoice_footer or "Thank you for your business. Pay by ACH or check."
    )
    rates = {"Remote": (15000, False), "Onsite": (20000, True), "After hours": (22500, False)}
    for wt in repo.list_lookup(db, WorkType, False):
        if wt.name in rates:
            wt.rate_cents, wt.taxable = rates[wt.name]
    db.flush()
    orgs = {o.name: o for o in db.execute(select(Organization)).scalars()}
    orgs["Contoso Dental"].tax_rate_bp = 825
    orgs["Contoso Dental"].payment_terms_days = 15
    plan = [
        ("Contoso Dental", "Managed Services", "per_user", 1200, 12, True),
        ("Fabrikam Engineering", "Endpoint Management", "per_device", 800, 30, False),
        ("Northwind Legal", "Security Retainer", "flat", 150000, 1, False),
    ]
    for org_name, name, kind, price, qty, taxable in plan:
        billing.create_agreement(
            ctx,
            {
                "organization_id": orgs[org_name].id,
                "name": name,
                "type": kind,
                "unit_price_cents": price,
                "quantity": qty,
                "taxable": taxable,
                "start_date": date(2026, 1, 1),
                "end_date": None,
                "notes": None,
            },
        )
    laptop = billing.create_product(
        ctx,
        {
            "sku": "LAP-14",
            "name": "Laptop 14in (business)",
            "description": None,
            "unit_price_cents": 89900,
            "cost_cents": 72000,
            "taxable": True,
        },
    )
    billing.create_charge(
        ctx,
        {
            "organization_id": orgs["Fabrikam Engineering"].id,
            "product_id": laptop.id,
            "quantity": 2,
        },
    )


def run() -> None:
    if get_settings().is_production:
        raise SystemExit("Refusing to seed demo data in production")
    with dbmod.new_session() as db:
        dbmod.set_org_scope(db, "all")
        if db.execute(select(func.count()).select_from(Organization)).scalar_one():
            print("Organizations already exist; skipping organizations and users.")
            seed_tickets(db)
            seed_billing(db)
            db.commit()
            return
        for email, name, role in USERS:
            if db.execute(select(User).where(func.lower(User.email) == email)).first() is None:
                user = User(email=email, display_name=name, role=role)
                db.add(user)
                db.flush()
                audit.record(
                    db, None, "user.create", user, after=audit.snapshot(user), detail={"seed": True}
                )
        for spec in ORGS:
            org = Organization(name=spec["name"], billing_address=spec["billing_address"])
            db.add(org)
            db.flush()
            audit.record(
                db,
                None,
                "organization.create",
                org,
                after=audit.snapshot(org),
                organization_id=org.id,
                detail={"seed": True},
            )
            first_site = None
            for name, line1, city, state, zip_ in spec["sites"]:
                site = Site(
                    organization_id=org.id,
                    name=name,
                    address_line1=line1,
                    city=city,
                    state=state,
                    postal_code=zip_,
                )
                db.add(site)
                db.flush()
                first_site = first_site or site
                audit.record(
                    db,
                    None,
                    "site.create",
                    site,
                    after=audit.snapshot(site),
                    organization_id=org.id,
                    detail={"seed": True},
                )
            for name, email, title, primary, billing in spec["contacts"]:
                contact = Contact(
                    organization_id=org.id,
                    site_id=first_site.id,
                    name=name,
                    email=email,
                    title=title,
                    is_primary=primary,
                    is_billing_contact=billing,
                )
                db.add(contact)
                db.flush()
                audit.record(
                    db,
                    None,
                    "contact.create",
                    contact,
                    after=audit.snapshot(contact),
                    organization_id=org.id,
                    detail={"seed": True},
                )
        seed_tickets(db)
        seed_billing(db)
        db.commit()
        print(f"Seeded {len(USERS)} users, {len(ORGS)} organizations, demo tickets and billing.")


if __name__ == "__main__":
    run()
