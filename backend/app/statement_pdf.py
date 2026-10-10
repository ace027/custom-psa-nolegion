"""Statement PDF, rendered from the frozen snapshot stored with the statement."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.money import format_money


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def render_statement_pdf(snap: dict) -> bytes:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=styles["BodyText"], fontSize=9, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.grey)
    bold = ParagraphStyle("bo", parent=body, fontName="Helvetica-Bold")
    right = ParagraphStyle("r", parent=body, alignment=2)
    rbold = ParagraphStyle("rb", parent=bold, alignment=2)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=20, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, spaceBefore=10)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        pageCompression=0,
        title=f"Statement {snap['as_of']}",
    )
    story = [
        Table(
            [
                [
                    _p(snap.get("seller_name"), h1),
                    _p("STATEMENT", ParagraphStyle("t", parent=h1, alignment=2)),
                ]
            ],
            colWidths=[4 * inch, 3 * inch],
        ),
        _p(snap.get("seller_address"), body),
        Spacer(1, 12),
        Table(
            [
                [
                    [
                        _p("ACCOUNT", small),
                        _p(snap["client_name"], bold),
                        _p(snap.get("client_address"), body),
                    ],
                    [
                        _p("As of", small),
                        _p(snap["as_of"], body),
                        Spacer(1, 6),
                        _p("Balance due", small),
                        _p(format_money(snap["total_due_cents"]), bold),
                    ],
                ]
            ],
            colWidths=[4 * inch, 3 * inch],
            style=[("VALIGN", (0, 0), (-1, -1), "TOP")],
        ),
        Spacer(1, 10),
    ]

    a = snap["aging"]
    aging_rows = [
        ["Current", "1-30", "31-60", "61-90", "90+"],
        [format_money(a[k]) for k in ("current", "d1_30", "d31_60", "d61_90", "d90_plus")],
    ]
    story.append(
        Table(
            [[_p(c, bold if r == 0 else body) for c in row] for r, row in enumerate(aging_rows)],
            colWidths=[1.4 * inch] * 5,
            style=TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ]
            ),
        )
    )

    story.append(_p("Open invoices", h2))
    rows = [
        [
            _p(h, bold if i < 3 else rbold)
            for i, h in enumerate(
                ["Invoice", "Date", "Due", "Total", "Paid / written off", "Balance"]
            )
        ]
    ]
    for inv in snap["invoices"]:
        late = f"  ({inv['days_past_due']}d late)" if inv["days_past_due"] > 0 else ""
        rows.append(
            [
                _p(inv["number"], body),
                _p(inv["invoice_date"], body),
                _p(inv["due_date"] + late, body),
                _p(format_money(inv["total_cents"]), right),
                _p(format_money(inv["settled_cents"]), right),
                _p(format_money(inv["balance_cents"]), right),
            ]
        )
    if not snap["invoices"]:
        rows.append([_p("No open invoices.", body)] + [""] * 5)
    story.append(
        Table(
            rows,
            colWidths=[1.2 * inch, 0.9 * inch, 1.5 * inch, 0.9 * inch, 1.1 * inch, 0.9 * inch],
            repeatRows=1,
            style=TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            ),
        )
    )

    story.append(_p(f"Payments received since {snap['payments_since']}", h2))
    prow = [[_p("Date", bold), _p("Method / reference", bold), _p("Amount", rbold)]]
    for pay in snap["payments"]:
        ref = pay["method"] + (f" #{pay['reference']}" if pay.get("reference") else "")
        prow.append(
            [
                _p(pay["received_on"], body),
                _p(ref, body),
                _p(format_money(pay["amount_cents"]), right),
            ]
        )
    if not snap["payments"]:
        prow.append([_p("None.", body), "", ""])
    story.append(
        Table(
            prow,
            colWidths=[1.2 * inch, 4 * inch, 1.3 * inch],
            style=TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
                ]
            ),
        )
    )

    story.append(Spacer(1, 10))
    summary = [
        ["Total balance due", format_money(snap["total_due_cents"])],
        ["  of which past due", format_money(snap["overdue_cents"])],
    ]
    if snap["credit_cents"]:
        summary.append(["Credit on account (not yet applied)", format_money(snap["credit_cents"])])
    story.append(
        Table(
            [[_p(k, right), _p(v, rbold)] for k, v in summary],
            colWidths=[5.2 * inch, 1.3 * inch],
            style=[("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black)],
        )
    )
    if snap.get("footer"):
        story += [Spacer(1, 16), _p(snap["footer"], small)]
    doc.build(story)
    return buf.getvalue()
