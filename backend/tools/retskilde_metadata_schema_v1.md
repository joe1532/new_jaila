# Retskilde Metadata v1 (DBO)

Formaal: robust soegning og entydig identifikation uden store alias-lister pr. artikel.

## Designprincip

- Strukturerede felter bruges til praecision (`instrument_id`, `section_type`, `section_number`).
- `search_aliases` bruges kun som fallback for sproglige variationer.
- `source_id` er unik pr. versioneret chunk.
- `instrument_id` er stabil logisk noegle pa tværs af versioner.

## Felter (minimum)

```json
{
  "source_id": "norden_dbo_art15_v1996",
  "instrument_id": "norden_dbo",
  "title": "DBO mellem de nordiske lande",
  "document_type": "Dobbeltbeskatningsoverenskomst",
  "jurisdiction": "norden",
  "section_type": "article",
  "section_number": "15",
  "section_label": "artikel 15",
  "canonical_path": "/documents/dbo/norden/norden_dbo_art15_v1996/source.pdf",
  "sha256": "<sha256>",
  "status": "active",
  "search_aliases": ["dbo", "norden", "art 15"]
}
```

## Feltregler

- `source_id`: unik, stabil noegle for den konkrete version/chunk.
- `instrument_id`: stabil noegle for dokumentfamilien (fx `norden_dbo`, `dk_de_dbo`).
- `section_type`: `article` | `protocol` | `document`.
- `section_number`: numerisk streng for artikler (`"15"`), tom for ikke-numeriske sektioner.
- `section_label`: visningslabel (fx `artikel 15`, `protokol`).
- `status`: `active` eller `deprecated`.

## Parser-regler (query -> filter)

Eksempel: `dansk tysk dbo art 15`

1. Genkend instrument:
   - landeterm -> `jurisdiction` eller direkte `instrument_id`.
2. Genkend sektion:
   - `art|artikel|article <nummer>` -> `section_type=article`, `section_number=<nummer>`.
3. Soeg i indeks med:
   - hard filters paa strukturerede felter.
4. Rank:
   - `status=active` foerst, derefter nyeste version.

## Hvorfor denne model

- Undgaar eksploderende alias-lister.
- Giver entydig afgraensning naar mange DBO'er har fx `art 15`.
- Skalerer bedre ved nye jurisdiktioner og flere versioner.
