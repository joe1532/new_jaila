"""Engangs-probe mod Retsinformation.

Formål: besvare de empiriske spørgsmål i DATAMODEL.md, før der bygges databaselag.
Scriptet henter et lille antal URL'er og rapporterer, hvad der faktisk kommer tilbage.

Det meste af denne kode skal smides væk; den er udforskning, ikke motor. Undtagelsen
er `mine`, som tæller på testmængden og henter sit udtræk fra lex_dania.py.

Kør med:  python lovhistorik/probe.py <kommando> [argumenter]

TLS: maskinen har TLS-inspektion, så Pythons certifi-bundle afvises. Vi bruger
truststore, der validerer via Windows' eget trust store. På en Linux-server uden
inspektion er det ikke nødvendigt.
"""

from __future__ import annotations

import difflib
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

# Windows-konsollen kører cp1252 og kan ikke skrive BOM og andre tegn fra XML'en.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

USER_AGENT = "JAILA-lovhistorik-probe/0.1 (teknisk afklaring)"
TIMEOUT_SECONDS = 30

# Vi kender ikke Retsinformations rate limits. Gå langsomt.
DELAY_SECONDS = 1.0

# Læs aldrig mere end dette i én probe. Sitemaps og JS-bundter kan være store.
MAX_BYTES = 8_000_000


def build_context() -> ssl.SSLContext:
    """Brug OS'ets trust store, hvis truststore er installeret."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        print("ADVARSEL: truststore mangler. Kører med standard-trust, som fejler")
        print("          på denne maskine. Kør: pip install truststore")
        return ssl.create_default_context()


CONTEXT = build_context()


def fetch(url: str, accept: str | None = None) -> tuple[int | None, str, bytes, str]:
    """Hent en URL. Returnerer (status, content_type, krop, fejlbesked)."""
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=CONTEXT) as response:
            return (
                response.status,
                response.headers.get("Content-Type", ""),
                response.read(MAX_BYTES),
                "",
            )
    except urllib.error.HTTPError as error:
        # 404 er et brugbart svar: mønstret findes ikke.
        return error.code, "", b"", f"HTTPError: {error.reason}"
    except urllib.error.URLError as error:
        return None, "", b"", f"URLError: {error.reason}"
    except TimeoutError:
        return None, "", b"", "TimeoutError"


def show(label: str, url: str, accept: str | None = None, preview: int = 700) -> bytes:
    status, content_type, body, error = fetch(url, accept)
    print(f"=== {label}")
    print(f"    {url}")
    if error:
        print(f"    FEJL: {error}")
    else:
        print(f"    status {status}, type: {content_type}, {len(body)} bytes læst")
        text = body.decode("utf-8", errors="replace")
        print("    " + text[:preview].replace("\n", "\n    "))
    print()
    time.sleep(DELAY_SECONDS)
    return body


def step_sitemap() -> int:
    # 1. Sitemap. robots.txt peger paa denne.
    sitemap = show("Sitemap (fra robots.txt)", "https://retsinformation.dk/sitemap.xml")

    # Er det et sitemap-indeks eller en flad liste?
    text = sitemap.decode("utf-8", errors="replace")
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)
    is_index = "<sitemapindex" in text
    print(f"--- Sitemap er {'et INDEKS' if is_index else 'en flad URL-liste'}")
    print(f"--- {len(locs)} <loc>-poster i det læste udsnit")
    for loc in locs[:15]:
        print(f"    {loc}")
    print()

    # 2. Første sitemap-side: hvilket URI-format har dokumenterne?
    page = show(
        "Sitemap side 1",
        "https://retsinformation.dk/sitemap.xml?page=1",
        preview=400,
    )
    page_text = page.decode("utf-8", errors="replace")
    page_locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", page_text)
    print(f"--- {len(page_locs)} URL'er paa side 1 (afkortet ved {MAX_BYTES} bytes)")
    for loc in page_locs[:20]:
        print(f"    {loc}")
    print()

    # Hvilke stimoenstre optraeder? Fortaeller om ELI-URI'er bruges direkte.
    patterns: dict[str, int] = {}
    for loc in page_locs:
        path = loc.split("://", 1)[-1].split("/", 1)[-1]
        segments = path.split("/")
        # Erstat rene tal med {n}, saa moensteret traeder frem.
        shape = "/".join("{n}" if seg.isdigit() else seg for seg in segments[:3])
        patterns[shape] = patterns.get(shape, 0) + 1
    print("--- Stimoenstre paa side 1:")
    for shape, count in sorted(patterns.items(), key=lambda item: -item[1])[:15]:
        print(f"    {count:6d}  /{shape}")
    print()

    return 0


def strip_html(raw: bytes) -> str:
    """Meget grov HTML-til-tekst. Kun til at laese en dokumentationsside i konsollen."""
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def step_eli_about() -> int:
    """Retsinformations egen ELI-dokumentation. Sitemap side 1 afsloerede den."""
    status, content_type, body, error = fetch("https://www.retsinformation.dk/eli/about")
    print(f"=== /eli/about -> status {status}, type {content_type}, {len(body)} bytes")
    if error:
        print(f"    FEJL: {error}")
        return 1
    print(strip_html(body)[:6000])
    return 0


def step_sitemap_page(page: str) -> int:
    """En vilkaarlig sitemap-side: hvilket URI-format har dokumenterne?"""
    url = f"https://retsinformation.dk/sitemap.xml?page={page}"
    status, content_type, body, error = fetch(url)
    print(f"=== {url} -> status {status}, type {content_type}, {len(body)} bytes")
    if error:
        print(f"    FEJL: {error}")
        return 1

    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body.decode("utf-8", errors="replace"))
    print(f"--- {len(locs)} URL'er (afkortet ved {MAX_BYTES} bytes)")
    for loc in locs[:10]:
        print(f"    {loc}")

    patterns: dict[str, int] = {}
    for loc in locs:
        segments = loc.split("://", 1)[-1].split("/")[1:]
        shape = "/".join("{n}" if seg.isdigit() else seg for seg in segments[:3])
        patterns[shape] = patterns.get(shape, 0) + 1
    print("--- Stimoenstre:")
    for shape, count in sorted(patterns.items(), key=lambda item: -item[1])[:10]:
        print(f"    {count:6d}  /{shape}")
    return 0


def step_document(eli_path: str) -> int:
    """Kan metadata og indhold hentes maskinelt for en ELI-URI?

    Vi proever baade indholdsforhandling paa selve ELI-URI'en og et par
    sandsynlige API-stier, som SPA'en kunne bruge.
    """
    base = "https://www.retsinformation.dk"
    attempts: list[tuple[str, str, str | None]] = [
        ("ELI-URI, JSON-LD", f"{base}/{eli_path}", "application/ld+json"),
        ("ELI-URI, RDF/XML", f"{base}/{eli_path}", "application/rdf+xml"),
        ("ELI-URI, XML", f"{base}/{eli_path}", "application/xml"),
        ("ELI-URI, JSON", f"{base}/{eli_path}", "application/json"),
        ("API: /api/document/<eli>", f"{base}/api/document/{eli_path}", "application/json"),
        ("API: /api/<eli>", f"{base}/api/{eli_path}", "application/json"),
        ("Sti-suffiks /metadata", f"{base}/{eli_path}/metadata", "application/json"),
    ]

    for label, url, accept in attempts:
        status, content_type, body, error = fetch(url, accept)
        head = body[:300].decode("utf-8", errors="replace").replace("\n", " ")
        print(f"=== {label}")
        print(f"    {url}   (Accept: {accept})")
        if error:
            print(f"    FEJL: {error}")
        else:
            print(f"    status {status}, type: {content_type}, {len(body)} bytes")
            print(f"    {head}")
        print()
        time.sleep(DELAY_SECONDS)
    return 0


DEFAULT_DOC = "https://www.retsinformation.dk/eli/lta/2026/682"

# SPA'ens JS-bundt. Hashen aendrer sig ved deploy hos Retsinformation.
BUNDLE_PATH = "/static/js/main.f17cbae8.js"


def step_get(path: str, limit: int = 4000) -> int:
    """Hent et API-endepunkt og vis svaret. Pretty-printer JSON, hvis det er JSON."""
    url = path if path.startswith("http") else f"https://www.retsinformation.dk/{path.lstrip('/')}"
    status, content_type, body, error = fetch(url, "application/json")
    print(f"=== {url}")
    print(f"    status {status}, type: {content_type}, {len(body)} bytes")
    if error:
        print(f"    FEJL: {error}")
        return 1

    text = body.decode("utf-8", errors="replace")
    if "json" in content_type.lower():
        try:
            data = json.loads(text)
            print(json.dumps(data, ensure_ascii=False, indent=2)[:limit])
        except json.JSONDecodeError as decode_error:
            print(f"    kunne ikke parse JSON: {decode_error}")
            print(text[:limit])
    else:
        print("    (ikke JSON - sandsynligvis SPA-skallen, dvs. stien findes ikke)")
    return 0


def step_find_api(page_url: str) -> int:
    """Find SPA'ens API-endepunkter ved at laese dens JavaScript-bundt.

    Vi udskriver kun de fundne sti-moenstre, ikke bundtets indhold.
    """
    status, _, body, error = fetch(page_url)
    if error:
        print(f"FEJL ved {page_url}: {error}")
        return 1

    html = body.decode("utf-8", errors="replace")
    scripts = re.findall(r'(?is)<script[^>]+src="([^"]+)"', html)
    print(f"=== {len(scripts)} script-filer paa siden:")
    for src in scripts:
        print(f"    {src}")
    print()

    found: dict[str, int] = {}
    for src in scripts:
        url = src if src.startswith("http") else f"https://www.retsinformation.dk{src}"
        time.sleep(DELAY_SECONDS)
        status, _, js, error = fetch(url)
        if error:
            print(f"    kunne ikke hente {url}: {error}")
            continue
        text = js.decode("utf-8", errors="replace")
        print(f"    hentet {url} ({len(js)} bytes)")
        # Strengliteraler der ligner API-stier.
        for match in re.findall(r'["\'`](/?api/[A-Za-z0-9_\-/{}$.:]*)["\'`]', text):
            found[match] = found.get(match, 0) + 1
        for match in re.findall(r'["\'`](https?://[^"\'`]*?/api/[^"\'`]*)["\'`]', text):
            found[match] = found.get(match, 0) + 1

    print()
    print(f"--- {len(found)} unikke API-stier fundet:")
    for path, count in sorted(found.items()):
        print(f"    {count:4d}  {path}")
    return 0


ODA_BASE = "https://oda.ft.dk/api"


def rdfa_summary(eli_uri: str) -> dict[str, object] | None:
    """Hent .rdfa for en ELI-URI og traek de felter ud, vi bruger igen og igen."""
    url = eli_uri if eli_uri.startswith("http") else f"https://www.retsinformation.dk/{eli_uri}"
    status, content_type, raw, error = fetch(f"{url}.rdfa", "application/json")
    if error or "json" not in content_type.lower():
        return None
    try:
        triples = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None

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


def eli_from_lov(lovnummer: str, lovnummerdato: str) -> str:
    """LOV nr 1772 af 29/12/2025 -> /eli/lta/2025/1772.

    Antagelse: aarstallet i ELI-URI'en er aaret i lovnummerdato. Verificeret paa
    LOV nr 1772 af 29/12/2025. Gaelder ikke nodvendigvis for love udstedt taet paa
    aarsskiftet, hvis Retsinformation bruger publiceringsaaret i stedet.
    """
    year = lovnummerdato[:4]
    return f"eli/lta/{year}/{lovnummer}"


def oda_get(path_and_query: str, limit: int = 3000) -> dict | None:
    """Hent fra Folketingets Aabne Data (OData v3). Returnerer parset JSON eller None."""
    url = f"{ODA_BASE}/{path_and_query}"
    status, content_type, body, error = fetch(url, "application/json")
    print(f"=== {url}")
    print(f"    status {status}, type: {content_type}, {len(body)} bytes")
    if error:
        print(f"    FEJL: {error}")
        return None
    if "json" not in content_type.lower():
        print(f"    (ikke JSON) {body[:200].decode('utf-8', errors='replace')}")
        return None
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as decode_error:
        print(f"    kunne ikke parse JSON: {decode_error}")
        return None
    print(json.dumps(data, ensure_ascii=False, indent=2)[:limit])
    return data


def step_oda(mode: str, arg: str = "") -> int:
    """Kan Folketingets Aabne Data koble en vedtaget lov til dens sagsforloeb?"""
    from urllib.parse import quote

    if mode == "ping":
        oda_get("Sag?$top=2&$format=json", 2500)
    elif mode == "sag":
        # OData v3-syntaks. Vi soeger paa titel, fordi vi endnu ikke kender noeglen
        # mellem Retsinformations lovnummer og Folketingets sag.
        odata_filter = quote(f"substringof('{arg}',titel)", safe="(),'")
        oda_get(f"Sag?$filter={odata_filter}&$top=5&$format=json", 4000)
    elif mode == "lov":
        # Det afgoerende opslag: fra vedtaget lovnummer til Folketingets sag.
        odata_filter = quote(f"lovnummer eq '{arg}'", safe="(),'")
        oda_get(f"Sag?$filter={odata_filter}&$top=5&$format=json", 5000)
    elif mode == "sagdok":
        # Fra sagen til dens dokumenter: lovforslag som fremsat, betaenkning m.v.
        odata_filter = quote(f"sagid eq {arg}", safe="(),'")
        data = oda_get(
            f"SagDokument?$filter={odata_filter}&$expand=Dokument,SagDokumentRolle&$top=60&$format=json",
            0,
        )
        if data:
            rows = data.get("value", [])
            print(f"--- {len(rows)} dokumenter knyttet til sag {arg}:")
            for row in rows:
                document = row.get("Dokument") or {}
                rolle = (row.get("SagDokumentRolle") or {}).get("rolle", "")
                print(
                    f"    [{document.get('id')}] {rolle:28s} "
                    f"{str(document.get('titel', ''))[:70]}"
                )
    elif mode == "meta":
        oda_get("$metadata", 1500)
    else:
        print(f"Ukendt oda-tilstand: {mode}. Brug: ping | sag <ord> | meta")
        return 2
    return 0


def step_find_law(term: str = "ligningsloven", sample: int = 6) -> int:
    """Find en lovs ELI-URI uden at kende den paa forhaand.

    Fremgangsmaade: find aendringslovforslag i Folketingets data, udled
    aendringslovens ELI af lovnummer + dato, og foelg dens eli:changes tilbage til
    selve loven.
    """
    from urllib.parse import quote

    odata_filter = quote(
        f"substringof('{term}',titel) and lovnummer ne null", safe="(),'"
    )
    data = oda_get(
        f"Sag?$filter={odata_filter}&$orderby=lovnummerdato%20desc&$top={sample}&$format=json",
        0,
    )
    if not data:
        return 1

    sager = data.get("value", [])
    print(f"--- {len(sager)} vedtagne sager med {term!r} i titlen:")
    for sag in sager:
        dato = str(sag.get("lovnummerdato") or "")[:10]
        print(
            f"    sag {sag.get('id')}  {str(sag.get('nummer') or ''):8s} "
            f"LOV {sag.get('lovnummer')} af {dato}"
        )
        print(f"        {str(sag.get('titel') or '')[:110]}")
    print()

    if not sager:
        return 1

    # Foelg den nyeste aendringslov tilbage til de love, den aendrer.
    sag = sager[0]
    eli = eli_from_lov(str(sag.get("lovnummer")), str(sag.get("lovnummerdato") or ""))
    print(f"--- Udledt ELI for aendringsloven: /{eli}")
    time.sleep(DELAY_SECONDS)
    summary = rdfa_summary(eli)
    if not summary:
        print("    kunne ikke hente metadata - antagelsen om aarstal holder maaske ikke")
        return 1

    print(f"    {summary['title_short']}  [{summary['type']}]")
    changes = summary["changes"]
    assert isinstance(changes, list)
    print(f"    aendrer {len(changes)} retsakter:")
    print()

    for target in changes:
        time.sleep(DELAY_SECONDS)
        target_summary = rdfa_summary(str(target))
        if not target_summary:
            print(f"    {target}: kunne ikke hente metadata")
            continue
        marker = "<<<" if term.lower() in str(target_summary["title"]).lower() else "   "
        print(f"{marker} {target}")
        print(
            f"        {target_summary['title_short']}  [{target_summary['type']}] "
            f"{target_summary['in_force']}"
        )
        print(f"        {str(target_summary['title'])[:100]}")
    return 0


def step_law_scope(eli: str, resolve_titles: int = 0) -> int:
    """Vis omfanget af en lovs relationer: hvad den konsoliderer, og hvad der har aendret den."""
    summary = rdfa_summary(eli)
    if not summary:
        print(f"Kunne ikke hente metadata for {eli}")
        return 1

    print(f"=== {summary['title_short']}  [{summary['type']}] {summary['in_force']}")
    print(f"    {summary['title']}")
    print(f"    id_local: {summary['id_local']}")
    print()

    for key in ("consolidates", "changed_by", "changes", "consolidated_by"):
        values = summary[key]
        assert isinstance(values, list)
        print(f"--- {key}: {len(values)}")
        for value in values:
            print(f"    {value}")
        print()

    if resolve_titles:
        targets = summary["consolidates"]
        assert isinstance(targets, list)
        print(f"--- Titler for de foerste {resolve_titles} konsoliderede retsakter:")
        for target in targets[:resolve_titles]:
            time.sleep(DELAY_SECONDS)
            target_summary = rdfa_summary(str(target))
            if not target_summary:
                print(f"    {target}: kunne ikke hentes")
                continue
            print(f"    {target_summary['title_short']:32s} [{target_summary['type']}]")
            print(f"        {str(target_summary['title'])[:100]}")
    return 0


def step_xml(eli: str, needle: str = "9 A") -> int:
    """Hent dokumentets XML og beskriv strukturen. Vi skal kende skemaet foer vi parser."""
    url = f"https://retsinformation.dk/{eli.lstrip('/')}/dan/xml"
    status, content_type, body, error = fetch(url)
    print(f"=== {url}")
    print(f"    status {status}, type: {content_type}, {len(body)} bytes")
    if error:
        print(f"    FEJL: {error}")
        return 1

    text = body.decode("utf-8", errors="replace")
    tags: dict[str, int] = {}
    for tag in re.findall(r"<([A-Za-z0-9_:.-]+)", text):
        tags[tag] = tags.get(tag, 0) + 1
    print(f"--- {len(tags)} forskellige elementnavne, de hyppigste:")
    for tag, count in sorted(tags.items(), key=lambda item: -item[1])[:20]:
        print(f"    {count:6d}  <{tag}>")
    print()

    positions = [match.start() for match in re.finditer(re.escape(needle), text)]
    print(f"--- {len(positions)} forekomster af {needle!r}. Foerste kontekst:")
    for position in positions[:2]:
        start = max(0, position - 250)
        end = min(len(text), position + 450)
        print("    " + re.sub(r"\s+", " ", text[start:end]))
        print()
    return 0


def step_paragraf(eli: str, wanted: str = "§ 9 A") -> int:
    """Traek en enkelt paragraf ud af Lex Dania-XML'en og vis dens struktur.

    Formaal: se om <Stk> og <Linea> giver os stykker og punktummer direkte, saa vi
    slipper for selv at segmentere saetninger.
    """
    import xml.etree.ElementTree as ElementTree

    url = f"https://retsinformation.dk/{eli.lstrip('/')}/dan/xml"
    status, content_type, body, error = fetch(url)
    if error:
        print(f"FEJL: {error}")
        return 1

    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as parse_error:
        print(f"Kunne ikke parse XML: {parse_error}")
        return 1

    def text_of(element: ElementTree.Element) -> str:
        return re.sub(r"\s+", " ", "".join(element.itertext())).strip()

    target = None
    for paragraf in root.iter("Paragraf"):
        head = text_of(paragraf)[:20]
        if head.startswith(wanted) and not head.startswith(f"{wanted} A"):
            target = paragraf
            break

    if target is None:
        print(f"Fandt ikke {wanted}. Foerste 10 paragraffer i dokumentet:")
        for index, paragraf in enumerate(root.iter("Paragraf")):
            if index >= 10:
                break
            print(f"    {text_of(paragraf)[:60]}")
        return 1

    print(f"=== {wanted} fundet. Attributter: {target.attrib}")
    print(f"--- direkte boernelementer: {[child.tag for child in target]}")
    print()

    for stk in target.iter("Stk"):
        label = ""
        for child in stk:
            if child.tag == "Explicatus":
                label = text_of(child)
                break
        lineas = list(stk.iter("Linea"))
        print(f"--- {label or '(stk. 1, uden Explicatus)'}  id={stk.get('id')}")
        print(f"    {len(lineas)} <Linea>-elementer (punktummer):")
        for number, linea in enumerate(lineas, start=1):
            print(f"    {number}. pkt.  {text_of(linea)[:150]}")
        print()
    return 0


def step_touches(eli: str, wanted: str = "§ 9 A") -> int:
    """Hvilke af lovens senere aendringslove naevner en bestemt paragraf?

    Groft tekstopslag, ikke en parser. Formaalet er at maale omfanget: hvor mange af
    aendringslovene skal vi overhovedet analysere for netop denne bestemmelse.
    """
    summary = rdfa_summary(eli)
    if not summary:
        print(f"Kunne ikke hente metadata for {eli}")
        return 1

    amendments = summary["changed_by"]
    assert isinstance(amendments, list)
    print(f"=== {summary['title_short']}: {len(amendments)} senere aendringslove")
    print(f"=== soeger efter {wanted!r} i hver\n")

    touching = 0
    for uri in amendments:
        time.sleep(DELAY_SECONDS)
        path = str(uri).split("retsinformation.dk/", 1)[-1]
        url = f"https://retsinformation.dk/{path}/dan/xml"
        status, content_type, body, error = fetch(url)
        if error:
            print(f"    {uri}: kunne ikke hentes ({error})")
            continue

        text = re.sub(r"\s+", " ", body.decode("utf-8", errors="replace"))
        plain = re.sub(r"<[^>]+>", " ", text)
        plain = re.sub(r"\s+", " ", plain)
        hits = [match.start() for match in re.finditer(re.escape(wanted), plain)]

        title = ""
        title_match = re.search(r"<Titel[^>]*>(.*?)</Titel>", text)
        if title_match:
            title = re.sub(r"<[^>]+>", "", title_match.group(1))[:70]

        marker = "TRAEF" if hits else "     "
        print(f"{marker} {uri}  ({len(body)} bytes, {len(hits)} forekomster)")
        if title:
            print(f"        {title}")
        if hits:
            touching += 1
            for position in hits[:2]:
                start = max(0, position - 120)
                end = min(len(plain), position + 200)
                print(f"        ...{plain[start:end].strip()}...")
        print()

    print(f"--- {touching} af {len(amendments)} aendringslove naevner {wanted!r}")
    return 0


def oda_entity(path: str) -> dict | None:
    """Hent en enkelt OData-entitet uden at printe hele svaret."""
    url = f"{ODA_BASE}/{path}"
    status, content_type, body, error = fetch(url, "application/json")
    if error or "json" not in content_type.lower():
        print(f"    FEJL ved {url}: {error or content_type}")
        return None
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as decode_error:
        print(f"    ugyldig JSON fra {url}: {decode_error}")
        return None


def step_chain(sag_id: str) -> int:
    """Fra Folketingets sag til lovforslagets bemaerkninger paa Retsinformation.

    Tester samtidig, om FT-accessionsnummeret kan udledes af periode og
    lovforslagsnummer, saa vi kan naa den maskinlaesbare XML frem for PDF.
    """
    sag = oda_entity(f"Sag({sag_id})?$format=json")
    if not sag:
        return 1
    nummer = str(sag.get("nummernumerisk") or "")
    periode_id = sag.get("periodeid")
    print(f"=== Sag {sag_id}: {sag.get('nummer')}  LOV {sag.get('lovnummer')} "
          f"af {str(sag.get('lovnummerdato') or '')[:10]}")
    print(f"    {str(sag.get('titel') or '')[:110]}")

    time.sleep(DELAY_SECONDS)
    periode = oda_entity(f"Periode({periode_id})?$format=json")
    if not periode:
        return 1
    kode = str(periode.get("kode") or "")
    print(f"    periode {periode_id}: kode={kode!r} titel={periode.get('titel')!r}")
    print()

    # Accessionsmoenstre set i sitemap'et: 202112L00195, 202522L00017, 20252XX00061.
    # Hypotese: {periodekode}{typekode}{nummer:05d}, hvor lovforslag har typekode '2L'.
    candidates = [
        f"{kode}2L{int(nummer):05d}",
        f"{kode}L{int(nummer):05d}",
        f"{kode}1L{int(nummer):05d}",
    ] if nummer.isdigit() else []

    found = ""
    for accn in candidates:
        time.sleep(DELAY_SECONDS)
        summary = rdfa_summary(f"eli/ft/{accn}")
        if summary and summary.get("title"):
            print(f"TRAEF  /eli/ft/{accn}")
            print(f"       {summary['title_short']}  [{summary['type']}]")
            print(f"       {str(summary['title'])[:110]}")
            found = accn
            break
        print(f"       /eli/ft/{accn}: intet")

    if not found:
        print()
        print("Accessionsnummeret kunne ikke udledes af periode og nummer.")
        return 1

    # Hent lovforslagets XML og find de specielle bemaerkninger.
    print()
    time.sleep(DELAY_SECONDS)
    url = f"https://retsinformation.dk/eli/ft/{found}/dan/xml"
    status, content_type, body, error = fetch(url)
    print(f"--- {url}")
    print(f"    status {status}, type {content_type}, {len(body)} bytes")
    if error:
        print(f"    FEJL: {error}")
        return 1

    text = re.sub(r"<[^>]+>", " ", body.decode("utf-8", errors="replace"))
    text = re.sub(r"\s+", " ", text)
    for marker in ("Bemærkninger til lovforslagets enkelte bestemmelser", "Til nr. 1", "Til nr. 2"):
        positions = [match.start() for match in re.finditer(re.escape(marker), text)]
        print(f"    {len(positions):3d} forekomster af {marker!r}")
        if positions:
            start = positions[-1]
            print(f"        ...{text[start:start + 420].strip()}...")
    return 0


def oda_quiet(path_and_query: str) -> dict | None:
    """Som oda_get, men uden at printe. Bruges naar opslaget er et mellemled."""
    status, content_type, body, error = fetch(f"{ODA_BASE}/{path_and_query}", "application/json")
    if error or status != 200 or "json" not in content_type.lower():
        return None
    try:
        return json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def find_bill(law_number: str, law_date: str) -> tuple[str, str, str] | None:
    """Fra vedtaget lov til lovforslag: returnerer (sag_id, lovforslagsnummer, periodekode).

    Opslaget sker paa lovnummer *og* dato. Lovnumre genbruges hvert aar, saa nummeret
    alene ville kunne knytte forarbejder fra en helt anden lov til bestemmelsen.
    """
    from urllib.parse import quote

    odata_filter = quote(f"lovnummer eq '{law_number}'", safe="(),'")
    data = oda_quiet(f"Sag?$filter={odata_filter}&$top=20&$format=json")
    if not data:
        return None

    for row in data.get("value", []):
        if str(row.get("lovnummerdato") or "")[:10] != law_date:
            continue
        number = str(row.get("nummernumerisk") or "")
        if not number.isdigit():
            continue
        time.sleep(DELAY_SECONDS)
        periode = oda_quiet(f"Periode({row.get('periodeid')})?$format=json")
        if not periode:
            continue
        return (str(row.get("id")), number, str(periode.get("kode") or ""))
    return None


AMENDMENT_REFERENCE = re.compile(r"§\s*(\d+),\s*nr\.\s*(\d+)")


def _instructions_of(amendment, law_name: str) -> list:
    """Aendringspunkter i den paragraf, lovbekendtgoerelsen har indarbejdet.

    Fejl slugges bevidst: funktionen bruges kun til at afgoere, om en paragraf er
    roert, og en enkelt lov, der ikke kan hentes, maa ikke stoppe soegningen bagud.
    """
    import lex_dania

    try:
        xml = lex_dania.fetch_document_xml(amendment.document_path)
        instructions = lex_dania.extract_instructions(xml, amendment.document_path, law_name)
    except Exception:  # noqa: BLE001 - netvaerk og XML fejler paa mange maader
        return []

    if not amendment.paragraph:
        return instructions
    kept = []
    for instruction in instructions:
        reference = AMENDMENT_REFERENCE.search(instruction.amendment_path)
        if reference and int(reference.group(1)) == amendment.paragraph:
            kept.append(instruction)
    return kept


def _fingerprint(text: str) -> str:
    """Instruksens indhold uden det ledende punktnummer, til sammenligning.

    Nummeret udelades netop, fordi det er dét, der kan vaere forskudt mellem
    lovforslag og vedtaget lov.
    """
    return re.sub(r"\s+", "", re.sub(r"^\s*\d+\.\s*", "", text)).lower()


def _realign(proposed: list, instruction_text: str) -> tuple[int, int] | None:
    """Genfind et aendringspunkt i lovforslaget, og giv forslagets egne numre.

    Returnerer None, hvis punktet ikke kan genfindes. Da er det formentlig kommet til
    ved et aendringsforslag under behandlingen, og bemaerkningen findes i betaenkningen
    i stedet — den henter vi ikke.
    """
    wanted = _fingerprint(instruction_text)
    # autojunk=False er noedvendigt: for strenge over 200 tegn behandler difflib
    # ellers hyppige tegn som stoej, og to naesten ens instrukser fik lighed 0,74,
    # hvor den rigtige vaerdi var 0,97. Forskellen var "el.lign." mod "eller lignende".
    best, best_ratio = None, 0.0
    for candidate in proposed:
        matcher = difflib.SequenceMatcher(
            None, _fingerprint(candidate.text), wanted, autojunk=False
        )
        if matcher.quick_ratio() <= best_ratio:
            continue
        ratio = matcher.ratio()
        if ratio > best_ratio:
            best, best_ratio = candidate, ratio

    # Taersklen er hoej, for et forkert match giver en forkert bemaerkning, og et
    # forkert svar er vaerre end intet svar.
    if best is None or best_ratio < 0.90:
        return None
    try:
        return (int(best.act_number), int(best.item_number.rstrip(".")))
    except ValueError:
        return None


def _note_for(
    lex_dania, document_path: str, law_paragraph: int, item: int,
    law_name: str = "", instruction_text: str = "",
) -> tuple[str, bool, str]:
    """Hent bemaerkningen til ét aendringspunkt. Returnerer (tekst, praecis, kilde).

    Paragrafnumrene i lovforslaget er ikke de samme som i den vedtagne lov. Slaar man
    op paa lovens numre, faar man en tilfaeldig anden bestemmelses bemaerkning — et
    forkert svar, der ser rigtigt ud. Punktet genfindes derfor i lovforslaget paa sin
    tekst, og forslagets egne numre bruges til opslaget.
    """
    number = document_path.rsplit("/", 1)[-1]
    try:
        date = lex_dania.document_date(lex_dania.fetch_document_xml(document_path))
    except Exception:  # noqa: BLE001
        return ("", False, "kunne ikke laese aendringsloven")

    bill = find_bill(number, date)
    if not bill:
        return ("", False, "lovforslaget findes ikke i Folketingets data")
    sag_id, bill_number, period = bill
    accession = f"{period}2L{int(bill_number):05d}"

    try:
        bill_xml = lex_dania.fetch_document_xml(f"eli/ft/{accession}")
        notes = lex_dania.extract_explanatory_notes(bill_xml)
    except Exception:  # noqa: BLE001
        return ("", False, f"L {bill_number} kunne ikke hentes (eli/ft/{accession})")

    realigned = ""
    if law_name and instruction_text:
        try:
            proposed = lex_dania.extract_instructions(
                bill_xml, f"eli/ft/{accession}", law_name
            )
        except Exception:  # noqa: BLE001
            proposed = []
        aligned = _realign(proposed, instruction_text)
        if aligned is None:
            return ("", False, f"L {bill_number}: punktet findes ikke i lovforslaget")
        if aligned != (law_paragraph, item):
            realigned = f", forslagets § {aligned[0]}, nr. {aligned[1]}"
        law_paragraph, item = aligned

    note = notes.get((law_paragraph, item))
    if note is not None:
        return (note, True, f"L {bill_number}, sag {sag_id}{realigned}")
    note = notes.get((law_paragraph, 0))
    if note is not None:
        return (note, False, f"L {bill_number}, sag {sag_id}{realigned}")
    return ("", False, f"L {bill_number}: ingen bemaerkning til § {law_paragraph}, nr. {item}")


def _paragraph_history(
    lex_dania, start: str, start_xml: bytes, amendments: list, law_name: str,
    wanted: str, paragraph_id: str, max_steps: int,
) -> int:
    """Hele forarbejdshistorikken for én paragraf, grupperet efter hvad der blev aendret.

    Vandrer kaeden af lovbekendtgoerelser bagud og samler alle aendringer af
    paragraffen undervejs, ikke kun den seneste.
    """
    print(f"=== {law_name} § {paragraph_id}: foelger kaeden bagud fra {start}")

    found: list[tuple[str, str, object, int]] = []  # (lbk, dokument, instruks, nr)
    seen: set[str] = set()
    current, current_xml, current_amendments = start, start_xml, amendments

    for _ in range(max_steps):
        touched = 0
        for amendment in current_amendments:
            if amendment.document_path in seen:
                continue
            for instruction in _instructions_of(amendment, law_name):
                targets = [
                    lex_dania.parse_target(raw) for raw in instruction.probable_targets
                ]
                hit = any(t.paragraph_id.upper() == wanted for t in targets)
                # Indsaettes paragraffen, er maalet den foregaaende paragraf, saa
                # den skal ogsaa soeges i den nye tekst.
                if not hit and wanted not in lex_dania.inserted_paragraphs(instruction.new_text):
                    continue
                reference = AMENDMENT_REFERENCE.search(instruction.amendment_path)
                item = int(reference.group(2)) if reference else 0
                found.append((current, amendment.document_path, instruction, item))
                touched += 1
            seen.add(amendment.document_path)

        print(f"--- {current}: {touched} aendringer af § {paragraph_id}")

        earlier = lex_dania.previous_consolidation(current_xml)
        if not earlier or earlier == current:
            print(f"--- kaeden stopper ved {current}")
            break
        try:
            current_xml = lex_dania.fetch_document_xml(earlier)
            current_amendments = lex_dania.consolidated_amendments(current_xml)
        except Exception as error:  # noqa: BLE001
            print(f"--- kunne ikke hente {earlier}: {error}")
            break
        current = earlier

    if not found:
        print()
        print(f"=== § {paragraph_id} er ikke aendret i den del af kaeden, vi kan naa.")
        print("    Bestemmelsens forarbejder ligger foer 2007, hvor Lex Dania-XML begynder.")
        return 0

    # Kronologi, nyeste foerst. Lovnumre stiger inden for et aar, saa (aar, nummer)
    # er en korrekt datoorden uden at hente hver lov igen. Raekkefoelgen i
    # lovbekendtgoerelsens egen liste er ikke kronologisk, og for § 33 A afgoer
    # forskellen, om ophaevelsen eller genindfoerelsen ser ud til at komme sidst.
    found.sort(key=lambda row: (int(row[1].split("/")[-2]), int(row[1].split("/")[-1])), reverse=True)

    # Oversigt pr. stykke. Det er den form, spoergsmaalet stilles i: "hvilke
    # forarbejder gaelder for § 9 C, stk. 3?"
    print()
    print(f"=== {len(found)} aendringer af § {paragraph_id}, fordelt paa stykker")
    by_stk: dict[str, list[str]] = {}
    for lbk, document, instruction, item in found:
        places: list[tuple[str, str]] = []  # (hvor, punktumangivelse)
        for raw in instruction.probable_targets:
            target = lex_dania.parse_target(raw)
            if target.paragraph_id.upper() != wanted:
                continue
            places.append((
                f"stk. {target.stk_number}" if target.stk_number else "hele paragraffen",
                ", ".join(f"{n}. pkt." for n in target.sentence_numbers)
                if target.sentence_numbers else "",
            ))
        if not places:
            places = [("hele paragraffen — indsat", "")]
        for where, sentences in places:
            entry = f"{document.rsplit('/', 1)[-1]}/{document.split('/')[-2]} {instruction.amendment_path}"
            by_stk.setdefault(where, []).append(f"{entry}{' — ' + sentences if sentences else ''}")
    for where in sorted(by_stk, key=lambda key: (key != "hele paragraffen", key)):
        print(f"    {where}:")
        for entry in by_stk[where]:
            print(f"        {entry}")

    print()
    print(f"=== bemaerkninger, nyeste foerst")
    print()

    confirmed = 0
    for lbk, document, instruction, item in found:
        # Bemaerkningen slaas op paa aendringslovens egen paragraf, ikke lovens.
        reference = AMENDMENT_REFERENCE.search(instruction.amendment_path)
        law_paragraph = int(reference.group(1)) if reference else 0
        note, precise, source = _note_for(
            lex_dania, document, law_paragraph, item, law_name, instruction.text
        )

        # Tomme maal opstaar, naar den nye betegnelse er kursiveret ("indsaettes som
        # stk. 6"), og de skal ikke vises som var de selvstaendige maal.
        targets = ", ".join(
            target.label
            for target in (lex_dania.parse_target(raw) for raw in instruction.probable_targets)
            if target.paragraph_id
        ) or f"§ {paragraph_id} (indsat her)"
        print(f"--- {document} {instruction.amendment_path}  (indarbejdet i {lbk})")
        print(f"    rammer: {targets}")
        print(f"    {instruction.text[:150]}")
        if not note:
            print(f"    INGEN bemaerkning: {source}")
            print()
            continue

        flat = re.sub(r"\s+", "", note).upper()
        confirms = f"§{wanted}" in flat
        confirmed += 1 if confirms else 0
        kind = "til dette nummer" if precise else "til hele aendringsparagraffen"
        print(f"    bemaerkning: {source}, {len(note)} tegn, {kind}, naevner § {paragraph_id}: {confirms}")
        print(f"    {note[:700]}")
        print()

    print(f"=== {confirmed} af {len(found)} bemaerkninger naevner § {paragraph_id}")
    return 0


def step_motiver(lbk_eli: str, paragraph_id: str, max_steps: str = "6") -> int:
    """Hele kaeden: fra en lovparagraf til lovforslagets specielle bemaerkninger.

    Gaar gennem de aendringslove, lovbekendtgoerelsen selv oplyser at have
    indarbejdet, finder de aendringspunkter der rammer paragraffen, og henter
    bemaerkningen til hvert punkt.
    """
    import xml.etree.ElementTree as ElementTree

    import lex_dania

    facit = lbk_eli.strip("/")
    # "alle" maaler daekningen for hele loven i stedet for at vise én paragraf.
    # Det er det tal, der siger, om koblingen kan baere.
    wanted = "" if paragraph_id.lower() == "alle" else paragraph_id.upper().replace(" ", "").lstrip("§")
    survey = not wanted

    try:
        target_xml = lex_dania.fetch_document_xml(facit)
        amendments = lex_dania.consolidated_amendments(target_xml)
        law_name = lex_dania.law_name_of(lex_dania.fetch_metadata(facit))
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        print(f"Kunne ikke forberede: {error}")
        return 1

    # For én paragraf foelges hele kaeden af lovbekendtgoerelser bagud, og alle
    # aendringer samles. Stopper man ved den foerste, faar man kun den seneste
    # aendring, mens de aeldre — som ofte baerer fortolkningen af den oprindelige
    # regel — falder ud.
    if not survey:
        return _paragraph_history(
            lex_dania, facit, target_xml, amendments, law_name, wanted, paragraph_id,
            int(max_steps),
        )

    scope = "alle paragraffer" if survey else f"§ {paragraph_id}"
    print(f"=== {law_name}, {scope}: soeger i {len(amendments)} aendringslove fra {facit}")
    print()

    hits = 0
    total = 0
    no_bill = 0
    no_note = 0
    unconfirmed: list[str] = []
    for amendment in amendments:
        try:
            xml = lex_dania.fetch_document_xml(amendment.document_path)
            instructions = lex_dania.extract_instructions(xml, amendment.document_path, law_name)
        except (lex_dania.FetchError, ElementTree.ParseError) as error:
            print(f"--- {amendment.document_path}: kunne ikke hentes ({error})")
            continue

        relevant = []
        for instruction in instructions:
            reference = AMENDMENT_REFERENCE.search(instruction.amendment_path)
            if not reference or int(reference.group(1)) != amendment.paragraph:
                continue
            if survey:
                relevant.append((instruction, int(reference.group(2))))
                continue
            for raw in instruction.probable_targets:
                if lex_dania.parse_target(raw).paragraph_id.upper() == wanted:
                    relevant.append((instruction, int(reference.group(2))))
                    break
        if not relevant:
            continue
        total += len(relevant)

        number = amendment.document_path.rsplit("/", 1)[-1]
        date = lex_dania.document_date(xml)
        print(f"--- LOV nr. {number} af {date}, § {amendment.paragraph}")

        bill = find_bill(number, date)
        if not bill:
            print("        fandt ikke lovforslaget i Folketingets data")
            no_bill += len(relevant)
            continue
        sag_id, bill_number, period = bill
        accession = f"{period}2L{int(bill_number):05d}"
        print(f"        sag {sag_id}, L {bill_number}, periode {period} -> eli/ft/{accession}")

        try:
            bill_xml = lex_dania.fetch_document_xml(f"eli/ft/{accession}")
            notes = lex_dania.extract_explanatory_notes(bill_xml)
            proposed = lex_dania.extract_instructions(
                bill_xml, f"eli/ft/{accession}", law_name
            )
        except (lex_dania.FetchError, ElementTree.ParseError) as error:
            print(f"        lovforslaget kunne ikke hentes: {error}")
            no_bill += len(relevant)
            continue

        for instruction, item in relevant:
            # Lovforslagets paragrafnumre er ikke lovens, saa punktet genfindes paa sin
            # tekst. Uden det henter man en anden bestemmelses bemaerkning.
            aligned = _realign(proposed, instruction.text)
            if aligned is None:
                no_note += 1
                if not survey:
                    print(f"        {instruction.amendment_path}: findes ikke i lovforslaget")
                continue
            bill_paragraph, item = aligned

            # Har paragraffen kun ét aendringspunkt, udelades "Til nr. 1" ofte, og
            # bemaerkningen staar direkte under "Til § N". Tilbagefaldet markeres, for
            # det er mindre praecist: teksten kan daekke hele paragraffen.
            note = notes.get((bill_paragraph, item))
            precise = note is not None
            if note is None:
                note = notes.get((bill_paragraph, 0))
            if not note:
                no_note += 1
                if not survey:
                    print(f"        {instruction.amendment_path}: INGEN bemaerkning")
                continue

            # Bemaerkningen citerer selv den bestemmelse, den forklarer. Naevner den
            # ikke maalet, er koblingen sandsynligvis forkert, og det skal ses.
            targets = [lex_dania.parse_target(raw) for raw in instruction.probable_targets]
            labels = {t.paragraph_id.upper() for t in targets if t.paragraph_id}
            flat = re.sub(r"\s+", "", note).upper()
            confirms = any(f"§{label}" in flat for label in labels) if labels else False
            if not confirms:
                unconfirmed.append(f"{amendment.document_path} {instruction.amendment_path}")
            hits += 1

            if not survey:
                kind = "til dette nummer" if precise else "til hele paragraffen (intet 'Til nr.')"
                print(f"        {instruction.amendment_path}: {instruction.text[:88]}")
                print(f"            {len(note)} tegn, {kind}, bekraefter maalet: {confirms}")
                print(f"            {note[:1100]}")
        if not survey:
            print()

    print()
    print(f"=== {total} aendringspunkter undersoegt")
    print(f"    {hits} fik en bemaerkning")
    print(f"    {no_note} havde intet 'Til nr.' i lovforslaget")
    print(f"    {no_bill} kunne ikke naa lovforslaget")
    if hits:
        share = 100.0 * (hits - len(unconfirmed)) / hits
        print(f"    {len(unconfirmed)} bemaerkninger naevner ikke maalbestemmelsen ({share:.1f}% bekraeftet)")
    for label in unconfirmed[:10]:
        print(f"        {label}")
    return 0


# En paragraf med bogstav ("§ 8 X") kan ikke stamme fra lovens oprindelige tekst.
# Bogstavet opstaar netop, fordi bestemmelsen er skudt ind mellem to eksisterende
# paragraffer. Findes den ikke i kaeden, er den enten indsat foer 2007, eller ogsaa
# overser vi den — og det sidste er en tavs fejl.
LETTERED_PARAGRAPH = re.compile(r"^\d+[A-ZÆØÅ]+$")


def step_daekning(lbk_eli: str, max_steps: str = "8") -> int:
    """Hvor mange af lovens paragraffer kan vi overhovedet finde forarbejder til?

    Maaler bredden i stedet for at se paa én paragraf ad gangen. Hele kaeden
    gennemloebes én gang, og alle aendringspunkter indekseres efter hvilken paragraf
    de rammer, saa alle lovens paragraffer kan bedoemmes samtidig. Formaalet er at
    finde tavse fejl: paragraffer, hvor soegningen svarer "ingen aendringer", uden at
    det er sandt.
    """
    import xml.etree.ElementTree as ElementTree

    import lex_dania

    facit = lbk_eli.strip("/")
    try:
        target_xml = lex_dania.fetch_document_xml(facit)
        amendments = lex_dania.consolidated_amendments(target_xml)
        law_name = lex_dania.law_name_of(lex_dania.fetch_metadata(facit))
        provisions = lex_dania.extract_provisions(target_xml)
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        print(f"Kunne ikke forberede: {error}")
        return 1

    paragraphs: list[str] = []
    for provision in provisions:
        if provision.paragraph_id and provision.paragraph_id not in paragraphs:
            paragraphs.append(provision.paragraph_id)

    print(f"=== {law_name} fra {facit}: {len(paragraphs)} paragraffer")
    print(f"=== gennemloeber kaeden bagud, hoejst {max_steps} led")

    # Indeks: paragraf -> liste af (lbk, dokument, instruks, ramt_som_maal).
    touched: dict[str, list[tuple[str, str, object, bool]]] = {}
    chain: list[str] = []
    seen: set[str] = set()
    current, current_xml, current_amendments = facit, target_xml, amendments

    for _ in range(int(max_steps)):
        chain.append(current)
        # En lovbekendtgoerelse uden indarbejdede aendringer findes stort set ikke.
        # Er listen tom, er indledningen naesten altid ikke blevet laest, og saa
        # forsvinder hele perioden lydloest.
        if not current_amendments:
            print(f"--- ADVARSEL: {current} har ingen laeselig liste over aendringer")
        for amendment in current_amendments:
            if amendment.document_path in seen:
                continue
            seen.add(amendment.document_path)
            for instruction in _instructions_of(amendment, law_name):
                hit: set[str] = set()
                for raw in instruction.probable_targets:
                    label = lex_dania.parse_target(raw).paragraph_id.upper()
                    if label:
                        hit.add(label)
                inserted = set(lex_dania.inserted_paragraphs(instruction.new_text))
                for label in hit | inserted:
                    touched.setdefault(label, []).append(
                        (current, amendment.document_path, instruction, label in hit)
                    )

        earlier = lex_dania.previous_consolidation(current_xml)
        if not earlier or earlier in chain:
            break
        try:
            current_xml = lex_dania.fetch_document_xml(earlier)
            current_amendments = lex_dania.consolidated_amendments(current_xml)
        except Exception as error:  # noqa: BLE001
            print(f"--- kunne ikke hente {earlier}: {error}")
            break
        current = earlier

    print(f"--- kaeden: {' -> '.join(chain)}")
    print(f"--- {len(seen)} aendringslove gennemgaaet, {sum(map(len, touched.values()))} punkter")
    print()

    found = [p for p in paragraphs if p in touched]
    missing = [p for p in paragraphs if p not in touched]
    share = 100.0 * len(found) / len(paragraphs) if paragraphs else 0.0
    print(f"=== {len(found)} af {len(paragraphs)} paragraffer har mindst én aendring ({share:.1f}%)")

    # Bogstavparagraffer uden fund er de mistaenkelige. En ren talparagraf kan
    # stamme fra lovens oprindelige tekst og aldrig vaere roert siden.
    suspect = [p for p in missing if LETTERED_PARAGRAPH.match(p)]
    plain = [p for p in missing if not LETTERED_PARAGRAPH.match(p)]
    print(f"    {len(plain)} uden fund er rene talparagraffer — kan vaere oprindelige")
    print(f"    {len(suspect)} uden fund har bogstav — maa vaere indsat, saa de skal ses efter")
    if suspect:
        print(f"        {', '.join('§ ' + p for p in suspect)}")

    # Rammer vi paragraffen kun via indsat tekst, er det praecis den fejlklasse,
    # § 33 A afsloerede. Tallet siger, hvor meget den rettelse betyder i bredden.
    only_inserted = [
        p for p in found if not any(as_target for _, _, _, as_target in touched[p])
    ]
    print(f"    {len(only_inserted)} paragraffer findes kun via indsat tekst, ikke via maal")
    # Instruksen vises, for moensteret kan tage fejl: en henvisning "jf. § 9 C." i ny
    # tekst ligner en indsat paragraf. Kun teksten afgoer, om fundet er aegte.
    for label in only_inserted:
        _, document, instruction, _ = touched[label][0]
        print(f"        § {label}  {document} {instruction.amendment_path}")
        print(f"            {instruction.text[:110]}")

    # Laekagetest mod en uafhaengig kilde. Kaeden bygger alene paa lovbekendtgoerelsernes
    # egne lister; er en liste ufuldstaendig, eller peger et led forkert, taber vi love
    # uden at opdage det. `eli:changed_by` paa hvert led siger, hvilke love der aendrede
    # netop den bekendtgoerelse, og de burde alle vaere indarbejdet senere i kaeden.
    print()
    print("=== laekagetest: love i eli:changed_by, som kaeden aldrig naaede")

    # To slags udeladelser er legitime, og de kan begge afgoeres af data.
    # Lovnumre og bekendtgoerelsesnumre deler nummerserie i Lovtidende A, saa
    # (aar, nummer) afgoer, om en lov er nyere end den nyeste bekendtgoerelse.
    newest = (int(facit.split("/")[-2]), int(facit.split("/")[-1]))
    excused: set[str] = set()
    for step in chain:
        try:
            excused.update(
                lex_dania.unincorporated_amendments(lex_dania.fetch_document_xml(step))
            )
        except Exception:  # noqa: BLE001
            continue

    leaked: list[tuple[str, str, str]] = []  # (led, dokument, forklaring)
    for step in chain:
        try:
            metadata = lex_dania.fetch_metadata(step)
        except Exception:  # noqa: BLE001
            continue
        for uri in metadata.get("changed_by", []):  # type: ignore[union-attr]
            document = lex_dania.document_path_of(str(uri))
            if document in seen:
                continue
            parts = document.split("/")
            if (int(parts[-2]), int(parts[-1])) > newest:
                reason = "nyere end lovbekendtgoerelsen"
            elif document in excused:
                reason = "oplyst som ikke indarbejdet"
            else:
                reason = ""
            leaked.append((step, document, reason))

    unexplained = [row for row in leaked if not row[2]]
    print(f"--- {len(leaked)} love uden for kaeden, heraf {len(unexplained)} uforklarede")
    for step, document, reason in leaked[:30]:
        print(f"        {document}  (aendrer {step}) — {reason or 'UFORKLARET'}")
    return 0


def step_notes(ft_eli: str) -> int:
    """Er de specielle bemaerkninger opmaerket, eller er de loebende tekst?

    Det afgoer, om vi kan udtraekke bemaerkningen til ét bestemt aendringspunkt
    praecist, eller om vi kun kan lede efter overskrifter i fritekst. I sidste
    tilfaelde skal koblingen behandles som usikker.
    """
    import xml.etree.ElementTree as ElementTree

    import lex_dania

    try:
        body = lex_dania.fetch_document_xml(ft_eli.strip("/"))
        root = ElementTree.fromstring(body)
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        print(f"Kunne ikke behandle {ft_eli}: {error}")
        return 1

    print(f"=== {ft_eli}: {len(body)} bytes")

    tags: dict[str, int] = {}
    for element in root.iter():
        tags[element.tag] = tags.get(element.tag, 0) + 1
    print("--- hyppigste elementer:")
    for tag, count in sorted(tags.items(), key=lambda item: -item[1])[:14]:
        print(f"    {count:5d}  <{tag}>")

    # Find de elementer, hvis tekst er en bemaerkningsoverskrift ("Til nr. 2"),
    # og vis deres placering i traeet. Er de opmaerket, har de en egen tag.
    print()
    print("--- elementer hvis tekst ligner en bemaerkningsoverskrift:")
    parents = {child: parent for parent in root.iter() for child in parent}
    shown = 0
    for element in root.iter():
        text = lex_dania.element_text(element)
        if not re.fullmatch(r"Til (nr\.|§)\s*[\d\w]+[\.\s]*", text or ""):
            continue
        if list(element):
            continue
        path = []
        node = element
        while node is not None and len(path) < 4:
            path.append(node.tag)
            node = parents.get(node)
        print(f"    {text!r:20s} {' < '.join(path)}  attrib={element.attrib or '{}'}")
        shown += 1
        if shown >= 12:
            break
    if not shown:
        print("    ingen — overskrifterne staar formentlig som loebende tekst")

    notes = lex_dania.extract_explanatory_notes(body)
    print()
    print(f"--- {len(notes)} specielle bemaerkninger udtrukket:")
    for (paragraph, item), text in sorted(notes.items()):
        print(f"    § {paragraph}, nr. {item}  ({len(text)} tegn)")
        print(f"        {text[:260]}")
    return 0


def step_mine(eli: str, max_acts: int = 40) -> int:
    """Udvind testmaengden: alle aendringsinstrukser mod en lov, grupperet efter type.

    Selve udtraekket ligger i lex_dania.py, saa proben og inspektionsappen maaler
    det samme. Her staar kun optaellingen.
    """
    import xml.etree.ElementTree as ElementTree

    import lex_dania

    law_name = "ligningslov"
    try:
        acts = lex_dania.amending_documents(eli)[:max_acts]
    except lex_dania.FetchError as error:
        print(f"Kunne ikke hente metadata for {eli}: {error}")
        return 1

    print(f"=== {eli}: undersoeger {len(acts)} aendringslove")
    print(f"=== leder efter aendringsparagraffer der naevner {law_name!r}\n")

    type_counts: dict[str, int] = {}
    instructions: list[lex_dania.Instruction] = []
    acts_with_hits = 0
    failed: list[str] = []

    for path in acts:
        try:
            body = lex_dania.fetch_document_xml(path)
            found = lex_dania.extract_instructions(body, path, law_name)
        except (lex_dania.FetchError, ElementTree.ParseError) as error:
            failed.append(f"{path}: {error}")
            continue

        if found:
            acts_with_hits += 1
        instructions.extend(found)
        for instruction in found:
            for name in instruction.constructions:
                type_counts[name] = type_counts.get(name, 0) + 1

    total = len(instructions)
    with_signi = sum(1 for item in instructions if item.target_markup == "signi_char")
    with_italic = sum(1 for item in instructions if item.target_markup == "italic")
    multi_target = sum(1 for item in instructions if len(item.targets) > 1)
    qualified = sum(1 for item in instructions if item.occurrences is not None)

    print(f"--- {acts_with_hits} af {len(acts)} love indeholder aendringer til {law_name}en")
    print(f"--- {total} nummererede aendringspunkter i alt")
    print(f"--- {with_signi} har maalet i signiChar='AendringURN'")
    print(f"--- {with_italic} har maalet kursiveret uden signiChar")
    print(f"--- {total - with_signi - with_italic} har intet opmaerket maal")
    print(f"--- {multi_target} punkter rammer mere end ét maal")
    print(f"--- {qualified} punkter har en forekomst-kvalifikator (fx »to steder«)")
    print()
    print("--- konstruktionstyper (et punkt kan taelle i flere):")
    for name, count in sorted(type_counts.items(), key=lambda item: -item[1]):
        share = 100.0 * count / total if total else 0.0
        print(f"    {count:5d}  {share:5.1f}%  {name}")

    unclassified = [item for item in instructions if "uklassificeret" in item.constructions]
    if unclassified:
        print()
        print(f"--- {len(unclassified)} uklassificerede punkter:")
        for item in unclassified[:6]:
            print(f"    {item.document_path} {item.amendment_path}: {item.text[:150]}")

    without_target = [item for item in instructions if item.target_markup == "none"]
    if without_target:
        print()
        print(f"--- {len(without_target)} punkter uden opmaerket maal:")
        for item in without_target[:6]:
            print(f"    {item.document_path} {item.amendment_path}: {item.text[:150]}")

    if failed:
        print()
        print(f"--- {len(failed)} love kunne ikke behandles:")
        for failure in failed[:5]:
            print(f"    {failure}")
    return 0


def step_intro(eli: str) -> int:
    """Vis lovbekendtgoerelsens indledning, som opregner de indarbejdede aendringslove.

    En LBK skriver selv, hvilke aendringer den omfatter ("med de aendringer, der
    foelger af § 2 i lov nr. X"). Det er en langt bedre kilde til, hvad der skal
    afspilles, end at gaette ikrafttraedelsen ud fra datoer.
    """
    import xml.etree.ElementTree as ElementTree

    import lex_dania

    try:
        root = ElementTree.fromstring(lex_dania.fetch_document_xml(eli.strip("/")))
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        print(f"Kunne ikke behandle {eli}: {error}")
        return 1

    print(f"=== {eli}: tekst foer foerste paragraf")
    for element in root.iter():
        if element.tag == "Paragraf":
            break
        if element.tag in ("Linea", "Titel", "Note", "NoteTekst"):
            text = lex_dania.element_text(element)
            if text:
                print(f"--- <{element.tag}>")
                print(f"    {text}")
    return 0


def step_laws(eli: str) -> int:
    """Vis hvilke love en aendringslov retter i, og hvor deres nyeste udgave ligger.

    Bruges til at finde et andet testinterval end ligningsloven, saa vi kan se, om
    motoren er bygget til lovgivning i almindelighed eller kun til én lov.
    """
    import lex_dania

    try:
        meta = lex_dania.fetch_metadata(eli.strip("/"))
    except lex_dania.FetchError as error:
        print(f"Kunne ikke hente metadata: {error}")
        return 1

    changes = [str(uri) for uri in meta.get("changes", [])]  # type: ignore[union-attr]
    print(f"=== {meta['title_short'] or meta['title']}")
    print(f"--- retter i {len(changes)} love")
    for uri in changes:
        path = lex_dania.document_path_of(uri)
        try:
            target = lex_dania.fetch_metadata(path)
        except lex_dania.FetchError as error:
            print(f"    {path}: kunne ikke hentes ({error})")
            continue
        newer = [lex_dania.document_path_of(item) for item in target.get("consolidated_by", [])]  # type: ignore[union-attr]
        amended = len(target.get("changed_by", []))  # type: ignore[arg-type]
        print(f"    {path}  {lex_dania.law_name_of(target) or target['title']}")
        print(f"        type={target['type']} aendret af {amended} love")
        if newer:
            print(f"        nyere udgave: {', '.join(newer)}")
    return 0


def step_replay(from_eli: str, to_eli: str, law_name: str = "") -> int:
    """Afspil aendringslovene fra én lovbekendtgoerelse til den naeste og maal traefsikkerheden.

    Det er motorens egentlige proeve. Kan vi ikke genskabe teksten, kan vi heller ikke
    sige med sikkerhed, hvilken aendringslov et tekststykke stammer fra.
    """
    import lex_dania
    import replay as replay_module

    start = from_eli.strip("/")
    facit = to_eli.strip("/")

    # Lovnavnet skal matche indledningen "I ligningsloven, jf. lovbekendtgoerelse …",
    # og lovbekendtgoerelsens korte titel er netop den form. Uden det ville motoren
    # kun kunne koere paa love, vi har skrevet ind i koden.
    if not law_name:
        try:
            law_name = lex_dania.law_name_of(lex_dania.fetch_metadata(facit))
        except lex_dania.FetchError as error:
            print(f"Kunne ikke finde lovens navn: {error}")
            return 1
        if not law_name:
            print("Kunne ikke udlede lovens navn fra titlen; angiv det som tredje argument.")
            return 1

    try:
        base_xml = lex_dania.fetch_document_xml(start)
        base = lex_dania.extract_provisions(base_xml)
        target_xml = lex_dania.fetch_document_xml(facit)
        expected = lex_dania.extract_provisions(target_xml)
        amendments = lex_dania.consolidated_amendments(target_xml)
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        print(f"Kunne ikke forberede afspilningen: {error}")
        return 1

    # Lovbekendtgoerelsen opregner selv de aendringer, den har indarbejdet, og med
    # hvilken paragraf i hver aendringslov. Kan den liste ikke laeses, falder vi
    # tilbage paa eli:changed_by, men det er en daarligere kilde: den rummer ogsaa
    # love, der endnu ikke er traadt i kraft.
    if amendments:
        source = "lovbekendtgoerelsens egen liste"
    else:
        source = "eli:changed_by (uden hensyn til ikrafttraeden)"
        try:
            paths = [p for p in lex_dania.amending_documents(facit) if p != start]
        except lex_dania.FetchError as error:
            print(f"Kunne ikke hente aendringslove: {error}")
            return 1
        facit_date = lex_dania.document_date(target_xml)
        dated: list[tuple[str, str]] = []
        for path in paths:
            try:
                dated.append((lex_dania.document_date(lex_dania.fetch_document_xml(path)), path))
            except (lex_dania.FetchError, ElementTree.ParseError):
                dated.append(("", path))
        dated.sort()
        amendments = [
            lex_dania.ConsolidatedAmendment(document_path=path, paragraph=0)
            for date, path in dated
            if not (date and facit_date and date > facit_date)
        ]

    print(f"=== afspiller {len(amendments)} love fra {start} til {facit} ({law_name})")
    print(f"--- udgangspunkt: {len(base)} stykker, facit: {len(expected)} stykker")
    print(f"--- kilde til listen: {source}")
    for amendment in amendments:
        where = f"§ {amendment.paragraph}" if amendment.paragraph else "hele loven"
        print(f"        {amendment.document_path}  {where}")
    if not amendments:
        print("Ingen love at afspille.")
        return 1
    print()

    state = replay_module.TextState(base)
    report = replay_module.replay(state, amendments, law_name)

    applied = report.count("applied")
    already = report.count("already_applied")
    failed = report.count("failed")
    print(f"--- {report.total} operationer i alt")
    print(f"    {applied} anvendt")
    print(f"    {already} stod allerede i teksten")
    print(f"    {failed} kunne ikke anvendes")
    share = 100.0 * (applied + already) / report.total if report.total else 0.0
    print(f"    det er {share:.1f}% haandteret")
    print()

    reasons: dict[str, int] = {}
    for result in report.results:
        if result.status == "failed":
            reason = re.sub(r"'.*?'", "…", result.note)
            reason = re.sub(r"\d+", "N", reason)
            reasons[reason] = reasons.get(reason, 0) + 1
    print("--- hvorfor operationer fejler:")
    for reason, count in sorted(reasons.items(), key=lambda item: -item[1])[:12]:
        print(f"    {count:4d}  {reason}")
    print()

    # Fejl i tekstmatchningen er de alvorlige: de betyder, at vi har forstaaet
    # instruksen, men ikke kan finde teksten. Vis dem enkeltvis.
    print("--- operationer hvor teksten ikke kunne findes:")
    for result in report.results:
        if result.status == "failed" and result.note.startswith(("fandt ikke", "forventede")):
            print(f"    {result.operation.where}")
            print(f"        {result.operation.op_type}: {result.note}")
    print()

    touched = {
        result.operation.target.key
        for result in report.results
        if result.status in ("applied", "already_applied")
    }
    same, different, examples = replay_module.compare(state, expected)
    print(f"--- tekstsammenligning mod {facit}:")
    print(f"    {same} stykker rammer ordret, {different} afviger")
    print(f"    {len(touched)} stykker blev roert af mindst én operation")

    changed_and_correct = 0
    for provision in expected:
        if provision.key not in touched:
            continue
        if state.text_of(provision.key) == replay_module.normalise(provision.text):
            changed_and_correct += 1
    if touched:
        rate = 100.0 * changed_and_correct / len(touched)
        print(f"    af de roerte rammer {changed_and_correct} ordret ({rate:.1f}%)")

    # Afgoerende skel: en beroert enhed kan afvige, fordi vores operation gjorde noget
    # forkert, eller fordi en anden operation paa samme enhed fejlede, saa teksten kun
    # er halvt opdateret. Det foerste er en fejl i motoren, det andet er manglende
    # daekning. De to kraever helt forskelligt arbejde.
    failed_units: dict[tuple, int] = {}
    for result in report.results:
        if result.status == "failed" and result.operation.target.is_resolvable:
            key = result.operation.target.key[:2]
            failed_units[key] = failed_units.get(key, 0) + 1

    clean_hit = clean_miss = polluted_hit = polluted_miss = 0
    clean_misses: list[str] = []
    for provision in expected:
        if provision.key not in touched:
            continue
        correct = state.text_of(provision.key) == replay_module.normalise(provision.text)
        polluted = provision.key[:2] in failed_units
        if polluted:
            if correct:
                polluted_hit += 1
            else:
                polluted_miss += 1
        elif correct:
            clean_hit += 1
        else:
            clean_miss += 1
            clean_misses.append(provision.label)

    print()
    print("--- hvorfor de beroerte enheder afviger:")
    print(f"    {clean_hit} rammer, hvor alle operationer paa enheden lykkedes")
    print(f"    {clean_miss} afviger, selv om alle operationer lykkedes  <- fejl i motoren")
    print(f"    {polluted_hit} rammer trods en fejlet operation paa samme enhed")
    print(f"    {polluted_miss} afviger, hvor en operation paa samme enhed fejlede")
    if clean_hit + clean_miss:
        rate = 100.0 * clean_hit / (clean_hit + clean_miss)
        print(f"    paa enheder uden fejlede operationer rammer vi {rate:.1f}%")

    # Fejlklasser tælles frem for at blive laest enkeltvis. Ellers risikerer man at
    # generalisere fra det foerste tilfaelde, man kigger paa.
    by_label = {provision.label: provision for provision in expected}
    classes: dict[str, list[str]] = {}
    for label in clean_misses:
        provision = by_label[label]
        kind = replay_module.classify_difference(
            state.text_of(provision.key), replay_module.normalise(provision.text)
        )
        classes.setdefault(kind, []).append(label)

    print()
    print("--- hvordan de fejler, naar alle operationer lykkedes:")
    for kind, labels in sorted(classes.items(), key=lambda item: -len(item[1])):
        print(f"    {len(labels):4d}  {kind}")
        print(f"          {', '.join(labels[:5])}")

    print()
    print("--- enheder der afviger, selv om alle operationer lykkedes:")
    for label in clean_misses[:6]:
        provision = by_label[label]
        ours = state.text_of(provision.key)
        theirs = replay_module.normalise(provision.text)
        print(f"    {label}")

        # Vis kun stedet, hvor de to tekster skilles, ellers drukner forskellen i
        # flere hundrede tegns enslydende lovtekst.
        cut = 0
        while cut < min(len(ours), len(theirs)) and ours[cut] == theirs[cut]:
            cut += 1
        start = max(0, cut - 40)
        print(f"        faelles: …{ours[start:cut]}")
        print(f"        vores:   {ours[cut:cut + 90]!r}")
        print(f"        facit:   {theirs[cut:cut + 90]!r}")

    print()
    print("--- eksempler paa stykker der afviger:")
    for label in examples[:10]:
        print(f"    {label}")
    return 0


def step_instructions(document: str, law_name: str = "ligningslov") -> int:
    """Vis alle aendringsinstrukser i ét dokument, med maal og ny tekst."""
    import lex_dania

    path = document.strip("/")
    try:
        xml = lex_dania.fetch_document_xml(path)
        instructions = lex_dania.extract_instructions(xml, path, law_name)
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        print(f"Kunne ikke behandle {path}: {error}")
        return 1

    print(f"=== {path}: {len(instructions)} punkter mod {law_name}en\n")
    for instruction in instructions:
        target = lex_dania.parse_target(instruction.probable_targets[0]) if instruction.probable_targets else None
        print(f"--- {instruction.amendment_path}  [{', '.join(instruction.constructions)}]")
        print(f"    maal: {target.label if target else '(intet)'}")
        print(f"    {instruction.text[:400]}")
        if instruction.new_text:
            print(f"    ny tekst: {instruction.new_text[:400]}")
        print()
    return 0


def step_validate(eli: str, law_name: str = "ligningslov") -> int:
    """Slaa aendringsinstruksernes maal op i den lovbekendtgoerelse, de sigter mod.

    Kun love i `changed_by` bruges. De aendrer netop denne lovbekendtgoerelse, saa
    dens tekst er det rigtige udgangspunkt. Love i `consolidates` sigter mod en
    tidligere tekst og kan ikke kontrolleres her.

    Det staerkeste enkeltsignal er "indsaettes som N. pkt.": det forudsaetter praecis
    N-1 punktummer i forvejen, saa det maaler punktumsegmenteringen direkte.
    """
    import lex_dania

    path = eli.strip("/")
    try:
        metadata = lex_dania.fetch_metadata(path)
        body = lex_dania.fetch_document_xml(path)
        provisions = lex_dania.extract_provisions(body)
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        print(f"Kunne ikke behandle {path}: {error}")
        return 1

    by_key = {provision.key: provision for provision in provisions}
    changed_by = metadata["changed_by"]
    assert isinstance(changed_by, list)
    documents = [lex_dania.document_path_of(str(uri)) for uri in changed_by]

    total = 0
    no_target = 0
    unparsed = 0
    missing_paragraph = 0
    missing_stk = 0
    sentence_ok = 0
    sentence_bad: list[str] = []
    insert_ok = 0
    insert_bad: list[str] = []

    for document in documents:
        try:
            xml = lex_dania.fetch_document_xml(document)
            instructions = lex_dania.extract_instructions(xml, document, law_name)
        except (lex_dania.FetchError, ElementTree.ParseError) as error:
            print(f"    kunne ikke behandle {document}: {error}")
            continue

        for instruction in instructions:
            total += 1
            if not instruction.probable_targets:
                no_target += 1
                continue

            target = lex_dania.parse_target(instruction.probable_targets[0])
            if not target.is_resolvable:
                unparsed += 1
                continue

            provision = by_key.get(target.key)
            if provision is None:
                if not any(key[0] == target.paragraph_id for key in by_key):
                    missing_paragraph += 1
                else:
                    missing_stk += 1
                continue

            count = len(provision.sentences)
            where = f"{document} {instruction.amendment_path} ({target.label})"

            # "indsættes som N. pkt." forudsætter præcis N-1 punktummer i forvejen.
            insert_as = re.search(r"indsættes\s+som\s+(\d+)\.\s*pkt", instruction.text)
            if insert_as:
                wanted = int(insert_as.group(1))
                if wanted == count + 1:
                    insert_ok += 1
                else:
                    insert_bad.append(f"{where}: vil indsaette {wanted}. pkt., men vi finder {count}")
                continue

            # En henvisning til "N. pkt." forudsætter mindst N punktummer.
            if target.sentence_numbers:
                highest = max(target.sentence_numbers)
                if highest <= count:
                    sentence_ok += 1
                else:
                    sentence_bad.append(f"{where}: peger paa {highest}. pkt., men vi finder {count}")

    print(f"=== {path}: {len(documents)} love i changed_by")
    print(f"--- {total} aendringspunkter")
    print(f"--- {no_target} uden opmaerket maal, {unparsed} hvor maalet ikke kunne laeses")
    print(f"--- {missing_paragraph} peger paa en paragraf der ikke findes i teksten")
    print(f"--- {missing_stk} peger paa et stykke der ikke findes i paragraffen")
    print()
    print("--- kontrol af punktumsegmenteringen:")
    print(f"    {insert_ok} korrekte af {insert_ok + len(insert_bad)} 'indsaettes som N. pkt.'")
    print(f"    {sentence_ok} korrekte af {sentence_ok + len(sentence_bad)} henvisninger til N. pkt.")

    for problem in insert_bad[:8] + sentence_bad[:8]:
        print(f"    FEJL {problem}")
    return 0


def step_tree(eli: str, paragraph_id: str, stk_number: str = "") -> int:
    """Vis XML-traeet under et stykke, saa nummer- og punktumniveauer kan ses."""
    import xml.etree.ElementTree as ElementTree

    import lex_dania

    try:
        body = lex_dania.fetch_document_xml(eli.strip("/"))
        root = ElementTree.fromstring(body)
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        print(f"Kunne ikke behandle {eli}: {error}")
        return 1

    wanted = paragraph_id.upper().replace(" ", "").lstrip("§")
    for paragraf in root.iter("Paragraf"):
        if (paragraf.get("localId") or "").upper() != wanted:
            continue

        for index, stk in enumerate(paragraf.iter("Stk"), start=1):
            label = ""
            for child in stk:
                if child.tag == "Explicatus":
                    label = lex_dania.element_text(child)
                    break
            match = lex_dania.STK_NUMBER.search(label)
            number = int(match.group(1)) if match else index
            if stk_number and number != int(stk_number):
                continue

            print(f"=== stk. {number}")

            def walk(element: ElementTree.Element, depth: int) -> None:
                indent = "    " * depth
                snippet = lex_dania.element_text(element)[:80]
                print(f"{indent}<{element.tag}> {element.attrib or ''}")
                if not list(element):
                    print(f"{indent}    {snippet}")
                for sub in element:
                    walk(sub, depth + 1)

            for child in stk:
                walk(child, 1)
        return 0

    print(f"Fandt ikke paragraf {paragraph_id!r}")
    return 1


def step_text(eli: str, paragraph_id: str, stk: str = "") -> int:
    """Vis den fulde tekst af et stykke, ét <Linea> ad gangen."""
    import lex_dania

    try:
        body = lex_dania.fetch_document_xml(eli.strip("/"))
        provisions = lex_dania.extract_provisions(body)
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        print(f"Kunne ikke behandle {eli}: {error}")
        return 1

    wanted = paragraph_id.upper().replace(" ", "").lstrip("§")
    hits = [item for item in provisions if item.paragraph_id.upper() == wanted]
    if stk:
        hits = [item for item in hits if item.stk_number == int(stk)]

    if not hits:
        print(f"Fandt ikke paragraf {paragraph_id!r} i {eli}")
        return 1

    for provision in hits:
        print(f"=== {provision.label}  ({len(provision.sentences)} <Linea>)")
        for number, sentence in enumerate(provision.sentences, start=1):
            print(f"--- {number}. <Linea>:")
            print(f"    {sentence}")
        print()
    return 0


def step_sentences(eli: str) -> int:
    """Maaler kvaliteten af punktumsegmenteringen mod lovens egne henvisninger.

    Naar loven selv skriver "jf. dog 4. pkt.", skal stykket have mindst fire
    punktummer. Finder vi faerre, er segmenteringen for grov. Kontrollen er ikke
    perfekt: en henvisning kan pege paa et andet stykke, saa et hoejt tal er et
    signal, ikke et bevis.
    """
    import lex_dania

    path = eli.strip("/")
    try:
        body = lex_dania.fetch_document_xml(path)
        provisions = lex_dania.extract_provisions(body)
    except (lex_dania.FetchError, ElementTree.ParseError) as error:
        print(f"Kunne ikke behandle {path}: {error}")
        return 1

    total_lineas = sum(len(provision.lineas) for provision in provisions)
    total_sentences = sum(len(provision.sentences) for provision in provisions)
    split_lineas = sum(
        1
        for provision in provisions
        for linea in provision.lineas
        if len(lex_dania.split_sentences(linea)) > 1
    )

    conflicts: list[tuple[lex_dania.Provision, int, int]] = []
    checked = 0
    for provision in provisions:
        highest = lex_dania.highest_referenced_sentence(provision.text)
        if not highest:
            continue
        checked += 1
        count = len(provision.sentences)
        if highest > count:
            conflicts.append((provision, highest, count))

    print(f"=== {path}")
    print(f"--- {len(provisions)} stykker, {total_lineas} <Linea>, {total_sentences} punktummer")
    print(f"--- {split_lineas} <Linea> rummer mere end ét punktum")
    print(f"--- {checked} stykker henviser til et punktumnummer og kan kontrolleres")
    print(f"--- {len(conflicts)} af dem har faerre punktummer end de selv henviser til")
    share = 100.0 * len(conflicts) / checked if checked else 0.0
    print(f"--- det er {share:.1f}% af de kontrollerbare stykker")

    if conflicts:
        print()
        print("--- stykker hvor segmenteringen ser for grov ud:")
        for provision, highest, count in conflicts[:10]:
            print(f"    {provision.label}: henviser til {highest}. pkt., men vi finder {count}")
    return 0


def step_structure(eli: str) -> int:
    """Vis en aendringslovs XML-struktur: hvordan er de nummererede punkter maerket op?"""
    import xml.etree.ElementTree as ElementTree

    url = f"https://retsinformation.dk/{eli.lstrip('/')}/dan/xml"
    status, content_type, body, error = fetch(url)
    print(f"=== {url} ({len(body)} bytes)")
    if error:
        print(f"    FEJL: {error}")
        return 1

    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as parse_error:
        print(f"Kunne ikke parse XML: {parse_error}")
        return 1

    def text_of(element: ElementTree.Element) -> str:
        return re.sub(r"\s+", " ", "".join(element.itertext())).strip()

    def walk(element: ElementTree.Element, depth: int = 0, limit: int = 60) -> int:
        if limit <= 0:
            return 0
        indent = "  " * depth
        attrs = " ".join(f"{k}={v!r}" for k, v in element.attrib.items())
        snippet = text_of(element)[:80]
        print(f"{indent}<{element.tag}> {attrs}")
        if not list(element):
            print(f"{indent}   {snippet}")
        used = 1
        for child in element:
            used += walk(child, depth + 1, limit - used)
            if used >= limit:
                break
        return used

    for paragraf in root.iter("Paragraf"):
        if "ligningslov" in text_of(paragraf).lower():
            print("--- Foerste Paragraf der naevner ligningsloven:")
            walk(paragraf, 0, 70)
            return 0

    print("--- Ingen Paragraf naevnte ligningsloven. Dokumentets struktur:")
    walk(root, 0, 80)
    return 0


def step_try(paths: list[str]) -> int:
    """Afproev flere kandidatstier og rapporter hvilke der giver JSON."""
    for path in paths:
        time.sleep(DELAY_SECONDS)
        url = f"https://www.retsinformation.dk/{path.lstrip('/')}"
        status, content_type, body, error = fetch(url, "application/json")
        is_json = "json" in content_type.lower()
        marker = "JSON" if is_json else "    "
        print(f"{marker} [{status}] {path}  ({len(body)} bytes)")
        if error:
            print(f"        {error}")
        elif is_json:
            head = body[:400].decode("utf-8", errors="replace").replace("\n", " ")
            print(f"        {head}")
    return 0


def step_references(eli_uri: str) -> int:
    """Findes relationen lov -> sagsforloeb -> lovforslag i references-endepunktet?

    ELI-metadata indeholder den ikke. SPA'en kalder api/document/{id}/references/{0|1},
    saa vi henter foerst dokumentets interne id fra .rdfa og proever derefter.
    """
    url = eli_uri if eli_uri.startswith("http") else f"https://www.retsinformation.dk/{eli_uri}"
    status, content_type, raw, error = fetch(f"{url}.rdfa", "application/json")
    if error or "json" not in content_type.lower():
        print(f"FEJL ved metadata: {error or content_type}")
        return 1

    triples = json.loads(raw.decode("utf-8", errors="replace"))
    id_local = ""
    title = ""
    for triple in triples:
        if triple.get("property") == "eli:id_local":
            id_local = str(triple.get("content", ""))
        if triple.get("property") == "eli:title_short":
            title = str(triple.get("content", ""))
    print(f"=== {title}  (id_local: {id_local or 'ikke fundet'})")
    print()

    if not id_local:
        print("Ingen id_local i metadata - kan ikke slaa referencer op.")
        return 1

    for flag in ("0", "1"):
        time.sleep(DELAY_SECONDS)
        api_url = f"https://www.retsinformation.dk/api/document/{id_local}/references/{flag}"
        status, content_type, body, error = fetch(api_url, "application/json")
        print(f"--- {api_url}")
        print(f"    status {status}, type {content_type}, {len(body)} bytes")
        if error:
            print(f"    FEJL: {error}")
            continue
        if "json" not in content_type.lower():
            print("    (ikke JSON - stien findes ikke i denne form)")
            continue
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as decode_error:
            print(f"    kunne ikke parse JSON: {decode_error}")
            continue
        print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
        print()
    return 0


def step_relations(eli_uri: str) -> int:
    """Vis kun relations-properties for et dokument, ikke hele metadatasaettet."""
    url = eli_uri if eli_uri.startswith("http") else f"https://www.retsinformation.dk/{eli_uri}"
    status, content_type, raw, error = fetch(f"{url}.rdfa", "application/json")
    print(f"=== {url}.rdfa -> status {status}, {len(raw)} bytes")
    if error or "json" not in content_type.lower():
        print(f"    FEJL: {error or content_type}")
        return 1

    triples = json.loads(raw.decode("utf-8", errors="replace"))
    counts: dict[str, int] = {}
    for triple in triples:
        prop = str(triple.get("property", ""))
        counts[prop] = counts.get(prop, 0) + 1
    print(f"--- {len(triples)} triples fordelt paa properties:")
    for prop, count in sorted(counts.items(), key=lambda item: -item[1]):
        print(f"    {count:4d}  {prop}")
    print()

    interesting = {
        "eli:changes",
        "eli:changed_by",
        "eli:consolidates",
        "eli:consolidated_by",
        "eli:commences",
        "eli:commenced_by",
        "eli:based_on",
        "eli:basis_for",
        "eli:title_short",
        "eli:type_document",
        "eli:in_force",
    }
    print("--- relations- og identitetstriples:")
    for triple in triples:
        prop = str(triple.get("property", ""))
        if prop in interesting:
            value = triple.get("content") or triple.get("resource") or ""
            print(f"    {prop:24s} {value}")
    return 0


def step_ft_relation(sample_size: int = 12) -> int:
    """Det afgoerende spoergsmaal: peger en retsakts metadata paa dens lovforslag?

    Vi tager et lille udsnit af lta-dokumenter fra sitemap'et, henter deres
    .rdfa-metadata og ser efter properties, der peger paa /ft/-URI'er.
    """
    status, _, body, error = fetch("https://retsinformation.dk/sitemap.xml?page=2")
    if error:
        print(f"FEJL ved sitemap: {error}")
        return 1

    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body.decode("utf-8", errors="replace"))
    lta = [loc for loc in locs if "/eli/lta/" in loc][:sample_size]
    print(f"=== Undersoeger {len(lta)} lta-dokumenter\n")

    ft_hits = 0
    for uri in lta:
        time.sleep(DELAY_SECONDS)
        status, content_type, raw, error = fetch(f"{uri}.rdfa", "application/json")
        if error or "json" not in content_type.lower():
            print(f"    {uri}: kunne ikke hente metadata ({error or content_type})")
            continue

        try:
            triples = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as decode_error:
            print(f"    {uri}: ugyldig JSON ({decode_error})")
            continue

        doc_type = ""
        ft_refs: list[str] = []
        for triple in triples:
            value = str(triple.get("content") or triple.get("resource") or "")
            prop = str(triple.get("property", ""))
            if prop == "eli:type_document":
                doc_type = value.rsplit("#", 1)[-1]
            if "/ft/" in value:
                ft_refs.append(f"{prop} -> {value}")

        marker = "FT!" if ft_refs else "   "
        print(f"{marker} {uri}  [{doc_type}]  {len(triples)} triples")
        for ref in ft_refs:
            print(f"        {ref}")
        if ft_refs:
            ft_hits += 1

    print()
    print(f"--- {ft_hits} af {len(lta)} dokumenter havde en /ft/-relation i metadata")
    return 0


def step_registry(term: str) -> int:
    """Slaa et emne op i lovregisteret, fx 'ligning'."""
    status, _, body, error = fetch(
        "https://www.retsinformation.dk/api/lawregistry", "application/json"
    )
    if error:
        print(f"FEJL: {error}")
        return 1

    entries = json.loads(body.decode("utf-8", errors="replace"))
    needle = term.lower()
    hits = [entry for entry in entries if needle in str(entry.get("label", "")).lower()]
    print(f"=== {len(hits)} emner matcher {term!r} (ud af {len(entries)})")
    for entry in hits:
        print(f"    id {entry.get('id'):>5}  {entry.get('label')}")
    return 0


def step_grep(needle: str, window: int = 160) -> int:
    """Vis konteksten omkring en streng i SPA'ens JS-bundt.

    Bruges til at se, hvilket id-format API-kaldene forventer. Vi udskriver kun
    smalle udsnit omkring traeffet.
    """
    status, _, body, error = fetch(f"https://www.retsinformation.dk{BUNDLE_PATH}")
    if error:
        print(f"FEJL: {error}")
        return 1

    text = body.decode("utf-8", errors="replace")
    hits = [match.start() for match in re.finditer(re.escape(needle), text)]
    print(f"=== {len(hits)} traef paa {needle!r} i bundtet ({len(text)} tegn)")
    for index, position in enumerate(hits[:10], start=1):
        start = max(0, position - window)
        end = min(len(text), position + len(needle) + window)
        print(f"--- traef {index}")
        print("    " + text[start:end].replace("\n", " "))
        print()
    return 0


def step_meta(url: str) -> int:
    """Vis kun <meta>- og <link>-tags.

    Spoergsmaalet er, om serveren renderer ELI-metadata som RDFa i <head>, selv om
    resten af siden bygges af JavaScript. Vi henter derfor ikke selve brodteksten.
    """
    status, content_type, body, error = fetch(url)
    print(f"=== {url} -> status {status}, type {content_type}, {len(body)} bytes")
    if error:
        print(f"    FEJL: {error}")
        return 1

    text = body.decode("utf-8", errors="replace")
    tags = re.findall(r"(?is)<(?:meta|link)\b[^>]*>", text)
    print(f"--- {len(tags)} meta/link-tags:")
    for tag in tags:
        print("    " + re.sub(r"\s+", " ", tag).strip())
    return 0


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "sitemap"
    if step == "sitemap":
        sys.exit(step_sitemap())
    elif step == "eli":
        sys.exit(step_eli_about())
    elif step == "page":
        sys.exit(step_sitemap_page(sys.argv[2] if len(sys.argv) > 2 else "2"))
    elif step == "doc":
        sys.exit(step_document(sys.argv[2] if len(sys.argv) > 2 else "eli/lta/2026/682"))
    elif step == "meta":
        sys.exit(step_meta(sys.argv[2]))
    elif step == "api":
        sys.exit(step_find_api(sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DOC))
    elif step == "get":
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 4000
        sys.exit(step_get(sys.argv[2], limit))
    elif step == "mine":
        sys.exit(
            step_mine(
                sys.argv[2] if len(sys.argv) > 2 else "eli/lta/2025/1500",
                int(sys.argv[3]) if len(sys.argv) > 3 else 40,
            )
        )
    elif step == "motiver":
        sys.exit(step_motiver(*sys.argv[2:5]))
    elif step == "daekning":
        sys.exit(step_daekning(*sys.argv[2:4]))
    elif step == "notes":
        sys.exit(step_notes(sys.argv[2]))
    elif step == "intro":
        sys.exit(step_intro(sys.argv[2]))
    elif step == "laws":
        sys.exit(step_laws(sys.argv[2]))
    elif step == "replay":
        sys.exit(step_replay(*sys.argv[2:5]))
    elif step == "instr":
        sys.exit(step_instructions(sys.argv[2]))
    elif step == "validate":
        sys.exit(step_validate(sys.argv[2]))
    elif step == "tree":
        sys.exit(step_tree(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else ""))
    elif step == "text":
        sys.exit(
            step_text(
                sys.argv[2],
                sys.argv[3],
                sys.argv[4] if len(sys.argv) > 4 else "",
            )
        )
    elif step == "sentences":
        sys.exit(step_sentences(sys.argv[2]))
    elif step == "struct":
        sys.exit(step_structure(sys.argv[2]))
    elif step == "chain":
        sys.exit(step_chain(sys.argv[2]))
    elif step == "touches":
        sys.exit(step_touches(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "§ 9 A"))
    elif step == "para":
        sys.exit(step_paragraf(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "§ 9 A"))
    elif step == "xml":
        sys.exit(step_xml(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "9 A"))
    elif step == "scope":
        sys.exit(
            step_law_scope(
                sys.argv[2],
                int(sys.argv[3]) if len(sys.argv) > 3 else 0,
            )
        )
    elif step == "findlaw":
        sys.exit(
            step_find_law(
                sys.argv[2] if len(sys.argv) > 2 else "ligningsloven",
                int(sys.argv[3]) if len(sys.argv) > 3 else 6,
            )
        )
    elif step == "oda":
        sys.exit(step_oda(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""))
    elif step == "try":
        sys.exit(step_try(sys.argv[2:]))
    elif step == "refs":
        sys.exit(step_references(sys.argv[2]))
    elif step == "rel":
        sys.exit(step_relations(sys.argv[2]))
    elif step == "ft":
        sys.exit(step_ft_relation(int(sys.argv[2]) if len(sys.argv) > 2 else 12))
    elif step == "registry":
        sys.exit(step_registry(sys.argv[2]))
    elif step == "grep":
        sys.exit(step_grep(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 160))
    else:
        print(f"Ukendt trin: {step}. Brug: sitemap | eli | page <n> | doc <eli-sti> | meta <url>")
        sys.exit(2)
