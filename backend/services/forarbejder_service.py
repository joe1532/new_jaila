"""Forarbejdsmotoren som JAILA-tjeneste.

Motoren selv ligger i `lovhistorik/` og bruges også af proben og Streamlit-appen. Dette
modul oversætter den til det, en webflade har brug for: JSON i stedet for dataklasser,
og en strøm af statuslinjer i stedet for et blokerende kald, fordi et koldt opslag tager
20-140 sekunder.

Der lægges ingen faglig logik her. Kommer der et andet svar i JAILA end i proben, er det
en fejl i dette lag, ikke en anden vurdering.

Kendte begrænsninger, som fladen selv oplyser om:

* Kæden går kun tilbage til omkring 2007, hvor Lex Dania-opmærkningen begynder.
* Kom et ændringspunkt til ved et ændringsforslag under udvalgsbehandlingen, står
  bemærkningen i betænkningen, som Folketinget kun udgiver som PDF bag botbeskyttelse.
* Bemærkningen dækker hele ændringspunktet og er ikke snævret ind til det stykke,
  der spørges om.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any, Iterator

BASE_DIR = Path(__file__).resolve().parents[2]
ENGINE_DIR = BASE_DIR / "lovhistorik"

# Motorens moduler importerer hinanden fladt (`import lex_dania`), fordi de er skrevet
# til at køre som scripts. Mappen skal derfor på sys.path frem for at blive importeret
# som en pakke.
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

# Et koldt opslag kan bruge op mod 1,1 GB hukommelse på et enkelt stort lovforslag og
# holder samtidig en fast pause mellem kald til Retsinformation. Kører to opslag
# samtidig, fordobles begge dele, og det er kilden — ikke os — der betaler. Derfor
# slipper kun ét tungt opslag igennem ad gangen. Prisen er, at bruger nummer to venter;
# det er en bevidst afvejning for et internt værktøj med få samtidige brugere.
_ENGINE_LOCK = threading.Lock()

# Hvor længe nummer to må vente på at komme til, før vi hellere siger det ligeud end at
# lade forbindelsen hænge. Sat over et typisk koldt opslag, men under nginx' 300 sekunder.
LOCK_WAIT_SECONDS = 180

# Mens der ventes på tur, sendes en linje med dette mellemrum. Uden den ville nginx se en
# tavs forbindelse og lukke den, længe før ventetiden var brugt.
WAIT_TICK_SECONDS = 5

# Flest led i kæden, et enkelt opslag må gå. Ligningsloven har omkring 13 tilbage til
# 2007, så grænsen rammer i praksis kun forsøg på at bede om alt.
MAX_STEPS = 40

# Så længe holder vi på svaret om, hvilken lovbekendtgørelse der er den nyeste. Kort nok
# til at en ny bekendtgørelse slår igennem samme dag, langt nok til at det ikke koster et
# netværkskald ved hvert klik.
NEWEST_TTL_SECONDS = 21600

_newest_cache: dict[str, tuple[float, tuple[str, list[str]]]] = {}
_chain_cache: dict[str, list[dict[str, str]]] = {}
_paragraph_cache: dict[str, list[str]] = {}


class EngineBusy(RuntimeError):
    """Et andet opslag optog motoren for længe."""


def _engine():
    """Hent motorens moduler.

    Importen er doven, så backend kan starte, selv om `lovhistorik/` mangler eller en af
    dens afhængigheder ikke er installeret. Fejlen viser sig da på den ene fane, der
    bruger den, i stedet for at vælte hele API'et.
    """
    import forarbejder
    import lex_dania

    return forarbejder, lex_dania


def engine_available() -> tuple[bool, str]:
    """Kan motoren indlæses? Returnerer (ja/nej, forklaring)."""
    if not ENGINE_DIR.is_dir():
        return (False, f"Mappen {ENGINE_DIR} findes ikke")
    try:
        _engine()
    except Exception as error:  # noqa: BLE001 - manglende modul, syntaksfejl, alt
        return (False, f"{type(error).__name__}: {error}")
    return (True, "")


def known_laws() -> list[dict[str, str]]:
    """De love, kæden er kørt igennem og målt på."""
    forarbejder, _ = _engine()
    return [{"name": name, "eli": eli} for name, eli in forarbejder.KNOWN_LAWS.items()]


def _newest(eli: str) -> tuple[str, list[str]]:
    """Lovens seneste bekendtgørelse, fundet fra et kendt holdepunkt."""
    _, lex_dania = _engine()
    now = time.monotonic()
    cached = _newest_cache.get(eli)
    if cached and now - cached[0] < NEWEST_TTL_SECONDS:
        return cached[1]
    result = lex_dania.newest_consolidation(eli)
    _newest_cache[eli] = (now, result)
    return result


def law_versions(eli: str) -> dict[str, Any]:
    """Lovens udgaver, nyeste først.

    Holdepunktet i lovlisten er ikke nødvendigvis den nyeste udgave. Uden dette opslag
    ville fladen tavst svare om en forældet retstilstand, når der kommer en ny
    bekendtgørelse.
    """
    forarbejder, lex_dania = _engine()
    start = eli.strip().strip("/")
    notice = ""
    try:
        newest, skipped = _newest(start)
        if skipped:
            notice = (
                f"Der er kommet {len(skipped)} nyere udgave"
                f"{'r' if len(skipped) > 1 else ''} siden {start}. Bruger {newest}."
            )
    except Exception as error:  # noqa: BLE001
        # Kontrollen er en ekstra sikkerhed, ikke en forudsætning. Fejler den, bruges
        # det kendte holdepunkt — men brugeren skal vide, at svaret kan være forældet.
        newest = start
        notice = (
            f"Kunne ikke kontrollere, om der findes en nyere udgave end {start}: {error}. "
            "Svaret bygger på den kendte udgave og kan være forældet."
        )

    if newest in _chain_cache:
        return {"newest_eli": newest, "versions": _chain_cache[newest], "notice": notice}

    chain = forarbejder.consolidation_chain(newest)
    if not chain:
        raise ValueError(f"Fandt ingen udgaver af loven fra {newest}")
    versions = [
        {"eli": step.eli, "label": step.label, "date": step.date} for step in chain
    ]
    _chain_cache[newest] = versions
    return {"newest_eli": newest, "versions": versions, "notice": notice}


def law_paragraphs(eli: str) -> list[str]:
    """Paragrafferne i én udgave af loven, i lovens egen rækkefølge.

    En bestemmelse, der først kom til senere, står ikke på listen — derfor hentes den
    for den valgte udgave og ikke for den nyeste.
    """
    _, lex_dania = _engine()
    key = eli.strip().strip("/")
    if key in _paragraph_cache:
        return _paragraph_cache[key]

    provisions = lex_dania.extract_provisions(lex_dania.fetch_document_xml(key))
    seen: list[str] = []
    for provision in provisions:
        if provision.paragraph_id and provision.paragraph_id not in seen:
            seen.append(provision.paragraph_id)
    _paragraph_cache[key] = seen
    return seen


def _context_block(change, law_name: str, paragraph_id: str) -> str:
    """Én ændring skrevet ud som fortolkningsbidrag til en sprogmodel.

    Formatet ligger her og ikke i frontenden, så chatten, en senere eksport og et
    eventuelt værktøjskald skriver det samme. Forbeholdene står *i* teksten, fordi en
    model, der kun får bemærkningen, ikke kan vide, hvor sikker koblingen er.
    """
    where = ", ".join(place for place, _ in change.places) or "hele paragraffen"
    lines = [
        f"{law_name} § {paragraph_id} — {change.label} ({where})",
        f"Indarbejdet i {change.consolidation}.",
        "",
        "Ændringen:",
        change.text.strip(),
    ]

    if not change.note.found:
        lines += ["", f"Ingen specielle bemærkninger fundet: {change.note.source}."]
        stage = getattr(change.note, "committee", None)
        if stage and stage.report_url:
            lines.append(f"Bemærkningen står i {stage.report_title}: {stage.report_url}")
        return "\n".join(lines)

    confirmation = change.confirm(paragraph_id)
    if confirmation.ok:
        reliability = f"Koblingen er bekræftet: {confirmation.how}."
    elif confirmation.suspect:
        reliability = (
            "Koblingen er ikke bekræftet: ændringen indsætter tekst, som bemærkningen "
            "burde gengive, men den nævner hverken paragraffen eller ordlyden. "
            "Bemærkningen kan høre til et andet ændringspunkt."
        )
    else:
        reliability = (
            "Koblingen kan ikke efterprøves: ændringen ophæver eller omnummererer uden "
            "at indsætte tekst, så der er intet at genfinde i bemærkningen."
        )

    scope = (
        "Bemærkning til netop dette ændringspunkt."
        if change.note.precise
        else "Bemærkning til hele ændringsparagraffen — lovforslaget har intet 'Til nr.'."
    )
    lines += [
        "",
        f"Specielle bemærkninger fra {change.note.source}. {scope} {reliability}",
        "",
        change.note.text.strip(),
    ]
    return "\n".join(lines)


def _serialise_change(change, law_name: str, paragraph_id: str) -> dict[str, Any]:
    confirmation = change.confirm(paragraph_id)
    stage = getattr(change.note, "committee", None)
    return {
        "label": change.label,
        "consolidation": change.consolidation,
        "places": [place for place, _ in change.places],
        "sentences": [sentences for _, sentences in change.places if sentences],
        "inserted": change.inserted,
        "text": change.text,
        "document_url": f"https://www.retsinformation.dk/{change.document_path}",
        "note_found": change.note.found,
        "note_text": change.note.text,
        "note_source": change.note.source,
        "note_url": change.note.url,
        "note_precise": change.note.precise,
        "bill_number": change.note.bill_number,
        "confirmed": confirmation.ok,
        "confirmation_how": confirmation.how,
        "suspect": confirmation.suspect,
        "report_title": stage.report_title if stage else "",
        "report_url": stage.report_url if stage else "",
        "context_block": _context_block(change, law_name, paragraph_id),
    }


def _serialise_history(history) -> dict[str, Any]:
    changes = [
        _serialise_change(change, history.law_name, history.paragraph_id)
        for change in history.changes
    ]
    return {
        "law_name": history.law_name,
        "paragraph_id": history.paragraph_id,
        "start": history.start,
        "chain": [{"eli": step, "found": found} for step, found in history.chain],
        "reached_end": history.reached_end,
        "paragraph_exists": history.paragraph_exists,
        "problems": history.problems,
        "notices": history.notices,
        "with_note": history.with_note,
        "confirmed": history.confirmed,
        "changes": changes,
    }


def _release_when_finished(worker: threading.Thread) -> None:
    """Giv turen fri, når en forladt kørsel er løbet ud."""
    worker.join()
    _ENGINE_LOCK.release()


def history_events(eli: str, paragraph: str, steps: int) -> Iterator[dict[str, Any]]:
    """Kør et forarbejdsopslag, og send statuslinjer undervejs.

    Motoren er blokerende og melder sin fremdrift gennem et kald. Den køres derfor i en
    tråd, mens denne generator videresender meldingerne, så fladen kan vise, hvad der
    sker, i stedet for at stå tom i op mod to minutter.
    """
    forarbejder, lex_dania = _engine()
    safe_steps = max(1, min(int(steps or 1), MAX_STEPS))

    # Vent på tur i korte spring frem for ét langt. Ventetiden kan være minutter, og en
    # forbindelse, der intet sender så længe, bliver lukket af nginx undervejs.
    waited = 0
    while not _ENGINE_LOCK.acquire(timeout=WAIT_TICK_SECONDS):
        waited += WAIT_TICK_SECONDS
        if waited >= LOCK_WAIT_SECONDS:
            raise EngineBusy(
                "Et andet forarbejdsopslag kører stadig. Motoren tager kun ét ad gangen "
                "for ikke at belaste Retsinformation. Prøv igen om et øjeblik."
            )
        yield {
            "type": "progress",
            "message": f"Venter på, at et andet opslag bliver færdigt ({waited} s) …",
        }

    updates: queue.Queue = queue.Queue()
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["history"] = forarbejder.paragraph_history(
                eli, paragraph, safe_steps, lambda message: updates.put(message)
            )
        except (lex_dania.FetchError, ElementTree.ParseError) as error:
            outcome["error"] = f"Kunne ikke hente materialet: {error}"
        except Exception as error:  # noqa: BLE001 - en uventet fejl må ikke hænge fladen
            outcome["error"] = f"Opslaget fejlede: {type(error).__name__}: {error}"
        finally:
            updates.put(None)

    worker = threading.Thread(target=run, name="forarbejder", daemon=True)
    try:
        worker.start()
        yield {"type": "progress", "message": "Starter opslaget …"}
        while True:
            message = updates.get()
            if message is None:
                break
            yield {"type": "progress", "message": message}
        worker.join()
    finally:
        if worker.is_alive():
            # Klienten lukkede forbindelsen midt i opslaget. Arbejderen kan ikke standses
            # midt i et netværkskald, så den kører færdig — og den skal blive ved med at
            # holde turen imens. Gav vi låsen fri her, ville næste opslag ramme
            # Retsinformation samtidig med et, vi troede var væk. Arbejdet er ikke spildt:
            # det, den når at hente, ligger i diskcachen bagefter.
            threading.Thread(
                target=_release_when_finished, args=(worker,), daemon=True
            ).start()
        else:
            _ENGINE_LOCK.release()

    if "error" in outcome:
        yield {"type": "error", "detail": outcome["error"]}
        return
    yield {"type": "done", "history": _serialise_history(outcome["history"])}
