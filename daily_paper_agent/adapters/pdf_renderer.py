from __future__ import annotations

import re
from pathlib import Path


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_inline(text: str) -> str:
    s = _escape_html(text)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="blue">\1</link>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', s)
    s = re.sub(r"(?<!\")\b(https?://[^\s<]+)", r'<link href="\1" color="blue">\1</link>', s)
    return s


def _is_table_sep(line: str) -> bool:
    line = line.strip()
    if "|" not in line:
        return False
    compact = line.replace("|", "").replace("-", "").replace(":", "").replace(" ", "")
    return compact == ""


def _parse_table_rows(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    rows: list[list[str]] = []
    i = start
    while i < len(lines):
        line = lines[i].rstrip("\n")
        if "|" not in line or not line.strip():
            break
        if _is_table_sep(line):
            i += 1
            continue
        parts = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(parts)
        i += 1
    return rows, i


def render_pdf(markdown_text: str, output_path: Path) -> Path:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise RuntimeError("reportlab is required for PDF generation") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Better CJK rendering for Chinese report.
    font_name = "Helvetica"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        font_name = "STSong-Light"
    except Exception:
        pass

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    base_styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="TitleCN",
        parent=base_styles["Title"],
        fontName=font_name,
        fontSize=20,
        leading=26,
        spaceAfter=10,
    )
    h2_style = ParagraphStyle(
        name="H2CN",
        parent=base_styles["Heading2"],
        fontName=font_name,
        fontSize=14,
        leading=20,
        spaceBefore=10,
        spaceAfter=6,
    )
    h3_style = ParagraphStyle(
        name="H3CN",
        parent=base_styles["Heading3"],
        fontName=font_name,
        fontSize=12,
        leading=18,
        spaceBefore=8,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        name="BodyCN",
        parent=base_styles["BodyText"],
        fontName=font_name,
        fontSize=10.8,
        leading=17,
        spaceAfter=5,
    )
    quote_style = ParagraphStyle(
        name="QuoteCN",
        parent=body_style,
        leftIndent=12,
        textColor=colors.HexColor("#444444"),
        backColor=colors.HexColor("#f6f6f6"),
    )
    code_style = ParagraphStyle(
        name="CodeCN",
        parent=body_style,
        fontName="Courier",
        fontSize=9.2,
        leading=13,
        backColor=colors.HexColor("#f5f5f5"),
        leftIndent=8,
        rightIndent=8,
        borderPadding=6,
    )

    lines = markdown_text.splitlines()
    story = []
    i = 0

    while i < len(lines):
        line = lines[i].rstrip("\n")
        stripped = line.strip()

        if not stripped:
            story.append(Spacer(1, 5))
            i += 1
            continue

        if stripped.startswith("```"):
            i += 1
            code_lines = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1
            code_text = "\n".join(code_lines).rstrip()
            if code_text:
                story.append(Preformatted(code_text, code_style))
                story.append(Spacer(1, 6))
            continue

        if stripped.startswith("# "):
            story.append(Paragraph(_format_inline(stripped[2:].strip()), title_style))
            i += 1
            continue

        if stripped.startswith("## "):
            story.append(Paragraph(_format_inline(stripped[3:].strip()), h2_style))
            i += 1
            continue

        if stripped.startswith("### "):
            story.append(Paragraph(_format_inline(stripped[4:].strip()), h3_style))
            i += 1
            continue

        if "|" in stripped and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
            rows, nxt = _parse_table_rows(lines, i)
            if rows:
                width = max(len(r) for r in rows)
                norm = [r + [""] * (width - len(r)) for r in rows]
                table_data = [[Paragraph(_format_inline(c), body_style) for c in row] for row in norm]
                tbl = Table(table_data, repeatRows=1)
                tbl.setStyle(
                    TableStyle(
                        [
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f2f5")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.append(tbl)
                story.append(Spacer(1, 8))
                i = nxt
                continue

        m_bullet = re.match(r"^[-*]\s+(.*)$", stripped)
        if m_bullet:
            story.append(Paragraph("• " + _format_inline(m_bullet.group(1)), body_style))
            i += 1
            continue

        m_num = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if m_num:
            story.append(Paragraph(f"{m_num.group(1)}. " + _format_inline(m_num.group(2)), body_style))
            i += 1
            continue

        m_quote = re.match(r"^>\s?(.*)$", stripped)
        if m_quote:
            story.append(Paragraph(_format_inline(m_quote.group(1)), quote_style))
            i += 1
            continue

        para = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt:
                break
            if nxt.startswith(("#", "##", "###", "```", "> ")):
                break
            if re.match(r"^[-*]\s+", nxt) or re.match(r"^\d+\.\s+", nxt):
                break
            if "|" in nxt and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
                break
            para.append(nxt)
            i += 1
        story.append(Paragraph(_format_inline(" ".join(para)), body_style))

    doc.build(story)
    return output_path
