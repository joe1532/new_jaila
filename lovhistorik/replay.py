"""Afspilning af ændringsoperationer på lovtekst.

Formålet er ét tal: hvor stor en andel af ændringsinstrukserne kan vi udføre, så
resultatet ordret svarer til den næste lovbekendtgørelse. Alt andet i motoren
hviler på det tal, for kan vi ikke genskabe teksten, ved vi heller ikke, hvilken
ændringslov et givet tekststykke stammer fra.

Modulet gætter aldrig. Kan en operation ikke stedfæstes entydigt, får den status
`failed` med en begrundelse, og teksten røres ikke. En stille halv-anvendelse ville
give en forkert provenienskæde, som ingen ville opdage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import lex_dania

# Lovtekst citerer med danske dobbelte anførselstegn, ikke ASCII.
QUOTE = r"»(.*?)«"

REPLACE_TEXT = re.compile(
    r"ændres\s+(?:(?P<count>\w+)\s+steder\s+)?" + QUOTE + r"\s*til:\s*" + QUOTE,
    re.IGNORECASE,
)
# "To steder i § X, stk. Y, ændres »A« til: »B«" sætter kvalifikatoren først i
# instruksen, men efter punktnummeret ("11. To steder i …"), så vi kan ikke forankre
# søgningen til strengens begyndelse.
LEADING_COUNT = re.compile(r"\b(?P<count>\w+)\s+steder\s+i\b", re.IGNORECASE)
INSERT_PHRASE = re.compile(
    r"indsættes\s+efter\s+" + QUOTE + r":\s*" + QUOTE,
    re.IGNORECASE,
)
# Begge ordstillinger forekommer: "»X« udgår" og "I § Y, stk. Z, udgår »X«".
DELETE_PHRASE = re.compile(QUOTE + r"\s*,?\s*udgår|udgår\s*:?\s*" + QUOTE, re.IGNORECASE)
INSERT_SENTENCE = re.compile(
    r"indsættes\s+som\s+(?P<first>\d+)\.(?:\s*(?:og|-)\s*(?P<last>\d+)\.)?\s*pkt",
    re.IGNORECASE,
)
RECAST = re.compile(r"affattes\s+således", re.IGNORECASE)


@dataclass
class Operation:
    """Én udførbar ændring af ét stykke lovtekst."""

    document_path: str
    amendment_path: str
    op_type: str  # replace_text | insert_phrase | delete_phrase | insert_sentence | recast
    target: lex_dania.Target
    old_text: str = ""
    new_text: str = ""
    occurrence_count: int | None = None
    status: str = "parsed"  # parsed | unsupported
    note: str = ""

    @property
    def where(self) -> str:
        return f"{self.document_path} {self.amendment_path} ({self.target.label})"


def parse_operations(instruction: lex_dania.Instruction) -> list[Operation]:
    """Omsæt ét nummereret ændringspunkt til udførbare operationer.

    Første udgave håndterer punkter med præcis ét mål. Punkter med flere mål kræver,
    at hvert verbum knyttes til sit eget mål, og det er en selvstændig opgave; de
    markeres `unsupported`, så de tæller med i nævneren og ikke forsvinder.
    """
    targets = instruction.probable_targets
    base = Operation(
        document_path=instruction.document_path,
        amendment_path=instruction.amendment_path,
        op_type="",
        target=lex_dania.parse_target(targets[0] if targets else ""),
    )

    if not targets:
        base.status = "unsupported"
        base.note = "intet opmærket mål"
        return [base]
    if len(instruction.targets) > 1:
        base.status = "unsupported"
        base.note = "flere mål i samme punkt"
        return [base]
    if not base.target.is_resolvable:
        base.status = "unsupported"
        base.note = f"målet kunne ikke læses: {targets[0]!r}"
        return [base]

    text = instruction.text

    replace = REPLACE_TEXT.search(text)
    if replace:
        count_word = replace.group("count")
        leading = LEADING_COUNT.search(text)
        if not count_word and leading:
            count_word = leading.group("count")
        base.op_type = "replace_text"
        base.old_text = replace.group(2)
        base.new_text = replace.group(3)
        base.occurrence_count = lex_dania.OCCURRENCE_WORDS.get((count_word or "").lower())
        if count_word and base.occurrence_count is None:
            base.status = "unsupported"
            base.note = f"ukendt antal forekomster: {count_word!r}"
        return [base]

    insert_phrase = INSERT_PHRASE.search(text)
    if insert_phrase:
        base.op_type = "insert_phrase"
        base.old_text = insert_phrase.group(1)
        base.new_text = insert_phrase.group(2)
        return [base]

    insert_sentence = INSERT_SENTENCE.search(text)
    if insert_sentence:
        base.op_type = "insert_sentence"
        base.new_text = instruction.new_text
        base.occurrence_count = int(insert_sentence.group("first"))
        if not base.new_text:
            base.status = "unsupported"
            base.note = "ingen ny tekst i AendringNyTekst"
        return [base]

    delete = DELETE_PHRASE.search(text)
    if delete:
        base.op_type = "delete_phrase"
        # Kun én af de to grupper er udfyldt, afhængigt af ordstillingen.
        base.old_text = delete.group(1) or delete.group(2) or ""
        return [base]

    if RECAST.search(text):
        base.op_type = "recast"
        base.new_text = instruction.new_text
        if not base.new_text:
            base.status = "unsupported"
            base.note = "ingen ny tekst i AendringNyTekst"
        return [base]

    base.status = "unsupported"
    base.note = f"konstruktion ikke understøttet: {', '.join(instruction.constructions)}"
    return [base]


@dataclass
class ApplicationResult:
    operation: Operation
    status: str  # applied | already_applied | failed
    note: str = ""


def normalise(text: str) -> str:
    """Sammenlignelig form. Kun whitespace røres — aldrig ordlyd."""
    return re.sub(r"\s+", " ", text).strip()


def tidy(text: str) -> str:
    """Ryd op i mellemrum, en tekstændring kan have efterladt.

    Fjerner man en frase midt i en opremsning, bliver der let to mellemrum tilbage
    eller et mellemrum foran et komma. Kun mellemrum røres, aldrig ordlyd.
    """
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text.strip()


# Tegn, en indsat frase kan begynde med, uden at der skal mellemrum foran.
PUNCTUATION_START = ",.;:)!?"


def join_after(anchor: str, addition: str) -> str:
    """Sæt en indsat frase efter sit anker med det mellemrum, der mangler i citatet.

    Ændringslove citerer anker og ny tekst hver for sig uden det mellemrum, der
    adskiller dem i den trykte lov: efter »lov om social service« indsættes
    »eller barnets lov«. Antagelsen er, at der skal et mellemrum imellem, medmindre
    den nye tekst begynder med tegnsætning. Det holder for de tilfælde, vi har målt,
    men er en heuristik og kan tage fejl ved indsættelse midt i et ord.
    """
    if not addition or not anchor:
        return f"{anchor}{addition}"
    if anchor.endswith(" ") or addition.startswith(" "):
        return f"{anchor}{addition}"
    if addition[0] in PUNCTUATION_START:
        return f"{anchor}{addition}"
    return f"{anchor} {addition}"


class TextState:
    """Lovens stykker under afspilning, som punktummer der kan ændres.

    Nøglen er (paragraf-localId, stykkenummer). Punktummer holdes som en liste, så
    en instruks om "3. pkt." kan slås op på plads uden at skulle regne offsets ud.
    """

    def __init__(self, provisions: list[lex_dania.Provision]) -> None:
        self.sentences: dict[tuple[str, int, int | None], list[str]] = {
            provision.key: list(provision.sentences) for provision in provisions
        }

    def text_of(self, key: tuple[str, int, int | None]) -> str:
        return normalise(" ".join(self.sentences.get(key, [])))

    def resolve(self, target: lex_dania.Target) -> tuple[tuple[str, int, int | None] | None, str]:
        """Find den enhed, en operation skal ændre.

        Peger målet på et nummer, er enheden entydig. Peger det kun på et stykke,
        som har numre, er det tvetydigt: teksten kan stå i flere af numrene, og et
        punktumnummer betyder noget forskelligt i hvert af dem. Vi vælger stykkets
        egen indledning, hvis den har indhold, og fejler ellers frem for at gætte.
        """
        if target.key in self.sentences and (target.nr_number or self.sentences[target.key]):
            return target.key, ""

        paragraph, stk, _ = target.key
        siblings = [key for key in self.sentences if key[0] == paragraph and key[1] == stk]
        if not siblings:
            return None, "stykket findes ikke i teksten"
        if target.nr_number:
            return None, f"nr. {target.nr_number} findes ikke i stykket"

        numbered = [key for key in siblings if key[2] is not None]
        if numbered:
            return None, "stykket har numre, men målet angiver ikke hvilket"
        return None, "stykket er tomt"

    def apply(self, operation: Operation) -> ApplicationResult:
        if operation.status != "parsed":
            return ApplicationResult(operation, "failed", operation.note)

        key, problem = self.resolve(operation.target)
        if key is None:
            return ApplicationResult(operation, "failed", problem)
        sentences = self.sentences[key]

        handlers = {
            "replace_text": self._replace_text,
            "insert_phrase": self._insert_phrase,
            "delete_phrase": self._delete_phrase,
            "insert_sentence": self._insert_sentence,
            "recast": self._recast,
        }
        handler = handlers.get(operation.op_type)
        if handler is None:
            return ApplicationResult(operation, "failed", f"ukendt type {operation.op_type!r}")
        return handler(operation, key, sentences)

    def _scope(self, operation: Operation, sentences: list[str]) -> list[int]:
        """Hvilke punktummer må operationen røre? Tom målangivelse betyder hele stykket."""
        numbers = operation.target.sentence_numbers
        if not numbers:
            return list(range(len(sentences)))
        return [number - 1 for number in numbers if 1 <= number <= len(sentences)]

    def _substitute(
        self,
        operation: Operation,
        sentences: list[str],
        needle: str,
        replacement: str,
    ) -> ApplicationResult:
        indexes = self._scope(operation, sentences)
        if not indexes:
            return ApplicationResult(operation, "failed", "punktummet findes ikke i stykket")

        found = sum(sentences[index].count(needle) for index in indexes)
        # Rammer instruksen flere punktummer ("1. og 2. pkt."), forventes frasen én
        # gang i hvert af dem, medmindre instruksen selv angiver et antal.
        expected = operation.occurrence_count or max(1, len(operation.target.sentence_numbers))

        if found == 0:
            # Står ændringen allerede i teksten, er den formentlig konsolideret ind.
            if replacement and any(replacement in sentences[index] for index in indexes):
                return ApplicationResult(operation, "already_applied", "resultatet står allerede")
            return ApplicationResult(operation, "failed", f"fandt ikke {needle!r}")
        if found != expected:
            return ApplicationResult(
                operation, "failed", f"forventede {expected} forekomster, fandt {found}"
            )

        for index in indexes:
            sentences[index] = tidy(sentences[index].replace(needle, replacement))
        return ApplicationResult(operation, "applied")

    def _replace_text(
        self, operation: Operation, key: tuple[str, int, int | None], sentences: list[str]
    ) -> ApplicationResult:
        return self._substitute(operation, sentences, operation.old_text, operation.new_text)

    def _insert_phrase(
        self, operation: Operation, key: tuple[str, int, int | None], sentences: list[str]
    ) -> ApplicationResult:
        anchor = operation.old_text
        return self._substitute(
            operation, sentences, anchor, join_after(anchor, operation.new_text)
        )

    def _delete_phrase(
        self, operation: Operation, key: tuple[str, int, int | None], sentences: list[str]
    ) -> ApplicationResult:
        return self._substitute(operation, sentences, operation.old_text, "")

    def _insert_sentence(
        self, operation: Operation, key: tuple[str, int, int | None], sentences: list[str]
    ) -> ApplicationResult:
        position = operation.occurrence_count or (len(sentences) + 1)
        new_sentences = lex_dania.split_sentences(operation.new_text)
        if not new_sentences:
            return ApplicationResult(operation, "failed", "tom ny tekst")

        if any(normalise(new_sentences[0]) in normalise(item) for item in sentences):
            return ApplicationResult(operation, "already_applied", "punktummet står allerede")
        if position != len(sentences) + 1:
            return ApplicationResult(
                operation,
                "failed",
                f"vil indsætte som {position}. pkt., men stykket har {len(sentences)}",
            )

        sentences.extend(new_sentences)
        return ApplicationResult(operation, "applied")

    def _recast(
        self, operation: Operation, key: tuple[str, int, int | None], sentences: list[str]
    ) -> ApplicationResult:
        new_sentences = lex_dania.split_sentences(operation.new_text)
        if not new_sentences:
            return ApplicationResult(operation, "failed", "tom ny tekst")
        # Den nye tekst indledes med sin egen etiket, som ikke er en del af
        # lovteksten i vores model. Genaffattes hele paragraffen, er etiketten
        # paragrafnummeret ("§ 5 D."); genaffattes et stykke, er den "Stk. 4.".
        # Punktummet er en del af etiketten ("§ 5 D." og "Stk. 4."). Det kræves
        # eksplicit, for uden det ville "§ 5 Den skattepligtige …" få sit "D" ædt.
        new_sentences[0] = re.sub(
            r"^(?:§\s*\d+\s*(?:[A-ZÆØÅ]\s*)?\.\s*|Stk\.\s*\d+\.\s*)+", "", new_sentences[0]
        )
        self.sentences[key] = new_sentences
        return ApplicationResult(operation, "applied")


def classify_difference(ours: str, theirs: str) -> str:
    """Sæt navn på, hvordan to tekster afviger, så mønstre kan tælles frem for læses.

    Klasserne er valgt, så de peger på hver sin årsag: mellemrum kommer af oprydning
    efter en tekstændring, manglende eller overskydende tekst til sidst kommer af
    punktummer, der ikke blev indsat eller fjernet, og helt forskellig tekst kommer
    typisk af, at stykker er forskudt af en indsættelse eller ophævelse.
    """
    if ours == theirs:
        return "ens"
    if re.sub(r"\s", "", ours) == re.sub(r"\s", "", theirs):
        return "kun mellemrum"
    if theirs.startswith(ours):
        return "vi mangler tekst til sidst"
    if ours.startswith(theirs):
        return "vi har for meget til sidst"
    if theirs in ours:
        return "vi har tekst udenom facit"
    if ours in theirs:
        return "facit har tekst udenom vores"

    shared = 0
    while shared < min(len(ours), len(theirs)) and ours[shared] == theirs[shared]:
        shared += 1
    if shared < 20:
        return "helt forskellig tekst"
    return "forskel midt i teksten"


@dataclass
class ReplayReport:
    results: list[ApplicationResult] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for result in self.results if result.status == status)

    @property
    def total(self) -> int:
        return len(self.results)


AMENDMENT_PARAGRAPH = re.compile(r"§\s*(\d+)")


def replay(
    state: TextState,
    amendments: list[lex_dania.ConsolidatedAmendment],
    law_name: str,
) -> ReplayReport:
    """Anvend ændringslovenes operationer på teksten, i den givne rækkefølge.

    Hver post angiver både ændringsloven og den paragraf i den, der skal afspilles.
    Afgrænsningen til paragraffen er nødvendig: en lov kan ændre samme lov flere
    steder med hver sin ikrafttræden, og kun nogle af dem er konsolideret ind.
    """
    report = ReplayReport(documents=[item.document_path for item in amendments])
    for amendment in amendments:
        document = amendment.document_path
        try:
            xml = lex_dania.fetch_document_xml(document)
            instructions = lex_dania.extract_instructions(xml, document, law_name)
        except Exception as error:  # noqa: BLE001 - netværk og XML fejler på mange måder
            report.results.append(
                ApplicationResult(
                    Operation(document, "-", "", lex_dania.Target(raw="")),
                    "failed",
                    f"kunne ikke hente eller parse: {error}",
                )
            )
            continue

        for instruction in instructions:
            if amendment.paragraph:
                match = AMENDMENT_PARAGRAPH.search(instruction.amendment_path)
                if match and int(match.group(1)) != amendment.paragraph:
                    continue
            for operation in parse_operations(instruction):
                report.results.append(state.apply(operation))
    return report


def compare(state: TextState, expected: list[lex_dania.Provision]) -> tuple[int, int, list[str]]:
    """Sammenlign afspillet tekst med facit. Returnerer (ens, forskellige, eksempler)."""
    same = 0
    different: list[str] = []
    for provision in expected:
        ours = state.text_of(provision.key)
        theirs = normalise(provision.text)
        if not ours:
            continue
        if ours == theirs:
            same += 1
        else:
            different.append(provision.label)
    return same, len(different), different
