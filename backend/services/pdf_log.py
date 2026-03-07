from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from uuid import uuid4

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from backend.config import LOG_DIR, VECTOR_STORE_IDS


def save_pdf_log(question: str, parsed: dict[str, Any], used_model: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"query_log_{timestamp}_{uuid4().hex[:8]}.pdf"
    output_path = LOG_DIR / filename

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="Juridisk forespørgselslog",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 10
    body_style.leading = 13
    heading_style = styles["Heading2"]
    heading_style.spaceBefore = 8
    heading_style.spaceAfter = 4
    mono_style = ParagraphStyle(
        "MonoLike",
        parent=body_style,
        fontName="Courier",
        fontSize=9,
        leading=11,
    )

    story: list[Any] = []
    story.append(Paragraph("Juridisk forespørgselslog", styles["Title"]))
    story.append(
        Paragraph(
            f"Tidspunkt: {escape(datetime.now().isoformat(timespec='seconds'))}",
            body_style,
        )
    )
    story.append(Paragraph(f"Model brugt: {escape(used_model)}", body_style))
    story.append(Paragraph(f"Vector stores: {escape(', '.join(VECTOR_STORE_IDS))}", body_style))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Spørgsmål", heading_style))
    story.append(Paragraph(escape(question).replace("\n", "<br/>"), body_style))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Svar", heading_style))
    answer = parsed.get("output_text", "") or "(Tomt svar)"
    story.append(Paragraph(escape(answer).replace("\n", "<br/>"), body_style))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Kilder (citations)", heading_style))
    citations = parsed.get("citations", []) or []
    if citations:
        for idx, citation in enumerate(citations, start=1):
            filename_text = citation.get("filename", "(ukendt filnavn)")
            file_id_text = citation.get("file_id", "(ukendt file_id)")
            story.append(
                Paragraph(
                    f"{idx}. {escape(filename_text)} - file_id: {escape(file_id_text)}",
                    body_style,
                )
            )
    else:
        story.append(Paragraph("Ingen citations fundet.", body_style))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Retrieval-træf (debug)", heading_style))
    chunks = parsed.get("retrieved_chunks", []) or []
    if chunks:
        for idx, chunk in enumerate(chunks, start=1):
            chunk_file = chunk.get("filename", "(ukendt fil)")
            chunk_score = chunk.get("score", "n/a")
            chunk_text = (chunk.get("text", "") or "").strip()
            story.append(
                Paragraph(
                    f"{idx}. {escape(chunk_file)} - score: {escape(str(chunk_score))}",
                    body_style,
                )
            )
            if chunk_text:
                preview = chunk_text[:1800]
                story.append(Paragraph(escape(preview).replace("\n", "<br/>"), mono_style))
            else:
                story.append(Paragraph("Intet tekstuddrag i resultatet.", body_style))
            story.append(Spacer(1, 3))
    else:
        story.append(Paragraph("Ingen retrieval-træf returneret.", body_style))

    doc.build(story)
    return output_path
