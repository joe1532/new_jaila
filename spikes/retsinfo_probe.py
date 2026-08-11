"""Engangs-probe mod Retsinformation.

Formål: besvare de empiriske spørgsmål i backend/LOVHISTORIK_DATAMODEL_v1.md, før
der bygges databaselag. Scriptet henter et lille antal URL'er og rapporterer, hvad
der faktisk kommer tilbage.

Denne kode skal smides væk. Den er ikke en del af motoren.

TLS: maskinen har TLS-inspektion, så Pythons certifi-bundle afvises. Vi bruger
truststore, der validerer via Windows' eget trust store. På en Linux-server uden
inspektion er det ikke nødvendigt.
"""

from __future__ import annotations

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
