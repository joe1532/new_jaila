# JAILA SKAT — PostgreSQL-skema

Nummererede SQL-migrations til afgørelseskorpusset (`jaila.skat.chunk.v1`).
Backend har ikke Alembic. Filerne her er migrationssystemet.

Korpus (importeret i `jaila_skat`):

- 11.707 dokumenter, 295.697 chunks, 280.548 referencer
- 2001–2026, chunker 1.0.1, `schema_version=jaila.skat.chunk.v1`
- embeddings: `text-embedding-3-large`, 1536 dimensioner, `inner_product`
- aktivt vektorindeks: `skat.chunk_embeddings_hnsw_ip_v2_idx` (må ikke genbygges af retrieval-CLI)

## Filer

| Fil | Indhold |
|---|---|
| `migrations/001_extensions.sql` | `vector`, `pgcrypto`, `pg_trgm`, `unaccent`, skema `skat`, immutable unaccent |
| `migrations/002_skat_schema.sql` | Tabeller, constraints, indekser, lookup-funktioner, grants |
| `migrations/003_chunk_embeddings_hnsw.sql` | HNSW **efter** bulk-import af embeddings. Ikke standard. |
| `migrations/004_import_audit.sql` | `import_runs` til genoptagelig import-audit |
| `migrations/005_question_number_text.sql` | `chunks.question_number` er text |
| `migrations/006_provenance_and_reference_occurrences.sql` | inferred year + referenceforekomster |
| `migrations/007_lexical_retrieval_indexes.sql` | Trigram-indekser til lexical retrieval. Ingen embeddings. |
| `migrations/008_embedding_audit.sql` | embedding_runs, requestlog og query_embeddings. Ingen HNSW. |

Importeren er `python -m backend.db.skat_import`. Den ændrer ikke JSONL og genererer ikke embeddings.

```powershell
$root = "C:\Users\minel\OneDrive\- Projekter\Vector Store\output\skat_info_personskat_chunks\v1"
python -m backend.db.skat_import preflight --input-root $root
python -m backend.db.skat_import dry-run --input-root $root --year 2026
# Først efter særskilt godkendelse:
python -m backend.db.skat_import import-documents --input-root $root
python -m backend.db.skat_import import-year --year 2026 --input-root $root
python -m backend.db.skat_import verify --year 2026 --input-root $root
```

## Lokalt

Kræver Docker Desktop (image `pgvector/pgvector:pg16`). Postgres/pgvector er ikke en del af Windows-installationen.

```powershell
cd "C:\Users\minel\OneDrive\- Projekter\JAILA OpenAI"
pip install -r backend/db/requirements.txt
docker compose -f backend/db/docker-compose.yml up -d
# Sæt JAILA_SKAT_DATABASE_URL fra .env (password må ikke committes).
python backend/db/migrate.py
python -m unittest tests.test_skat_schema tests.test_skat_retrieval tests.test_skat_embed
```

Uden `JAILA_SKAT_DATABASE_URL` springer testene over.

## SKAT-retrieval CLI

`python -m backend.db.skat_retrieval` er read-only. Den læser kun
`JAILA_SKAT_DATABASE_URL`, udfører `SELECT` og `SET LOCAL`, og åbner
forbindelsen med `SET TRANSACTION READ ONLY`. Ingen migrationer, ingen
nye embeddings, og HNSW-indekset røres ikke.

Til senere MCP/API-brug anbefales en særskilt PostgreSQL-login med rollen
`jaila_app` (kun SELECT/EXECUTE). Brug ikke `jaila_ingest` til retrieval.

### Installation og kørsel

```powershell
cd "C:\Users\minel\OneDrive\- Projekter\JAILA OpenAI"
pip install -r backend/db/requirements.txt
# JAILA_SKAT_DATABASE_URL sættes i .env eller i sessionen. Password må ikke hardcodes i scripts.
python -m backend.db.skat_retrieval search --query "fradrag for moms"
```

### Kommandoer

```text
python -m backend.db.skat_retrieval search --query "..."
python -m backend.db.skat_retrieval summary --identifier "SKM..."
python -m backend.db.skat_retrieval result --identifier "SKM..."
python -m backend.db.skat_retrieval reasoning --identifier "SKM..."
python -m backend.db.skat_retrieval references --identifier "SKM..."
python -m backend.db.skat_retrieval evaluate --dataset backend/db/eval/skat_retrieval_eval_v1.jsonl
```

Fælles argumenter (lookup-kommandoer ignorerer søgefiltre):

| Argument | Betydning |
|---|---|
| `--format text\|json\|jsonl` | Standard `text` (bagudkompatibelt) |
| `--limit N` | Maks. antal søgetræf (standard 10) |
| `--include-references` | Vedhæft referencer på search-hits |
| `--year-from YYYY` / `--year-to YYYY` | Publikationsår |
| `--document-type TYPE` | `legal_documents.document_type` / chunk-felt |
| `--topic TOPIC` | `main_topic` eller `subject_terms` |
| `--section-type TYPE` | `chunks.section_type` |
| `--debug` | Stack trace på stderr |

`search` har desuden `--mode auto|hybrid|vector|lexical|exact` (standard
`auto`) samt de eksisterende flag `--exact-vector` og `--high-risk`.
Begge flag aktiverer den samme udtømmende vector-scan uden HNSW som
`--mode exact`.

### Søgemodes

| Mode | Betydning |
|---|---|
| `auto` | Eksisterende A–F-routing. A–E er deterministiske opslag uden embeddings. Topical/F bruger hybrid. |
| `hybrid` | Lexical + vector med deterministisk RRF. Standard for `retrieve()`. |
| `vector` | Ren vektorsøgning via HNSW v2. |
| `lexical` | Dansk FTS/metadata. Ingen embeddings. |
| `exact` | Udtømmende vector-scan uden HNSW (samme sti som `--exact-vector` / `--high-risk`). Langsommere, men ikke approximate. |

Ved approximate vector/hybrid sættes `SET LOCAL hnsw.ef_search = 800` i
samme transaktion, så værdien ikke lækker i en connection pool. Indekset
er `chunk_embeddings_hnsw_ip_v2_idx`.

Query-vektorer hentes i prioriteret rækkefølge: (1) en allerede gemt,
kompatibel række i `skat.query_embeddings` (eval eller samme
`query_text_sha256` som `Forespørgsel:\n` plus query-teksten);
(2) on-demand OpenAI-kald (`text-embedding-3-large`, 1536 dimensioner,
`encoding_format=float`) som **ikke** gemmes i databasen eller på disk;
(3) fallback. Nøglen læses kun fra `OPENAI_API_KEY`. A–E og `--mode lexical`
kalder aldrig OpenAI.

`--mode auto` og `--mode hybrid` falder ved manglende nøgle eller
embeddingfejl tilbage til lexical med `effective_mode=lexical` og
`fallback_reason` `missing_openai_api_key`, `query_embedding_api_error`
eller `invalid_query_embedding`. `--mode vector`, `--mode exact`,
`--exact-vector` og `--high-risk` må ikke falde tilbage til lexical: de
returnerer `query_embedding_unavailable` med exit code 4.

Approximate vector/hybrid bruger `SET LOCAL hnsw.ef_search = 800` og
kandidatbegrænsning (lexical og HNSW top 200) før RRF og hydration.
Exact kører i to SQL-trin i samme read-only transaktion: først inner-product
scan på `chunk_embeddings` med indexscan/bitmapscan slået fra (kandidatpulje
200/500/1000), derefter `SET LOCAL enable_* TO DEFAULT` og metadata/tekst via
almindelige indeksopslag. JSON-søgning inkluderer `timings_ms` og
`embedding_usage` (`null` når der ikke er foretaget API-kald).

Standard er ét bedste chunk pr. dokument. Scores er rangeringsværdier, ikke
sandsynligheder.

### Lovhenvisninger

Entydige lovhenvisninger normaliseres generisk i `document_references` som
lovnøgle, paragraf/start-slut, stykke, nummer og litra. Den originale
`cited_identifier` bevares. De 174 kendte retskilde- og
bekendtgørelsesforkortelser foldes til samme lovnøgle som deres populære titel.
Eksempelvis behandles `KSL § 1`, `KSL§1` og `kildeskattelovens § 1` som samme
reference. Parseren understøtter også `stk.`, `nr.`, `litra`, intervaller,
flere referencer samt kendte flerordsnavne som `lov om kreditaftaler`.

Ved flere referencer kræver `og` som udgangspunkt, at dokumentet matcher dem
alle; `eller` kræver mindst én. En specifik underhenvisning rangeres før en
fallback til samme hovedparagraf. Migration `010_structured_law_references.sql`
opretter felterne og indekset. Eksisterende rækker backfilles idempotent med:

```powershell
python -m backend.db.backfill_law_references
```

En ren lovhenvisning bruger i `auto` det strukturerede, lexical referencespor
uden embedding eller almindelig full-text-søgning. Et længere spørgsmål bruger
fortsat hybrid. Hvis det indeholder en eksplicit lovhenvisning, køres den
semantiske rangering inden for de strukturerede referencekandidater; semantik
kan dermed omrangere relevante dokumenter uden at trække dokumenter fra en
anden lov ind. En bar paragraf som `§ 1` er bevidst ikke en struktureret
lovreference, fordi lovidentiteten er tvetydig.

### Formater, stdout og stderr

- `text`: menneskeligt output på stdout, inkl. redacted `forbindelse ...`.
- `json`: stdout er **udelukkende ét** UTF-8 JSON-objekt (`ensure_ascii=false`,
  danske tegn bevares). Logs og fejl går til stderr.
- `jsonl`: første linje er `record_type=query_metadata` (søgemetadata uden
  resultatliste). Hver efterfølgende linje er én selvstændig JSON-resultatrække
  med `record_type=result`. Lookup-kommandoer bruger tilsvarende metadata-linje
  plus én linje pr. chunk/reference.

JSON-fejl skrives til **stderr** med non-zero exit code. Ingen stack trace
uden `--debug`. Hemmeligheder, embeddingstekst og query-vektorer logges ikke.

### Exit codes

| Kode | Betydning |
|---|---|
| 0 | Succes |
| 2 | Ugyldige CLI-argumenter |
| 3 | Dokument/identifier ikke fundet |
| 4 | Databaseforbindelse eller query-fejl |
| 5 | Integritetsfejl eller ugyldigt databaseoutput |

Eksempel på JSON-fejl (stderr):

```json
{
  "schema_version": "1.0",
  "error": {
    "code": "identifier_not_found",
    "message": "Dokumentet blev ikke fundet",
    "identifier": "SKM2099.1.X"
  }
}
```

### JSON-kontrakt (`search`)

Stabile felter inkluderer `schema_version`, `query`, `requested_mode`,
`effective_mode`, `fallback_reason`, `resolved_route` (A–F),
`retrieval_mode`, `limit`, `filters` (manglende filtre er JSON `null`),
`result_count`, `elapsed_ms`, `timings_ms`, `embedding_usage` og
`results[]`. Hvert resultat har `ranking_signals` kun for signaler der
faktisk er brugt (`score_kind`, eventuelt `lexical_rank` / `vector_rank` /
`rrf_score`).

`summary` returnerer hele `legal_documents.summary` uden klip.
`result` returnerer `is_final_result`-chunks i `chunk_index`-orden plus
`combined_text`. `reasoning` er `authoritative_reasoning` uden
`prior_instance` (`prior_instance_omitted` angives eksplicit).
`references` returnerer både incoming og outgoing, inkl. dublette
forekomster og `occurrence_index`.

### PowerShell

```powershell
python -m backend.db.skat_retrieval summary --identifier "SKM2026.46.BR" --format json |
  ConvertFrom-Json |
  Select-Object identifier, skm_number, summary_length
python -m backend.db.skat_retrieval search --query "beskatning af udenlandsk indkomst" --mode hybrid --limit 10 --format json
```

### Python

```python
import json
import os
import subprocess

env = os.environ.copy()  # JAILA_SKAT_DATABASE_URL skal allerede være sat
proc = subprocess.run(
    [
        "python", "-m", "backend.db.skat_retrieval",
        "summary", "--identifier", "SKM2026.46.BR", "--format", "json",
    ],
    check=False,
    capture_output=True,
    text=True,
    encoding="utf-8",
    env=env,
)
if proc.returncode != 0:
    error = json.loads(proc.stderr)
    raise SystemExit(error["error"]["message"])
payload = json.loads(proc.stdout)
print(payload["skm_number"], payload["summary_length"])
```

Draft-evalueringssættet er automatisk udledt (`gold_status=draft`) og er ikke fagligt godkendt.

Embedding-pilot (`text-embedding-3-large`, 1536 dimensioner). Nøgle kun fra `OPENAI_API_KEY`. Kør ikke `--with-hnsw` og ikke fuld korpus uden særskilt godkendelse:

```powershell
python -m backend.db.skat_embed dry-run
python -m backend.db.skat_embed pilot
python -m backend.db.skat_embed resume
python -m backend.db.skat_embed verify
python -m backend.db.skat_embed query --text "fradrag for moms"
```

HNSW (først når hele korpussets vektorer er indlæst):

```powershell
python backend/db/migrate.py --with-hnsw
```

## Roller

- `jaila_app` — SELECT på dokumenter, chunks, referencer, embeddings og views; EXECUTE på lookup-funktioner. **Anbefalet login-rolle til retrieval-CLI og senere MCP/API.**
- `jaila_ingest` — skrivning. Må ikke bruges af retrieval.

Login-brugere oprettes uden for migrations (password i `.env` / `/etc/jaila-backend.env`):

```sql
GRANT jaila_app TO <app_login>;
GRANT jaila_ingest TO <ingest_login>;
```

`JAILA_SKAT_DATABASE_URL` hører i `.env` / `/etc/jaila-backend.env`, ikke i git.

Projektet bruger ikke Supabase. Der er ingen RLS-policies.
