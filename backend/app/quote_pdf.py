"""Client-facing proposal PDF, rendered from `quoting.proposal()` (no internal notes)."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.money import format_money

CLASS_LABELS = {
    "workstation": "Workstations",
    "server": "Servers",
    "network": "Network devices",
    "other": "Other devices",
}


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def render_quote_pdf(q: dict) -> bytes:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=styles["BodyText"], fontSize=9, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.grey)
    bold = ParagraphStyle("bo", parent=body, fontName="Helvetica-Bold")
    right = ParagraphStyle("r", parent=body, alignment=2)
    rbold = ParagraphStyle("rb", parent=bold, alignment=2)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=20, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, spaceBefore=10)
    price = ParagraphStyle("p", parent=h1, fontSize=26, spaceBefore=4)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        pageCompression=0,
        title=f"Proposal {q['number']}",
    )
    reprice = q["kind"] == "reprice"
    story = [
        Table(
            [
                [
                    _p(q["seller_name"], h1),
                    _p("PROPOSAL", ParagraphStyle("t", parent=h1, alignment=2)),
                ]
            ],
            colWidths=[4 * inch, 3 * inch],
        ),
        _p(q["seller_address"], body),
        Spacer(1, 12),
        Table(
            [
                [
                    [
                        _p("PREPARED FOR", small),
                        _p(q["client_name"], bold),
                        _p(q["client_address"], body),
                    ],
                    [
                        _p("Proposal", small),
                        _p(f"{q['number']} (version {q['version']})", body),
                        _p("Prepared", small),
                        _p(q["prepared"], body),
                        _p("Valid until", small),
                        _p(q["valid_until"] or "-", body),
                    ],
                ]
            ],
            colWidths=[4 * inch, 3 * inch],
            style=[("VALIGN", (0, 0), (-1, -1), "TOP")],
        ),
        Spacer(1, 10),
    ]
    if q.get("intro_text"):
        story += [_p(q["intro_text"], body), Spacer(1, 8)]
    story += [
        _p("Managed services, per month", small),
        _p(format_money(q["price_cents"]), price),
        _p(
            f"{q['term_months']}-month agreement"
            + (f", starting {q['effective_date']}" if reprice and q["effective_date"] else "")
            + ". Onboarding is included; there is no separate setup fee.",
            body,
        ),
        _p("How this price is built", h2),
    ]
    rows = [[_p("Item", bold), _p("Qty", rbold), _p("Rate", rbold), _p("Monthly", rbold)]]
    for line in q["base_lines"]:
        rows.append(
            [
                _p(line["description"], body),
                _p(line["quantity"], right),
                _p(format_money(line["unit_cents"]), right),
                _p(format_money(line["amount_cents"]), right),
            ]
        )
    rows.append(["", "", _p("Base price", bold), _p(format_money(q["base_cents"]), rbold)])
    for f in q["factors"]:
        rows.append(
            [
                _p(f"{f['label']}: {f['reason']}", body),
                "",
                _p(f"+{f['bp'] / 100:g}%", right),
                "",  # percentages only: per-factor cents would not add up to the once-rounded total
            ]
        )
    if q["adjustment_cents"]:
        rows.append(
            ["", "", _p("Pricing adjustment", body), _p(format_money(q["adjustment_cents"]), right)]
        )
    rows.append(["", "", _p("Monthly total", bold), _p(format_money(q["price_cents"]), rbold)])
    story.append(
        Table(
            rows,
            colWidths=[3.6 * inch, 0.6 * inch, 1.4 * inch, 1.4 * inch],
            style=TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.grey),
                ]
            ),
        )
    )
    env = q["environment"]
    dev = env["devices"]
    story += [
        _p("What we found on site", h2),
        _p(
            f"{env['users']} users across {env['sites']} site(s); {dev['priced']} covered devices, "
            f"{dev['out']} of them out of warranty.",
            body,
        ),
        Spacer(1, 6),
        _p(
            "The price reflects how much effort your environment takes to support. If the items "
            "that add to it are resolved, for example by replacing out-of-warranty equipment, "
            "ask us for a re-assessment and the corresponding additions come off your price from "
            "the following month.",
            small,
        ),
    ]
    doc.build(story)
    return buf.getvalue()
