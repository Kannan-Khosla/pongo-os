import csv
import html
from io import BytesIO, StringIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape, legal, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle


def tabular_pdf_bytes(csv_text: str, title: str) -> bytes:
    """Render an existing CSV export as the matching operational PDF."""
    parsed_rows = list(csv.reader(StringIO(csv_text)))
    headers = [value.lstrip("\ufeff") for value in parsed_rows[0]] if parsed_rows else ["Record"]
    rows = parsed_rows[1:]
    column_count = max(1, len(headers))
    page_size = landscape(letter if column_count <= 8 else legal if column_count <= 16 else A3)
    page_width, _ = page_size
    font_size = 6.5 if column_count <= 8 else 5.5 if column_count <= 16 else 4.8

    def safe(value: object) -> str:
        return html.escape(str(value or "")).replace("\n", "<br/>")

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PongoDocumentTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=22,
        textColor=colors.HexColor("#10114d"),
        spaceAfter=4,
    )
    eyebrow_style = ParagraphStyle(
        "PongoDocumentEyebrow",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#b43b18"),
        spaceAfter=3,
    )
    cell_style = ParagraphStyle(
        "PongoDocumentCell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=font_size,
        leading=font_size + 1.5,
        textColor=colors.HexColor("#18192b"),
        splitLongWords=True,
    )
    header_style = ParagraphStyle(
        "PongoDocumentHeader",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=page_size,
        leftMargin=0.35 * inch,
        rightMargin=0.35 * inch,
        topMargin=0.32 * inch,
        bottomMargin=0.48 * inch,
        title=title,
        author="Pongo Inventory OS",
        subject="Operational record",
    )

    def footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dcdde8"))
        canvas.line(doc.leftMargin, 0.34 * inch, page_width - doc.rightMargin, 0.34 * inch)
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#62647b"))
        canvas.drawString(doc.leftMargin, 0.19 * inch, "Pongo Inventory OS · Operational record")
        canvas.drawRightString(page_width - doc.rightMargin, 0.19 * inch, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    story = [
        Paragraph("PONGO OS / DOCUMENT RECORD", eyebrow_style),
        Paragraph(safe(title), title_style),
        Paragraph("Generated from the same verified rows as the CSV download.", cell_style),
        Spacer(1, 10),
    ]
    if rows:
        widths = []
        for index, header in enumerate(headers):
            observed = [len(str(row[index])) for row in rows[:50] if index < len(row)]
            widths.append(max(7, min(32, max([len(header), *observed]))))
        available_width = document.width
        width_total = sum(widths) or column_count
        table_rows = [
            [Paragraph(safe(header), header_style) for header in headers],
            *[
                [Paragraph(safe(row[index] if index < len(row) else ""), cell_style) for index in range(column_count)]
                for row in rows
            ],
        ]
        table = LongTable(
            table_rows,
            colWidths=[available_width * (width / width_total) for width in widths],
            repeatRows=1,
            splitByRow=True,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10114d")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f9")]),
                    ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#dcdde8")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e6e7ee")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)
    else:
        story.append(Paragraph("This record has no line items.", cell_style))
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def pdf_content_disposition(filename: str, preview: bool) -> str:
    disposition = "inline" if preview else "attachment"
    return f'{disposition}; filename="{filename}"'
