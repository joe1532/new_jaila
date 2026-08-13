"""Fra en lovparagraf til dens specielle bemærkninger.

Modulet samler hele forarbejdshistorikken for én bestemmelse: det vandrer kæden af
lovbekendtgørelser bagud, finder hver ændring af paragraffen undervejs, slår det
tilhørende lovforslag op i Folketingets Åbne Data og henter bemærkningen til netop det
ændringspunkt.

Logikken ligger her og ikke i `probe.py`, fordi både proben og Streamlit-appen bruger
den. Ellers ville de to kunne nå frem til forskellige svar på samme spørgsmål.

Kendte begrænsninger, som svaret selv oplyser om:

* Kæden kan kun følges tilbage til omkring 2007, hvor Lex Dania-opmærkningen begynder.
  Ældre forarbejder findes ikke i maskinlæsbar form her.
* Kan et ændringspunkt ikke genfindes i lovforslaget, er det formentlig kommet til ved
  et ændringsforslag under behandlingen. Bemærkningen står da i betænkningen, som vi
  ikke henter, og der svares ikke i stedet for at gætte.
* Bemærkningen dækker hele ændringspunktet. Den er ikke snævret ind til det stykke, der
  spørges om.
"""

from __future__ import annotations

import difflib
import json
import re
import time
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Callable

import lex_dania

ODA_BASE = "https://oda.ft.dk/api"

# Lovforslagets paragraf og punkt: "§ 3, nr. 1".
AMENDMENT_REFERENCE = re.compile(r"§\s*(\d+),\s*nr\.\s*(\d+)")

# Under denne lighed regnes to instrukser ikke for den samme. Tærsklen er høj, fordi et
# forkert match giver en forkert bemærkning, og et forkert svar er værre end intet svar.
MATCH_THRESHOLD = 0.90


class LookupFailed(Exception):
    """Opslaget kunne ikke gennemføres.

    Adskilt fra "der var intet at finde", som er et gyldigt svar. Blandes de to, kommer
    et netværksglip til at ligne et forarbejde, der ikke findes.
    """


def oda_json(path_and_query: str) -> dict:
    """Hent JSON fra Folketingets Åbne Data."""
    try:
        body, content_type = lex_dania.fetch(f"{ODA_BASE}/{path_and_query}", "application/json")
    except lex_dania.FetchError as error:
        raise LookupFailed(f"Folketingets data svarede ikke: {error}") from error
    if "json" not in content_type.lower():
        raise LookupFailed(f"Folketingets data svarede med {content_type!r}, ikke JSON")
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as error:
        raise LookupFailed(f"Folketingets data gav ulæselig JSON: {error}") from error


def find_bill(law_number: str, law_date: str) -> tuple[str, str, str] | None:
    """Fra vedtaget lov til lovforslag: (sag_id, lovforslagsnummer, periodekode).

    Opslaget sker på lovnummer *og* dato. Lovnumre genbruges hvert år, så nummeret
    alene ville kunne knytte forarbejder fra en helt anden lov til bestemmelsen.
    """
    from urllib.parse import quote

    odata_filter = quote(f"lovnummer eq '{law_number}'", safe="(),'")
    # Sorteringen er eksplicit, fordi OData ellers ikke garanterer en rækkefølge, og et
    # opslag kunne give forskellige svar fra gang til gang.
    data = oda_json(
        f"Sag?$filter={odata_filter}&$orderby=id&$top=50&$format=json"
    )

    for row in data.get("value", []):
        if str(row.get("lovnummerdato") or "")[:10] != law_date:
            continue
        number = str(row.get("nummernumerisk") or "")
        if not number.isdigit():
            continue
        time.sleep(lex_dania.DELAY_SECONDS)
        period = oda_json(f"Periode({row.get('periodeid')})?$format=json")
        return (str(row.get("id")), number, str(period.get("kode") or ""))
    return None


def fingerprint(text: str) -> str:
    """Instruksens indhold uden det ledende punktnummer, til sammenligning.

    Nummeret udelades netop, fordi det er dét, der kan være forskudt mellem lovforslag
    og vedtaget lov.
    """
    return re.sub(r"\s+", "", re.sub(r"^\s*\d+\.\s*", "", text)).lower()


def realign(proposed: list, instruction_text: str) -> tuple[int, int] | None:
    """Genfind et ændringspunkt i lovforslaget, og giv forslagets egne numre.

    Lovforslagets paragrafnumre er ikke den vedtagne lovs: ligningsloven er § 6 i LOV
    84/2019, men § 5 i lovforslag L 114. Slår man bemærkningen op på lovens numre, får
    man en anden bestemmelses bemærkning — et forkert svar, der ser rigtigt ud.

    Teksten redigeres let undervejs ("som nyt stk. 7" mod "som nyt stykke"), så der
    måles lighed frem for at kræve identitet. Returnerer None, hvis punktet ikke kan
    genfindes.
    """
    wanted = fingerprint(instruction_text)
    # autojunk=False er nødvendigt: for strenge over 200 tegn behandler difflib ellers
    # hyppige tegn som støj, og to næsten ens instrukser fik lighed 0,74, hvor den
    # rigtige værdi var 0,97. Forskellen var "el.lign." mod "eller lignende".
    best, best_ratio = None, 0.0
    for candidate in proposed:
        matcher = difflib.SequenceMatcher(
            None, fingerprint(candidate.text), wanted, autojunk=False
        )
        if matcher.quick_ratio() <= best_ratio:
            continue
        ratio = matcher.ratio()
        if ratio > best_ratio:
            best, best_ratio = candidate, ratio

    if best is None or best_ratio < MATCH_THRESHOLD:
        return None
    try:
        return (int(best.act_number), int(best.item_number.rstrip(".")))
    except ValueError:
        return None


def plausible_year(document_path: str) -> bool:
    """Kan årstallet i en ELI-sti passe?"""
    year = document_path.split("/")[-2]
    return year.isdigit() and 1849 <= int(year) <= date.today().year


def missing(document_path: str) -> bool:
    """Er dokumentet beviseligt fraværende hos Retsinformation?

    Kun et 404 tæller. En netværksfejl eller en tidsudløben forbindelse siger intet om,
    hvorvidt dokumentet findes, og må ikke bruges som argument for at læse en henvisning
    om til en anden lov.
    """
    try:
        lex_dania.fetch_document_xml(document_path)
    except lex_dania.FetchError as error:
        return error.status == 404
    except Exception:  # noqa: BLE001
        return False
    return False


def resolve_path(document_path: str, consolidates: str) -> tuple[str | None, str]:
    """Find den lov, en bekendtgørelse peger på, også når årstallet er en trykfejl.

    LBK 176/2009 skriver "§ 7 i lov nr. 1534 af 19. december 2207". Året findes ikke, og
    loven — en reel ændring af ligningsloven — falder ud af kæden.

    Rettelsen gættes ikke. Den slås op i `eli:changed_by` for den bekendtgørelse, der
    blev konsolideret, altså Retsinformations egen liste over, hvad der har ændret
    loven. Er der præcis ét lovnummer, der passer, er sagen afgjort af data. Er der flere
    eller ingen, rapporteres det i stedet, for et gæt ville være netop den slags tavse
    fejl, vi leder efter.

    Et umuligt årstal er den nemme sag. Den farlige er trykfejlen, der ser rigtig ud:
    opkrævningslovens LBK 569/2014 skriver "§ 8 i lov nr. 1634 af 26. december 2012", men
    loven er fra 2013. Året består enhver rimelighedsprøve, så uden opslag ville vi hente
    forarbejder til en helt anden lov — eller til ingen — og intet ville se forkert ud.
    Derfor efterprøves hvert årstal mod listen, ikke kun de umulige.

    Returnerer (sti, note). Sti er None, når loven ikke kan findes.
    """
    number = document_path.rsplit("/", 1)[-1]
    stated_year = document_path.split("/")[-2]
    impossible = not plausible_year(document_path)

    if not consolidates:
        if impossible:
            return (None, f"{document_path}: årstallet {stated_year} kan ikke passe, og "
                          "der er ingen liste at slå det rigtige op i.")
        return (document_path, "")

    try:
        listed = lex_dania.amending_documents(consolidates)
    except Exception as error:  # noqa: BLE001
        if impossible:
            return (None, f"{document_path}: årstallet {stated_year} kan ikke passe, og "
                          f"{consolidates} kunne ikke slås op: {error}")
        # Årstallet er plausibelt, så det bruges. Kontrollen var en ekstra sikkerhed, ikke
        # en forudsætning, og et opslag der fejler må ikke koste den normale vej.
        return (document_path, "")

    if not impossible and document_path in listed:
        return (document_path, "")

    candidates = [
        path for path in listed
        if path.rsplit("/", 1)[-1] == number and plausible_year(path)
    ]
    if len(candidates) != 1:
        if impossible:
            return (None, f"{document_path}: årstallet {stated_year} kan ikke passe. "
                          f"{len(candidates)} love med nummer {number} ændrer "
                          f"{consolidates}, så det rigtige år kan ikke afgøres.")
        # Listen kan være ufuldstændig, så et fravær beviser ikke en fejl. Stien bruges
        # som skrevet, og et forkert år vil vise sig som en manglende bemærkning.
        return (document_path, "")
    if candidates[0] == document_path:
        return (document_path, "")
    if not impossible and not missing(document_path):
        # Lovnumre genbruges hvert år, så to love kan hedde nr. 753. Er den angivne lov
        # rigtig nok til at findes, må vi ikke rette den om til en anden, blot fordi den
        # mangler i listen. Kun et bevist fravær — 404 — gør rettelsen forsvarlig.
        return (document_path, "")
    return (candidates[0], f"{document_path}: årstallet {stated_year} er en trykfejl i "
                           f"lovbekendtgørelsen. Læst som {candidates[0]}, bekræftet af "
                           f"listen over love, der ændrer {consolidates}, og af at "
                           f"{document_path} ikke findes.")


def instructions_of(
    amendment, law_name: str, consolidates: str = ""
) -> tuple[list, str, str]:
    """Ændringspunkter i den paragraf, lovbekendtgørelsen har indarbejdet.

    `consolidates` er den bekendtgørelse, ændringerne blev indarbejdet i, og bruges kun
    til at opklare trykfejl i årstallet.

    Returnerer (punkter, problem, oplysning). Et problem betyder, at svaret mangler
    noget; en oplysning, at noget usædvanligt blev håndteret. En lov, der ikke kan
    hentes, må ikke stoppe søgningen bagud, men fejlen skal med ud: sluges den, ligner
    en utilgængelig ændringslov en lov, der ikke rørte paragraffen.
    """
    path, note = resolve_path(amendment.document_path, consolidates)
    if path is None:
        return ([], note, "")
    if path != amendment.document_path:
        amendment = replace(amendment, document_path=path)

    try:
        xml = lex_dania.fetch_document_xml(amendment.document_path)
        instructions = lex_dania.extract_instructions(xml, amendment.document_path, law_name)
    except Exception as error:  # noqa: BLE001 - netværk og XML fejler på mange måder
        return ([], f"{amendment.document_path} kunne ikke læses: {error}", "")

    # Paragraf 0 betyder, at hele ændringsloven er indarbejdet.
    if amendment.paragraph:
        kept = []
        for instruction in instructions:
            reference = AMENDMENT_REFERENCE.search(instruction.amendment_path)
            if reference and int(reference.group(1)) == amendment.paragraph:
                kept.append(instruction)
        instructions = kept
    return (instructions, "", note)


@dataclass
class CommitteeStage:
    """Hvad der skete med lovforslaget under udvalgsbehandlingen.

    Bruges kun, når et ændringspunkt ikke kan genfindes i det fremsatte lovforslag. Vi
    svarede tidligere "kom formentlig ved ændringsforslag" uden at se efter. Formodningen
    holder oftest, men ikke altid, og et gæt, der er rigtigt syv ud af otte gange, er
    værre end et opslag, fordi den ottende ikke kan skelnes fra de andre.
    """

    amendment_titles: list[str] = field(default_factory=list)
    report_title: str = ""
    report_url: str = ""  # PDF på ft.dk
    problem: str = ""  # opslaget kunne ikke gennemføres

    @property
    def explains(self) -> bool:
        """Er der faktisk stillet ændringsforslag?"""
        return bool(self.amendment_titles)


# Betænkningens titel begynder sådan. "1. udkast til betænkning" må ikke forveksles med
# den afgivne, og et spørgsmål *om* ændringsforslag er ikke et ændringsforslag — derfor
# matches begyndelsen og ikke blot et ord i titlen.
REPORT_TITLE = re.compile(r"^betænkning afgivet\b", re.IGNORECASE)
AMENDMENT_TITLE = re.compile(r"^ændringsforslag\b", re.IGNORECASE)


def committee_stage(case_id: str) -> CommitteeStage:
    """Slå op, om sagen har ændringsforslag og en afgivet betænkning.

    Koster to kald til Folketingets data og foretages kun for de punkter, der ikke kunne
    genfindes i lovforslaget — i praksis omkring hvert tiende.
    """
    from urllib.parse import quote

    try:
        rows = oda_json(
            f"SagDokument?$filter={quote(f'sagid eq {case_id}', safe='(),')}"
            "&$expand=Dokument&$top=90&$format=json"
        ).get("value", [])
    except LookupFailed as error:
        return CommitteeStage(problem=str(error))

    stage = CommitteeStage()
    report_id = None
    for row in rows:
        document = row.get("Dokument") or {}
        title = str(document.get("titel") or "").strip()
        if AMENDMENT_TITLE.match(title):
            stage.amendment_titles.append(title)
        elif REPORT_TITLE.match(title) and not stage.report_title:
            stage.report_title = title
            report_id = document.get("id")

    if report_id:
        try:
            files = oda_json(
                f"Fil?$filter={quote(f'dokumentid eq {report_id}', safe='(),')}&$format=json"
            ).get("value", [])
            if files:
                stage.report_url = str(files[0].get("filurl") or "")
        except LookupFailed:
            pass  # Titlen alene er nok til at finde betænkningen.
    return stage


@dataclass
class Note:
    """Den specielle bemærkning til ét ændringspunkt."""

    text: str = ""
    bill_number: str = ""  # "114" for L 114
    case_id: str = ""  # sagsnummer i Folketingets Åbne Data
    accession: str = ""  # lovforslagets ELI-nøgle, fx "201812L00114"
    # Falsk, når bemærkningen står under "Til § N" uden et "Til nr." — den dækker da
    # hele ændringsparagraffen og ikke kun det punkt, der spørges om.
    precise: bool = False
    realigned: str = ""  # forslagets egne numre, når de afviger fra lovens
    problem: str = ""  # hvorfor der ingen bemærkning er
    # Sat, når punktet ikke stod i det fremsatte lovforslag. Bemærkningen findes da i
    # betænkningen, som kun udgives som PDF bag botbeskyttelse og derfor ikke kan hentes.
    committee: CommitteeStage | None = None

    @property
    def found(self) -> bool:
        return bool(self.text)

    @property
    def source(self) -> str:
        if not self.found:
            return self.problem
        where = f"L {self.bill_number}, sag {self.case_id}"
        return f"{where}{self.realigned}" if self.realigned else where

    @property
    def url(self) -> str:
        """Lovforslaget på Retsinformation."""
        return f"https://www.retsinformation.dk/eli/ft/{self.accession}" if self.accession else ""


def note_for(
    document_path: str, law_paragraph: int, item: int, law_name: str, instruction_text: str
) -> Note:
    """Hent bemærkningen til ét ændringspunkt i en ændringslov."""
    number = document_path.rsplit("/", 1)[-1]
    try:
        date = lex_dania.document_date(lex_dania.fetch_document_xml(document_path))
    except Exception:  # noqa: BLE001
        return Note(problem="ændringsloven kunne ikke læses")

    try:
        bill = find_bill(number, date)
    except LookupFailed as error:
        # Adskilt fra "findes ikke": her ved vi ikke, om der er et forarbejde.
        return Note(problem=f"opslaget kunne ikke gennemføres — {error}")
    if not bill:
        return Note(problem="lovforslaget findes ikke i Folketingets data")
    case_id, bill_number, period = bill
    accession = f"{period}2L{int(bill_number):05d}"

    try:
        bill_xml = lex_dania.fetch_document_xml(f"eli/ft/{accession}")
        notes = lex_dania.extract_explanatory_notes(bill_xml)
        proposed = lex_dania.extract_instructions(bill_xml, f"eli/ft/{accession}", law_name)
    except Exception:  # noqa: BLE001
        return Note(problem=f"L {bill_number} kunne ikke hentes (eli/ft/{accession})")

    aligned = realign(proposed, instruction_text)
    if aligned is None:
        # Punktet stod ikke i det fremsatte forslag. Den nærliggende forklaring er et
        # ændringsforslag under udvalgsbehandlingen, men den efterprøves frem for at
        # antages: holder den ikke, er der en anden fejl, og den skal kunne ses.
        stage = committee_stage(case_id)
        if stage.problem:
            explanation = (
                f"punktet findes ikke i L {bill_number}, og udvalgsbehandlingen kunne "
                f"ikke slås op: {stage.problem}"
            )
        elif stage.explains:
            explanation = (
                f"punktet findes ikke i L {bill_number} som fremsat, men der blev stillet "
                f"ændringsforslag ({stage.amendment_titles[0]}). Bemærkningen står i "
                f"{stage.report_title or 'betænkningen'}, som Folketinget kun udgiver som "
                "PDF, vi ikke kan hente"
            )
        else:
            explanation = (
                f"punktet findes ikke i L {bill_number}, og der blev ikke stillet "
                "ændringsforslag på sagen. Årsagen er ukendt"
            )
        return Note(
            bill_number=bill_number,
            case_id=case_id,
            accession=accession,
            problem=explanation,
            committee=stage,
        )

    realigned = ""
    if aligned != (law_paragraph, item):
        realigned = f", forslagets § {aligned[0]}, nr. {aligned[1]}"

    # Har ændringsparagraffen kun ét punkt, udelades "Til nr. 1" ofte, og bemærkningen
    # står direkte under "Til § N". Tilbagefaldet markeres som upræcist.
    text = notes.get(aligned)
    precise = text is not None
    if text is None:
        text = notes.get((aligned[0], 0))
    if not text:
        return Note(
            bill_number=bill_number,
            case_id=case_id,
            accession=accession,
            problem=f"L {bill_number} har ingen bemærkning til § {aligned[0]}, nr. {aligned[1]}",
        )
    return Note(
        text=text,
        bill_number=bill_number,
        case_id=case_id,
        accession=accession,
        precise=precise,
        realigned=realigned,
    )


@dataclass
class Confirmation:
    """Hvorfor koblingen mellem en ændring og dens bemærkning holder."""

    how: str = ""  # tom betyder, at intet tegn blev fundet
    # Falsk, når ændringen ikke rummer tekst, en bemærkning kunne gengive — en ophævelse
    # eller en ren henvisningsændring. Så siger et manglende overlap intet.
    checkable: bool = True

    @property
    def ok(self) -> bool:
        return bool(self.how)

    @property
    def suspect(self) -> bool:
        """Burde koblingen kunne bekræftes, men kan ikke?"""
        return not self.ok and self.checkable


WORD = re.compile(r"[0-9a-zæøå]+", re.IGNORECASE)

# Målt på 49 bemærkninger, der nævner målparagraffen og derfor er sikkert koblet: alle
# deler mindst 5 ord i træk med ændringen, medianen er 10. Tærsklen sættes over minimum,
# fordi et kort forløb kan være almindeligt lovsprog frem for et citat. Blandt de
# bemærkninger, der ikke nævner paragraffen, skiller det de tydeligt rigtige (9-22 ord)
# fra dem, der ikke kan bekræftes (0-2 ord).
SHARED_RUN_WORDS = 8

QUOTED_PHRASE = re.compile(r"»([^«»]+)«")
REAL_WORD = re.compile(r"[a-zæøå]{3,}", re.IGNORECASE)

# Så mange egentlige ord skal et citat rumme, før bemærkningen kan ventes at gengive det.
# Længde alene rækker ikke: »3. eller 4. pkt.« fylder 16 tegn, men er en henvisning, ikke
# lovtekst. En ophævelse citerer slet intet. I begge tilfælde er der intet at genfinde,
# og fraværet af overlap siger da intet om koblingen.
QUOTE_WORDS = 3


def quotes_real_text(instruction: str) -> bool:
    """Indsætter ændringen ordlyd, som en bemærkning kunne gengive?"""
    return any(
        len(REAL_WORD.findall(quote)) >= QUOTE_WORDS
        for quote in QUOTED_PHRASE.findall(instruction)
    )


def longest_shared_run(first: str, second: str) -> int:
    """Længste sammenhængende ordforløb, som to tekster deler.

    Bemærkningen citerer som regel den tekst, ændringen indsætter, så et langt fælles
    forløb er et stærkt tegn på, at de hører sammen. Sammenligningen sker på ord og ikke
    på tegn: det er både hurtigere og mindre følsomt over for tegnsætning.
    """
    a = [w.lower() for w in WORD.findall(first)]
    b = [w.lower() for w in WORD.findall(second)]
    if not a or not b:
        return 0
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return matcher.find_longest_match(0, len(a), 0, len(b)).size


@dataclass
class Change:
    """Én ændring af den søgte paragraf, med dens forarbejde."""

    consolidation: str  # den lovbekendtgørelse, ændringen er indarbejdet i
    document_path: str  # ændringsloven
    amendment_path: str  # "§ 3, nr. 1"
    text: str  # instruksen, som den står i ændringsloven
    places: list[tuple[str, str]] = field(default_factory=list)  # (stykke, punktummer)
    inserted: bool = False  # fundet i ny tekst, ikke som mål
    note: Note = field(default_factory=Note)

    @property
    def label(self) -> str:
        number = self.document_path.rsplit("/", 1)[-1]
        year = self.document_path.split("/")[-2]
        return f"LOV {number}/{year} {self.amendment_path}"

    @property
    def sort_key(self) -> tuple[int, int]:
        """Kronologi. Lovnumre stiger inden for et år, så (år, nummer) er datoorden."""
        parts = self.document_path.split("/")
        return (int(parts[-2]), int(parts[-1]))

    def confirm(self, paragraph_id: str) -> Confirmation:
        """Holder koblingen mellem denne ændring og bemærkningen?

        Kontrollen er sekundær. Punktet er allerede genfundet i lovforslaget ved
        tekstsammenligning, og kun instrukser, der ændrer den rigtige lov, indgår. Det,
        der efterprøves her, er, om selve *bemærkningen* handler om ændringen — den
        hentes ved et opslag på nummer, og et forskudt opslag ville ellers ikke ses.
        """
        if not self.note.found:
            # Uden bemærkning er der ingen kobling at efterprøve. Manglen er allerede
            # oplyst gennem `note.problem` og skal ikke tælles med som mistanke.
            return Confirmation(checkable=False)

        flat = re.sub(r"\s+", "", self.note.text).upper()
        if f"§{paragraph_id.upper()}" in flat:
            return Confirmation(f"bemærkningen nævner § {paragraph_id}")

        run = longest_shared_run(self.text, self.note.text)
        if run >= SHARED_RUN_WORDS:
            return Confirmation(f"bemærkningen gengiver {run} ord i træk fra ændringen")
        return Confirmation(checkable=quotes_real_text(self.text))

    def mentions(self, paragraph_id: str) -> bool:
        """Bevaret navn for den samlede kontrol."""
        return self.confirm(paragraph_id).ok


@dataclass
class History:
    """Hele forarbejdshistorikken for én paragraf."""

    law_name: str
    paragraph_id: str
    start: str
    chain: list[tuple[str, int]] = field(default_factory=list)  # (lovbekendtgørelse, fund)
    changes: list[Change] = field(default_factory=list)
    reached_end: bool = False  # kæden løb tør for led, ikke for skridt
    problems: list[str] = field(default_factory=list)  # svaret mangler noget
    notices: list[str] = field(default_factory=list)  # noget usædvanligt blev håndteret
    # Står paragraffen i den valgte lovbekendtgørelse? Uden dette svarer en paragraf,
    # der ikke findes, præcis som en paragraf, der aldrig er ændret: med ingenting.
    paragraph_exists: bool = True

    @property
    def by_place(self) -> dict[str, list[Change]]:
        """Ændringerne grupperet efter stykke — den form, spørgsmålet stilles i."""
        grouped: dict[str, list[Change]] = {}
        for change in self.changes:
            for where, _ in change.places or [("hele paragraffen", "")]:
                grouped.setdefault(where, []).append(change)
        return grouped

    @property
    def with_note(self) -> int:
        return sum(1 for change in self.changes if change.note.found)

    @property
    def confirmed(self) -> int:
        return sum(1 for change in self.changes if change.mentions(self.paragraph_id))


def normalise_paragraph(paragraph_id: str) -> str:
    """'§ 9 C' og '9c' bliver begge til '9C', som er Lex Danias localId."""
    return paragraph_id.upper().replace(" ", "").lstrip("§").strip()


DANISH_MONTHS = (
    "januar", "februar", "marts", "april", "maj", "juni",
    "juli", "august", "september", "oktober", "november", "december",
)


@dataclass
class Consolidation:
    """En lovbekendtgørelse — én udgave af loven, som den så ud på en bestemt dag."""

    eli: str
    date: str  # ISO, fx "2015-09-07"

    @property
    def number(self) -> str:
        return self.eli.rsplit("/", 1)[-1]

    @property
    def label(self) -> str:
        try:
            year, month, day = (int(part) for part in self.date.split("-"))
            when = f"{day}. {DANISH_MONTHS[month - 1]} {year}"
        except (ValueError, IndexError):
            when = self.date or "ukendt dato"
        return f"LBK {self.number} af {when}"


def consolidation_chain(newest_eli: str, max_steps: int = 40) -> list[Consolidation]:
    """Lovens udgaver, nyeste først, så langt tilbage materialet rækker.

    Kæden findes ved at følge hver bekendtgørelses henvisning til sin forgænger. Det
    koster ét kald pr. led første gang — omkring 13 for ligningsloven, der når tilbage
    til 2006 — og svares derefter af diskcachen.

    Formålet er at kunne spørge til retstilstanden på en bestemt dato i stedet for i
    dag. Vil man vide, hvad der gjaldt i 2015, er ændringer fra 2016 og frem ikke bare
    overflødige, de er vildledende.
    """
    chain: list[Consolidation] = []
    current = newest_eli.strip("/")
    for _ in range(max_steps):
        try:
            xml = lex_dania.fetch_document_xml(current)
        except Exception:  # noqa: BLE001 - et manglende led afslutter kæden
            break
        chain.append(Consolidation(eli=current, date=lex_dania.document_date(xml)))
        earlier = lex_dania.previous_consolidation(xml)
        if not earlier or earlier in {step.eli for step in chain}:
            break
        current = earlier
    return chain


def paragraph_history(
    lbk_eli: str,
    paragraph_id: str,
    max_steps: int = 8,
    progress: Callable[[str], None] | None = None,
) -> History:
    """Saml hele forarbejdshistorikken for én paragraf.

    `progress` kaldes med en kort statuslinje undervejs, så en brugerflade kan vise,
    hvad der sker. Opslaget tager typisk 20-45 sekunder første gang, fordi hvert led i
    kæden kræver flere netværkskald; derefter svarer diskcachen.
    """
    def announce(message: str) -> None:
        if progress:
            progress(message)

    start = lbk_eli.strip("/")
    wanted = normalise_paragraph(paragraph_id)

    target_xml = lex_dania.fetch_document_xml(start)
    law_name = lex_dania.law_name_of(lex_dania.fetch_metadata(start))
    history = History(law_name=law_name, paragraph_id=wanted, start=start)

    # Lex Danias localId staves ikke ens fra lov til lov: ligningsloven skriver "9C",
    # personskatteloven "8a". Sammenligningen må derfor være uafhængig af versaler.
    present = {
        provision.paragraph_id.upper()
        for provision in lex_dania.extract_provisions(target_xml)
    }
    if wanted not in present:
        history.paragraph_exists = False
        history.problems.append(
            f"§ {paragraph_id.strip()} står ikke i {start}. Findes der alligevel "
            "ændringer nedenfor, er bestemmelsen ophævet undervejs; er der ingen, er "
            "det tomme svar udtryk for, at paragraffen ikke blev fundet — ikke for at "
            "den har stået uændret."
        )

    seen: set[str] = set()
    current, current_xml = start, target_xml
    current_amendments = lex_dania.consolidated_amendments(target_xml)

    for _ in range(max_steps):
        announce(f"Gennemgår {current} ({len(current_amendments)} ændringslove)")
        if not current_amendments:
            # En lovbekendtgørelse uden indarbejdede ændringer er sjælden, men findes:
            # en ren genudsendelse retter en fejl i den forrige uden at tilføje noget.
            # Kun når listen mangler *uden* den forklaring, er perioden gået tabt.
            if lex_dania.restates_only(current_xml):
                history.notices.append(
                    f"{current} indarbejder ingen nye ændringslove. Den er udsendt for at "
                    "rette den forrige bekendtgørelse, og der mangler derfor intet."
                )
            else:
                history.problems.append(f"{current}: ingen læselig liste over ændringer")

        # Bekendtgørelsens liste opregner ændringer af den forrige bekendtgørelse, så
        # det er dennes changed_by, der kan afgøre et årstal, listen har skrevet forkert.
        earlier = lex_dania.previous_consolidation(current_xml)

        found_here = 0
        for amendment in current_amendments:
            if amendment.document_path in seen:
                continue
            seen.add(amendment.document_path)
            instructions, problem, notice = instructions_of(amendment, law_name, earlier)
            if problem:
                history.problems.append(problem)
            if notice:
                history.notices.append(notice)
            for instruction in instructions:
                places: list[tuple[str, str]] = []
                for raw in instruction.probable_targets:
                    target = lex_dania.parse_target(raw)
                    if target.paragraph_id.upper() != wanted:
                        continue
                    places.append((
                        f"stk. {target.stk_number}" if target.stk_number else "hele paragraffen",
                        ", ".join(f"{n}. pkt." for n in target.sentence_numbers)
                        if target.sentence_numbers else "",
                    ))

                # Indsættes paragraffen, er målet den foregående paragraf ("Efter § 33
                # indsættes: § 33 A"), så den skal også søges i den nye tekst.
                inserted = not places and wanted in lex_dania.inserted_paragraphs(
                    instruction.new_text
                )
                if not places and not inserted:
                    continue
                if inserted:
                    places = [("hele paragraffen — indsat", "")]

                history.changes.append(
                    Change(
                        consolidation=current,
                        # Instruksens egen sti, ikke listens: er årstallet rettet, er
                        # det den rettede sti, dokumentet faktisk blev hentet fra.
                        document_path=instruction.document_path,
                        amendment_path=instruction.amendment_path,
                        text=instruction.text,
                        places=places,
                        inserted=inserted,
                    )
                )
                found_here += 1

        history.chain.append((current, found_here))

        if not earlier or earlier == current or earlier in {step for step, _ in history.chain}:
            history.reached_end = True
            break
        try:
            current_xml = lex_dania.fetch_document_xml(earlier)
            current_amendments = lex_dania.consolidated_amendments(current_xml)
        except Exception as error:  # noqa: BLE001
            history.problems.append(f"{earlier} kunne ikke hentes: {error}")
            history.reached_end = True
            break
        current = earlier

    # Nyeste først. Rækkefølgen i lovbekendtgørelsens egen liste er ikke kronologisk, og
    # for § 33 A afgør det, om ophævelsen eller genindførelsen ser ud til at komme sidst.
    history.changes.sort(key=lambda change: change.sort_key, reverse=True)

    for index, change in enumerate(history.changes, start=1):
        announce(f"Henter bemærkning {index} af {len(history.changes)}: {change.label}")
        reference = AMENDMENT_REFERENCE.search(change.amendment_path)
        law_paragraph = int(reference.group(1)) if reference else 0
        item = int(reference.group(2)) if reference else 0
        change.note = note_for(
            change.document_path, law_paragraph, item, law_name, change.text
        )

    return history
