# Lovhistorik: datamodel v1

Formål: kunne besvare "hvilke forarbejder gælder for den gældende ordlyd af LL § 9 A,
stk. 3?" gennem eksplicitte relationer i stedet for at håbe, at embeddings rammer de
rigtige lovbemærkninger.

Motoren bygges **ved siden af** den nuværende File Search/RAG-løsning
(`backend/services/legal_search.py`). Den erstatter den ikke. Vector store bruges
fortsat til praksis, vejledninger og fritekst; lovhistorikken leverer det juridisk
bestemte forarbejdsmateriale.

Dette dokument beskriver datamodellen. Der er ingen implementering endnu.

Motoren bruger to kilder: Retsinformation til retsakter, tekst og ændringsrelationer,
og Folketingets Åbne Data til koblingen mellem en vedtaget lov og dens lovforslag.

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

Ændringsinstrukser peger på "1. pkt.". Oprindeligt antog vi, at vi selv skulle segmentere
sætninger, hvilket er skrøbeligt på dansk lovtekst ("jf.", "nr.", "stk.", talangivelser).

Det viste sig at være unødvendigt for dokumenter i Lex Dania-XML: hvert punktum er
markeret op som sit eget `<Linea>`-element. Lovgiverens egen optælling ligger altså i
opmærkningen. Kontrolleret på ligningslovens § 9 A, stk. 5, hvis 3. punktum henviser til
"2. pkt.", og hvor `<Linea>`-nummereringen rammer rigtigt.

Atomar enhed er stk./nr., som er utvetydigt afgrænset af `<Stk>`. Offsets er stadig
nødvendige, fordi ændringer går under sætningsniveau — en instruks kan udskifte en frase
inde i et punktum. Men sætningsgrænserne er nu givet frem for gættet, og det fjerner en
hel klasse af fejl for moderne dokumenter.

For dokumenter uden Lex Dania-opmærkning (før 2007) vender problemet tilbage. Punktum-
nummerering skal derfor stadig være en afledt, versioneret beregning, ikke en del af
identiteten — så den kan falde tilbage på egen segmentering, hvor opmærkningen mangler.

Offsets regnes på normaliseret tekst. `normalization_version = 1` betyder: sammenfaldende
whitespace kollapset til ét mellemrum, hårde mellemrum og typografiske citationstegn
erstattet af ASCII, ingen ændring af ordlyd. Versionsnummeret gemmes sammen med hvert
interval, ellers rådner alle offsets stille, første gang normaliseringen forbedres.

## Verificeret adgang

Afklaret empirisk med `spikes/retsinfo_probe.py` den 11. august 2026. Alt herunder er
målt, ikke antaget.

**Metadata.** Hæng `.rdfa` på en vilkårlig ELI-URI, så returneres ELI-metadata som
struktureret JSON — fx `/eli/lta/2025/1772.rdfa`. Ingen autentificering. Relationerne
`changes`, `changed_by`, `consolidates`, `consolidated_by`, `commences`, `basis_for`,
`in_force` og `id_local` findes, som Retsinformations egen dokumentation på
`api/eli/documentation/metadata-types` beskriver.

**Indhold.** `eli:is_embodied_by` peger direkte på `/dan/xml`, `/dan/html` og
`/dan/pdf`. Vi skal ikke crawle websider. Selve sitet er en JavaScript-app, hvis HTML
kun indeholder OpenGraph-tags, så server-renderet indhold er ikke en farbar vej.

**Omfang.** Sitemap'et er et indeks med 21 sider à 10.000 URL'er, altså cirka 200.000
dokumenter. `robots.txt` indeholder kun en sitemap-henvisning og ingen `Disallow`.

**Identitet.** `eli:id_local` er identisk med accessionsnummeret, fx `A20250177230`.
URI-skabelonerne er officielt dokumenteret på `api/eli/documentation/uri-templates`:
`/{pubMedia}/{year}/{number}` og `/ft/{accn}` for Folketingets dokumenter.

**Forarbejder.** Relationen lov → lovforslag findes IKKE i ELI-metadata. Det blev
testet på en rigtig ændringslov (LOV nr. 1772 af 29/12/2025, 54 triples): den har
`changes` og `consolidated_by`, men ingen henvisning til `/eli/ft/`. Koblingen hentes
i stedet fra Folketingets Åbne Data (`https://oda.ft.dk/api`, OData v3), hvor
`Sag`-entiteten har `lovnummer` og `lovnummerdato`. Kæden er verificeret hele vejen:
lov 1772/2025 → sag 103490 ("L 68") → 14 dokumenter, herunder skriftlig fremsættelse,
det fremsatte lovforslag, ændringsforslag, betænkning og vedtagelse ved 3. behandling.

Feltet `Sag.retsinformationsurl` findes, men var tomt på begge undersøgte sager. Det
kan bruges som bekræftelse, aldrig som primær kobling.

**Dokumentstruktur.** Lex Dania-XML'en har `<Paragraf localId="9A">`, `<Stk id="...">`
med GUID, og `<Linea>` pr. punktum. Paragraffens `localId` er en maskinlæsbar nøgle, vi
ikke selv skal udlede af overskriftsteksten. Det er uafklaret, om `<Stk>`-GUID'erne er
stabile på tværs af lovbekendtgørelser — indtil det er målt, må de ikke bruges som
bestemmelsesidentitet.

**Ændringsinstrukser.** Grammatikken er som forventet og går ned på punktumniveau.
Konkret eksempel fra LOV nr. 616 af 30/06/2026:

```text
1. I § 9 C, stk. 3, 1. pkt., ændres »4. pkt.« til: »4. og 5. pkt.«, og i 2. pkt.
   indsættes efter »kilometertakst«: »efter 1. og 5. pkt.«
2. I § 9 C, stk. 3, indsættes som 5. pkt.: ...
```

Citationstegnene er danske dobbelte anførselstegn (»…«), ikke ASCII. Ændringslovene
angiver desuden selv deres udgangspunkt i teksten — "som ændret senest ved lov nr. 1781
af 29. december 2025" — hvilket giver en gratis kontrol af, at replay-kæden er komplet.

**Omfang for prototypen.** Ligningsloven er `/eli/lta/2025/1500` (LBK nr. 1500 af
24/11/2025, 700 KB XML, 171 paragraffer). Den konsoliderer 33 ændringslove og er derefter
ændret af 9. Ingen af de 9 nævner § 9 A — kontrolleret med en positiv kontrol på § 9 C,
som gav træf i én af dem. Den gældende ordlyd af § 9 A, stk. 3 (tre punktummer) er
altså identisk med lovbekendtgørelsens, og hele proveniensen ligger før november 2025.

To URI'er optræder både i `consolidates` og `changed_by`. Det tyder på delvis
ikrafttræden, hvor dele af en ændringslov er konsolideret og andre dele endnu ikke er
trådt i kraft. Modellen må derfor ikke antage, at de to mængder er disjunkte.

**TLS.** Udviklingsmaskinen har TLS-inspektion, så Pythons certifi-bundle afvises med
"unable to get local issuer certificate". Brug pakken `truststore`, der validerer mod
OS'ets eget trust store. På en Linux-server uden inspektion er det ikke nødvendigt.

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

-- Ændringslov -> Folketingets sagsforløb -> lovforslag.
-- Koblingen kommer fra Folketingets Åbne Data, ikke fra Retsinformations ELI-metadata.
-- Nøglen er PARRET lovnummer + lovnummerdato: lovnumre genbruges hvert år.
bill_link (
  id                  INTEGER PRIMARY KEY,
  act_document_id     INTEGER NOT NULL REFERENCES document(id),
  lovnummer           TEXT NOT NULL,  -- fx '1772'
  lovnummerdato       TEXT NOT NULL,  -- fx '2025-12-29'  ALDRIG nummer alene
  oda_sag_id          INTEGER,        -- Folketingets Sag.id, fx 103490
  ft_bill_number      TEXT,           -- fx 'L 68'
  ft_periode_id       INTEGER,
  ft_accession        TEXT,           -- Retsinformations /eli/ft/{accn}, hvis udledt
  bill_document_id    INTEGER REFERENCES document(id),
  resolution_method   TEXT NOT NULL,  -- oda_lovnummer | oda_titel
                                      -- | retsinfo_sagsforloeb | manual
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
8. Koblingen til et lovforslag laves aldrig på `lovnummer` alene. Lovnumre genbruges
   hvert år — et opslag på "1772" rammer både en lov fra 2023 og en fra 2025. Uden
   datoen ville forarbejder fra en helt anden lov blive knyttet til bestemmelsen, og
   fejlen ville være svær at opdage bagefter.

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

1. AFKLARET. Relationen findes ikke i ELI-metadata, men i Folketingets Åbne Data via
   parret `lovnummer` + `lovnummerdato`. Se afsnittet om verificeret adgang.
2. Hvor stor en andel af ændringsinstrukserne kan parses deterministisk?
   `operation.parse_status` måler det.
3. Kan Retsinformations FT-accession (`/eli/ft/{accn}`, fx `202522L00017`) udledes
   deterministisk af Folketingets periode og lovforslagsnummer? Hvis ja, har vi en ren
   bro fra sagen til den maskinlæsbare XML-udgave af lovforslaget i stedet for PDF.
   Ikke testet endnu.
4. Hvor langt tilbage findes Lex Dania-XML? Formatet er bekræftet for dokumenter fra
   2025 og 2026, men grænsen ved 2007-09-24 stammer fra Retsinformations egen
   beskrivelse og er ikke målt. Det afgør, hvornår vi mister `<Linea>`-opmærkningen og
   må segmentere selv.
5. Er `<Stk id="...">`-GUID'erne stabile på tværs af lovbekendtgørelser? Hvis ja, er de
   en gratis bestemmelsesidentitet. Hvis nej — og det er det, jeg forventer — skal de
   ignoreres helt, så de ikke smugler falsk kontinuitet ind i modellen.
6. Ophævelse efterfulgt af genindsættelse af samme paragrafnummer modelleres som ny
   `provision` med `succeeds_provision_id`, så gamle forarbejder ikke arves utilsigtet.
   Konstruktionen er ikke afprøvet mod et virkeligt eksempel endnu.
7. Punktumsegmenteringen er bekræftet for XML-dokumenter via `<Linea>`. For ældre
   dokumenter uden opmærkning er spørgsmålet stadig åbent og måles ved, hvor ofte
   `target_ref_raw` peger på et punktum, vi ikke kan opløse.

## Hvad modellen bevidst ikke gør

- Den gemmer ingen juridiske fortolkninger som kildedata. Kun operationer og tekst.
- Den forsøger ikke at afgøre, om en ændring er materiel. Det er LLM-lagets opgave, og
  svaret er afledt.
- Den håndterer ikke krydshenvisninger i v1. De kan bygges ovenpå senere uden at ændre
  kernen.
