"""PDF Builder skill — generate professional invoices, contracts, proposals and documents."""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from src.skills.base_skill import BaseSkill, SkillResult

log = structlog.get_logger("assistant.skills.pdf_builder")

OUTPUT_DIR = Path("/tmp/ASSISTANT_AI/output/pdfs")

# ── Branding constants ──────────────────────────────────────────────
COMPANY_NAME = "XPlus Technologies LLC"
COMPANY_WEBSITE = "xplustechnologies.com"
COMPANY_TAGLINE = "Technology Solutions & Digital Innovation"

# Colors (RGB tuples)
COLOR_PRIMARY = (15, 30, 65)       # Deep navy
COLOR_SECONDARY = (0, 120, 200)    # Bright blue accent
COLOR_ACCENT = (0, 180, 140)       # Teal accent
COLOR_TEXT = (30, 30, 30)          # Near-black text
COLOR_TEXT_LIGHT = (100, 100, 100) # Gray text
COLOR_TABLE_HEADER = (15, 30, 65)  # Navy header
COLOR_TABLE_ROW_ALT = (240, 245, 250)  # Light blue-gray alternating row
COLOR_WHITE = (255, 255, 255)
COLOR_BORDER = (200, 210, 220)     # Subtle border
COLOR_TOTAL_BG = (235, 245, 255)   # Light blue for total row


def _ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _generate_invoice_number() -> str:
    """Generate invoice number based on date + short hash for uniqueness."""
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y%m%d")
    time_hash = hashlib.sha256(now.isoformat().encode()).hexdigest()[:4].upper()
    return f"INV-{date_part}-{time_hash}"


def _generate_doc_number(prefix: str) -> str:
    now = datetime.now(timezone.utc)
    date_part = now.strftime("%Y%m%d")
    time_hash = hashlib.sha256(now.isoformat().encode()).hexdigest()[:4].upper()
    return f"{prefix}-{date_part}-{time_hash}"


def _safe_filename(text: str) -> str:
    """Convert text to safe filename component."""
    safe = "".join(c if c.isalnum() or c in "-_ " else "" for c in text)
    return safe.strip().replace(" ", "_")[:50]


def _sanitize_text(text: str) -> str:
    """Replace Unicode chars unsupported by Helvetica (latin-1) with safe equivalents."""
    replacements = {
        "\u2014": "--",   # em-dash
        "\u2013": "-",    # en-dash
        "\u2018": "'",    # left single quote
        "\u2019": "'",    # right single quote / apostrophe
        "\u201c": '"',    # left double quote
        "\u201d": '"',    # right double quote
        "\u2026": "...",  # ellipsis
        "\u00a0": " ",    # non-breaking space
        "\u2022": "*",    # bullet
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


class _PDFDoc:
    """Wrapper around fpdf.FPDF with branding helpers."""

    def __init__(self) -> None:
        try:
            from fpdf import FPDF
        except ImportError:
            raise ImportError("fpdf2")

        self.pdf = FPDF(orientation="P", unit="mm", format="A4")
        self.pdf.set_auto_page_break(auto=True, margin=25)
        self.pdf.add_page()
        self._width = self.pdf.w - self.pdf.l_margin - self.pdf.r_margin

    # ── Header / Footer ─────────────────────────────────────────────

    def draw_header(self, doc_type: str = "", doc_number: str = "") -> None:
        pdf = self.pdf
        top_y = pdf.get_y()

        # Top accent bar
        pdf.set_fill_color(*COLOR_SECONDARY)
        pdf.rect(0, 0, pdf.w, 3, "F")

        # Company name block
        pdf.set_y(10)
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_text_color(*COLOR_PRIMARY)
        pdf.cell(0, 10, COMPANY_NAME, new_x="LMARGIN", new_y="NEXT")

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_TEXT_LIGHT)
        pdf.cell(0, 5, COMPANY_TAGLINE, new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 5, COMPANY_WEBSITE, new_x="LMARGIN", new_y="NEXT")

        # Doc type and number on the right side
        if doc_type:
            pdf.set_y(12)
            pdf.set_font("Helvetica", "B", 20)
            pdf.set_text_color(*COLOR_SECONDARY)
            pdf.cell(0, 10, doc_type.upper(), align="R", new_x="LMARGIN", new_y="NEXT")

            if doc_number:
                pdf.set_y(24)
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(*COLOR_TEXT_LIGHT)
                pdf.cell(0, 5, doc_number, align="R", new_x="LMARGIN", new_y="NEXT")

        # Separator line
        pdf.set_y(38)
        pdf.set_draw_color(*COLOR_SECONDARY)
        pdf.set_line_width(0.5)
        pdf.line(pdf.l_margin, 38, pdf.w - pdf.r_margin, 38)
        pdf.set_y(42)

    def draw_footer_on_pages(self) -> None:
        """Draw footer on all pages after content is done."""
        pdf = self.pdf
        total_pages = pdf.pages_count
        for page_num in range(1, total_pages + 1):
            pdf.page = page_num
            y_footer = pdf.h - 18

            # Footer line
            pdf.set_draw_color(*COLOR_BORDER)
            pdf.set_line_width(0.3)
            pdf.line(pdf.l_margin, y_footer, pdf.w - pdf.r_margin, y_footer)

            pdf.set_y(y_footer + 2)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*COLOR_TEXT_LIGHT)
            pdf.cell(0, 4, f"{COMPANY_NAME}  |  {COMPANY_WEBSITE}", new_x="LMARGIN", new_y="NEXT")
            pdf.cell(
                self._width / 2, 4,
                f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            )
            pdf.cell(
                self._width / 2, 4,
                f"Page {page_num} of {total_pages}",
                align="R",
            )

    # ── Content helpers ──────────────────────────────────────────────

    def info_block(self, label: str, lines: list[str], x: float | None = None) -> None:
        pdf = self.pdf
        if x is not None:
            pdf.set_x(x)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*COLOR_SECONDARY)
        pdf.cell(0, 5, label.upper(), new_x="LMARGIN", new_y="NEXT")
        if x is not None:
            pdf.set_x(x)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*COLOR_TEXT)
        for line in lines:
            if x is not None:
                pdf.set_x(x)
            pdf.cell(0, 5, _sanitize_text(line), new_x="LMARGIN", new_y="NEXT")

    def section_title(self, title: str) -> None:
        pdf = self.pdf
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*COLOR_PRIMARY)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*COLOR_ACCENT)
        pdf.set_line_width(0.4)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.l_margin + 40, y)
        pdf.ln(3)

    def body_text(self, text: str) -> None:
        pdf = self.pdf
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*COLOR_TEXT)
        pdf.multi_cell(0, 5.5, _sanitize_text(text))
        pdf.ln(2)

    def save(self, filepath: Path) -> None:
        self.draw_footer_on_pages()
        self.pdf.output(str(filepath))


# ── PDF generators ───────────────────────────────────────────────────

def _build_invoice(client: str, items_raw: str) -> Path:
    """Build a professional invoice PDF and return the file path."""
    _ensure_output_dir()

    # Parse items: "item1:price1, item2:price2"
    items: list[tuple[str, float]] = []
    for chunk in items_raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            name, price_str = chunk.rsplit(":", 1)
            try:
                price = float(price_str.strip().replace("$", "").replace(",", ""))
            except ValueError:
                price = 0.0
            items.append((name.strip(), price))
        else:
            items.append((chunk, 0.0))

    if not items:
        raise ValueError("No se encontraron items. Formato: item1:precio1, item2:precio2")

    inv_number = _generate_invoice_number()
    today = datetime.now(timezone.utc)
    due_date = today.strftime("%B %d, %Y")  # Same day for simplicity

    doc = _PDFDoc()
    doc.draw_header(doc_type="Invoice", doc_number=inv_number)

    pdf = doc.pdf

    # ── Date and invoice meta ────────────────────────────────────────
    y_info = pdf.get_y()

    # Left: Bill To
    pdf.set_y(y_info)
    doc.info_block("Bill To", [client])

    # Right: Invoice details
    pdf.set_y(y_info)
    right_x = pdf.l_margin + doc._width * 0.6
    pdf.set_x(right_x)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*COLOR_SECONDARY)
    pdf.cell(0, 5, "INVOICE DETAILS", new_x="LMARGIN", new_y="NEXT")

    detail_lines = [
        ("Invoice Date:", today.strftime("%B %d, %Y")),
        ("Due Date:", due_date),
        ("Invoice #:", inv_number),
    ]
    for label, value in detail_lines:
        pdf.set_x(right_x)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_TEXT_LIGHT)
        pdf.cell(30, 5, label)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*COLOR_TEXT)
        pdf.cell(0, 5, value, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(10)

    # ── Items table ──────────────────────────────────────────────────
    col_widths = [12, doc._width - 12 - 30 - 30 - 35, 30, 30, 35]
    headers = ["#", "Description", "Qty", "Unit Price", "Amount"]

    # Table header
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*COLOR_TABLE_HEADER)
    pdf.set_text_color(*COLOR_WHITE)
    pdf.set_draw_color(*COLOR_TABLE_HEADER)
    for i, (header, w) in enumerate(zip(headers, col_widths)):
        align = "R" if i >= 2 else "L"
        pdf.cell(w, 8, header, border=1, fill=True, align=align)
    pdf.ln()

    # Table rows
    subtotal = 0.0
    pdf.set_draw_color(*COLOR_BORDER)
    for idx, (item_name, price) in enumerate(items, 1):
        if idx % 2 == 0:
            pdf.set_fill_color(*COLOR_TABLE_ROW_ALT)
            fill = True
        else:
            pdf.set_fill_color(*COLOR_WHITE)
            fill = True

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_TEXT)

        amount = price  # qty=1 per item
        subtotal += amount

        cells = [
            (str(idx), "L"),
            (item_name, "L"),
            ("1", "R"),
            (f"${price:,.2f}", "R"),
            (f"${amount:,.2f}", "R"),
        ]
        for (val, align), w in zip(cells, col_widths):
            pdf.cell(w, 7, val, border="LR", fill=fill, align=align)
        pdf.ln()

    # Close table bottom border
    pdf.set_draw_color(*COLOR_BORDER)
    pdf.cell(sum(col_widths), 0, "", border="T")
    pdf.ln(2)

    # ── Totals ───────────────────────────────────────────────────────
    totals_x = pdf.l_margin + doc._width - 75
    total_label_w = 40
    total_val_w = 35

    def _total_row(label: str, value: str, bold: bool = False, bg: bool = False) -> None:
        pdf.set_x(totals_x)
        if bg:
            pdf.set_fill_color(*COLOR_TOTAL_BG)
        else:
            pdf.set_fill_color(*COLOR_WHITE)
        font_style = "B" if bold else ""
        size = 11 if bold else 9
        pdf.set_font("Helvetica", font_style, size)
        pdf.set_text_color(*COLOR_TEXT)
        pdf.cell(total_label_w, 7, label, fill=bg, align="R")
        pdf.set_text_color(*COLOR_PRIMARY if bold else COLOR_TEXT)
        pdf.cell(total_val_w, 7, value, fill=bg, align="R", new_x="LMARGIN", new_y="NEXT")

    _total_row("Subtotal:", f"${subtotal:,.2f}")
    _total_row("Tax (0%):", "$0.00")

    # Bold total line with accent
    pdf.set_draw_color(*COLOR_SECONDARY)
    pdf.set_line_width(0.5)
    pdf.line(totals_x, pdf.get_y(), totals_x + total_label_w + total_val_w, pdf.get_y())
    pdf.ln(1)

    _total_row("TOTAL:", f"${subtotal:,.2f}", bold=True, bg=True)

    # ── Payment info ─────────────────────────────────────────────────
    pdf.ln(12)
    doc.section_title("Payment Information")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*COLOR_TEXT)
    pdf.multi_cell(0, 5, (
        "Please make payment within 30 days of the invoice date.\n"
        "For questions regarding this invoice, contact us at: "
        f"{COMPANY_WEBSITE}"
    ))

    # ── Thank you ────────────────────────────────────────────────────
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(*COLOR_SECONDARY)
    pdf.cell(0, 6, "Thank you for your business!", align="C")

    filename = f"invoice_{_safe_filename(client)}_{today.strftime('%Y%m%d')}.pdf"
    filepath = OUTPUT_DIR / filename
    doc.save(filepath)
    return filepath


def _build_contract(client: str, terms: str) -> Path:
    """Build a contract PDF."""
    _ensure_output_dir()

    doc_number = _generate_doc_number("CTR")
    today = datetime.now(timezone.utc)

    doc = _PDFDoc()
    doc.draw_header(doc_type="Contract", doc_number=doc_number)

    pdf = doc.pdf

    # Parties
    doc.section_title("Parties")
    doc.body_text(
        f"This agreement (\"Agreement\") is entered into as of "
        f"{today.strftime('%B %d, %Y')}, by and between:\n\n"
        f"Provider: {COMPANY_NAME}\n"
        f"Client:   {client}"
    )

    # Scope of Work
    doc.section_title("Scope of Work")
    doc.body_text(terms if terms else "To be defined upon mutual agreement.")

    # Standard sections
    standard_sections = {
        "Terms and Conditions": (
            "1. This Agreement shall commence on the date first written above and "
            "continue until the completion of the services described herein, unless "
            "terminated earlier in accordance with the provisions below.\n\n"
            "2. Either party may terminate this Agreement with 30 days written notice.\n\n"
            "3. All work products created under this Agreement shall be the property "
            "of the Client upon full payment."
        ),
        "Payment Terms": (
            "Payment is due within 30 days of invoice date. Late payments may incur "
            "a fee of 1.5% per month on outstanding balances. All fees are in USD."
        ),
        "Confidentiality": (
            "Both parties agree to maintain the confidentiality of any proprietary "
            "information shared during the course of this Agreement. This obligation "
            "shall survive the termination of this Agreement for a period of 2 years."
        ),
        "Limitation of Liability": (
            f"{COMPANY_NAME}'s total liability under this Agreement shall not exceed "
            "the total fees paid by the Client under this Agreement."
        ),
        "Governing Law": (
            "This Agreement shall be governed by and construed in accordance with "
            "the laws of the State of Florida, United States."
        ),
    }

    for title, content in standard_sections.items():
        doc.section_title(title)
        doc.body_text(content)

    # Signature block
    doc.section_title("Signatures")
    pdf.ln(5)

    sig_width = doc._width / 2 - 10

    for label in [COMPANY_NAME, f"Client: {client}"]:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*COLOR_TEXT)
        pdf.ln(10)
        y = pdf.get_y()
        pdf.set_draw_color(*COLOR_BORDER)
        pdf.line(pdf.l_margin, y, pdf.l_margin + sig_width, y)
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*COLOR_TEXT_LIGHT)
        pdf.cell(sig_width, 4, f"Signature -- {label}")
        pdf.ln()
        pdf.line(pdf.l_margin, pdf.get_y() + 8, pdf.l_margin + sig_width, pdf.get_y() + 8)
        pdf.ln(9)
        pdf.cell(sig_width, 4, "Date")
        pdf.ln()

    filename = f"contract_{_safe_filename(client)}_{today.strftime('%Y%m%d')}.pdf"
    filepath = OUTPUT_DIR / filename
    doc.save(filepath)
    return filepath


def _build_proposal(client: str, title: str, description: str) -> Path:
    """Build a proposal PDF."""
    _ensure_output_dir()

    doc_number = _generate_doc_number("PRO")
    today = datetime.now(timezone.utc)

    doc = _PDFDoc()
    doc.draw_header(doc_type="Proposal", doc_number=doc_number)

    pdf = doc.pdf

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Prepared for / by
    y_info = pdf.get_y()
    doc.info_block("Prepared For", [client])

    pdf.set_y(y_info)
    right_x = pdf.l_margin + doc._width * 0.55
    pdf.set_x(right_x)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*COLOR_SECONDARY)
    pdf.cell(0, 5, "PREPARED BY", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(right_x)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*COLOR_TEXT)
    pdf.cell(0, 5, COMPANY_NAME, new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(right_x)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*COLOR_TEXT_LIGHT)
    pdf.cell(0, 5, today.strftime("%B %d, %Y"), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)

    # Executive Summary
    doc.section_title("Executive Summary")
    doc.body_text(description if description else "To be defined.")

    # Standard proposal sections
    sections = {
        "Approach": (
            "Our team will work closely with you to deliver a solution tailored to "
            "your specific needs. We follow agile methodologies to ensure transparency, "
            "flexibility, and timely delivery."
        ),
        "Timeline": (
            "A detailed project timeline will be provided upon approval of this proposal. "
            "We are committed to delivering results within the agreed-upon timeframe."
        ),
        "Investment": (
            "Pricing details will be discussed and finalized based on the scope of work "
            "outlined in this proposal. We offer flexible payment terms."
        ),
        "Why XPlus Technologies": (
            f"{COMPANY_NAME} brings deep expertise in technology solutions, digital "
            "innovation, application security, and modern web development. Our team is "
            "dedicated to delivering exceptional results and long-term value."
        ),
        "Next Steps": (
            "1. Review this proposal\n"
            "2. Schedule a follow-up call to discuss details\n"
            "3. Finalize scope and pricing\n"
            "4. Sign agreement and begin work"
        ),
    }

    for sec_title, content in sections.items():
        doc.section_title(sec_title)
        doc.body_text(content)

    filename = f"proposal_{_safe_filename(client)}_{today.strftime('%Y%m%d')}.pdf"
    filepath = OUTPUT_DIR / filename
    doc.save(filepath)
    return filepath


def _build_document(title: str, content: str) -> Path:
    """Build a generic document PDF."""
    _ensure_output_dir()

    doc_number = _generate_doc_number("DOC")
    today = datetime.now(timezone.utc)

    doc = _PDFDoc()
    doc.draw_header(doc_type="Document", doc_number=doc_number)

    pdf = doc.pdf

    # Title
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*COLOR_PRIMARY)
    pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Content — split by double newlines into paragraphs
    paragraphs = content.split("\n\n") if content else ["(Empty document)"]
    for para in paragraphs:
        doc.body_text(para.strip())

    filename = f"doc_{_safe_filename(title)}_{today.strftime('%Y%m%d')}.pdf"
    filepath = OUTPUT_DIR / filename
    doc.save(filepath)
    return filepath


# ── Skill class ──────────────────────────────────────────────────────

class PDFBuilderSkill(BaseSkill):

    @property
    def name(self) -> str:
        return "pdf_builder"

    @property
    def description(self) -> str:
        return (
            "Genera PDFs profesionales: facturas, contratos, propuestas y documentos "
            "con branding de XPlus Technologies"
        )

    @property
    def natural_patterns(self) -> dict[str, list[str]]:
        return {
            "factura": [
                r"(?:genera|crea|hazme|necesito)\s+(?:una?\s+)?factura(?:\s+(?:para|a|de)\s+(?P<args>.+))?",
                r"factura(?:r|le)?\s+(?:a|para)\s+(?P<args>.+)",
                r"(?:nueva\s+)?factura\s+(?P<args>.+)",
            ],
            "contrato": [
                r"(?:genera|crea|hazme|necesito)\s+(?:un\s+)?contrato(?:\s+(?:para|con|de)\s+(?P<args>.+))?",
                r"(?:nuevo\s+)?contrato\s+(?:para|con)\s+(?P<args>.+)",
            ],
            "propuesta": [
                r"(?:genera|crea|hazme|necesito)\s+(?:una?\s+)?propuesta(?:\s+(?:para|de)\s+(?P<args>.+))?",
                r"(?:nueva\s+)?propuesta\s+(?:para|de)\s+(?P<args>.+)",
            ],
            "documento": [
                r"(?:genera|crea|hazme|necesito)\s+(?:un\s+)?(?:pdf|documento)(?:\s+(?:de|sobre|para)\s+(?P<args>.+))?",
                r"(?:nuevo\s+)?(?:pdf|documento)\s+(?:de|sobre|para)\s+(?P<args>.+)",
            ],
        }

    @property
    def triggers(self) -> list[str]:
        return ["!pdf", "!factura", "!invoice", "!contrato", "!propuesta", "!documento"]

    async def execute(self, args: str, context: dict[str, Any]) -> SkillResult:
        # Determine subcommand from trigger or first arg
        raw_text: str = context.get("raw_text", "") or ""
        raw_lower = raw_text.lower().strip()

        # Map trigger to subcommand
        trigger_map = {
            "!factura": "factura",
            "!invoice": "factura",
            "!contrato": "contrato",
            "!propuesta": "propuesta",
            "!documento": "documento",
        }

        sub_cmd = ""
        for trigger, cmd in trigger_map.items():
            if raw_lower.startswith(trigger):
                sub_cmd = cmd
                break

        # If triggered via !pdf, subcommand is first arg
        if not sub_cmd:
            parts = args.split(maxsplit=1)
            sub_cmd = parts[0].lower() if parts else ""
            args = parts[1] if len(parts) > 1 else ""

        if sub_cmd == "plantillas":
            return SkillResult(
                success=True,
                message=(
                    "Plantillas disponibles:\n"
                    "  1. factura  — Factura profesional con tabla de items\n"
                    "  2. contrato — Contrato con secciones legales estandar\n"
                    "  3. propuesta — Propuesta de proyecto\n"
                    "  4. documento — Documento generico\n\n"
                    "Uso:\n"
                    "  !factura <cliente> | item1:precio1, item2:precio2\n"
                    "  !contrato <cliente> | <terminos>\n"
                    "  !propuesta <cliente> | <titulo> | <descripcion>\n"
                    "  !documento <titulo> | <contenido>\n"
                    "  !pdf plantillas"
                ),
            )

        if not args:
            return SkillResult(
                success=False,
                message=(
                    "Faltan argumentos. Uso:\n"
                    "  !factura <cliente> | item1:precio1, item2:precio2\n"
                    "  !contrato <cliente> | <terminos>\n"
                    "  !propuesta <cliente> | <titulo> | <descripcion>\n"
                    "  !documento <titulo> | <contenido>\n"
                    "  !pdf plantillas  — ver todas las plantillas"
                ),
            )

        try:
            if sub_cmd == "factura":
                return await self._make_invoice(args)
            elif sub_cmd == "contrato":
                return await self._make_contract(args)
            elif sub_cmd == "propuesta":
                return await self._make_proposal(args)
            elif sub_cmd in ("documento", "doc"):
                return await self._make_document(args)
            else:
                return SkillResult(
                    success=False,
                    message=(
                        f"Subcomando desconocido: {sub_cmd}\n"
                        "Usa: !pdf plantillas para ver las opciones."
                    ),
                )
        except ImportError:
            log.warning("pdf_builder.fpdf2_missing")
            return SkillResult(
                success=False,
                message=(
                    "La libreria fpdf2 no esta instalada.\n"
                    "Instala con:  pip install fpdf2"
                ),
            )
        except Exception as exc:
            log.error("pdf_builder.error", error=str(exc), sub_cmd=sub_cmd)
            return SkillResult(success=False, message=f"Error generando PDF: {exc}")

    # ── Subcommand handlers ──────────────────────────────────────────

    async def _make_invoice(self, args: str) -> SkillResult:
        parts = args.split("|", maxsplit=1)
        client = parts[0].strip()
        items_raw = parts[1].strip() if len(parts) > 1 else ""

        if not client:
            return SkillResult(
                success=False,
                message="Especifica el cliente. Ej: !factura Acme Corp | Web Design:1500, Hosting:200",
            )
        if not items_raw:
            return SkillResult(
                success=False,
                message="Especifica los items. Ej: !factura Acme Corp | Web Design:1500, Hosting:200",
            )

        filepath = await asyncio.to_thread(_build_invoice, client, items_raw)
        log.info("pdf_builder.invoice_created", client=client, path=str(filepath))
        return SkillResult(
            success=True,
            message=f"Factura generada para {client}: {filepath.name}",
            data={"file_path": str(filepath), "type": "document"},
        )

    async def _make_contract(self, args: str) -> SkillResult:
        parts = args.split("|", maxsplit=1)
        client = parts[0].strip()
        terms = parts[1].strip() if len(parts) > 1 else ""

        if not client:
            return SkillResult(
                success=False,
                message="Especifica el cliente. Ej: !contrato Acme Corp | Desarrollo de app movil",
            )

        filepath = await asyncio.to_thread(_build_contract, client, terms)
        log.info("pdf_builder.contract_created", client=client, path=str(filepath))
        return SkillResult(
            success=True,
            message=f"Contrato generado para {client}: {filepath.name}",
            data={"file_path": str(filepath), "type": "document"},
        )

    async def _make_proposal(self, args: str) -> SkillResult:
        parts = args.split("|")
        client = parts[0].strip() if len(parts) >= 1 else ""
        title = parts[1].strip() if len(parts) >= 2 else "Project Proposal"
        description = parts[2].strip() if len(parts) >= 3 else ""

        if not client:
            return SkillResult(
                success=False,
                message="Especifica el cliente. Ej: !propuesta Acme Corp | App Movil | Desarrollo completo...",
            )

        filepath = await asyncio.to_thread(_build_proposal, client, title, description)
        log.info("pdf_builder.proposal_created", client=client, path=str(filepath))
        return SkillResult(
            success=True,
            message=f"Propuesta generada para {client}: {filepath.name}",
            data={"file_path": str(filepath), "type": "document"},
        )

    async def _make_document(self, args: str) -> SkillResult:
        parts = args.split("|", maxsplit=1)
        title = parts[0].strip()
        content = parts[1].strip() if len(parts) > 1 else ""

        if not title:
            return SkillResult(
                success=False,
                message="Especifica el titulo. Ej: !documento Reporte Mensual | Contenido del reporte...",
            )

        filepath = await asyncio.to_thread(_build_document, title, content)
        log.info("pdf_builder.document_created", title=title, path=str(filepath))
        return SkillResult(
            success=True,
            message=f"Documento generado: {filepath.name}",
            data={"file_path": str(filepath), "type": "document"},
        )
