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
# Et kendt holdepunkt pr. lov — ikke nødvendigvis den nyeste udgave. Appen følger selv
# `eli:consolidated_by` frem til den seneste bekendtgørelse, så listen ikke forælder, når
# Skatteministeriet udsender en ny. Da kontrollen blev bygget, var to af posterne allerede
# overhalet, uden at det kunne ses.
#
# Stierne er fundet ved at spørge samlelovene LOV 679/2023 og LOV 1563/2023, hvilke love de
# ændrer, ikke skrevet efter hukommelsen. Bemærk at ejendomsavancebeskatningsloven i
# metadata hedder "lov om beskatning af fortjeneste ved afståelse af fast ejendom".
KNOWN_LAWS = {
    "Ligningsloven": "eli/lta/2025/1500",
    "Kildeskatteloven": "eli/lta/2024/460",
    "Selskabsskatteloven": "eli/lta/2025/279",
    "Personskatteloven": "eli/lta/2021/1284",
    "Afskrivningsloven": "eli/lta/2025/1222",
    "Aktieavancebeskatningsloven": "eli/lta/2025/1098",
    "Kursgevinstloven": "eli/lta/2025/1176",
    "Ejendomsavancebeskatningsloven": "eli/lta/2019/132",
    "Pensionsbeskatningsloven": "eli/lta/2024/1243",
    "Virksomhedsskatteloven": "eli/lta/2021/1836",
    "Dødsboskatteloven": "eli/lta/2019/426",
    "Fondsbeskatningsloven": "eli/lta/2025/207",
    "Skatteforvaltningsloven": "eli/lta/2024/1053",
    "Skattekontrolloven": "eli/lta/2024/12",
    "Skatteindberetningsloven": "eli/lta/2025/1059",
    "Opkrævningsloven": "eli/lta/2024/1040",
    "Ejendomsvurderingsloven": "eli/lta/2023/1510",
    "Tinglysningsafgiftsloven": "eli/lta/2025/27",
    "Arbejdsmarkedsbidragsloven": "eli/lta/2020/121",
    "Aktiesparekontoloven": "eli/lta/2025/281",
    "Konkursskatteloven": "eli/lta/2019/353",
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
def load_chain(eli: str) -> list[forarbejder.Consolidation]:
    return forarbejder.consolidation_chain(eli)


# Kort levetid, ikke ubegrænset: en ny lovbekendtgørelse skal slå igennem i en kørende
# app, men opslaget koster netværkskald og skal ikke gentages ved hvert klik.
@st.cache_data(show_spinner="Kontrollerer, om der er kommet en nyere udgave …", ttl=21600)
def load_newest(eli: str) -> tuple[str, list[str]]:
    return lex_dania.newest_consolidation(eli)


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
    newest = KNOWN_LAWS[choice] or st.text_input(
        "Lovbekendtgørelsens ELI-sti", DEFAULT_ELI, help="Fx eli/lta/2025/1500"
    )
    if not newest.strip():
        st.info("Angiv en ELI-sti.")
        return
    newest = newest.strip().strip("/")

    # Holdepunktet i listen er ikke nødvendigvis lovens seneste udgave. Kommer der en ny
    # bekendtgørelse, ville et fast opslag tavst svare om en forældet retstilstand.
    try:
        latest, skipped_forward = load_newest(newest)
    except lex_dania.FetchError as error:
        st.warning(
            f"Kunne ikke kontrollere, om der findes en nyere udgave end {newest}: {error}. "
            "Svaret bygger på den kendte udgave og kan være forældet."
        )
        latest, skipped_forward = newest, []
    if skipped_forward:
        st.caption(
            f"Der er kommet {len(skipped_forward)} nyere udgave"
            f"{'r' if len(skipped_forward) > 1 else ''} siden {newest}. Bruger {latest}."
        )
    newest = latest

    try:
        chain = load_chain(newest)
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        st.error(f"Kunne ikke hente {newest}: {error}")
        return
    if not chain:
        st.error(f"Fandt ingen udgaver af loven fra {newest}.")
        return

    version = st.selectbox(
        "Udgave", chain, index=0, format_func=lambda step: step.label,
        help="Vælg den udgave, spørgsmålet handler om. Søgningen går bagud herfra, så "
        "en ældre udgave viser retstilstanden dengang og springer alt nyere over.",
    )
    eli = version.eli
    # Antallet af led skal ikke gættes: kæden er kendt, og fra den valgte udgave er der
    # præcis så mange tilbage. Vælger man en ældre udgave, falder tallet af sig selv.
    position = next(i for i, step in enumerate(chain) if step.eli == eli)
    remaining = len(chain) - position

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
            help="Paragrafferne er dem, der findes i den valgte udgave. En bestemmelse, "
            "der først kom til senere, står derfor ikke på listen.",
        )
    with right:
        steps = st.number_input(
            "Led i kæden", min_value=1, max_value=remaining, value=remaining,
            help=f"Fra denne udgave er der {remaining} udgaver tilbage, ned til "
            f"{chain[-1].label}. Sænk tallet for et hurtigere, men kortere svar.",
        )

    # Sammenlign på ELI, ikke på objektet: udgaven kommer gennem cachen og er derfor
    # ikke det samme objekt som det i kæden, selv når den er det samme led.
    skipped = len(chain) - remaining
    if skipped:
        st.info(
            f"Du ser loven, som den var den {version.label.split(' af ')[-1]}. "
            f"Ændringer efter den dato er ikke med, og {skipped} nyere "
            f"{'udgave springes' if skipped == 1 else 'udgaver springes'} over, "
            "så søgningen er hurtigere."
        )

    if not st.button("Find forarbejder", type="primary"):
        st.caption("Vælg en paragraf og tryk på knappen. Første opslag tager typisk "
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
    if history.problems:
        # Et problem betyder, at en ændringslov ikke kunne læses. Svaret er da
        # ufuldstændigt, og det skal stå, hvor man ser resultatet — ikke nede i en log.
        with st.expander(
            f"{len(history.problems)} ændringslove kunne ikke læses — svaret kan mangle noget",
            expanded=True,
        ):
            for problem in history.problems:
                st.warning(problem)

    if history.notices:
        with st.expander(f"{len(history.notices)} usædvanlige forhold blev håndteret"):
            for notice in history.notices:
                st.info(notice)

    if not history.changes:
        if not history.paragraph_exists:
            # Det tomme svar må ikke læses som "bestemmelsen har stået uændret".
            st.error(
                f"§ {history.paragraph_id} blev ikke fundet i {history.start}, og der er "
                "heller ingen ændringer. Svaret er altså tomt, fordi paragraffen ikke "
                "findes — ikke fordi den er uændret. Kontrollér nummeret, eller vælg en "
                "udgave, hvor bestemmelsen fandtes."
            )
            return
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
                # Kom punktet ved ændringsforslag, ved vi præcis hvor bemærkningen står,
                # selv om vi ikke kan hente den. Henvisningen er langt mere værd end
                # beskeden om, at der intet er.
                stage = change.note.committee
                if stage and stage.report_url:
                    st.link_button(f"Åbn {stage.report_title}", stage.report_url)
            else:
                kind = ("bemærkning til netop dette nummer" if change.note.precise
                        else "bemærkning til hele ændringsparagraffen — intet 'Til nr.'")
                st.markdown(f"**Specielle bemærkninger** · {change.note.source} · {kind}")
                confirmation = change.confirm(history.paragraph_id)
                if confirmation.ok:
                    st.caption(f"Koblingen er bekræftet: {confirmation.how}.")
                elif confirmation.suspect:
                    st.warning(
                        f"Koblingen kunne ikke bekræftes. Ændringen indsætter tekst, som "
                        f"bemærkningen burde gengive, men den nævner hverken "
                        f"§ {history.paragraph_id} eller ændringens ordlyd. Bør efterses."
                    )
                else:
                    st.caption(
                        "Koblingen kan ikke efterprøves: ændringen ophæver eller "
                        "omnummererer uden at indsætte tekst, så der er intet at genfinde "
                        "i bemærkningen."
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
