# Lovhistorik

Sporing af dansk lovtekst tilbage til den ændringslov, der indsatte den, og videre til
lovforslagets specielle bemærkninger. Målet er, at et svar om en bestemmelse kan pege på
det rigtige forarbejde — ikke et forarbejde, der handler om nabobestemmelsen eller om en
ordlyd, der blev ændret to år senere.

Komponenten er selvstændig. Den kan udvikles og køres uden resten af JAILA.

## Status

Opslag fra en lovparagraf til dens specielle bemærkninger virker og kan bruges. På
ligningsloven findes der en bemærkning til 96 af 104 ændringspunkter, og 95,8 % af dem
citerer selv målbestemmelsen. Replay-motoren, som afspiller ændringer på selve
lovteksten, er derimod stadig under arbejde.

Det, der er målt indtil nu, står i [DATAMODEL.md](DATAMODEL.md). Kort fortalt:

- Retsinformation udleverer ELI-metadata som JSON ved at hænge `.rdfa` på en ELI-URI,
  og fuld Lex Dania-XML på `/dan/xml`. Ingen autentificering.
- Ændringsinstrukser er strukturelt opmærkede i XML'en. Målbestemmelsen står i sit eget
  element, og den nye tekst er adskilt fra instruksen.
- 151 ændringspunkter mod ligningsloven fordelt på 39 love dækkes af otte verbalmønstre.
- Koblingen til lovforslaget går via Folketingets Åbne Data på lovnummer plus dato, og
  accessionsnummeret til lovforslagets XML kan udledes deterministisk.
- Lovforslagets paragrafnumre er ikke den vedtagne lovs. Bemærkningen findes derfor ved
  at genkende instruksens tekst, ikke ved at slå nummeret op.

## Kom i gang

```bash
pip install -r lovhistorik/requirements.txt
```

Slå forarbejder op i browseren — vælg lov og paragraf, og få de specielle bemærkninger
til hver ændring, nyeste først:

```bash
streamlit run lovhistorik/app.py
```

Det samme fra kommandolinjen, hvis man vil se hele udskriften:

```bash
python lovhistorik/probe.py motiver eli/lta/2025/1500 9C 8
```

Sidste tal er antallet af led i kæden af lovbekendtgørelser. Otte led rækker typisk til
2014, fjorten til 2006, hvor Lex Dania-opmærkningen begynder.

Første opslag på en ny paragraf tager 20-45 sekunder, fordi vi bevidst venter et sekund
mellem kald til kilderne. Dokumenterne caches i `lovhistorik/.cache/`, som ikke er i
git, så efterfølgende opslag er hurtigere.

## Filer

| Fil | Rolle |
| --- | --- |
| `DATAMODEL.md` | Datamodel, invarianter, teststrategi og alle empiriske fund |
| `lex_dania.py` | Hentning, cache og udtræk af ændringsinstrukser fra Lex Dania-XML |
| `forarbejder.py` | Fra en lovparagraf til dens specielle bemærkninger |
| `replay.py` | Afspilning af ændringer på lovteksten (under arbejde) |
| `app.py` | Streamlit-flade: forarbejdsopslag og inspektion af instrukser |
| `probe.py` | Udforskende kommandolinjeprobe mod Retsinformation og Folketingets data |
| `tls_check.py` | Diagnostik, hvis TLS-verifikation fejler lokalt |

`lex_dania.py` er den eneste implementering af udtræk og klassifikation, og
`forarbejder.py` den eneste af forarbejdssøgningen. Både `app.py` og `probe.py` bruger
dem, så de to ikke kan komme til at vise forskellige tal. Det meste af `probe.py` er
derimod udforskning, som skal smides væk.

## Vigtige forbehold

Klassifikation er ikke anvendelse. At en instruks kan henføres til et verbum betyder
kun, at vi ved, hvilken slags operation der er tale om — ikke at vi kan udføre den på
teksten. Først når operationer kan afspilles fra én lovbekendtgørelse til den næste og
sammenlignes med den faktiske tekst, ved vi, hvor stor en andel der reelt er dækket.

Replayet tekst er ikke gældende ret. Den bruges til at fastslå, hvor et tekststykke
stammer fra, og må ikke vises som lovtekst.
