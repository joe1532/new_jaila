# Lovhistorik: datamodel v1

Formål: kunne besvare "hvilke forarbejder gælder for den gældende ordlyd af LL § 9 A,
stk. 3?" gennem eksplicitte relationer i stedet for at håbe, at embeddings rammer de
rigtige lovbemærkninger.

Motoren bygges **ved siden af** den nuværende File Search/RAG-løsning
(`backend/services/legal_search.py`). Den erstatter den ikke. Vector store bruges
fortsat til praksis, vejledninger og fritekst; lovhistorikken leverer det juridisk
bestemte forarbejdsmateriale.

Dette dokument beskriver datamodellen. Der er ingen implementering endnu.

## Afgrænsning for v1

- Kun én lovfamilie: ligningsloven.
- Proveniens spores kun tilbage til 2007-09-24 (Lex Dania-XML). Ældre lag markeres
  som afkortet historik, ikke som ukendt eller fraværende.
- Krydshenvisninger mellem bestemmelser (fx stk. 3 → stk. 2) er ikke med.
- Ingen kobling til vector store.

## Tre bærende beslutninger

**1. Etiket er ikke identitet.** "§ 9 A, stk. 3" er en etiket, der gælder i et
tidsrum. Når en ændringslov siger "stk. 4 bliver herefter stk. 3", flytter teksten sig
ikke — kun etiketten. Bestemmelsen har derfor en intern, stabil identitet, og etiketten
er en tidsversioneret egenskab ved den.

**2. Ændringer gemmes som operationer, ikke som fakta.** Vi gemmer ikke "stk. 3 blev
ændret i 2003", men selve instruksen med type, mål, payload og virkningstidspunkt.
Ordlyden på et tidspunkt er så resultatet af et replay. Omnummerering falder naturligt
ud, fordi den er en operation, der kun rører etiketter.

**3. Konsolideret og replayet tekst gemmes side om side.** Lovbekendtgørelsen er
autoritativ og er det eneste, der vises som gældende ret. Replay bruges udelukkende til
proveniens. Uenighed mellem de to er ikke en fejl, der skal skjules — den er
kvalitetsmålet, og den gør testorakelet permanent i stedet for kun aktivt i en
testsuite.

## Punktummer er offsets, ikke entiteter

Ændringsinstrukser peger på "1. pkt.", men sætningsopdeling af dansk lovtekst er
skrøbelig ("jf.", "nr.", "stk.", talangivelser), og lovgiverens egen optælling er den
autoritative — ikke vores.

Atomar enhed er derfor stk./nr., som er utvetydigt afgrænset i både XML og HTML.
"2. pkt." er et offset-interval ind i en konkret tekstversion. Punktumnummerering er en
afledt visning beregnet af en versioneret segmenteringsfunktion. Er vores optælling
uenig med instruksen, fejler ét opslag i stedet for hele datamodellen.

Offsets regnes på normaliseret tekst. `normalization_version = 1` betyder: sammenfaldende
whitespace kollapset til ét mellemrum, hårde mellemrum og typografiske citationstegn
erstattet af ASCII, ingen ændring af ordlyd. Versionsnummeret gemmes sammen med hvert
interval, ellers rådner alle offsets stille, første gang normaliseringen forbedres.

## Tabeller

Rådokumenter ligger på disk. Databasen gemmer sti og hash, ikke blobs — så forbliver
relations-databasen lille og hurtig, når omfanget går fra én lov til hele
Retsinformation, og genparsning kræver ikke ny høst.

```sql
-- Rå dokumenter som hentet fra Retsinformation.
document (
  id                  INTEGER PRIMARY KEY,
  eli_uri             TEXT UNIQUE NOT NULL,
  accession           TEXT,           -- fx 202112L00195 for Folketingets dokumenter
  document_type       TEXT NOT NULL,  -- lov | lovbekendtgoerelse | aendringslov
                                      -- | lovforslag | betaenkning
  title               TEXT,
  signed_date         TEXT,           -- ISO-8601
  published_date      TEXT,
  raw_path            TEXT NOT NULL,  -- sti på disk
  raw_format          TEXT NOT NULL,  -- xml | html
  raw_sha256          TEXT NOT NULL,
  fetched_at          TEXT NOT NULL
)

-- "Værket" på tværs af alle lovbekendtgørelser og ændringslove.
act_family (
  id                  INTEGER PRIMARY KEY,
  key                 TEXT UNIQUE NOT NULL,   -- 'ligningsloven'
  title               TEXT,
  eli_work_uri        TEXT
)

-- Stabil identitet. Overlever omnummerering.
provision (
  id                      INTEGER PRIMARY KEY,
  act_family_id           INTEGER NOT NULL REFERENCES act_family(id),
  kind                    TEXT NOT NULL,   -- paragraf | stykke | nummer | litra
  parent_id               INTEGER REFERENCES provision(id),
  created_by_operation_id INTEGER REFERENCES operation(id),
  succeeds_provision_id   INTEGER REFERENCES provision(id),  -- ved genindsættelse
  repealed_at             TEXT
)

-- Etiketten som tidsversioneret egenskab.
provision_label (
  id                  INTEGER PRIMARY KEY,
  provision_id        INTEGER NOT NULL REFERENCES provision(id),
  label               TEXT NOT NULL,   -- '§ 9 A, stk. 3'
  paragraph           TEXT,            -- '9 A'   normaliseret til opslag
  subsection          TEXT,            -- '3'
  number              TEXT,            -- nr., hvis relevant
  valid_from          TEXT NOT NULL,
  valid_to            TEXT,            -- NULL = gældende
  source_document_id  INTEGER REFERENCES document(id)
)

-- Ordlyd over tid. Både konsolideret og replayet.
text_version (
  id                      INTEGER PRIMARY KEY,
  provision_id            INTEGER NOT NULL REFERENCES provision(id),
  text                    TEXT NOT NULL,
  normalization_version   INTEGER NOT NULL,
  valid_from              TEXT NOT NULL,
  valid_to                TEXT,
  origin                  TEXT NOT NULL,  -- consolidated | replayed
  source_document_id      INTEGER REFERENCES document(id),
  content_sha256          TEXT NOT NULL,
  UNIQUE (provision_id, valid_from, origin)
)

-- Én parset ændringsinstruks, fx "§ 1, nr. 7".
operation (
  id                      INTEGER PRIMARY KEY,
  source_document_id      INTEGER NOT NULL REFERENCES document(id),
  amendment_path          TEXT NOT NULL,  -- '§ 1, nr. 7'
  sequence                INTEGER NOT NULL,
  op_type                 TEXT NOT NULL,  -- replace_text | recast | insert_after
                                          -- | insert_before | repeal | renumber
                                          -- | insert_provision
  target_ref_raw          TEXT NOT NULL,  -- som skrevet i ændringsloven
  target_provision_id     INTEGER REFERENCES provision(id),
  payload_before          TEXT,
  payload_after           TEXT,
  effective_date          TEXT,
  effective_date_source   TEXT,           -- ikrafttraedelsesbestemmelse
                                          -- | publicering | ukendt
  parse_status            TEXT NOT NULL,  -- resolved | unresolved_target
                                          -- | unsupported_construction | parse_error
  parse_note              TEXT
)

-- Blame: hvilket tekststykke stammer fra hvilken operation.
provenance_range (
  id                  INTEGER PRIMARY KEY,
  text_version_id     INTEGER NOT NULL REFERENCES text_version(id),
  start_offset        INTEGER NOT NULL,
  end_offset          INTEGER NOT NULL,
  operation_id        INTEGER REFERENCES operation(id),
  completeness        TEXT NOT NULL   -- complete | truncated_at_cutoff | unknown
)

-- Det empirisk usikre led: ændringslov -> Folketingets sagsforløb -> lovforslag.
bill_link (
  id                  INTEGER PRIMARY KEY,
  act_document_id     INTEGER NOT NULL REFERENCES document(id),
  ft_accession        TEXT,
  bill_document_id    INTEGER REFERENCES document(id),
  resolution_method   TEXT NOT NULL,  -- eli_metadata | sagsforloeb_html
                                      -- | heuristic | manual
  verified            INTEGER NOT NULL DEFAULT 0,
  verified_note       TEXT
)

-- Specielle bemærkninger i lovforslaget.
remarks_section (
  id                  INTEGER PRIMARY KEY,
  bill_document_id    INTEGER NOT NULL REFERENCES document(id),
  section_label       TEXT NOT NULL,  -- 'Til § 1'
  item_label          TEXT,           -- 'Til nr. 7'
  start_offset        INTEGER NOT NULL,
  end_offset          INTEGER NOT NULL,
  text                TEXT NOT NULL
)

-- Afstemning mellem konsolideret og replayet tekst. Kvalitetsmålet.
reconciliation (
  id                  INTEGER PRIMARY KEY,
  provision_id        INTEGER NOT NULL REFERENCES provision(id),
  lbk_document_id     INTEGER NOT NULL REFERENCES document(id),
  checked_at          TEXT NOT NULL,
  status              TEXT NOT NULL,  -- match | mismatch | not_replayable
  diff_summary        TEXT
)

-- Afledt. Må slettes og regenereres. Indgår aldrig i operationskæden.
llm_interpretation (
  id                      INTEGER PRIMARY KEY,
  operation_id            INTEGER NOT NULL REFERENCES operation(id),
  remarks_section_id      INTEGER REFERENCES remarks_section(id),
  model                   TEXT NOT NULL,
  prompt_version          TEXT NOT NULL,
  change_type             TEXT,   -- materiel | sproglig | konsekvens | praecisering
                                  -- | videerefoerelse
  continues_previous_law  INTEGER,
  payload_json            TEXT,
  created_at              TEXT NOT NULL
)
```

## Invarianter

Disse skal håndhæves i kode, ikke kun i hovedet:

1. Kun `text_version.origin = 'consolidated'` må vises som gældende ret. Replayet tekst
   forlader aldrig motoren som lovtekst.
2. Ved `reconciliation.status = 'mismatch'` markeres proveniensen for det berørte
   interval som usikker, og svaret skal indeholde et forbehold. Uenighed må koste et
   forbehold, aldrig et forkert forarbejdslink.
3. En fejlet parsning gemmes som en `operation`-række med `parse_status != 'resolved'`.
   Aldrig som en manglende række — ellers kan dækningsgraden ikke måles.
4. `effective_date` tages fra ikrafttrædelsesbestemmelsen. Publiceringsdato er et
   fallback, og det skal fremgå af `effective_date_source`.
5. Offsets peger altid ind i én bestemt `text_version` med kendt
   `normalization_version`.
6. Punktumnummerering lagres ikke som identitet. Den beregnes.
7. `llm_interpretation` er afledt data. Den må ikke læses af replay-motoren.

## Algoritmisk hovedarbejde

Når teksten ændres, skal proveniensintervallerne føres videre til den nye tekstversion.
Det er en alignment mellem to på hinanden følgende `text_version`-rækker, og det udgør
størstedelen af det algoritmiske arbejde. Det bør bygges bevidst fra start, ikke
opdages undervejs.

Selve replayet er billigt: ligningsloven har i størrelsesordenen hundredvis af
ændringslove over perioden, og hver operation er en simpel tekstoperation. SQLite er
rigeligt til relationsdata i dette omfang, også hvis modellen senere udvides til hele
Retsinformation.

## Testorakel

Replay fra LBK *n* til LBK *n+1* skal reproducere LBK *n+1*'s faktiske ordlyd. Det
giver et objektivt, selvgenererende testorakel på tværs af hele lovsamlingen uden
manuel annotering. `reconciliation` er tabellen, hvor resultatet lander.

Acceptkriteriet for prototypen bør formuleres herefter: motoren skal bestå på at
*vide*, hvad den ikke kan spore — ikke på at finde forarbejder fra før 2007. En motor,
der ærligt melder hul i historikken, er brugbar; en der gætter, er værre end ingenting
i juridisk sammenhæng.

## Åbne spørgsmål

Disse er empiriske og skal afklares med data, ikke med antagelser:

1. Kan relationen ændringslov → Folketingets sagsforløb hentes fra ELI-metadata, eller
   kræver den parsning af sagsforløbs-HTML? `bill_link.resolution_method` måler det
   løbende.
2. Hvor stor en andel af ændringsinstrukserne kan parses deterministisk?
   `operation.parse_status` måler det.
3. Holder antagelsen om, at Lex Dania-XML findes for dokumenter efter 2007-09-24?
   Oplysningen stammer fra Retsinformations egen beskrivelse og er ikke verificeret her.
4. Ophævelse efterfulgt af genindsættelse af samme paragrafnummer modelleres som ny
   `provision` med `succeeds_provision_id`, så gamle forarbejder ikke arves utilsigtet.
   Konstruktionen er ikke afprøvet mod et virkeligt eksempel endnu.
5. Stemmer vores punktumsegmentering overens med lovgiverens optælling? Måles ved, hvor
   ofte `target_ref_raw` peger på et punktum, vi ikke kan opløse.

## Hvad modellen bevidst ikke gør

- Den gemmer ingen juridiske fortolkninger som kildedata. Kun operationer og tekst.
- Den forsøger ikke at afgøre, om en ændring er materiel. Det er LLM-lagets opgave, og
  svaret er afledt.
- Den håndterer ikke krydshenvisninger i v1. De kan bygges ovenpå senere uden at ændre
  kernen.
