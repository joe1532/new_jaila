# Lovhistorik

Sporing af dansk lovtekst tilbage til den ændringslov, der indsatte den, og videre til
lovforslagets specielle bemærkninger. Målet er, at et svar om en bestemmelse kan pege på
det rigtige forarbejde — ikke et forarbejde, der handler om nabobestemmelsen eller om en
ordlyd, der blev ændret to år senere.

Komponenten er selvstændig. Den kan udvikles og køres uden resten af JAILA.

## Status

Empirisk afklaring er færdig, og datamodellen er beskrevet. Der er endnu ingen database
og ingen replay-motor. Det næste skridt er at oversætte ændringsinstrukser til
operationer og forsøge at anvende dem på lovteksten.

Det, der er målt indtil nu, står i [DATAMODEL.md](DATAMODEL.md). Kort fortalt:

- Retsinformation udleverer ELI-metadata som JSON ved at hænge `.rdfa` på en ELI-URI,
  og fuld Lex Dania-XML på `/dan/xml`. Ingen autentificering.
- Ændringsinstrukser er strukturelt opmærkede i XML'en. Målbestemmelsen står i sit eget
  element, og den nye tekst er adskilt fra instruksen.
- 151 ændringspunkter mod ligningsloven fordelt på 39 love dækkes af otte verbalmønstre.
- Koblingen til lovforslaget går via Folketingets Åbne Data på lovnummer plus dato, og
  accessionsnummeret til lovforslagets XML kan udledes deterministisk.

## Kom i gang

```bash
pip install -r lovhistorik/requirements.txt
```

Optæl konstruktionstyperne i testmængden:

```bash
python lovhistorik/probe.py mine eli/lta/2025/1500
```

Gennemse instrukserne enkeltvis i browseren:

```bash
streamlit run lovhistorik/app.py
```

Første kørsel henter omkring 40 dokumenter og tager cirka et minut, fordi vi bevidst
venter et sekund mellem kald. Dokumenterne caches i `lovhistorik/.cache/`, som ikke er
i git, så efterfølgende kørsler tager få sekunder.

## Filer

| Fil | Rolle |
| --- | --- |
| `DATAMODEL.md` | Datamodel, invarianter, teststrategi og alle empiriske fund |
| `lex_dania.py` | Hentning, cache og udtræk af ændringsinstrukser fra Lex Dania-XML |
| `app.py` | Streamlit-værktøj til at gennemse instrukser, mål og klassifikationer |
| `probe.py` | Udforskende kommandolinjeprobe mod Retsinformation og Folketingets data |
| `tls_check.py` | Diagnostik, hvis TLS-verifikation fejler lokalt |

`lex_dania.py` er den eneste implementering af udtræk og klassifikation. Både `app.py`
og `probe.py mine` bruger den, så de to ikke kan komme til at vise forskellige tal. Det
meste af `probe.py` er derimod udforskning, som skal smides væk.

## Vigtige forbehold

Klassifikation er ikke anvendelse. At en instruks kan henføres til et verbum betyder
kun, at vi ved, hvilken slags operation der er tale om — ikke at vi kan udføre den på
teksten. Først når operationer kan afspilles fra én lovbekendtgørelse til den næste og
sammenlignes med den faktiske tekst, ved vi, hvor stor en andel der reelt er dækket.

Replayet tekst er ikke gældende ret. Den bruges til at fastslå, hvor et tekststykke
stammer fra, og må ikke vises som lovtekst.
