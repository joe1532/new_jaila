"""Slå forarbejder op til en enkelt lovparagraf.

To faner: forarbejdssøgningen, som er formålet, og en inspektion af ændringsinstrukser,
som blev bygget for at kunne se materialet med egne øjne.

Kør med:  streamlit run lovhistorik/app.py

Al søgelogik ligger i forarbejder.py og lex_dania.py, som proben bruger samme vej, så de
to aldrig kan komme til at vise forskellige tal.
"""

from __future__ import annotations

import pathlib
import sys
import xml.etree.ElementTree as ElementTree

import pandas as pd
import streamlit as st

# Streamlit kører filen som script, ikke som pakke, så mappen skal med i sys.path.
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import forarbejder  # noqa: E402
import lex_dania  # noqa: E402

DEFAULT_ELI = "eli/lta/2025/1500"
DEFAULT_LAW = "ligningslov"

# Love, hvor kæden er kørt igennem og målt. Andre kan indtastes frit.
KNOWN_LAWS = {
    "Ligningsloven (LBK 1500/2025)": "eli/lta/2025/1500",
    "Afskrivningsloven (LBK 1222/2025)": "eli/lta/2025/1222",
    "Skatteindberetningsloven (LBK 1059/2025)": "eli/lta/2025/1059",
    "Anden lov — indtast selv": "",
}

MARKUP_LABELS = {
    "signi_char": "opmærket (signiChar)",
    "italic": "kun kursiveret",
    "none": "intet opmærket mål",
}


@st.cache_data(show_spinner=False)
def load_metadata(eli: str) -> dict[str, object]:
    return lex_dania.fetch_metadata(eli)


@st.cache_data(show_spinner=False, ttl=3600)
def load_history(eli: str, paragraph: str, steps: int, _progress=None) -> forarbejder.History:
    """Hent hele historikken. Argumenter med underscore indgår ikke i cachenøglen."""
    return forarbejder.paragraph_history(eli, paragraph, steps, _progress)


@st.cache_data(show_spinner=False)
def load_paragraph_list(eli: str) -> list[str]:
    """Lovens paragraffer, så man kan vælge frem for at gætte en betegnelse."""
    provisions = lex_dania.extract_provisions(lex_dania.fetch_document_xml(eli))
    seen: list[str] = []
    for provision in provisions:
        if provision.paragraph_id and provision.paragraph_id not in seen:
            seen.append(provision.paragraph_id)
    return seen


def render_history_tab() -> None:
    st.subheader("Forarbejder til én paragraf")
    st.caption(
        "Søgningen følger kæden af lovbekendtgørelser bagud, finder hver ændring af "
        "paragraffen og henter de specielle bemærkninger fra det lovforslag, ændringen "
        "stammer fra."
    )

    choice = st.selectbox("Lov", list(KNOWN_LAWS), index=0)
    eli = KNOWN_LAWS[choice] or st.text_input(
        "Lovbekendtgørelsens ELI-sti", DEFAULT_ELI, help="Fx eli/lta/2025/1500"
    )
    if not eli.strip():
        st.info("Angiv en ELI-sti.")
        return
    eli = eli.strip().strip("/")

    try:
        paragraphs = load_paragraph_list(eli)
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        st.error(f"Kunne ikke hente {eli}: {error}")
        return

    left, right = st.columns([3, 1])
    with left:
        paragraph = st.selectbox(
            "Paragraf",
            paragraphs,
            index=paragraphs.index("9C") if "9C" in paragraphs else 0,
            format_func=lambda value: f"§ {value}",
        )
    with right:
        # Otte led rækker typisk tilbage til 2014, fjorten til 2006, hvor Lex
        # Dania-opmærkningen begynder. Flere led koster tid ved første opslag.
        steps = st.number_input("Led i kæden", min_value=1, max_value=20, value=8)

    if not st.button("Find forarbejder", type="primary"):
        st.info("Vælg en paragraf og tryk på knappen. Første opslag tager typisk "
                "20-45 sekunder; derefter svarer diskcachen.")
        return

    status = st.status("Søger …", expanded=True)
    try:
        # st.status.update tager kun nøgleordsargumenter, så kaldet pakkes ind.
        history = load_history(
            eli, paragraph, int(steps), lambda message: status.update(label=message)
        )
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        status.update(label="Søgningen fejlede", state="error")
        st.error(f"Kunne ikke hente materialet: {error}")
        return
    status.update(label=f"Færdig: {len(history.changes)} ændringer", state="complete",
                  expanded=False)

    st.markdown(f"### {history.law_name} § {history.paragraph_id}")

    chain = " → ".join(step for step, _ in history.chain)
    st.caption(
        f"Kæden: {chain}"
        + ("  ·  nåede enden af det maskinlæsbare materiale" if history.reached_end else
           "  ·  standsede efter det valgte antal led — hæv det for at gå længere tilbage")
    )
    for problem in history.problems:
        st.warning(problem)

    if not history.changes:
        st.info(
            f"§ {history.paragraph_id} er ikke ændret i den del af kæden, vi kan nå. "
            "Det betyder ikke, at bestemmelsen er uden forarbejder — de ligger da før "
            "2007, hvor Lex Dania-XML begynder. Prøv med flere led i kæden."
        )
        return

    first, second, third = st.columns(3)
    first.metric("Ændringer", len(history.changes))
    second.metric("Med bemærkning", f"{history.with_note} af {len(history.changes)}")
    third.metric(
        "Bekræftet af teksten",
        f"{history.confirmed} af {history.with_note}",
        help="Bemærkningen citerer normalt selv den bestemmelse, den forklarer. Nævner "
        "den ikke paragraffen, er koblingen mindre sikker — men ikke nødvendigvis "
        "forkert: handler hele ændringsloven om én bestemmelse, er nummeret overflødigt.",
    )

    grouped = history.by_place
    places = sorted(grouped, key=lambda key: (not key.startswith("hele"), key))
    chosen = st.multiselect(
        "Vis kun ændringer af", places, placeholder="Alle stykker",
        help="Grupperingen efter stykke er den form, spørgsmålet stilles i.",
    )

    shown = history.changes
    if chosen:
        wanted = {id(change) for place in chosen for change in grouped[place]}
        shown = [change for change in history.changes if id(change) in wanted]

    st.markdown(f"**{len(shown)} ændringer, nyeste først**")
    for change in shown:
        where = ", ".join(place for place, _ in change.places)
        header = f"{change.label} — {where}"
        if not change.note.found:
            header += "  ·  ingen bemærkning"
        with st.expander(header, expanded=len(shown) <= 3):
            st.markdown(f"*Indarbejdet i {change.consolidation}*")
            st.markdown("**Ændringen**")
            st.write(change.text)

            if not change.note.found:
                st.warning(f"Ingen bemærkning: {change.note.source}")
            else:
                kind = ("bemærkning til netop dette nummer" if change.note.precise
                        else "bemærkning til hele ændringsparagraffen — intet 'Til nr.'")
                st.markdown(f"**Specielle bemærkninger** · {change.note.source} · {kind}")
                if not change.mentions(history.paragraph_id):
                    st.caption(
                        f"Bemærkningen nævner ikke § {history.paragraph_id} ordret. "
                        "Det er ofte fint, når hele ændringsloven handler om denne ene "
                        "bestemmelse, men koblingen er mindre sikker."
                    )
                st.write(change.note.text)

            links = st.columns(2)
            links[0].link_button(
                "Ændringsloven", f"https://www.retsinformation.dk/{change.document_path}"
            )
            if change.note.url:
                links[1].link_button(f"Lovforslag L {change.note.bill_number}", change.note.url)


@st.cache_data(show_spinner=False)
def load_instructions(
    eli: str, law_name: str, max_acts: int
) -> tuple[list[dict[str, object]], list[str], int]:
    """Hent og udtræk instrukser. Returnerer (rækker, fejl, antal undersøgte love)."""
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


def render_instruction_tab() -> None:
    st.subheader("Ændringsinstrukser i Lex Dania")
    st.caption(
        "Værktøjet klassificerer instrukser. Det anvender dem ikke på lovteksten, "
        "så en klassificeret instruks er ikke det samme som en, vi kan udføre."
    )

    top = st.columns([2, 2, 1])
    eli = top[0].text_input("Lovens ELI-sti", DEFAULT_ELI, key="instr_eli")
    law_name = top[1].text_input(
        "Mållov", DEFAULT_LAW, key="instr_law",
        help="Matches mod ændringsparagraffens indledning. En samlelov ændrer flere love.",
    )
    max_acts = top[2].number_input("Højst antal love", 1, 100, 40)

    if not eli.strip() or not law_name.strip():
        st.info("Angiv både ELI-sti og mållov.")
        return

    try:
        metadata = load_metadata(eli.strip())
        rows, failures, document_count = load_instructions(
            eli.strip(), law_name.strip(), int(max_acts)
        )
    except lex_dania.FetchError as error:
        st.error(f"Kunne ikke hente: {error}")
        return

    st.write(metadata["title"])

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

    if failures:
        st.warning(f"{len(failures)} dokumenter kunne ikke behandles")
        for failure in failures:
            st.text(failure)


def main() -> None:
    st.set_page_config(page_title="Lovhistorik", layout="wide")
    st.title("Lovhistorik")

    history_tab, instruction_tab = st.tabs(["Forarbejder", "Ændringsinstrukser"])
    with history_tab:
        render_history_tab()
    with instruction_tab:
        render_instruction_tab()

    with st.sidebar:
        st.header("Om værktøjet")
        st.markdown(
            "Materialet hentes fra Retsinformation og Folketingets Åbne Data og "
            "gemmes i `lovhistorik/.cache/`. Første opslag på en ny lov er langsomt, "
            "fordi vi bevidst går skånsomt mod kilderne."
        )
        st.divider()
        st.subheader("Hvad svaret ikke kan")
        st.markdown(
            "- Kæden går kun tilbage til omkring 2007, hvor Lex Dania-XML begynder.\n"
            "- Kom et ændringspunkt til ved et ændringsforslag under behandlingen, "
            "står bemærkningen i betænkningen, som ikke hentes. Det oplyses.\n"
            "- Bemærkningen dækker hele ændringspunktet og er ikke snævret ind til "
            "det stykke, der spørges om."
        )


if __name__ == "__main__":
    main()
