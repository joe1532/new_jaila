"""Udtræk af ændringsinstrukser fra Retsinformations Lex Dania-XML.

Dette modul er den ene implementering af hentning, udtræk og klassifikation.
Både proben (`probe.py mine`) og inspektionsappen (`app.py`) bruger det, så de aldrig
kan komme til at måle to forskellige ting.

Modulet klassificerer kun. Det anvender ikke operationerne på lovteksten, og en
klassificeret instruks er derfor ikke det samme som en instruks, vi kan udføre.

TLS: udviklingsmaskinen har TLS-inspektion, så Pythons certifi-bundle afvises. Vi
bruger truststore, der validerer mod OS'ets eget trust store. På en Linux-server
uden inspektion er det ikke nødvendigt.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import ssl
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field

USER_AGENT = "JAILA-lovhistorik/0.1 (teknisk afklaring)"
TIMEOUT_SECONDS = 30

# Vi kender ikke Retsinformations rate limits. Gå langsomt ved hentning over nettet.
DELAY_SECONDS = 1.0

# Grænsen findes for ikke at æde hukommelsen på et uventet svar, ikke for at afvise
# store dokumenter. Den var 8 MB, hvilket huggede lovforslag L 88 (2022-23) over midt i
# et element; den afkortede fil blev gemt i cachen og gjorde forslagets bemærkninger
# permanent utilgængelige. Størstedelen af det, der fylder, er indlejret formatering.
#
# 64 MB var stadig for lidt: LOV 1489/2024 fylder 85,4 MB og ændrer skatteforvaltningsloven
# to steder, så to bemærkninger forsvandt. Prisen for at læse den er målt og er høj — 3
# sekunder at parse, spids 1,1 GB hukommelse under udtrækket — men den betales sjældent.
# Hæves grænsen yderligere, bør `extract_instructions` skrives om til `iterparse`, for
# hukommelsen vokser med dokumentet, ikke med det, vi leder efter.
MAX_BYTES = 128_000_000

# Cachen ligger ved siden af koden, når motoren køres fra arbejdsmappen. På en server skal
# den kunne ligge et andet sted: udrulningen synkroniserer applikationsmappen med
# `rsync --delete`, så en cache derinde ville blive slettet ved hver udrulning, og hvert
# opslag ville begynde forfra med minutters hentning. `LOVHISTORIK_CACHE_DIR` peger den
# mod en mappe, der overlever.
CACHE_DIRECTORY = pathlib.Path(
    os.getenv("LOVHISTORIK_CACHE_DIR") or pathlib.Path(__file__).with_name(".cache")
)

# Verbalmønstre for ændringsinstrukser. Rækkefølgen er uden betydning; en instruks
# kan matche flere, fordi ét nummereret punkt kan indeholde flere operationer.
CONSTRUCTIONS: list[tuple[str, str]] = [
    # "affattes som bilag 1 til denne lov" er samme operation som "affattes således".
    ("affattes", r"affattes\s+(således|som)\b"),
    ("ophaeves", r"\bophæves\b"),
    ("indsaettes_som", r"indsættes\s+som\b"),
    # To ordstillinger for samme operation: "I § X indsættes efter »Y«:" og
    # "Efter § X indsættes:" (sidstnævnte når en helt ny paragraf indsættes).
    ("indsaettes_efter", r"indsættes\s+efter\b|\befter\s+§[^.]{0,60}?\bindsættes\b"),
    ("indsaettes_foer", r"indsættes\s+(før|forud for)\b|\bfør\s+§[^.]{0,60}?\bindsættes\b"),
    # "ændres »X« til: »Y«". Vi kan ikke søge frem til "til:", fordi den citerede
    # tekst selv kan indeholde punktummer og kolonner (»6.000 kr.«), så vi rammer
    # kun citatets start. Der kan stå et indskud imellem: "ændres to steder »X«".
    ("aendres_til", r"\bændres\b[^»:]{0,40}[»:]"),
    ("omnummerering", r"\bbliver\s+(herefter\s+)?(til\s+)?(§|stk\.|nr\.|litra)"),
    ("udgaar", r"\budgår\b"),
]

# Angiver hvor mange forekomster en tekstudskiftning rammer. Uden denne oplysning
# kan en "ændres ... til"-operation ikke anvendes deterministisk.
OCCURRENCE_QUALIFIER = re.compile(
    r"\b(to|tre|fire|fem|seks|syv|otte|ni|ti|begge|alle|samtlige)\s+steder\b"
)

OCCURRENCE_WORDS: dict[str, int] = {
    "to": 2,
    "tre": 3,
    "fire": 4,
    "fem": 5,
    "seks": 6,
    "syv": 7,
    "otte": 8,
    "ni": 9,
    "ti": 10,
}


def build_context() -> ssl.SSLContext:
    """Brug OS'ets trust store, hvis truststore er installeret."""
    try:
        import truststore
    except ImportError:
        return ssl.create_default_context()
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


CONTEXT = build_context()


class FetchError(RuntimeError):
    """Netværks-, TLS- eller HTTP-fejl ved hentning fra Retsinformation.

    `status` er HTTP-koden, når der kom et svar, ellers None. Forskellen har betydning:
    404 betyder, at dokumentet ikke findes, mens en afbrudt forbindelse intet siger om,
    hvad der ligger i den anden ende. Kun det første må bruges som bevis.
    """

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


# Et forbigående svigt må ikke blive til et fagligt svar. Uden genforsøg gav to ens
# opslag på ligningslovens § 16 henholdsvis 48 og 49 bemærkninger, fordi én hentning
# faldt undervejs og blev til "kunne ikke hentes". Ventetiden fordobles mellem forsøgene.
RETRY_ATTEMPTS = 3
RETRY_PAUSE_SECONDS = 1.5

# 5xx er serverens eget svigt og kan gå over. 4xx er et svar om, at forespørgslen er
# forkert, og den bliver ikke rigtigere af at blive gentaget.
def _worth_retrying(error: "FetchError") -> bool:
    return error.status is None or error.status >= 500


def fetch(url: str, accept: str | None = None) -> tuple[bytes, str]:
    """Hent en URL. Returnerer (indhold, content-type) eller kaster FetchError.

    Forbigående fejl genforsøges. Det er ikke en bekvemmelighed: uden genforsøg afhænger
    svaret af netværkets luner, og to ens spørgsmål kan give forskellige svar.
    """
    for attempt in range(RETRY_ATTEMPTS):
        try:
            return _fetch_once(url, accept)
        except FetchError as error:
            if attempt == RETRY_ATTEMPTS - 1 or not _worth_retrying(error):
                raise
            time.sleep(RETRY_PAUSE_SECONDS * (2**attempt))
    raise AssertionError("uopnåelig")  # løkken vender altid tilbage eller kaster


def _fetch_once(url: str, accept: str | None = None) -> tuple[bytes, str]:
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=CONTEXT) as response:
            # Der læses én byte mere end grænsen, så et for stort svar kan afvises i
            # stedet for stiltiende at blive skåret over. Et afkortet dokument ligner
            # et helt dokument og forsvinder ellers ind i cachen.
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                # Et for stort svar bliver ikke mindre af at blive hentet igen.
                raise FetchError(f"Svaret overstiger {MAX_BYTES} bytes for {url}", status=413)
            return body, response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as http_error:
        raise FetchError(
            f"HTTP {http_error.code} for {url}", status=http_error.code
        ) from http_error
    except (urllib.error.URLError, ssl.SSLError, TimeoutError, OSError) as error:
        raise FetchError(f"{type(error).__name__}: {error}") from error


def cache_path_for(document_path: str) -> pathlib.Path:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", document_path).strip("_")
    return CACHE_DIRECTORY / f"{slug}.xml"


def fetch_document_xml(document_path: str) -> bytes:
    """Hent et dokuments XML med diskcache.

    `document_path` er ELI-stien uden vært, fx 'eli/lta/2025/1500'. Cachen gør, at
    gentagne analysekørsler ikke belaster kilden. Dokumenterne er uforanderlige
    udgivelser, så cachen har ingen udløbstid.
    """
    cache_file = cache_path_for(document_path)
    if cache_file.exists():
        cached = cache_file.read_bytes()
        if is_complete_document(cached):
            return cached
        # En ufuldstændig fil i cachen ville aldrig blive hentet igen, og fejlen ville
        # være permanent. Den kasseres i stedet, så hentningen kan forsøges på ny.
        cache_file.unlink()

    # parents=True, fordi cachen kan være peget mod en sti, hvis mellemled ikke findes endnu.
    CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    time.sleep(DELAY_SECONDS)
    body, _ = fetch(f"https://retsinformation.dk/{document_path}/dan/xml")
    if not body:
        raise FetchError(f"Tomt svar for {document_path}")
    if not is_complete_document(body):
        raise FetchError(f"Ufuldstændigt dokument for {document_path} ({len(body)} bytes)")

    # Skriv gennem en midlertidig fil og byt den ind. Så længe kun proben og Streamlit-
    # appen brugte modulet, kørte der én hentning ad gangen, og en direkte skrivning var
    # nok. Kaldes modulet fra en webserver, kan to forespørgsler hente samme dokument
    # samtidig, og en læser ville da kunne ramme en halvskrevet fil. `os.replace` er
    # atomisk på både Windows og Linux, så en læser ser enten den gamle fil eller den
    # færdige — aldrig noget derimellem. Den midlertidige fil får processens id i navnet,
    # så to skrivere ikke deler den.
    temporary = cache_file.with_suffix(f".{os.getpid()}.part")
    try:
        temporary.write_bytes(body)
        os.replace(temporary, cache_file)
    except OSError:
        # Cachen er en bekvemmelighed. Kan den ikke skrives — fuld disk, manglende
        # rettigheder — skal opslaget stadig lykkes, blot uden at blive gemt.
        temporary.unlink(missing_ok=True)
    return body


def is_complete_document(body: bytes) -> bool:
    """Slutter dokumentet, hvor det skal?

    Kontrollen er bevidst billig: den skal kunne køre ved hver læsning fra cachen. Den
    fanger afkortede svar, ikke skader midt i dokumentet — dem opdager XML-parseren.
    """
    return body.rstrip().endswith(b"</Dokument>")


def fetch_metadata(eli_uri: str) -> dict[str, object]:
    """Hent ELI-metadata (.rdfa) og træk de felter ud, vi bruger igen og igen."""
    url = eli_uri if eli_uri.startswith("http") else f"https://www.retsinformation.dk/{eli_uri}"
    raw, content_type = fetch(f"{url}.rdfa", "application/json")
    if "json" not in content_type.lower():
        raise FetchError(f"Forventede JSON, fik {content_type!r} for {url}.rdfa")
    try:
        triples = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as error:
        raise FetchError(f"Ugyldig JSON fra {url}.rdfa: {error}") from error

    summary: dict[str, object] = {
        "uri": url,
        "title_short": "",
        "title": "",
        "type": "",
        "id_local": "",
        "in_force": "",
        "changes": [],
        "changed_by": [],
        "consolidates": [],
        "consolidated_by": [],
    }
    for triple in triples:
        prop = str(triple.get("property", ""))
        value = str(triple.get("content") or triple.get("resource") or "")
        if prop == "eli:title_short":
            summary["title_short"] = value
        elif prop == "eli:title":
            summary["title"] = value
        elif prop == "eli:type_document":
            summary["type"] = value.rsplit("#", 1)[-1]
        elif prop == "eli:id_local":
            summary["id_local"] = value
        elif prop == "eli:in_force":
            summary["in_force"] = value.rsplit("-", 1)[-1]
        elif prop in ("eli:changes", "eli:changed_by", "eli:consolidates", "eli:consolidated_by"):
            key = prop.split(":", 1)[1]
            values = summary[key]
            assert isinstance(values, list)
            values.append(value)
    return summary


# "§ 10 i lov nr. 1454 af 10. december 2024" — paragraffen i ændringsloven, lovens
# nummer og året. Året er det, der sammen med nummeret giver ELI-stien.
#
# Paragrafangivelsen er valgfri: er hele ændringsloven indarbejdet, står der blot
# "lov nr. 1379 af 28. december 2011". Uden den valgfrihed forsvandt sådanne love
# lydløst fra listen, og deres ændringer kunne aldrig findes.
CONSOLIDATED_AMENDMENT = re.compile(
    r"(?:§+\s*(?P<paragraph>\d+)(?:\s*(?:og|,)\s*\d+)*\s+i\s+)?"
    # Punktummet efter dagen er valgfrit: LBK 42/2023 skriver "af 30 november 2021",
    # og en enkelt manglende tegnsætning må ikke koste hele lovens ændringer.
    r"lov\s+nr\.\s*(?P<number>\d+)\s+af\s+\d+\.?\s*\w+\s+(?P<year>\d{4})",
    re.IGNORECASE,
)
# Uden IGNORECASE: flaget ville få [A-ZÆØÅ] til også at matche små bogstaver, og så
# ville "af 10. december" blive læst som en sætningsafslutning midt i opremsningen.
# Kommaet og valget mellem "der" og "som" varierer fra bekendtgørelse til
# bekendtgørelse. LBK 42/2023 skriver "med de ændringer der følger af" uden komma, og
# et krav om kommaet gjorde hele perioden juni 2021 – oktober 2022 usynlig, uden at
# noget fejlede.
# Det afsluttende punktum er valgfrit. Færdselslovens LBK 1320/2010 slutter opremsningen
# uden punktum, og kravet kostede hele listen. Alternativet med punktum står først, så
# en opremsning, der efterfølges af mere tekst, stadig standser det rigtige sted.
# Indledningen varierer mere end ventet. Ud over komma og valget mellem "der" og "som"
# skrives den i ental, når kun én lov er indarbejdet ("med den ændring, der følger af §
# 6 i lov nr. 540", LBK 1192/2007), og personskattelovens LBK 143/2011 skyder et led ind:
# "med de ændringer og tilføjelser, der følger af". Hver af de tre varianter kostede hele
# bekendtgørelsens liste — for LBK 143/2011 var det 21 ændringslove.
CONSOLIDATION_CLAUSE = re.compile(
    r"med de[nt]?\s+ændring(?:er)?(?:\s+og\s+tilføjelser)?,?\s+(?:der|som)\s+følger\s+af"
    r"(.*?)(?:\.\s*$|\.\s+[A-ZÆØÅ]|\s*$)",
    re.DOTALL,
)


def unincorporated_amendments(xml_bytes: bytes) -> list[str]:
    """Ændringslove, bekendtgørelsen udtrykkeligt oplyser ikke at have indarbejdet.

    Efter opremsningen begrundes udeladelserne: "Den ændring, der følger af § 3 i lov
    nr. 624 af 14. juni 2011, er ikke indarbejdet i denne lovbekendtgørelse, da
    ændringen efterfølgende er ophævet." Uden dem ligner en legitim udeladelse en
    lækage, og en kontrol, der larmer ved korrekte tilfælde, bliver ignoreret.
    """
    found: list[str] = []
    for element in _preamble_lineas(xml_bytes):
        text = element_text(element)
        if "ikke indarbejdet" not in text.lower():
            continue
        for match in CONSOLIDATED_AMENDMENT.finditer(text):
            path = f"eli/lta/{match.group('year')}/{match.group('number')}"
            if path not in found:
                found.append(path)
    return found


PREVIOUS_CONSOLIDATION = re.compile(
    r"jf\.\s*lovbekendtgørelse\s+nr\.\s*(\d+)\s+af\s+\d+\.\s*\w+\s+(\d{4})", re.IGNORECASE
)


def previous_consolidation(xml_bytes: bytes) -> str:
    """Den lovbekendtgørelse, denne bygger videre på, som ELI-sti — ellers tom streng.

    Indledningen lyder "Herved bekendtgøres ligningsloven, jf. lovbekendtgørelse nr. 42
    af 13. januar 2023, med de ændringer, der følger af …". Første led er kædens
    forrige led, og det er vejen bagud for bestemmelser, der ikke er ændret for nylig.
    """
    root = ElementTree.fromstring(xml_bytes)
    for element in root.iter():
        if element.tag == "Paragraf":
            break
        if element.tag != "Linea":
            continue
        text = element_text(element)
        if "bekendtgøres" not in text.lower():
            continue
        match = PREVIOUS_CONSOLIDATION.search(text)
        if match:
            return f"eli/lta/{match.group(2)}/{match.group(1)}"
    return ""


@dataclass
class ConsolidatedAmendment:
    """Én ændringslov, som en lovbekendtgørelse selv oplyser at have indarbejdet."""

    document_path: str
    paragraph: int  # ændringslovens egen paragraf, fx 10 i "§ 10 i lov nr. 1454"


def _preamble_lineas(xml_bytes: bytes) -> list[ElementTree.Element]:
    """Tekstblokke før første paragraf. Det er dér, bekendtgørelsen taler om sig selv."""
    root = ElementTree.fromstring(xml_bytes)
    blocks: list[ElementTree.Element] = []
    for element in root.iter():
        if element.tag == "Paragraf":
            break
        if element.tag == "Linea":
            blocks.append(element)
    return blocks


# En fortsættelse af opremsningen begynder, hvor sætningen blev brudt: med resten af en
# dato, med den næste lovhenvisning, eller med bindeordet foran den sidste.
CONTINUES_LIST = re.compile(r"^\s*(?:\d|§|og\s+§|og\s+lov\s+nr\.|lov\s+nr\.)")

# Et punktum, der hører til en forkortelse, må ikke fjernes ved sammenkædningen.
# Ombrydningen falder både efter "af." (hvor punktummet er en artefakt) og efter "lov
# nr." (hvor det er en del af henvisningen), og de to skal behandles forskelligt.
ABBREVIATION_END = re.compile(r"\b(?:nr|jf|stk|pkt|litra|kap)\.$")


def _join_continuations(texts: list[str], start: int, limit: int = 4) -> str:
    """Saml en indledning, der er brudt over flere tekstblokke.

    Færdselslovens LBK 1047/2011 bryder opremsningen midt i en dato: første blok slutter
    med "§ 2 i lov nr. 1338 af.", og den næste begynder "19. december 2008, § 106 i lov
    nr. 1537 …". Læses blokkene hver for sig, standser opremsningen ved det falske
    punktum, og hele listen går tabt uden at noget fejler.

    Kun blokke, der tydeligt fortsætter opremsningen, føjes til. Det er afgørende: efter
    opremsningen står som regel sætninger om ændringer, der udtrykkeligt *ikke* er
    indarbejdet, og de må under ingen omstændigheder havne i listen.
    """
    joined = texts[start]
    for text in texts[start + 1 : start + 1 + limit]:
        if not CONTINUES_LIST.match(text):
            break
        tail = joined.rstrip()
        if tail.endswith(".") and not ABBREVIATION_END.search(tail):
            tail = tail[:-1]
        joined = f"{tail} {text.lstrip()}"
    return joined


# En afbrudt indledning tages op igen med et komma: kursgevinstlovens LBK 140/2008 slutter
# blokken ved lovens navn og fortsætter to bemærkningsblokke senere med ", jf.
# lovbekendtgørelse nr. 978 …, med de ændringer, der følger af …".
RESUMED_CLAUSE = re.compile(r"^\s*,\s*jf\.\s*lovbekendtgørelse", re.IGNORECASE)


def _clause_after_interruption(texts: list[str], start: int, limit: int = 5):
    """Find opremsningen, når indledningen er afbrudt af indskudte bemærkninger.

    Sammenkædning virker kun på blokke, der følger umiddelbart efter hinanden. Her står
    der andet imellem, så fortsættelsen må genkendes på sin egen form.

    Kravet om det indledende komma og "jf. lovbekendtgørelse" er ikke pynt. De indskudte
    blokke handler netop om ændringer, der *ikke* er indarbejdet — "Lovbekendtgørelsen
    indeholder ikke de ændringer, der følger af § 6 i lov nr. 1534 …" — og en løsere
    søgning ville føje netop de love til listen. Det ville være værre end at mangle dem.
    """
    for text in texts[start + 1 : start + 1 + limit]:
        if RESUMED_CLAUSE.match(text):
            return CONSOLIDATION_CLAUSE.search(text)
    return None


def consolidated_amendments(xml_bytes: bytes) -> list[ConsolidatedAmendment]:
    """Læs, hvilke ændringer en lovbekendtgørelse selv siger den indeholder.

    Indledningen lyder "Herved bekendtgøres skatteindberetningsloven, jf.
    lovbekendtgørelse nr. 15 af 8. januar 2024, med de ændringer, der følger af § 10 i
    lov nr. 1454 af 10. december 2024, …". Det er en langt bedre kilde end
    `eli:changed_by`, som også rummer love, der endnu ikke er trådt i kraft.

    Den peger tilmed på den enkelte paragraf i ændringsloven, hvilket er nødvendigt,
    når en lov ændrer samme lov flere steder med hver sin ikrafttræden.

    Returnerer en tom liste, hvis sætningen ikke findes. Kalderen må da selv afgøre,
    hvad der skal afspilles — vi opfinder ikke en liste.
    """
    texts = [element_text(element) for element in _preamble_lineas(xml_bytes)]
    for index, text in enumerate(texts):
        if "bekendtgøres" not in text.lower():
            continue
        text = _join_continuations(texts, index)
        clause = CONSOLIDATION_CLAUSE.search(text)
        if not clause:
            clause = _clause_after_interruption(texts, index)
        if not clause:
            continue

        found: list[ConsolidatedAmendment] = []
        for match in CONSOLIDATED_AMENDMENT.finditer(clause.group(1)):
            paragraph = match.group("paragraph")
            found.append(
                ConsolidatedAmendment(
                    document_path=f"eli/lta/{match.group('year')}/{match.group('number')}",
                    # 0 betyder, at hele ændringsloven er indarbejdet.
                    paragraph=int(paragraph) if paragraph else 0,
                )
            )
        if found:
            return found
    return []


# En indsat paragraf indledes med sin egen betegnelse: "§ 33 A. Har en person, …".
INSERTED_PARAGRAPH = re.compile(r"(?:^|\.\s+)§\s*(\d+)\s*([A-ZÆØÅ])?\.\s")


def inserted_paragraphs(new_text: str) -> list[str]:
    """Paragraffer, en instruks indsætter, som normaliserede localId ('33A').

    Indsættes en ny paragraf, er målet den *foregående* paragraf: "Efter § 33
    indsættes: § 33 A. …". Søger man på den nye paragraf, findes ændringen derfor
    ikke blandt målene, selv om det er dér, hele bestemmelsen kommer fra. Uden dette
    ville den vigtigste forarbejde til en bestemmelse — den, der indførte den — være
    usynlig.
    """
    found: list[str] = []
    for number, letter in INSERTED_PARAGRAPH.findall(new_text or ""):
        label = f"{number}{letter or ''}".upper()
        if label not in found:
            found.append(label)
    return found


NOTE_PARAGRAPH = re.compile(r"^Til\s+§+\s*(\d+)\s*$")
# Ældre lovforslag skriver overskriften uden "Til". L 199 (2008-09) har bare "§ 1", og
# uden dette mønster mistede afsnittets 43 "Til nr."-overskrifter deres paragraf og
# dermed hele bemærkningen. Formen er kun sikker inde i bemærkningsafsnittet, hvor en
# bar paragrafhenvisning ikke kan forveksles med lovtekst.
BARE_NOTE_PARAGRAPH = re.compile(r"^§+\s*(\d+)\s*$")
SPECIAL_NOTES_HEADING = re.compile(
    r"^Bemærkninger til lovforslagets enkelte bestemmelser", re.IGNORECASE
)
# "Til nr. 7", "Til nr. 7 og 8", "Til nr. 2-5" og "Til nr. 1, 3 og 4" er alle
# almindelige. Én bemærkning kan altså dække flere ændringspunkter. Kolonet til sidst
# er valgfrit: samme dokument kan skrive både "Til nr. 1" og "Til nr. 2:".
NOTE_ITEM = re.compile(r"^Til\s+nr\.\s*([\d\s,ogå-]+?)\s*:?\s*$", re.IGNORECASE)


def note_item_numbers(text: str) -> list[int]:
    """Hvilke ændringspunkter dækker en overskrift som "Til nr. 2-5 og 7"?

    Intervaller udvides. Er overskriften uforståelig, returneres en tom liste, og
    bemærkningen henføres ikke — det er bedre end at gætte på ét nummer.
    """
    numbers: list[int] = []
    for part in re.split(r"\s*(?:,|\bog\b)\s*", text):
        part = part.strip()
        if not part:
            continue
        span = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if span:
            first, last = int(span.group(1)), int(span.group(2))
            if first <= last <= first + 50:  # værn mod at et årstal læses som interval
                numbers.extend(range(first, last + 1))
            continue
        if part.isdigit():
            numbers.append(int(part))
    return numbers


def extract_explanatory_notes(xml_bytes: bytes) -> dict[tuple[int, int], str]:
    """Træk lovforslagets specielle bemærkninger ud, nøglet på (paragraf, nummer).

    Bemærkningerne er ikke semantisk opmærkede. Overskrifterne "Til § 1" og
    "Til nr. 2" står som almindelig tekst i `<Char>`, og kun paragrafoverskriften er
    kursiveret. Udtrækket bygger derfor på tekstmønstre, og det er en svaghed: en
    ændret formulering af overskriften vil få bemærkninger til at forsvinde frem for
    at fejle højlydt. Derfor skal antallet af fundne bemærkninger altid kontrolleres
    mod antallet af ændringspunkter i loven.

    Nøglen svarer til ændringslovens egen struktur: (§ i ændringsloven, nummeret i
    opremsningen), altså præcis det, en instruks som "§ 1, nr. 2" identificeres ved.

    Nummer 0 er tekst, der står under "Til § N" uden en "Til nr."-overskrift. Det er
    enten en indledning til hele paragraffen, eller — når paragraffen kun har ét
    ændringspunkt — hele bemærkningen, fordi "Til nr. 1" da ofte udelades. Kalderen
    bør falde tilbage på nummer 0, når det søgte nummer ikke findes.
    """
    root = ElementTree.fromstring(xml_bytes)

    notes: dict[tuple[int, int], list[str]] = {}
    paragraph: int | None = None
    items: list[int] = []
    in_special_notes = False

    for linea in root.iter("Linea"):
        text = element_text(linea)
        if not text:
            continue

        if SPECIAL_NOTES_HEADING.match(text):
            in_special_notes = True
            continue

        heading = NOTE_PARAGRAPH.match(text) or (
            BARE_NOTE_PARAGRAPH.match(text) if in_special_notes else None
        )
        if heading:
            paragraph = int(heading.group(1))
            items = [0]
            continue

        heading = NOTE_ITEM.match(text)
        if heading:
            found = note_item_numbers(heading.group(1))
            if found:
                items = found
                continue

        # Samme tekst føres til alle de numre, overskriften dækker. Bemærkningen er
        # skrevet under ét, og der findes ingen opdeling at læse.
        if paragraph is not None and items:
            for item in items:
                notes.setdefault((paragraph, item), []).append(text)

    return {key: " ".join(parts) for key, parts in notes.items()}


def law_name_of(metadata: dict[str, object]) -> str:
    """Lovens navn, som ændringslove omtaler den i "I ligningsloven, jf. …".

    `title_short` duer ikke: den er dokumentnummeret ("LBK nr 42 af 13/01/2023").
    Den fulde titel er "Bekendtgørelse af lov om påligningen af indkomstskat til
    staten (ligningsloven)", og det er kaldenavnet i parentesen, ændringslovene
    bruger. Har loven intet kaldenavn, bruges dens egen betegnelse ("lov om …").
    """
    title = str(metadata.get("title") or "")
    title = re.sub(r"^Bekendtgørelse af\s+", "", title, flags=re.IGNORECASE).strip()

    nickname = re.search(r"\(([^)]*lov[^)]*)\)\s*$", title, re.IGNORECASE)
    if nickname:
        return nickname.group(1).strip()
    return re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()


def document_date(xml_bytes: bytes) -> str:
    """Lovens underskriftsdato (`DiesSigni`) som ISO-dato, eller tom streng.

    Bemærk at underskriftsdato ikke er ikrafttrædelsesdato. Den rigtige rækkefølge
    følger ikrafttrædelsesbestemmelserne, som vi endnu ikke læser. Datoen her er en
    tilnærmelse, der er god nok til at sortere love, men ikke til at afgøre, hvilken
    tekst der var gældende en bestemt dag.
    """
    root = ElementTree.fromstring(xml_bytes)
    for tag in ("DiesSigni", "DiesEdicti"):
        for element in root.iter(tag):
            value = element_text(element)
            if value:
                return value
    return ""


def document_path_of(uri: str) -> str:
    """'https://www.retsinformation.dk/eli/lta/2025/1500' -> 'eli/lta/2025/1500'."""
    return str(uri).split("retsinformation.dk/", 1)[-1].strip("/")


def classify(text: str) -> list[str]:
    """Hvilke konstruktioner optræder i én ændringsinstruks? Der kan være flere."""
    found = [name for name, pattern in CONSTRUCTIONS if re.search(pattern, text, re.IGNORECASE)]
    return found or ["uklassificeret"]


def occurrence_count(text: str) -> int | None:
    """Antal forekomster en tekstudskiftning rammer, hvis instruksen angiver det.

    None betyder, at instruksen ikke siger noget, hvilket i praksis betyder én.
    "begge", "alle" og "samtlige" giver ikke et tal og returnerer 0, som kalderen
    må behandle som "ukendt antal, skal tælles i teksten".
    """
    match = OCCURRENCE_QUALIFIER.search(text)
    if not match:
        return None
    return OCCURRENCE_WORDS.get(match.group(1).lower(), 0)


# Typografiske tegn uden betydning for ordlyden. Retsinformation sætter blød
# orddeling og zero-width-tegn ind midt i ord — "personskat\u00adte\u200dlovens" er ét
# ord i loven, men fem tegn længere end det ser ud. Uden denne rensning kan en
# citeret frase fra en ændringslov ikke findes i lovteksten.
INVISIBLE_CHARACTERS = str.maketrans(
    {
        "\u00ad": "",  # blød bindestreg
        "\u200b": "",  # zero width space
        "\u200c": "",  # zero width non-joiner
        "\u200d": "",  # zero width joiner
        "\ufeff": "",  # byte order mark
        "\u00a0": " ",  # hårdt mellemrum
        "\u2011": "-",  # hård bindestreg
    }
)


def element_text(element: ElementTree.Element) -> str:
    """Tekstindholdet af et element, renset for usynlige tegn og gentaget whitespace.

    Rensningen svarer til `normalization_version = 1` i DATAMODEL.md. Ordlyden røres
    ikke; kun tegn, der er typografi og ikke sprog, fjernes.
    """
    text = "".join(element.itertext()).translate(INVISIBLE_CHARACTERS)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Instruction:
    """Ét nummereret ændringspunkt, fx "§ 1, nr. 2", som det står i ændringsloven."""

    document_path: str
    act_number: str  # ændringslovens egen paragraf, fx '1'
    item_number: str  # punktets nummer, fx '2.'
    text: str  # hele instruksen som løbende tekst
    targets: list[str] = field(default_factory=list)  # kun signiChar='AendringURN'
    italic_spans: list[str] = field(default_factory=list)
    new_text: str = ""
    constructions: list[str] = field(default_factory=list)
    occurrences: int | None = None

    @property
    def amendment_path(self) -> str:
        return f"§ {self.act_number}, nr. {self.item_number.rstrip('.')}"

    @property
    def target_markup(self) -> str:
        """Hvor sikkert målet er opmærket: signi_char | italic | none."""
        if self.targets:
            return "signi_char"
        return "italic" if self.italic_spans else "none"

    @property
    def probable_targets(self) -> list[str]:
        """Bedste bud på målbestemmelserne.

        Kursivering er et upålideligt fallback: den bruges både om målet og om den
        nye betegnelse ("indsættes som *stk. 2:*"). Antallet af kursiverede spans
        må derfor ikke bruges som antal mål — kun `targets` kan tælles.
        """
        return self.targets or self.italic_spans


def extract_instructions(
    xml_bytes: bytes, document_path: str, target_law: str
) -> list[Instruction]:
    """Find alle nummererede ændringspunkter, der retter sig mod `target_law`.

    `target_law` matches mod ændringsparagraffens indledning ("I ligningsloven, jf.
    lovbekendtgørelse nr. …, foretages følgende ændringer:"), som er den eneste
    angivelse af, hvilken lov punkterne under den ændrer. En samlelov ændrer flere
    love, så filtreringen er nødvendig, ikke en optimering.

    Kaster ElementTree.ParseError, hvis XML'en ikke kan parses.
    """
    root = ElementTree.fromstring(xml_bytes)
    needle = target_law.lower()
    instructions: list[Instruction] = []

    for block in root.iter("AendringCentreretParagraf"):
        chapeau = ""
        for child in block:
            if child.tag == "Exitus":
                chapeau = element_text(child)
                break
        if needle not in chapeau.lower():
            continue

        act_number = block.get("localId") or ""
        for item in block.iter("AendringsNummer"):
            item_number = ""
            for child in item:
                if child.tag == "Explicatus":
                    item_number = element_text(child)
                    break

            text = element_text(item)
            targets = [
                (element.text or "").strip()
                for element in item.iter("Char")
                if element.get("signiChar") == "AendringURN"
            ]
            # Nogle ændringslove kursiverer målet uden at sætte signiChar. Vi gemmer
            # kursiveringerne separat, fordi de også bruges til andet end mål.
            italic_spans = [
                re.sub(r"\s+", " ", element.text or "").strip()
                for element in item.iter("Char")
                if element.get("formaChar") == "Italic"
            ]
            italic_spans = [value for value in italic_spans if value]

            new_text = " ".join(
                element_text(element) for element in item.iter("AendringNyTekst")
            ).strip()

            instructions.append(
                Instruction(
                    document_path=document_path,
                    act_number=act_number,
                    item_number=item_number,
                    text=text,
                    targets=targets,
                    italic_spans=italic_spans,
                    new_text=new_text,
                    constructions=classify(text),
                    occurrences=occurrence_count(text),
                )
            )

    return instructions


@dataclass
class Provision:
    """Ét stykke i en lovbekendtgørelse, med dets punktummer som selvstændige strenge."""

    paragraph_id: str  # Paragraf/@localId, fx '9C'
    paragraph_label: str  # som trykt, fx '§ 9 C'
    stk_number: int  # 1 for stykker uden egen Explicatus
    nr_number: int | None = None  # nummer i en opremsning, None for selve stykket
    lineas: list[str] = field(default_factory=list)  # rå <Linea>-blokke

    @property
    def key(self) -> tuple[str, int, int | None]:
        return (self.paragraph_id, self.stk_number, self.nr_number)

    @property
    def label(self) -> str:
        base = f"{self.paragraph_label}, stk. {self.stk_number}"
        return f"{base}, nr. {self.nr_number}" if self.nr_number else base

    @property
    def text(self) -> str:
        return " ".join(self.lineas)

    @property
    def sentences(self) -> list[str]:
        """Stykkets punktummer.

        En `<Linea>`-grænse er altid en punktumgrænse, men ikke den eneste, så hver
        blok segmenteres for sig og resultaterne lægges i forlængelse af hinanden.
        """
        return [sentence for linea in self.lineas for sentence in split_sentences(linea)]


STK_NUMBER = re.compile(r"Stk\.\s*(\d+)")


def extract_provisions(xml_bytes: bytes) -> list[Provision]:
    """Læs en lovbekendtgørelses paragraffer, stykker og punktummer.

    `<Linea>` gemmes råt. Det er målt, at et `<Linea>` kan rumme flere punktummer —
    i LBK 1500 rummer § 9 C, stk. 3 fire punktummer fordelt på to `<Linea>` — så
    punktummer beregnes med `split_sentences` i stedet for at læses af opmærkningen.
    """
    root = ElementTree.fromstring(xml_bytes)
    provisions: list[Provision] = []

    for paragraph in root.iter("Paragraf"):
        paragraph_id = paragraph.get("localId") or ""
        paragraph_label = ""
        for child in paragraph:
            if child.tag == "Explicatus":
                paragraph_label = element_text(child)
                break

        for index, stk in enumerate(paragraph.iter("Stk"), start=1):
            label = ""
            for child in stk:
                if child.tag == "Explicatus":
                    label = element_text(child)
                    break
            # Stykke 1 har ingen Explicatus; senere stykker har "Stk. 3.".
            match = STK_NUMBER.search(label)
            stk_number = int(match.group(1)) if match else index

            # Opremsninger ligger som <Indentatio> med egen <Explicatus>"1)" og egne
            # <Linea>. Hvert nummer er en selvstændig enhed med sin egen
            # punktumnummerering, så dets tekst må ikke blandes ind i stykkets.
            numbered = [
                item for item in stk.iter("Indentatio") if item.get("formaInd") == "Nummer"
            ]
            inside_numbers = {id(linea) for item in numbered for linea in item.iter("Linea")}

            chapeau = [
                element_text(linea)
                for linea in stk.iter("Linea")
                if id(linea) not in inside_numbers
            ]
            provisions.append(
                Provision(
                    paragraph_id=paragraph_id,
                    paragraph_label=paragraph_label,
                    stk_number=stk_number,
                    lineas=[value for value in chapeau if value],
                )
            )

            for item in numbered:
                number_label = ""
                for child in item:
                    if child.tag == "Explicatus":
                        number_label = element_text(child)
                        break
                digits = re.search(r"(\d+)", number_label)
                if not digits:
                    continue
                lineas = [element_text(linea) for linea in item.iter("Linea")]
                provisions.append(
                    Provision(
                        paragraph_id=paragraph_id,
                        paragraph_label=paragraph_label,
                        stk_number=stk_number,
                        nr_number=int(digits.group(1)),
                        lineas=[value for value in lineas if value],
                    )
                )

    return provisions


# Et punktum efterfulgt af mellemrum og stort bogstav er en punktumgrænse. Kravet om
# stort bogstav klarer det meste af arbejdet: "10 pct. af" og "1. pkt. finder" bliver
# ikke delt, fordi der følger småt bogstav. Listen herunder er derfor kort og rummer
# kun forkortelser, der jævnligt efterfølges af et stort bogstav uden at afslutte
# sætningen — typisk fordi det næste ord er et egennavn eller en lovtitel.
#
# "pkt." står bevidst ikke på listen: "jf. dog 4. pkt. For befordring herudover …"
# afslutter faktisk et punktum, og det er den hyppigste sætningsafslutning i loven.
ABBREVIATIONS = (
    "jf.",
    "ca.",
    "f.eks.",
    "bl.a.",
    "litra",
    "art.",
    "kap.",
)

SENTENCE_BOUNDARY = re.compile(r"(?<=\.)\s+(?=[A-ZÆØÅ])")


def ends_with_abbreviation(text: str) -> bool:
    last_word = text.rsplit(" ", 1)[-1].lower()
    return any(last_word.endswith(abbreviation) for abbreviation in ABBREVIATIONS)


def split_sentences(text: str) -> list[str]:
    """Del en tekstblok i punktummer.

    Nødvendigt, fordi `<Linea>` ikke er en punktumgrænse: ét `<Linea>` kan rumme
    flere punktummer. Uden denne opdeling kan en instruks som "indsættes som 5. pkt."
    ikke stedfæstes.

    Metoden er regelbaseret og kan tage fejl. Brug `sentence_reference_conflicts`
    til at måle, hvor ofte den er i modstrid med lovens egne henvisninger.
    """
    parts = SENTENCE_BOUNDARY.split(text)
    merged: list[str] = []
    for part in parts:
        if merged and ends_with_abbreviation(merged[-1]):
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return [part.strip() for part in merged if part.strip()]


# Henvisninger som "4. pkt." eller "3. og 4. pkt." i lovens egen tekst.
SENTENCE_REFERENCE = re.compile(r"(\d+)\.(?:\s*(?:og|eller|-)\s*(\d+)\.)?\s*pkt\b")


# Hvor langt tilbage vi kigger efter en henvisning til et andet stykke eller en anden
# paragraf. "jf. fondsbeskatningslovens § 4, stk. 2, 2. pkt." handler ikke om vores
# eget stykkes punktummer og duer derfor ikke som kontrol.
REFERENCE_CONTEXT = 60


def highest_referenced_sentence(text: str) -> int:
    """Højeste punktumnummer, teksten henviser til i sit eget stykke.

    Henvisninger, der er kvalificeret med "§" eller "stk." kort forinden, springes
    over, fordi de peger et andet sted hen. Det er en forsigtig regel: den overser
    hellere en brugbar kontrol end at rejse en falsk alarm.
    """
    highest = 0
    for match in SENTENCE_REFERENCE.finditer(text):
        context = text[max(0, match.start() - REFERENCE_CONTEXT) : match.start()]
        if "§" in context or "stk." in context.lower():
            continue
        for group in match.groups():
            if group:
                highest = max(highest, int(group))
    return highest


PARAGRAPH_REFERENCE = re.compile(r"§\s*(\d+)\s*([A-ZÆØÅ])?")
STK_REFERENCE = re.compile(r"stk\.\s*(\d+)", re.IGNORECASE)
NR_REFERENCE = re.compile(r"nr\.\s*(\d+)", re.IGNORECASE)


@dataclass
class Target:
    """En målangivelse fra en ændringsinstruks, fx "§ 9 C, stk. 3, 1. pkt.".

    `sentence_numbers` er tom, når instruksen rammer hele stykket. `nr_number` er
    sat, når målet er et nummer i en opremsning, fx "§ 7, nr. 38".
    """

    raw: str
    paragraph_id: str = ""
    stk_number: int | None = None
    sentence_numbers: list[int] = field(default_factory=list)
    nr_number: int | None = None

    @property
    def is_resolvable(self) -> bool:
        """Kan målet slås op i en bestemt tekst? Kræver som minimum en paragraf."""
        return bool(self.paragraph_id)

    @property
    def key(self) -> tuple[str, int, int | None]:
        return (self.paragraph_id, self.stk_number or 1, self.nr_number)

    @property
    def label(self) -> str:
        parts = [f"§ {self.paragraph_id}"]
        if self.stk_number:
            parts.append(f"stk. {self.stk_number}")
        if self.nr_number:
            parts.append(f"nr. {self.nr_number}")
        for number in self.sentence_numbers:
            parts.append(f"{number}. pkt.")
        return ", ".join(parts)


def parse_target(text: str) -> Target:
    """Læs en målangivelse som "§ 9 C, stk. 3, 1. pkt." til strukturerede felter.

    Paragrafnummeret sammensættes til samme form som `Paragraf/@localId` i XML'en,
    så "§ 9 C" bliver til "9C" og kan slås direkte op.

    Bemærk at et stykke uden `stk.` betyder stk. 1, men kun når målet overhovedet
    peger på en paragraf. Vi udleder det ikke her, fordi forskellen mellem "ikke
    angivet" og "udtrykkeligt stk. 1" er værd at bevare i data.
    """
    target = Target(raw=text.strip())

    paragraph = PARAGRAPH_REFERENCE.search(text)
    if paragraph:
        letter = paragraph.group(2) or ""
        target.paragraph_id = f"{paragraph.group(1)}{letter}"

    stk = STK_REFERENCE.search(text)
    if stk:
        target.stk_number = int(stk.group(1))

    nr = NR_REFERENCE.search(text)
    if nr:
        target.nr_number = int(nr.group(1))

    numbers: list[int] = []
    for match in SENTENCE_REFERENCE.finditer(text):
        for group in match.groups():
            if group:
                numbers.append(int(group))
    target.sentence_numbers = sorted(set(numbers))

    return target


# "… jf. lovbekendtgørelse nr. 27 af 13. januar 2025." — sætningen slutter ved
# henvisningen, uden at der følger en opremsning af indarbejdede ændringer.
RESTATEMENT_ONLY = re.compile(
    r"jf\.\s*lovbekendtgørelse\s+nr\.\s*\d+\s+af\s+\d+\.?\s*\w+\s+\d{4}\s*\.\s*$",
    re.IGNORECASE,
)


def restates_only(xml_bytes: bytes) -> bool:
    """Er bekendtgørelsen en ren genudsendelse uden nye ændringslove?

    Tinglysningsafgiftslovens LBK 307/2025 indarbejder ingen ændringer. Den er udsendt,
    fordi to ændringer "ved en fejl ikke [var] indarbejdet korrekt" i LBK 27/2025, og
    indledningen slutter derfor ved henvisningen til den forrige bekendtgørelse.

    Sondringen er nødvendig, fordi en tom liste ellers rapporteres som en indledning, vi
    ikke kunne læse. Det er en falsk alarm, og falske alarmer er ikke harmløse: de lærer
    den, der læser svaret, at se bort fra advarsler, og så overses den ægte.
    """
    for element in _preamble_lineas(xml_bytes):
        text = element_text(element)
        if "bekendtgøres" not in text.lower():
            continue
        if CONSOLIDATION_CLAUSE.search(text):
            return False
        return bool(RESTATEMENT_ONLY.search(text.strip()))
    return False


def newest_consolidation(document_path: str, max_steps: int = 12) -> tuple[str, list[str]]:
    """Følg en lov frem til dens nyeste lovbekendtgørelse.

    En håndholdt liste over lovbekendtgørelser forælder, så snart Skatteministeriet
    udsender en ny, og den, der slår op, får svar om en forældet udgave uden at vide det.
    Ved at følge `eli:consolidated_by` fremad behøver kun ét kendt holdepunkt at stå fast.

    Kun bekendtgørelser af *samme* lov tæller. Det er ikke en formalitet: på en
    ændringslov peger `consolidated_by` på enhver bekendtgørelse, der har indarbejdet den,
    og de er bekendtgørelser af helt andre love. Uden navnekontrollen ville et opslag på
    en ændringslov ende i en tilfældig anden lov.

    `fetch_metadata` har ingen diskcache, så en ny udgave opdages med det samme.

    Returnerer (nyeste sti, mellemliggende skridt). Er stien allerede den nyeste, er
    listen tom. Fejler et opslag undervejs, returneres det, vi nåede — et netværkssvigt
    må ikke forhindre opslaget, kun gøre det mindre aktuelt.
    """
    current = document_path.strip("/")
    steps: list[str] = []
    for _ in range(max_steps):
        try:
            metadata = fetch_metadata(current)
        except FetchError:
            return (current, steps)
        wanted_name = law_name_of(metadata)
        newer: list[str] = []
        for uri in metadata["consolidated_by"]:
            path = document_path_of(str(uri))
            if path in steps or path == current:
                continue
            try:
                other = fetch_metadata(path)
            except FetchError:
                continue
            if law_name_of(other) == wanted_name:
                newer.append(path)
        if not newer:
            return (current, steps)
        current = newer[-1]
        steps.append(current)
    return (current, steps)


def amending_documents(eli_uri: str) -> list[str]:
    """Alle dokumentstier, der har ændret loven: konsoliderede og senere ændringer.

    De to mængder er ikke disjunkte. En ændringslov kan optræde begge steder ved
    delvis ikrafttræden, hvor dele er konsolideret og andre endnu ikke er trådt i
    kraft, så vi fjerner dubletter med bevaret rækkefølge.
    """
    metadata = fetch_metadata(eli_uri)
    consolidates = metadata["consolidates"]
    changed_by = metadata["changed_by"]
    assert isinstance(consolidates, list) and isinstance(changed_by, list)
    paths = [document_path_of(str(uri)) for uri in list(consolidates) + list(changed_by)]
    return list(dict.fromkeys(paths))
