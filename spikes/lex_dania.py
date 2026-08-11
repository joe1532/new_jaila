"""Udtræk af ændringsinstrukser fra Retsinformations Lex Dania-XML.

Dette modul er den ene implementering af hentning, udtræk og klassifikation.
Både proben (`retsinfo_probe.py mine`) og inspektionsappen (`lovhistorik_app.py`)
bruger det, så de aldrig kan komme til at måle to forskellige ting.

Modulet klassificerer kun. Det anvender ikke operationerne på lovteksten, og en
klassificeret instruks er derfor ikke det samme som en instruks, vi kan udføre.

TLS: udviklingsmaskinen har TLS-inspektion, så Pythons certifi-bundle afvises. Vi
bruger truststore, der validerer mod OS'ets eget trust store. På en Linux-server
uden inspektion er det ikke nødvendigt.
"""

from __future__ import annotations

import json
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
MAX_BYTES = 8_000_000

CACHE_DIRECTORY = pathlib.Path(__file__).with_name(".cache")

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
    """Netværks-, TLS- eller HTTP-fejl ved hentning fra Retsinformation."""


def fetch(url: str, accept: str | None = None) -> tuple[bytes, str]:
    """Hent en URL. Returnerer (indhold, content-type) eller kaster FetchError."""
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=CONTEXT) as response:
            return response.read(MAX_BYTES), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as http_error:
        raise FetchError(f"HTTP {http_error.code} for {url}") from http_error
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
        return cache_file.read_bytes()

    CACHE_DIRECTORY.mkdir(exist_ok=True)
    time.sleep(DELAY_SECONDS)
    body, _ = fetch(f"https://retsinformation.dk/{document_path}/dan/xml")
    if not body:
        raise FetchError(f"Tomt svar for {document_path}")
    cache_file.write_bytes(body)
    return body


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


def element_text(element: ElementTree.Element) -> str:
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


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
