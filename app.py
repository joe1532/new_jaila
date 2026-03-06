import os
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

import streamlit as st
from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


VECTOR_STORE_IDS = [
    "vs_67d1e99c789c8191bd776ac5437cbc08",
    "vs_69ab3cf9971c8191be5aaf4eb04d69f0",
]
PRIMARY_MODEL = "gpt-5.4"
FALLBACK_MODEL = "gpt-5.2"
LOG_DIR = Path(__file__).resolve().parent / "logs"
ANSWER_INSTRUCTIONS = (
    "Du er en juridisk assistent. Svar på dansk. "
    "Brug kun oplysninger, der kan underbygges af file_search-kilderne. "
    "Afslut ALTID svaret med en sektion med overskriften "
    "'Anvendte kilder/love' efterfulgt af korte punktlinjer med de centrale "
    "kilder/love, du faktisk har anvendt i analysen."
)


def get_value(obj: Any, key: str, default: Any = None) -> Any:
    """Read a key from dict-like objects or SDK objects safely."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def parse_response(resp: Any) -> dict[str, Any]:
    """Extract answer text, citations and optional file search results."""
    output_text = get_value(resp, "output_text", "") or ""
    output_items = get_value(resp, "output", []) or []

    citations: list[dict[str, str]] = []
    retrieved_chunks: list[dict[str, str]] = []

    for item in output_items:
        item_type = get_value(item, "type", "")

        if item_type == "message":
            for content in get_value(item, "content", []) or []:
                if get_value(content, "type", "") != "output_text":
                    continue
                for annotation in get_value(content, "annotations", []) or []:
                    if get_value(annotation, "type", "") == "file_citation":
                        citations.append(
                            {
                                "file_id": str(get_value(annotation, "file_id", "")),
                                "filename": str(get_value(annotation, "filename", "")),
                            }
                        )

        if item_type == "file_search_call":
            for result in get_value(item, "results", []) or []:
                # Responses file_search results can return snippet in `text`.
                # Keep fallback parsing for potential `content`-based shapes.
                chunk_text = str(get_value(result, "text", "")).strip()
                if not chunk_text:
                    for part in get_value(result, "content", []) or []:
                        if get_value(part, "type", "") == "text":
                            text_part = str(get_value(part, "text", "")).strip()
                            if text_part:
                                chunk_text = text_part
                                break

                retrieved_chunks.append(
                    {
                        "filename": str(get_value(result, "filename", "")),
                        "score": str(get_value(result, "score", "")),
                        "text": chunk_text,
                    }
                )

    # Deduplicate citations while preserving order.
    seen: set[tuple[str, str]] = set()
    unique_citations: list[dict[str, str]] = []
    for citation in citations:
        key = (citation["file_id"], citation["filename"])
        if key in seen:
            continue
        seen.add(key)
        unique_citations.append(citation)

    return {
        "output_text": output_text.strip(),
        "citations": unique_citations,
        "retrieved_chunks": retrieved_chunks,
    }


def extract_legal_references(chunks: list[dict[str, str]]) -> list[str]:
    """Extract likely law references from retrieval snippets."""
    references: list[str] = []
    seen: set[str] = set()

    patterns = [
        r"(?:ligningsloven|ligningslovens)\s*§+\s*\d+\s*[A-Za-z]?",
        r"(?:kildeskatteloven|kildeskattelovens)\s*§+\s*\d+\s*[A-Za-z]?",
        r"(?:personskatteloven|personskattelovens)\s*§+\s*\d+\s*[A-Za-z]?",
        r"(?:pensionsbeskatningsloven|PBL)\s*§+\s*\d+\s*[A-Za-z]?",
        r"\bSKM\s*\d{4}\s*\d+\s*[A-ZÆØÅ]{2,5}\b",
    ]

    for chunk in chunks:
        text = chunk.get("text", "") or ""
        for pattern in patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                normalized = re.sub(r"\s+", " ", match).strip()
                key = normalized.lower()
                if key in seen:
                    continue
                seen.add(key)
                references.append(normalized)
                if len(references) >= 12:
                    return references
    return references


def ensure_sources_section(parsed: dict[str, Any]) -> dict[str, Any]:
    """Append a deterministic sources/laws section if model omitted it."""
    output_text = (parsed.get("output_text", "") or "").strip()
    if "anvendte kilder/love" in output_text.lower():
        return parsed

    lines: list[str] = []
    for citation in parsed.get("citations", []) or []:
        filename = citation.get("filename", "").strip()
        if filename:
            lines.append(f"- Kilde: {filename}")

    for ref in extract_legal_references(parsed.get("retrieved_chunks", []) or []):
        lines.append(f"- Lov/praksis: {ref}")

    if not lines:
        lines.append("- Ingen eksplicitte kilder/love kunne udledes automatisk.")

    parsed["output_text"] = output_text + "\n\nAnvendte kilder/love\n" + "\n".join(lines)
    return parsed


def run_query(client: OpenAI, user_query: str) -> tuple[dict[str, Any], str]:
    """Run file_search with primary model and fallback model if needed."""
    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]
    last_error: Exception | None = None

    for model in models_to_try:
        try:
            resp = client.responses.create(
                model=model,
                instructions=ANSWER_INSTRUCTIONS,
                input=user_query,
                reasoning={"effort": "high"},
                tools=[
                    {
                        "type": "file_search",
                        "vector_store_ids": VECTOR_STORE_IDS,
                        "max_num_results": 10,
                    }
                ],
                include=["file_search_call.results"],
            )
            parsed = ensure_sources_section(parse_response(resp))
            return parsed, model
        except Exception as exc:  # Keep broad to support SDK/API-level errors.
            last_error = exc

    raise RuntimeError(
        f"Kald fejlede for modellerne {PRIMARY_MODEL} og {FALLBACK_MODEL}: {last_error}"
    )


def save_pdf_log(user_query: str, parsed: dict[str, Any], used_model: str) -> Path:
    """Save one request/response log to PDF for auditability."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"query_log_{timestamp}.pdf"
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
            f"Tidspunkt: {escape(datetime.now().isoformat(timespec='seconds'))}", body_style
        )
    )
    story.append(Paragraph(f"Model brugt: {escape(used_model)}", body_style))
    story.append(
        Paragraph(
            f"Vector stores: {escape(', '.join(VECTOR_STORE_IDS))}",
            body_style,
        )
    )
    story.append(Spacer(1, 6))

    story.append(Paragraph("Spørgsmål", heading_style))
    story.append(Paragraph(escape(user_query).replace("\n", "<br/>"), body_style))
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


def main() -> None:
    st.set_page_config(page_title="Juridisk File Search", page_icon=":mag:", layout="wide")
    st.title("Juridisk File Search (OpenAI Vector Store)")
    st.caption(
        f"Søger i vector stores: `{', '.join(VECTOR_STORE_IDS)}`. "
        f"Model-fallback: `{PRIMARY_MODEL}` -> `{FALLBACK_MODEL}`."
    )

    if not os.getenv("OPENAI_API_KEY"):
        st.error(
            "Miljøvariablen OPENAI_API_KEY mangler. "
            "Sæt den i operativsystemet og genstart appen."
        )
        return

    default_prompt = (
        "Lav en juridisk analyse af, om en person er fuldt skattepligtig til Danmark."
    )
    user_query = st.text_area(
        "Dit spørgsmål",
        value=default_prompt,
        height=140,
        help="Skriv dit juridiske spørgsmål. Appen bruger file_search i dit vector store.",
    )

    if st.button("Kør analyse", type="primary", use_container_width=True):
        if not user_query.strip():
            st.warning("Skriv et spørgsmål først.")
            return

        client = OpenAI()
        with st.spinner("Søger i dokumenter og genererer svar..."):
            try:
                parsed, used_model = run_query(client, user_query.strip())
            except Exception as exc:
                st.error(f"Fejl under kald til OpenAI API: {exc}")
                return

        st.success(f"Færdig. Brugte model: `{used_model}`")
        st.subheader("Svar")
        st.write(parsed["output_text"] or "_Intet svar returneret._")

        try:
            log_path = save_pdf_log(user_query.strip(), parsed, used_model)
            st.caption(f"PDF-log gemt: `{log_path}`")
        except Exception as exc:
            st.warning(f"Kunne ikke gemme PDF-log: {exc}")

        st.subheader("Kilder (citations)")
        citations = parsed["citations"]
        if not citations:
            st.info("Ingen file citations fundet i svaret.")
        else:
            for idx, citation in enumerate(citations, start=1):
                filename = citation["filename"] or "(ukendt filnavn)"
                file_id = citation["file_id"] or "(ukendt file_id)"
                st.markdown(f"{idx}. `{filename}`  \n   - file_id: `{file_id}`")

        with st.expander("Vis retrieval-træf (debug/validering)"):
            chunks = parsed["retrieved_chunks"]
            if not chunks:
                st.write("Ingen `file_search_call.results` modtaget.")
            else:
                for i, chunk in enumerate(chunks, start=1):
                    st.markdown(
                        f"**{i}. {chunk['filename'] or '(ukendt fil)'}**  \n"
                        f"Score: `{chunk['score'] or 'n/a'}`"
                    )
                    preview = chunk["text"][:900].strip() if chunk["text"] else ""
                    if preview:
                        st.code(preview, language="text")
                    else:
                        st.write("_Intet tekstuddrag i resultatet._")


if __name__ == "__main__":
    main()
