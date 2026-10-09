"""Invoice PDF (reportlab, pure Python). Uncompressed streams so tests can read the text."""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import Invoice, InvoiceLine, Settings
from app.money import format_money


def _p(text: str | None, style) -> Paragraph:
    return Paragraph(escape(text or "").replace("\n", "<br/>"), style)


def _qty(q) -> str:
    text = f"{q:f}".rstrip("0").rstrip(".")
    return text or "0"


def render_invoice_pdf(invoice: Invoice, lines: list[InvoiceLine], settings: Settings) -> bytes:
    """Final invoices render from their frozen snapshots; drafts from live data + DRAFT mark."""
    final = invoice.status in ("final", "void") and invoice.number is not None
    seller_name = invoice.seller_name if final else settings.company_name
    seller_address = invoice.seller_address if final else settings.company_address
    footer = invoice.footer if final else settings.invoice_footer
    bill_name = invoice.bill_to_name if final else invoice.organization.name
    bill_address = invoice.bill_to_address if final else invoice.organization.billing_address

    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9, leading=12)
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.grey)
    right = ParagraphStyle("right", parent=body, alignment=2)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=20, spaceAfter=2)
    bold = ParagraphStyle("bold", parent=body, fontName="Helvetica-Bold")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=f"Invoice {invoice.number or 'DRAFT'}",
        pageCompression=0,
    )
    label = "INVOICE"
    if invoice.status == "void":
        label = "INVOICE (VOID)"
    elif invoice.status == "draft":
        label = "INVOICE (DRAFT)"

    story = [
        Table(
            [[_p(seller_name or "", h1), _p(label, ParagraphStyle("t", parent=h1, alignment=2))]],
            colWidths=[4 * inch, 3 * inch],
        ),
        _p(seller_address, body),
        Spacer(1, 14),
    ]
    meta = [
        ["Invoice #", invoice.number or "(assigned when finalized)"],
        ["Invoice date", invoice.invoice_date.isoformat() if invoice.invoice_date else ""],
        ["Due date", invoice.due_date.isoformat() if invoice.due_date else ""],
    ]
    if invoice.terms_days is not None:
        meta.append(["Terms", f"Net {invoice.terms_days}"])
    if invoice.period_start and invoice.period_end:
        meta.append(["Period", f"{invoice.period_start} to {invoice.period_end}"])
    story.append(
        Table(
            [
                [
                    [_p("BILL TO", small), _p(bill_name, bold), _p(bill_address, body)],
                    Table(
                        [[_p(k, small), _p(v, body)] for k, v in meta],
                        colWidths=[1.1 * inch, 2.0 * inch],
                    ),
                ]
            ],
            colWidths=[3.8 * inch, 3.2 * inch],
            style=[("VALIGN", (0, 0), (-1, -1), "TOP")],
        )
    )
    story.append(Spacer(1, 14))

    rows = [
        [
            _p("Description", bold),
            _p("Qty", ParagraphStyle("r1", parent=bold, alignment=2)),
            _p("Unit price", ParagraphStyle("r2", parent=bold, alignment=2)),
            _p("Amount", ParagraphStyle("r3", parent=bold, alignment=2)),
            _p("Tax", ParagraphStyle("r4", parent=bold, alignment=2)),
        ]
    ]
    for line in lines:
        tax = f"{line.tax_rate_bp / 100:g}%" if line.tax_rate_bp else ""
        rows.append(
            [
                _p(line.description, body),
                _p(_qty(line.quantity), right),
                _p(format_money(line.unit_price_cents), right),
                _p(format_money(line.amount_cents), right),
                _p(tax, right),
            ]
        )
    story.append(
        Table(
            rows,
            colWidths=[3.4 * inch, 0.7 * inch, 1.1 * inch, 1.1 * inch, 0.7 * inch],
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
    story.append(Spacer(1, 10))
    totals = [
        ["Subtotal", format_money(invoice.subtotal_cents)],
        ["Tax", format_money(invoice.tax_cents)],
        ["Total due", format_money(invoice.total_cents)],
    ]
    story.append(
        Table(
            [
                [_p(a, right), _p(b, ParagraphStyle("tb", parent=right, fontName="Helvetica-Bold"))]
                for a, b in totals
            ],
            colWidths=[5.6 * inch, 1.4 * inch],
            style=[("LINEABOVE", (0, 2), (-1, 2), 0.8, colors.black)],
        )
    )
    if invoice.memo:
        story += [Spacer(1, 12), _p("Notes", bold), _p(invoice.memo, body)]
    if invoice.status == "void" and invoice.void_reason:
        story += [Spacer(1, 8), _p(f"Voided: {invoice.void_reason}", bold)]
    if footer:
        story += [Spacer(1, 18), _p(footer, small)]

    def watermark(canvas, _doc):
        if invoice.status in ("draft", "void"):
            canvas.saveState()
            canvas.setFont("Helvetica-Bold", 90)
            canvas.setFillColor(colors.Color(0.85, 0.85, 0.85, alpha=0.5))
            canvas.translate(LETTER[0] / 2, LETTER[1] / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "VOID" if invoice.status == "void" else "DRAFT")
            canvas.restoreState()

    doc.build(story, onFirstPage=watermark, onLaterPages=watermark)
    return buf.getvalue()
