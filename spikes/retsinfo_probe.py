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
