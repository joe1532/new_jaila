"""Generisk parsing af entydige danske lov- og paragrafhenvisninger."""

from __future__ import annotations

import re
from dataclasses import dataclass


# Domæneordbog fra Skatteforvaltningens forkortelsesliste. Den indeholder kun
# retskilder (love, kodekser og bekendtgørelser) – ikke institutioner,
# selskabsformer, paragrafnumre eller konkrete afgørelser.
LAW_ABBREVIATIONS = {
    "abl": "aktieavancebeskatningsloven",
    "askl": "aktiesparekontoloven",
    "absal": "arbejdsskadeafgiftsloven",
    "admbil": "administrativ bistandsloven",
    "affal": "affalds- og råstofafgiftsloven",
    "al": "afskrivningsloven",
    "ambitbl": "ambi-tilbagebetalingsloven",
    "ambl": "arbejdsmarkedsbidragsloven",
    "amfl": "arbejdsmarkedsfondsloven",
    "ansal": "ansvarsforsikringsafgiftsloven",
    "apsl": "anpartsselskabsloven",
    "asl": "aktieselskabsloven",
    "atpl": "atp-loven",
    "aal": "arveafgiftsloven",
    "bal": "boafgiftsloven",
    "batal": "batteriafgiftsloven",
    "bbrl": "bbr-loven",
    "bekæmpal": "bekæmpelsesmiddelafgiftsloven",
    "betfrul": "betalingsfristudskydelsesloven",
    "brændal": "brændstofforbrugsafgiftsloven",
    "bøungl": "børne- og ungeydelsesloven",
    "cfcal": "cfc-afgiftsloven",
    "choal": "chokoladeafgiftsloven",
    "co2al": "co2-afgiftsloven",
    "dfo": "kommissionens delegerede forordning om overgangsordninger",
    "dbf": "databeskyttelsesforordningen",
    "dbl": "databeskyttelsesloven",
    "dbsl": "dødsboskatteloven",
    "df": "kommissionens delegerede forordning",
    "dl": "danske lov",
    "dsl": "dødsboskifteloven",
    "ebl": "ejendomsavancebeskatningsloven",
    "efl": "erhvervsfondsloven",
    "eftgl": "eftergivelsesloven",
    "ef-vgl": "ef-voldgiftskonventionsloven",
    "elal": "elafgiftsloven",
    "elbl": "ejerlejlighedsbeskatningsloven",
    "emal": "emissionsafgiftsloven",
    "embal": "emballageafgiftsloven",
    "esl": "ejendomsskatteloven",
    "etbl": "etableringskontoloven",
    "eutk": "eu-toldkodeksen",
    "evl": "ejendomsvurderingsloven",
    "evsl": "ejendomsværdiskatteloven",
    "fal": "forsikringsaftaleloven",
    "fbl": "fondsbeskatningsloven",
    "fedtal": "fedtafgiftsloven",
    "fl": "fondsloven",
    "flyal": "flyrejseafgiftsloven",
    "forbral": "forbrugsafgiftsloven",
    "forsvbil": "forsvarerbistandsloven",
    "foræl": "forældelsesloven",
    "fosal": "foderfosfatafgiftsloven",
    "fremtbl": "fremskyndet tilbagebetalingsloven",
    "ful": "fusionsskatteloven",
    "fvl": "forvaltningsloven",
    "fæl": "færdselsloven",
    "gasal": "gasafgiftsloven",
    "gb": "gennemførelsesbestemmelserne til ef-toldkodeksen",
    "gbl": "gældsbrevsloven",
    "genbil": "gensidig bistandsloven",
    "geval": "gevinstafgiftsloven",
    "gf": "kommissionens gennemførelsesforordning",
    "glån": "grundskyldslåneloven",
    "kelån": "lov om lån til betaling af kommunale ejendomsbidrag",
    "husdyl": "husdyrbeskatningsloven",
    "ibl": "international bistandsloven",
    "ifl": "investeringsfondsloven",
    "ivfl": "investorfradragsloven",
    "indbil": "inddrivelsesbistandsloven",
    "ikr": "indkomstregisterloven",
    "indog": "gældsinddrivelsesloven",
    "invl": "investeringsforeningsloven",
    "isal": "isafgiftsloven",
    "itl": "indtægtsloftsloven",
    "kal": "lov om kreditaftaler",
    "kasinoal": "kasinoafgiftsloven",
    "kesl": "kommunal ejendomsskattelov",
    "kgl": "kursgevinstloven",
    "kl": "konkursloven",
    "klasl": "klasselotteriloven",
    "kloral": "klorerede opløsningsmiddellov",
    "kn": "kombinerede nomenklatur",
    "kompl": "kompensationsloven",
    "kosl": "kommuneskatteloven",
    "kksl": "konkursskatteloven",
    "ksl": "kildeskatteloven",
    "kulal": "kulafgiftsloven",
    "kulbopkl": "kulbrinteopkrævningsloven",
    "kulbrl": "kulbrinteskatteloven",
    "kvælal": "kvælstofafgiftsloven",
    "kvæloxal": "kvælstofoxiderafgiftsloven",
    "køregl": "køretøjsregistreringsloven",
    "lal": "lønsumsafgiftsloven",
    "lbl": "lastbiltilskudsloven",
    "ll": "ligningsloven",
    "lodfbl": "lodseddelforbudsloven",
    "lotal": "lotterigevinstafgiftsloven",
    "lystfal": "lystfartøjsforsikringsafgiftsloven",
    "løindregl": "lønindeholdelsesregisterloven",
    "mbl": "minimumsbeskatningsloven",
    "minal": "mineralolieafgiftsloven",
    "minval": "mineralvandsafgiftsloven",
    "ml": "momsloven",
    "moal": "motoransvarsforsikringsafgiftsloven",
    "napoli-ii-kl": "napoli ii-konventionsloven",
    "narkopkl": "narkotikaprækursorerloven",
    "noxal": "nox-afgiftsloven",
    "ofl": "offentlighedsloven",
    "oil": "opkrævnings- og inddrivelsesloven",
    "opal": "opløsningsmiddelafgiftsloven",
    "opkl": "opkrævningsloven",
    "pal": "pensionsafkastbeskatningsloven",
    "pbl": "pensionsbeskatningsloven",
    "pdl": "persondataloven",
    "pasal": "lov om passagerafgift på flyrejser",
    "pokl": "pokerloven",
    "psl": "personskatteloven",
    "pvcal": "pvc-afgiftsloven",
    "ral": "realrenteafgiftsloven",
    "regal": "registreringsafgiftsloven",
    "rekl": "reklameafgiftsloven",
    "rfl": "renteforsikringsloven",
    "rl": "renteloven",
    "rpl": "retsplejeloven",
    "rsl": "retssikkerhedsloven",
    "sbl": "solidaritetsbidragsloven",
    "sel": "selskabsskatteloven",
    "seniorl": "seniornedslagsloven",
    "sfl": "skatteforvaltningsloven",
    "sil": "skatteindberetningsloven",
    "skadl": "skadesforsikringsafgiftsloven",
    "skindl": "skatteinddrivelsesloven",
    "skl": "skattekontrolloven",
    "sl": "statsskatteloven",
    "sll": "selskabsloven",
    "sksl": "skattestraffesagsloven",
    "spilal": "spilleafgiftsloven",
    "spilaul": "spilleautomatloven",
    "spildal": "spildevandsafgiftsloven",
    "spilgrøl": "spillelov grønland",
    "spill": "spilleloven",
    "sprital": "spiritusafgiftsloven",
    "ssl": "skattestyrelsesloven",
    "stempal": "stempelafgiftsloven",
    "stlånl": "studielånsloven",
    "strafnedsl": "strafnedsættelsesloven",
    "strfl": "straffeloven",
    "svovlal": "svovlafgiftsloven",
    "søbl": "sømandsbeskatningslov",
    "tal": "tinglysningsafgiftsloven",
    "tdl": "toldloven",
    "tiplotl": "tips- og lottoloven",
    "tk": "ef-toldkodeksen",
    "tl": "tinglysningsloven",
    "toal": "totalisatorafgiftsloven",
    "tobakal": "tobaksafgiftsloven",
    "tsl": "tonnageskatteloven",
    "tspilal": "totalisatorspilafgiftsloven",
    "vandal": "vandafgiftsloven",
    "veal": "vejafgiftsloven",
    "vejal": "vejbenyttelsesafgiftsloven",
    "virkregl": "virksomhedsregisterloven",
    "vll": "varelagerloven",
    "vol": "virksomhedsomdannelsesloven",
    "vsl": "virksomhedsskatteloven",
    "vul": "vurderingsloven",
    "vægtal": "vægtafgiftsloven",
    "vækstal": "vækstfremmerafgiftsloven",
    "ølvinal": "øl- og vinafgiftsloven",
    "1908-lov": "forældelsesloven af 1908",
    # Bekendtgørelser fra samme officielle forkortelsesliste.
    "kslbek": "kildeskattebekendtgørelsen",
    "sib": "skatteindberetningsbekendtgørelsen",
    "tbek": "toldbekendtgørelsen",
}

def _definite_law_name(value: str) -> str:
    law = re.sub(r"\s+", " ", value.casefold().strip())
    if law.endswith("lovens"):
        return law[:-1]
    if law.endswith("loven"):
        return law
    if law.endswith("lov") and not law.endswith(" lov"):
        return law + "en"
    return law


def _title_forms(value: str) -> set[str]:
    title = re.sub(r"\s+", " ", value.casefold().strip())
    canonical = _definite_law_name(title)
    forms = {title, canonical}
    if canonical.endswith("loven"):
        forms.update((canonical + "s", canonical[:-2]))
    elif canonical.endswith("loven om"):
        forms.add(canonical + "s")
    elif canonical.startswith("lov om "):
        rest = canonical[7:]
        forms.update((f"loven om {rest}", f"lovens om {rest}"))
    elif canonical.endswith("bekendtgørelsen"):
        forms.update((canonical + "s", canonical[:-2]))
    else:
        forms.add(canonical + "s")
    return {form for form in forms if form}


_CANONICAL_BY_KEY = {
    key: _definite_law_name(title) for key, title in LAW_ABBREVIATIONS.items()
}
_TITLE_ALIASES: dict[str, tuple[str, str]] = {}
for _key, _title in LAW_ABBREVIATIONS.items():
    for _alias in _title_forms(_title):
        _TITLE_ALIASES.setdefault(_alias, (_key, _CANONICAL_BY_KEY[_key]))

_ABBREVIATIONS = "|".join(sorted(map(re.escape, LAW_ABBREVIATIONS), key=len, reverse=True))
_TITLES = "|".join(
    sorted(
        (re.escape(value).replace(r"\ ", r"\s+") for value in _TITLE_ALIASES),
        key=len,
        reverse=True,
    )
)
_SECTION = r"(?P<section_number>\d+)\s*(?P<section_suffix>[A-Za-zÆØÅæøå]?(?![A-Za-zÆØÅæøå]))"
_REFERENCE_TAIL = (
    rf"{_SECTION}"
    r"(?:\s*(?:-|–|—|til|og)\s*§*\s*(?P<end_number>\d+)\s*"
    r"(?P<end_suffix>[A-Za-zÆØÅæøå]?(?![A-Za-zÆØÅæøå])))?"
    r"(?:\s*,?\s*stk\.?\s*(?P<subsection>\d+[A-Za-zÆØÅæøå]?))?"
    r"(?:\s*,?\s*nr\.?\s*(?P<item_number>\d+[A-Za-zÆØÅæøå]?))?"
    r"(?:\s*,?\s*litra\s*(?P<letter>[A-Za-zÆØÅæøå]))?"
)
_ABBREVIATION_RE = re.compile(
    rf"\b(?P<law>{_ABBREVIATIONS})\s*(?:§{{1,2}}\s*)?{_REFERENCE_TAIL}",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(
    rf"(?<![\w-])(?P<law>{_TITLES})\s*§{{1,2}}\s*{_REFERENCE_TAIL}",
    re.IGNORECASE,
)
_FULL_LAW_RE = re.compile(
    rf"\b(?P<law>[A-Za-zÆØÅæøå-]{{4,}}lov(?:en|ens)?)\s*§{{1,2}}\s*{_REFERENCE_TAIL}",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LawReference:
    canonical_law: str
    section: str
    law_key: str
    section_number: int
    section_suffix: str | None = None
    section_end: str | None = None
    section_end_number: int | None = None
    section_end_suffix: str | None = None
    subsection: str | None = None
    item_number: str | None = None
    letter: str | None = None
    start_offset: int = 0
    end_offset: int = 0


def _law_identity(value: str) -> tuple[str, str]:
    law = re.sub(r"\s+", " ", value.casefold().strip())
    if law in LAW_ABBREVIATIONS:
        return law, _CANONICAL_BY_KEY[law]
    known = _TITLE_ALIASES.get(law)
    if known:
        return known
    canonical = _definite_law_name(law)
    return canonical, canonical


def _component(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", "", value).upper()


def _from_match(match: re.Match[str]) -> LawReference:
    law_key, canonical_law = _law_identity(match.group("law"))
    section_number = int(match.group("section_number"))
    section_suffix = _component(match.group("section_suffix"))
    end_raw = match.group("end_number")
    end_number = int(end_raw) if end_raw else None
    end_suffix = _component(match.group("end_suffix"))
    section = f"{section_number}{section_suffix or ''}"
    section_end = f"{end_number}{end_suffix or ''}" if end_number is not None else None
    return LawReference(
        canonical_law=canonical_law,
        section=section,
        law_key=law_key,
        section_number=section_number,
        section_suffix=section_suffix,
        section_end=section_end,
        section_end_number=end_number,
        section_end_suffix=end_suffix,
        subsection=_component(match.group("subsection")),
        item_number=_component(match.group("item_number")),
        letter=_component(match.group("letter")),
        start_offset=match.start(),
        end_offset=match.end(),
    )


def extract_law_references(query: str) -> tuple[LawReference, ...]:
    """Find alle entydige lovhenvisninger i tekst, i deres oprindelige rækkefølge."""
    source = str(query or "")
    matches = [
        match
        for pattern in (_ABBREVIATION_RE, _TITLE_RE, _FULL_LAW_RE)
        for match in pattern.finditer(source)
    ]
    selected: list[re.Match[str]] = []
    for match in sorted(matches, key=lambda item: (item.start(), -(item.end() - item.start()))):
        if any(match.start() < kept.end() and kept.start() < match.end() for kept in selected):
            continue
        selected.append(match)
    references = [_from_match(match) for match in sorted(selected, key=lambda item: item.start())]
    return tuple(dict.fromkeys(references))


def extract_law_reference(query: str) -> LawReference | None:
    """Bagudkompatibel adgang til den første entydige lovhenvisning."""
    references = extract_law_references(query)
    return references[0] if references else None


def reference_match_mode(query: str, references: tuple[LawReference, ...] | None = None) -> str:
    """Returnér ``any`` ved 'eller' mellem referencer; ellers ``all``."""
    refs = references if references is not None else extract_law_references(query)
    if len(refs) < 2:
        return "all"
    source = str(query or "").casefold()
    between = source[refs[0].end_offset : refs[-1].start_offset]
    return "any" if re.search(r"\beller\b", between) else "all"


def structured_reference_payload(query: str) -> tuple[list[dict[str, object]], int]:
    """Serialisér alle query-referencer til den strukturerede SQL-søgning."""
    references = extract_law_references(query)
    payload = [
        {
            "ordinal": index,
            "law_key": ref.law_key,
            "section_number": ref.section_number,
            "section_suffix": ref.section_suffix or "",
            "section_end_number": ref.section_end_number,
            "section_end_suffix": ref.section_end_suffix or "",
            "subsection": ref.subsection,
            "item_number": ref.item_number,
            "letter": ref.letter,
        }
        for index, ref in enumerate(references, start=1)
    ]
    required = 1 if reference_match_mode(query, references) == "any" else len(payload)
    return payload, required


def normalized_reference_columns(value: str) -> tuple[object, ...]:
    """Kolonneværdier til document_references; tvetydig tekst giver kun NULL'er."""
    reference = extract_law_reference(value)
    if reference is None:
        return (None,) * 8
    return (
        reference.law_key,
        reference.section_number,
        reference.section_suffix,
        reference.section_end_number,
        reference.section_end_suffix,
        reference.subsection,
        reference.item_number,
        reference.letter,
    )


def law_reference_variants(query: str) -> tuple[str, ...]:
    """Bagudkompatible tekstvarianter; ny søgning bruger de strukturerede felter."""
    reference = extract_law_reference(query)
    if reference is None:
        return ()
    number = str(reference.section_number)
    suffix = reference.section_suffix or ""
    section_forms = (f"{number}{suffix}", f"{number} {suffix}") if suffix else (number,)
    prefixes = set(_title_forms(reference.canonical_law))
    prefixes.update(
        abbreviation
        for abbreviation, canonical in _CANONICAL_BY_KEY.items()
        if canonical == reference.canonical_law
    )
    prefixes.update(prefix.upper() for prefix in tuple(prefixes) if prefix in LAW_ABBREVIATIONS)
    prefixes.update(prefix.capitalize() for prefix in tuple(prefixes))
    variants: list[str] = []
    for prefix in sorted(prefixes):
        for section_form in section_forms:
            bases = (
                f"{prefix} § {section_form}",
                f"{prefix} §{section_form}",
                f"{prefix}§ {section_form}",
                f"{prefix}§{section_form}",
            )
            variants.extend(bases)
            if reference.subsection:
                tail = f", stk. {reference.subsection}"
                if reference.item_number:
                    tail += f", nr. {reference.item_number}"
                if reference.letter:
                    tail += f", litra {reference.letter.casefold()}"
                variants.extend(base + tail for base in bases)
    variants.extend(f"{value}," for value in tuple(variants))
    return tuple(dict.fromkeys(variants))


def is_bare_law_reference(query: str) -> bool:
    """Sand når hele forespørgslen kun er én entydig lovhenvisning."""
    source = str(query or "").strip().rstrip("?.").strip()
    references = extract_law_references(source)
    return bool(
        len(references) == 1
        and references[0].start_offset == 0
        and references[0].end_offset == len(source)
    )
