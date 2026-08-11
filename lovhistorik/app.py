"""Inspektionsværktøj til ændringsinstrukser i Retsinformations Lex Dania-XML.

Formålet er at kunne se materialet med egne øjne, før parseren bygges: hvilke
konstruktioner findes, hvor godt er målene opmærket, og hvordan ser de svære
tilfælde ud. Værktøjet klassificerer kun — det anvender ikke operationerne på
lovteksten, så en instruks kan sagtens være klassificeret uden at kunne udføres.

Kør med:  streamlit run lovhistorik/app.py

Udtrækket ligger i lex_dania.py, som proben bruger samme vej, så de to aldrig kan
komme til at vise forskellige tal.
"""

from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ElementTree

import pandas as pd
import streamlit as st

# Streamlit kører filen som script, ikke som pakke, så mappen skal med i sys.path.
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import lex_dania  # noqa: E402

DEFAULT_ELI = "eli/lta/2025/1500"
DEFAULT_LAW = "ligningslov"

MARKUP_LABELS = {
    "signi_char": "opmærket (signiChar)",
    "italic": "kun kursiveret",
    "none": "intet opmærket mål",
}


@st.cache_data(show_spinner=False)
def load_metadata(eli: str) -> dict[str, object]:
    return lex_dania.fetch_metadata(eli)


@st.cache_data(show_spinner=False)
def load_instructions(
    eli: str, law_name: str, max_acts: int
) -> tuple[list[dict[str, object]], list[str], int]:
    """Hent og udtræk instrukser. Returnerer (rækker, fejl, antal undersøgte love).

    Dokumenterne hentes højst én gang: lex_dania cacher dem på disk, og Streamlit
    cacher resultatet i hukommelsen. Første kørsel for en ny lov tager omkring et
    sekund pr. dokument, fordi vi bevidst går langsomt mod kilden.
    """
    documents = lex_dania.amending_documents(eli)[:max_acts]
    rows: list[dict[str, object]] = []
    failures: list[str] = []

    progress = st.progress(0.0, text="Henter ændringslove …")
    for index, path in enumerate(documents, start=1):
        progress.progress(index / len(documents), text=f"Henter {path} ({index}/{len(documents)})")
        try:
            body = lex_dania.fetch_document_xml(path)
            instructions = lex_dania.extract_instructions(body, path, law_name)
        except (lex_dania.FetchError, ElementTree.ParseError) as error:
            failures.append(f"{path}: {error}")
            continue

        for instruction in instructions:
            rows.append(
                {
                    "dokument": instruction.document_path,
                    "punkt": instruction.amendment_path,
                    "konstruktion": ", ".join(instruction.constructions),
                    "mål": " | ".join(instruction.probable_targets),
                    "opmærkning": MARKUP_LABELS[instruction.target_markup],
                    "antal mål": len(instruction.targets),
                    "forekomster": instruction.occurrences,
                    "instruks": instruction.text,
                    "ny tekst": instruction.new_text,
                }
            )
    progress.empty()
    return rows, failures, len(documents)


def main() -> None:
    st.set_page_config(page_title="Lovhistorik: ændringsinstrukser", layout="wide")
    st.title("Ændringsinstrukser i Lex Dania")
    st.caption(
        "Værktøjet klassificerer instrukser. Det anvender dem ikke på lovteksten, "
        "så en klassificeret instruks er ikke det samme som en, vi kan udføre."
    )

    with st.sidebar:
        st.header("Kilde")
        eli = st.text_input("Lovens ELI-sti", DEFAULT_ELI, help="Fx eli/lta/2025/1500")
        law_name = st.text_input(
            "Mållov",
            DEFAULT_LAW,
            help="Matches mod ændringsparagraffens indledning. En samlelov ændrer "
            "flere love, så filtreringen er nødvendig.",
        )
        max_acts = st.slider("Højst antal ændringslove", 1, 100, 40)
        st.divider()
        st.caption(
            "Dokumenter caches i lovhistorik/.cache/. Første kørsel for en ny lov tager "
            "omkring et sekund pr. dokument."
        )

    if not eli.strip() or not law_name.strip():
        st.info("Angiv både ELI-sti og mållov i sidepanelet.")
        return

    try:
        metadata = load_metadata(eli.strip())
    except lex_dania.FetchError as error:
        st.error(f"Kunne ikke hente metadata for {eli}: {error}")
        return

    st.subheader(str(metadata["title_short"]) or eli)
    st.write(metadata["title"])

    try:
        rows, failures, document_count = load_instructions(eli.strip(), law_name.strip(), max_acts)
    except lex_dania.FetchError as error:
        st.error(f"Kunne ikke hente ændringslovene: {error}")
        return

    if not rows:
        st.warning(
            f"Fandt ingen ændringspunkter mod {law_name!r} i {document_count} dokumenter. "
            "Tjek at mållovens navn står, som det skrives i ændringsparagraffens indledning."
        )
        return

    frame = pd.DataFrame(rows)

    total = len(frame)
    signi = int((frame["opmærkning"] == MARKUP_LABELS["signi_char"]).sum())
    italic = int((frame["opmærkning"] == MARKUP_LABELS["italic"]).sum())
    multi = int((frame["antal mål"] > 1).sum())
    qualified = int(frame["forekomster"].notna().sum())

    first, second, third, fourth = st.columns(4)
    first.metric("Ændringspunkter", total, f"{frame['dokument'].nunique()} love")
    second.metric("Mål opmærket", f"{signi + italic}", f"heraf {italic} kun kursiveret")
    third.metric("Flere mål i ét punkt", multi, f"{100 * multi / total:.0f} %")
    fourth.metric("Med forekomstantal", qualified, "»to steder« o.l.")

    construction_counts: dict[str, int] = {}
    for value in frame["konstruktion"]:
        for name in str(value).split(", "):
            construction_counts[name] = construction_counts.get(name, 0) + 1

    left, right = st.columns([1, 2])
    with left:
        st.markdown("**Konstruktionstyper**")
        st.caption("Summen overstiger antallet af punkter: ét punkt kan rumme flere operationer.")
        st.bar_chart(pd.Series(construction_counts).sort_values(ascending=False))
    with right:
        st.markdown("**Filtre**")
        chosen_constructions = st.multiselect(
            "Konstruktion", sorted(construction_counts), placeholder="Alle"
        )
        chosen_markup = st.multiselect(
            "Målopmærkning", sorted(frame["opmærkning"].unique()), placeholder="Alle"
        )
        search = st.text_input("Fritekst i instruksen", placeholder="fx »kilometertakst«")

    filtered = frame
    if chosen_constructions:
        pattern = "|".join(chosen_constructions)
        filtered = filtered[filtered["konstruktion"].str.contains(pattern, regex=True)]
    if chosen_markup:
        filtered = filtered[filtered["opmærkning"].isin(chosen_markup)]
    if search.strip():
        filtered = filtered[filtered["instruks"].str.contains(search.strip(), case=False)]

    st.markdown(f"**{len(filtered)} af {total} punkter**")
    st.dataframe(
        filtered[["dokument", "punkt", "konstruktion", "mål", "opmærkning", "instruks"]],
        width="stretch",
        hide_index=True,
    )

    st.markdown("### Enkelt punkt")
    if filtered.empty:
        st.info("Ingen punkter matcher filtrene.")
        return

    labels = [
        f"{row['dokument']} {row['punkt']} — {str(row['instruks'])[:70]}"
        for _, row in filtered.iterrows()
    ]
    choice = st.selectbox("Vælg et punkt", range(len(labels)), format_func=lambda i: labels[i])
    selected = filtered.iloc[choice]

    st.markdown(f"**{selected['dokument']} · {selected['punkt']}**")
    st.link_button(
        "Åbn i Retsinformation", f"https://www.retsinformation.dk/{selected['dokument']}"
    )
    st.markdown("**Instruks**")
    st.write(selected["instruks"])
    if selected["ny tekst"]:
        st.markdown("**Ny tekst (AendringNyTekst)**")
        st.write(selected["ny tekst"])
    detail_left, detail_right = st.columns(2)
    detail_left.markdown(f"**Mål:** {selected['mål'] or '—'}")
    detail_left.markdown(f"**Opmærkning:** {selected['opmærkning']}")
    detail_right.markdown(f"**Konstruktion:** {selected['konstruktion']}")
    # pandas gør None til NaN, og NaN er sand i en boolsk test, så vi spørger eksplicit.
    occurrences = selected["forekomster"]
    detail_right.markdown(
        f"**Forekomster:** {'ikke angivet' if pd.isna(occurrences) else int(occurrences)}"
    )

    if failures:
        st.divider()
        st.warning(f"{len(failures)} dokumenter kunne ikke behandles")
        for failure in failures:
            st.text(failure)


if __name__ == "__main__":
    main()
