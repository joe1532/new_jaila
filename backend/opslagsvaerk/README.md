# Opslagsværk (lag A + DJV-noder)

Strukturerede noder. Ligger her og ikke i `data/`, fordi den mappe er
gitignored og derfor ikke kommer med i deploy.

## Ligningsloven

Tre LBKG'er: 1735 (2021), 42 (2023), 1500 (2025). Opslaget bruger altid 1500.
De to ældre er til stabilitetstest.

`aendringer-2021-2025.json` er de to hop 1735→42 og 42→1500 fra høstens
`rapport.jsonl`. `oldText`/`newText` er ikke med; bindestreg er forudberegnet
som `cosmetic`.

Genimport når høsten opdateres:

```
python -m backend.tools.import_opslagsvaerk
```

## DJV 2026-2

Flade noder fra json-cleanerens rensede filer. Adressen er nøglen, fx
`C.A.7.3.2`. Binding til LL § læses af overskriften (stk. når det står der)
og af afsnittets Regel/indledning, ikke af praksistabellen. `chunks.jsonl`
bruges ikke.

| Fil | Kilde |
|---|---|
| `c-a.json` | `DJV C.A.json` |
| `c-f.json` | `DJV C.F.json` |
| `c-h.json` | `DJV C.H.json` |
| `edition.json` | `2026-2` |

Genimport:

```
python -m backend.tools.import_djv
```
