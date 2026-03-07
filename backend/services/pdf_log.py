from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
import unicodedata
from uuid import uuid4

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from backend.config import LOG_DIR, VECTOR_STORE_IDS


def normalize_mojibake_text(text: str) -> str:
    """Repair common UTF-8/latin1 mojibake such as Ã¸, Ã¦, Ã¥."""
    if not text:
        return text
    if not any(marker in text for marker in ("Ã", "Â", "â")):
        return text

    candidates = [text]

    try:
        candidates.append(text.encode("latin1").decode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    try:
        candidates.append(text.encode("cp1252").decode("utf-8"))
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

    def mojibake_score(value: str) -> int:
        return value.count("Ã") + value.count("Â") + value.count("â")

    best = min(candidates, key=mojibake_score)
    return unicodedata.normalize("NFC", best)


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
    story.append(
        Paragraph(
            escape(normalize_mojibake_text(question)).replace("\n", "<br/>"),
            body_style,
        )
    )
    story.append(Spacer(1, 6))

    story.append(Paragraph("Svar", heading_style))
    answer = normalize_mojibake_text(parsed.get("output_text", "") or "(Tomt svar)")
    story.append(Paragraph(escape(answer).replace("\n", "<br/>"), body_style))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Kilder (citations)", heading_style))
    citations = parsed.get("citations", []) or []
    chunks = parsed.get("retrieved_chunks", []) or []
    if citations:
        for idx, citation in enumerate(citations, start=1):
            filename_text = normalize_mojibake_text(
                citation.get("filename", "(ukendt filnavn)")
            )
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

    raw_citations = parsed.get("raw_citations", []) or []
    strict_audit = parsed.get("strict_sourcing_audit", {}) or {}
    if raw_citations or strict_audit:
        story.append(Paragraph("Strict sourcing (audit)", heading_style))
        allowed_file_ids = strict_audit.get("allowed_file_ids", []) or []
        filtered_count = strict_audit.get("filtered_citation_count", len(citations))
        raw_count = strict_audit.get("raw_citation_count", len(raw_citations))
        rejected = strict_audit.get("rejected_citations", []) or []
        status_text = (
            "OK - alle model-citations er inden for funden kontekst."
            if raw_count == filtered_count and not rejected
            else "ADVARSEL - nogle model-citations blev afvist af strict filter."
        )
        story.append(Paragraph(escape(status_text), body_style))
        story.append(
            Paragraph(
                f"Rå citations: {raw_count} | Efter filter: {filtered_count}",
                body_style,
            )
        )
        if allowed_file_ids:
            story.append(
                Paragraph(
                    "Tilladte file_id fra retrieval: "
                    + escape(", ".join(allowed_file_ids)),
                    body_style,
                )
            )
        if rejected:
            story.append(Paragraph("Afviste citations:", body_style))
            for item in rejected:
                fname = normalize_mojibake_text(str(item.get("filename", "")))
                fid = str(item.get("file_id", ""))
                story.append(
                    Paragraph(
                        f"- {escape(fname)} (file_id: {escape(fid)})",
                        body_style,
                    )
                )
        citation_hit_mapping = strict_audit.get("citation_hit_mapping", []) or []
        if citation_hit_mapping:
            story.append(Paragraph("Citations -> retrieval-hit #:", body_style))
            for item in citation_hit_mapping:
                fname = normalize_mojibake_text(str(item.get("filename", "")))
                fid = str(item.get("file_id", ""))
                hit_indices = item.get("retrieval_hit_indices", []) or []
                hit_text = ", ".join(str(x) for x in hit_indices) if hit_indices else "ingen match"
                note_refs = item.get("note_refs", []) or []
                note_text = ", ".join(str(x) for x in note_refs) if note_refs else "ingen"
                story.append(
                    Paragraph(
                        f"- {escape(fname)} (file_id: {escape(fid)}) -> hit #{escape(hit_text)} | noter: {escape(note_text)}",
                        body_style,
                    )
                )
            story.append(Spacer(1, 4))
            story.append(Paragraph("Retrieval-tekst for citerede hits:", body_style))
            rendered_hits: set[int] = set()
            for item in citation_hit_mapping:
                for hit_idx in item.get("retrieval_hit_indices", []) or []:
                    if not isinstance(hit_idx, int) or hit_idx < 1:
                        continue
                    if hit_idx in rendered_hits:
                        continue
                    if hit_idx > len(chunks):
                        continue
                    rendered_hits.add(hit_idx)
                    chunk = chunks[hit_idx - 1]
                    chunk_file = normalize_mojibake_text(chunk.get("filename", "(ukendt fil)"))
                    chunk_file_id = str(chunk.get("file_id", ""))
                    chunk_score = chunk.get("score", "n/a")
                    chunk_text = normalize_mojibake_text((chunk.get("text", "") or "").strip())
                    story.append(
                        Paragraph(
                            f"Hit #{hit_idx}: {escape(chunk_file)} - file_id: {escape(chunk_file_id)} - score: {escape(str(chunk_score))}",
                            body_style,
                        )
                    )
                    if chunk_text:
                        preview = chunk_text[:1800]
                        story.append(
                            Paragraph(escape(preview).replace("\n", "<br/>"), mono_style)
                        )
                    else:
                        story.append(Paragraph("Intet tekstuddrag i resultatet.", body_style))
                    story.append(Spacer(1, 3))
        story.append(Spacer(1, 6))

    story.append(Paragraph("Retrieval-træf (debug)", heading_style))
    if chunks:
        for idx, chunk in enumerate(chunks, start=1):
            chunk_file = normalize_mojibake_text(chunk.get("filename", "(ukendt fil)"))
            chunk_file_id = str(chunk.get("file_id", ""))
            chunk_score = chunk.get("score", "n/a")
            chunk_text = normalize_mojibake_text((chunk.get("text", "") or "").strip())
            story.append(
                Paragraph(
                    f"{idx}. {escape(chunk_file)} - file_id: {escape(chunk_file_id)} - score: {escape(str(chunk_score))}",
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


def save_chat_pdf_log(messages: list[dict[str, str]], used_model: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"chat_log_{timestamp}_{uuid4().hex[:8]}.pdf"
    output_path = LOG_DIR / filename

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="Chatlog",
    )
    styles = getSampleStyleSheet()
    body_style = styles["BodyText"]
    body_style.fontSize = 10
    body_style.leading = 13
    heading_style = styles["Heading2"]
    heading_style.spaceBefore = 8
    heading_style.spaceAfter = 4

    story: list[Any] = []
    story.append(Paragraph("Chatlog", styles["Title"]))
    story.append(
        Paragraph(
            f"Tidspunkt: {escape(datetime.now().isoformat(timespec='seconds'))}",
            body_style,
        )
    )
    story.append(Paragraph(f"Model brugt: {escape(used_model)}", body_style))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Samtale", heading_style))
    if not messages:
        story.append(Paragraph("Ingen beskeder at eksportere.", body_style))
    else:
        for idx, msg in enumerate(messages, start=1):
            role = str(msg.get("role", "ukendt")).strip().lower()
            if role == "user":
                role_label = "Du"
            elif role == "assistant":
                role_label = "JAILA"
            else:
                role_label = "System"
            text = normalize_mojibake_text(str(msg.get("text", "") or ""))
            text = text.strip() or "(Tom besked)"
            story.append(Paragraph(f"{idx}. {escape(role_label)}", heading_style))
            story.append(Paragraph(escape(text).replace("\n", "<br/>"), body_style))
            story.append(Spacer(1, 4))

    doc.build(story)
    return output_path
