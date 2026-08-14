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

Ændringsinstrukser peger på "1. pkt.", så vi skal kunne tælle punktummer i et stykke.

**En tidligere antagelse her var forkert.** Vi troede, at `<Linea>` markerede ét punktum,
og at optællingen dermed lå færdig i opmærkningen. Det gør den ikke. I LBK 1500 rummer
§ 9 C, stk. 3 fire punktummer fordelt på to `<Linea>`, hvor det første alene indeholder
tre. Målt på hele loven gælder det 58 af 1.639 `<Linea>`. En `<Linea>`-grænse *er* altid
en punktumgrænse, men den er ikke den eneste, så vi skal segmentere selv.

Segmenteringen deler ved punktum efterfulgt af mellemrum og stort bogstav. Kravet om
stort bogstav gør det meste af arbejdet: "10 pct. af" og "1. pkt. finder" bliver ikke
delt. Kun en kort liste af forkortelser, der jævnligt efterfølges af et stort bogstav
uden at afslutte sætningen, skal undtages — først og fremmest "jf." foran en lovtitel.
Bemærk at "pkt." ikke må undtages: "jf. dog 4. pkt. For befordring herudover …" er den
hyppigste sætningsafslutning i loven.

Segmenteringen er kontrolleret ad to uafhængige veje:

- **Lovens egne henvisninger.** Skriver et stykke "jf. dog 4. pkt.", skal det have mindst
  fire punktummer. 115 stykker i LBK 1500 kan kontrolleres sådan, og ingen af dem er i
  modstrid med segmenteringen. Henvisninger kvalificeret med "§" eller "stk." tæller
  ikke med, fordi de peger på et andet stykke eller en anden lov.
- **Ændringslovenes forudsætninger.** "Indsættes som 6. pkt." forudsætter præcis fem
  punktummer i forvejen. Kontrolleret mod de ni love, der ændrer LBK 1500, uden
  uoverensstemmelser. To tilsyneladende afvigelser viste sig at være ændringer, der
  allerede var indarbejdet i lovbekendtgørelsen — se afsnittet om delvis ikrafttræden.

Den første kontrol kan kun afsløre for få punktummer, ikke for mange. Den anden fanger
begge retninger, men findes kun for de stykker, der faktisk er blevet ændret. Endelig
sikkerhed får vi først af replay mod den næste lovbekendtgørelse.

Atomar enhed er stk./nr., som er utvetydigt afgrænset af `<Stk>`. Offsets er nødvendige,
fordi ændringer går under sætningsniveau — en instruks kan udskifte en frase inde i et
punktum. Punktumnummerering forbliver en afledt, versioneret beregning og aldrig en del
af identiteten. Det var rigtigt af andre grunde, end vi troede: ikke fordi opmærkningen
mangler før 2007, men fordi den aldrig har givet os punktummerne.

Offsets regnes på normaliseret tekst. `normalization_version = 1` betyder: sammenfaldende
whitespace kollapset til ét mellemrum, hårde mellemrum og typografiske citationstegn
erstattet af ASCII, ingen ændring af ordlyd. Versionsnummeret gemmes sammen med hvert
interval, ellers rådner alle offsets stille, første gang normaliseringen forbedres.

## Verificeret adgang

Afklaret empirisk med `probe.py` den 11. august 2026. Alt herunder er målt, ikke antaget.

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
med GUID, og `<Linea>` som tekstblokke. Blokkene er ikke punktummer — se afsnittet om
punktummer. Paragraffens `localId` er en maskinlæsbar nøgle, vi ikke selv skal udlede af
overskriftsteksten. Det er uafklaret, om `<Stk>`-GUID'erne er
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

**FT-accession kan udledes.** Folketingets `Periode.kode` (fx `20252` for 2025-26,
2. samling) kombineret med lovforslagets nummer giver Retsinformations accession efter
mønsteret `{periodekode}2L{nummer:05d}`. Verificeret: sag 105171 (L 4, periode 167)
giver `202522L00004`, som er `/eli/ft/202522L00004` — "2025/2 LSF 4". Det betyder, at vi
når lovforslagets XML frem for Folketingets PDF.

**Hele kæden er demonstreret.** For LL § 9 C, stk. 3:

```text
LL § 9 C, stk. 3                     LBK nr 1500 af 24/11/2025, <Linea> pr. punktum
  → ændret ved                       LOV nr 616 af 30/06/2026  (eli:changed_by)
  → § 1, nr. 2                       "I § 9 C, stk. 3, indsættes som 5. pkt.: …"
  → sag 105171, L 4                  Folketingets Åbne Data (lovnummer + dato)
  → /eli/ft/202522L00004             udledt accession, XML på 117 KB
  → "Til § 1" → "Til nr. 2"          "Det foreslås i ligningslovens § 9 C, stk. 3,
                                      at indsætte som 5. pkt.: »For indkomståret …«"
```

Ingen LLM indgår i noget af dette. Bemærkningen citerer selv den ændring, instruksen
foreskriver, hvilket giver en direkte kontrol af, at koblingen er rigtig.

**Bemærkningerne er ikke opmærkede.** Overskrifterne "Til § 1" og "Til nr. 2" står som
almindelig tekst i `<Char>` inde i `<Linea>`; kun paragrafoverskriften er kursiveret, og
"Til nr."-overskriften har ingen attributter overhovedet. Udtrækket må derfor bygge på
tekstmønstre. Det er en reel svaghed: ændres formuleringen af en overskrift, forsvinder
bemærkningen i stilhed frem for at fejle. Antallet af fundne bemærkninger skal derfor
altid holdes op mod antallet af ændringspunkter.

**Én bemærkning kan dække flere ændringspunkter.** "Til nr. 7 og 8" og "Til nr. 2-5" er
almindelige. Læser man kun det første tal, mister man resten uden at opdage det — på
ligningslovens § 9 C gjaldt det 2 af 6 punkter. Samme tekst føres til hvert af de numre,
overskriften nævner; der findes ingen opdeling at læse.

**"Til nr. 1" udelades ofte.** Har en ændringsparagraf kun ét ændringspunkt, står
bemærkningen direkte under "Til § 3" uden underopdeling. Tekst uden en "Til nr."-
overskrift gemmes derfor under nummer 0, og opslag falder tilbage på det, når det søgte
nummer ikke findes. Tilbagefaldet markeres i outputtet, fordi det er mindre præcist:
teksten kan dække hele paragraffen frem for det enkelte punkt.

**En bestemmelse kan være uændret gennem flere lovbekendtgørelser.** Ligningslovens
§ 33 A er ikke rørt i LBK 1500 (2025) og heller ikke i LBK 42 (2023). Søgningen følger
derfor kæden bagud via `previous_consolidation`, indtil en ændring findes:

```text
LL § 33 A                       LBK 1500 (2025) — ikke ændret
  → LBK 42 (2023)               ikke ændret
  → LBK 1735 (2021)             ændret ved LOV 871 af 14/06/2020, § 3, nr. 1
  → sag 83692, L 199            Folketingets Åbne Data (lovnummer + dato)
  → /eli/ft/201912L00199        udledt accession
  → bemærkning på 9.779 tegn    "Efter ligningslovens § 33 A kan en person, der er
                                 fuldt skattepligtig til Danmark, … få nedsat skatten
                                 af lønindkomst under ophold uden for riget …"
```

Uden vandringen ville et tomt svar blive forvekslet med "der findes ingen forarbejder".
Skellet mellem "ikke ændret" og "ikke fundet" er afgørende, og motoren skal aldrig
returnere det ene som det andet.

**Hele historikken, ikke kun den seneste ændring.** Vandringen må ikke stoppe, første
gang paragraffen er rørt. Ældre ændringer bærer ofte fortolkningen af den oprindelige
regel, og et fortolkningsbidrag, der kun omfatter den nyeste ændring, er misvisende.
For ligningslovens § 9 C findes 14 ændringer i kæden tilbage til 2019, fordelt sådan:

| Stykke | Ændringer |
| --- | --- |
| Hele paragraffen | 1 |
| stk. 1 | 1 |
| stk. 3 | 6 |
| stk. 5 | 2 |
| stk. 7 | 1 |
| stk. 9 | 3 |

Alle fandt deres bemærkning. Grupperingen efter stykke er den form, spørgsmålet stilles
i: "hvilke forarbejder gælder for § 9 C, stk. 3?"

**Kontrolmålet er ikke ufejlbarligt.** At bemærkningen nævner målbestemmelsen er et godt
tegn, men fraværet er ikke bevis for en forkert kobling. LOV 1890/2015 § 1, nr. 1 hæver
Storebæltsfradraget i § 9 C, stk. 9 fra 90 til 110 kr., og bemærkningen er korrekt fundet:
"Det foreslås at forhøje fradraget for skattepligtiges passage over Storebæltsforbindelsen
fra 90 kr. til 110 kr." Den nævner aldrig "§ 9 C", fordi hele ændringsloven kun handler om
den ene bestemmelse, og paragrafnummeret derfor er overflødigt. Et lavt tal skal
undersøges, ikke bortforklares — men enkelttilfælde skal læses, før de tælles som fejl.

### At lede efter tavse fejl

Fejlene i forarbejdssøgningen larmer ikke. Der kommer bare færre eller forkerte
resultater, og uden en facitliste ser et mangelfuldt svar ud som et fuldstændigt. At
§ 33 A manglede sin vigtigste forarbejde blev kun opdaget, fordi nogen tilfældigvis
vidste det. Det er ikke en holdbar kvalitetssikring.

`probe.py daekning <lbk> [led]` måler derfor bredden i stedet for enkelttilfælde. Hele
kæden gennemløbes én gang, alle ændringspunkter indekseres efter hvilken paragraf de
rammer, og lovens paragraffer bedømmes samlet. Tre kontroller falder ud af det:

1. **Paragraffer uden fund.** En bogstavparagraf ("§ 8 X") kan ikke stamme fra lovens
   oprindelige tekst — bogstavet opstår netop, fordi bestemmelsen er skudt ind mellem to
   eksisterende. Findes den ikke i kæden, er den enten indsat før 2007 eller overset.
2. **Paragraffer der kun findes via indsat tekst.** For ligningsloven er det 10 af 171,
   altså 6 %. Alle er ægte ("Efter § 16 J indsættes: § 16 K …"), og alle var usynlige,
   før indsættelser blev læst med.
3. **Lækagetest mod `eli:changed_by`.** Kæden bygger alene på lovbekendtgørelsernes egne
   lister. `changed_by` er en uafhængig kilde til, hvilke love der ændrede hvert led, og
   de burde alle dukke op senere i kæden.

Lækagetesten fandt straks noget. Ligningsloven: 28 love uden for kæden. To slags
udeladelser er legitime og kan afgøres af data — loven er nyere end bekendtgørelsen, eller
bekendtgørelsen oplyser selv, at den ikke er indarbejdet ("da ændringen efterfølgende er
ophævet"). Resten var fejl.

### Tre tavse fejl, fundet af målingen

**Kommaet i indledningen.** Mønsteret krævede "med de ændringer, der følger af". LBK
42/2023 skriver "med de ændringer der følger af" uden komma. Konsekvens: hele perioden
juni 2021 til oktober 2022 var usynlig for forarbejdssøgningen — 16 ændringslove og 35
ændringspunkter — uden at noget fejlede. Nu accepteres både med og uden komma, og både
"der" og "som".

**Punktummet i datoen.** Samme bekendtgørelse skriver "lov nr. 2194 af 30 november 2021"
uden punktum efter dagen. Mønsteret krævede det, så den ene lov faldt ud. En manglende
tegnsætning må ikke koste en lovs ændringer.

Begge er nu dækket af en advarsel: et led i kæden uden læselig liste er næsten altid en
ulæst indledning, ikke en bekendtgørelse uden ændringer. Efter rettelserne står
ligningsloven med 227 ændringslove mod 211, og af 11 love uden for kæden er 10 forklaret
af data. Den sidste rammer 2006, hvor Lex Dania-opmærkningen slipper op. Afskrivningsloven
og skatteindberetningsloven har nul uforklarede.

### Hentningen kunne ødelægge et dokument og gemme det for altid

Spørgsmålet "fungerer det deterministisk?" viste tre fejl, som alle sad i hentningen og
ikke i logikken.

**Et for stort dokument blev skåret over i stilhed.** `response.read(MAX_BYTES)` med
grænsen 8 MB huggede lovforslag L 88 (2022-23) over midt i et element ved præcis
8.000.000 bytes. Den afkortede fil blev skrevet i cachen, og da cachen ikke har
udløbstid, blev fejlen permanent: forslagets 564 bemærkninger var utilgængelige, og
dokumentet ville aldrig blive hentet igen. Det rigtige dokument fylder 10,99 MB. Nu
læses én byte mere end grænsen, så et for stort svar afvises frem for at blive
forkortet, og grænsen er hævet til 64 MB. Grænsen findes for ikke at æde hukommelsen
på et uventet svar — ikke for at afvise store dokumenter.

**En fejlside blev gemt som et dokument.** Retsinformation svarer med HTTP 200 og en
HTML-side for en ELI-sti, der ikke findes. Uden en kontrol af indholdet endte siden i
cachen under dokumentets navn. Nu kontrolleres det ved både skrivning og læsning, at
indholdet slutter med `</Dokument>`. Kontrollen er billig nok til at køre hver gang og
fanger netop afkortning og fejlsider; skader midt i dokumentet opdager XML-parseren.

**Kilden indeholder trykfejl.** LBK 176/2009 skriver "§ 7 i lov nr. 1534 af 19. december
2207". Året findes ikke, og loven — en reel ændring af ligningsloven — faldt ud af
kæden. Vores parsing læste teksten korrekt; fejlen står i bekendtgørelsen.

Lækagetesten pegede uafhængigt på den samme lov, og det gav rettelsen: `eli:changed_by`
for LBK 1061/2006 indeholder `eli/lta/2007/1534`. Året kan derfor afgøres af data i
stedet for at gættes. Et umuligt årstal slås nu op i changed_by for den bekendtgørelse,
der blev konsolideret, og bruges kun, hvis præcis ét lovnummer passer; ellers
rapporteres tvetydigheden. Rettelsen oplyses altid — en tavs rettelse af kildens tekst
ville være netop den slags fejl, vi leder efter.

Det lukkede den sidste uforklarede lækage: ligningsloven står nu med 228 ændringslove og
771 punkter mod 227 og 768, og alle tre love har nul uforklarede love i lækagetesten.

### Ældre lovforslag skriver overskriften anderledes

At kunne vælge en gammel udgave af loven afslørede med det samme, at dækningen faldt
længere tilbage: § 9 C fik kun 3 af 13 bemærkninger bekræftet fra 2015-udgaven mod 18 af
23 fra 2025-udgaven. To mønstre var for snævre.

**Overskriften uden "Til".** L 199 (2008-09) skriver bare "§ 1" som overskrift over de
specielle bemærkninger, ikke "Til § 1". Afsnittets 43 "Til nr."-overskrifter mistede
dermed deres paragraf, og hele afsnittet forsvandt: udtrækket fandt 4 bemærkninger i et
dokument med 64 ændringspunkter mod ligningsloven alene. Den bare form accepteres nu,
men kun efter overskriften "Bemærkninger til lovforslagets enkelte bestemmelser", hvor
en paragrafhenvisning ikke kan forveksles med lovtekst.

**Kolonet efter nummeret.** Samme dokument skriver både "Til nr. 1" og "Til nr. 2:".
Mønsteret krævede, at linjen sluttede efter tallet, så hver overskrift med kolon faldt
ud. Kolonet er nu valgfrit.

Efter rettelsen giver L 199 68 bemærkninger mod 4, og § 9 C i 2015-udgaven 8 af 13 mod 3.
Nyere materiale er uændret, hvilket er ventet: fejlen ramte kun den ældre skrivemåde.
Det illustrerer, hvorfor målingerne skal spænde over hele tidsrummet — en måling, der kun
rammer de seneste år, ville have vist grønt hele vejen.

### Lovforslagets paragrafnumre er ikke lovens

Den alvorligste fejl gav ikke for få svar, men forkerte. Bemærkningerne slås op på
"Til § N, Til nr. M", og vi brugte den vedtagne lovs numre. De er ikke de samme som
lovforslagets: ligningsloven er § 6 i LOV 84/2019, men § 5 i lovforslag L 114.
Bemærkningerne til § 7 P handlede derfor om personskatteloven og aktieavancebeskatnings-
loven. Et forkert svar, der ser rigtigt ud, er værre end intet svar.

Punktet genfindes nu i lovforslaget på sin egen tekst, og forslagets numre bruges til
opslaget. Teksten redigeres let undervejs — forslaget skriver "som nyt stk. 7", loven "som
nyt stykke" — så der måles lighed med tærskel 0,90 i stedet for at kræve identitet.

En faldgrube undervejs er værd at huske: `difflib.SequenceMatcher` har som standard
`autojunk=True`, som for strenge over 200 tegn behandler hyppige tegn som støj. To
instrukser, der kun adskilte sig ved "el.lign." mod "eller lignende", fik lighed 0,74 i
stedet for 0,97. Sammenligner man lange tekster, skal `autojunk=False` sættes.

| Måling | Før | Efter |
| --- | --- | --- |
| Ligningsloven, punkter med bemærkning | 99 af 104 | 96 af 104 |
| — heraf bekræftet af teksten | 92,9 % | 95,8 % |
| Skatteindberetningsloven (LBK 15/2024) | 36 af 40 | 38 af 40 |
| § 7 P, bemærkninger der nævner § 7 P | 4 af 12 | 12 af 12 |
| § 9 C | 14 af 14 | 17 af 18 |

Tallet for ligningsloven **falder** med tre, og det er meningen: de tre var forkerte
koblinger, som nu afvises. Kan et punkt ikke genfindes i lovforslaget, er det formentlig
kommet til ved et ændringsforslag under behandlingen, og bemærkningen står da i
betænkningen, som vi ikke henter.

### En indsat paragraf står ikke som mål for sin egen indsættelse

§ 33 A så længe ud til kun at være ændret én gang, tilbage til 2016. Det var forkert, og
fejlen var principiel. Da kæden blev ført helt tilbage til 2006, dukkede dette op:

```text
LOV 921 af 18/09/2012, § 1, nr. 7    "§ 33 A ophæves."
LOV 1395 af 23/12/2012, § 3, nr. 2   "Efter § 33 indsættes: § 33 A. Har en person, …"
```

Bestemmelsen blev **ophævet og tre måneder senere genindført med tilbagevirkende kraft**
til ophævelsesdagen, så ophævelsen aldrig fik virkning. Bemærkningerne siger det selv:
"Det foreslås at genindføre ligningslovens § 33 A, sådan som bestemmelsen var udformet på
det tidspunkt, hvor ophævelsen af bestemmelsen trådte i kraft."

Genindførelsen var usynlig for søgningen, fordi **målet for en indsættelse er den
foregående paragraf**. Instruksen peger på § 33, ikke på § 33 A; den nye paragraf findes
kun i den indsatte tekst. Søger man på målene alene, mangler netop den ændring, der
indførte bestemmelsen — det vigtigste forarbejde, der findes til den. Søgningen læser nu
også paragrafbetegnelser i den nye tekst (`inserted_paragraphs`).

For § 33 A giver det 3 ændringer i stedet for 1, alle med bekræftet bemærkning:

| Lov | Punkt | Hvad | Forslag |
| --- | --- | --- | --- |
| LOV 871/2020 | § 3, nr. 1 | Nyt stk. 6 (corona) | L 199 |
| LOV 1395/2012 | § 3, nr. 2 | Genindført | L 82 |
| LOV 921/2012 | § 1, nr. 7 | Ophævet | L 195 |

Rækkefølgen i lovbekendtgørelsens egen liste er ikke kronologisk, så historikken sorteres
efter (år, lovnummer). For § 33 A afgør det, om ophævelsen eller genindførelsen ser ud til
at komme sidst — altså om bestemmelsen ser ud til at gælde.

### En overskrift mellem to paragraffer skjulte 386 indsættelser

Rettelsen ovenfor løste § 33 A, men kun fordi den paragraf blev indsat alene. Aktie-
avancebeskatningslovens § 19 D gav et tomt svar: "ikke ændret i den del af kæden, vi kan
nå" — uden advarsel, selv om paragraffen står i loven. Den blev indsat af LOV 84/2019,
§ 1, nr. 15:

```text
§ 19 A ophæves, og i stedet indsættes:
  Aktier og investeringsbeviser i investeringsselskaber  Selskaber m.v.
  § 19 A. …
  Aktier og investeringsbeviser i aktiebaserede investeringsselskaber  Personer
  § 19 B. …
  … Fradrag  Personer
  § 19 D. …
```

Ét punkt indsætter fire paragraffer. `inserted_paragraphs` læste dem ud af ordlyden med
mønstret `(?:^|\.\s+)§\s*(\d+)\s*([A-ZÆØÅ])?\.\s`, som kræver tekststart eller punktum
umiddelbart foran. **Overskrifterne står imellem**, så kun § 19 A blev fundet — og den kun
ved et tilfælde, fordi forkortelsen "m.v." efterlod et punktum på den rigtige plads. §§ 19
B, C og D var usynlige.

Målt over 263 blokke indsat tekst fra fire skattelove:

| | Antal |
| --- | --- |
| Paragraffer mønstret mistede | 386 |
| Paragraffer mønstret opfandt | 19 |
| Blokke uden `Paragraf`-opmærkning | 13 af 263 |

Mønstret fejlede altså i begge retninger. De 19 er henvisninger i løbende tekst, der
tilfældigt stod efter et punktum, og de blev talt som indsættelser.

Den indsatte tekst bærer selv sine paragraffer: `<Paragraf localId="19D">` inde i
`<AendringNyTekst>`. Det er samme maskinlæsbare nøgle, vi bruger i lovbekendtgørelsen.
`Instruction.inserted_paragraph_ids` læser den nu og falder kun tilbage på ordlyden for de
13 blokke uden opmærkning.

Fejlen er den samme, som modellen advarer imod ét afsnit længere oppe: *`localId` er en
maskinlæsbar nøgle, vi ikke selv skal udlede af overskriftsteksten.* Reglen var skrevet
for lovbekendtgørelsen og blev ikke anvendt på ændringslovens nye tekst, selv om
opmærkningen er den samme dér.

Rettelsen ændrer intet i de eksisterende målinger — § 9 C giver stadig 23 ændringer ved
otte led og 13 i 2015-udgaven, `probe.py mine` er uændret, og lækagetesten er fortsat nul
uforklarede på alle tre love. Den tilføjer kun ændringer, der før manglede.

**Målt dækning.** For de 40 ændringspunkter bag LBK 15/2024 (skatteindberetningsloven):

| Resultat | Antal |
| --- | --- |
| Fik en bemærkning | 36 |
| Intet "Til nr." i lovforslaget | 2 |
| Kunne ikke nå lovforslaget | 2 |
| Bemærkning nævner ikke målbestemmelsen | 3 af 36 |

Den sidste linje er kontrollen: bemærkningen citerer selv den bestemmelse, den forklarer
("Det foreslås i ligningslovens § 9 C, stk. 3, at indsætte som 5. pkt.: …"). Nævner den
ikke målet, er koblingen sandsynligvis forkert, og den skal efterses frem for at indgå.
For ligningslovens § 9 C blev alle 6 punkter koblet og alle 6 bekræftet.

**Titler kan ikke bruges som nøgle.** Sagens titel i Folketingets data er "ændring af
ligningsloven og lov om en aktiv beskæftigelsesindsats", mens lovforslagets egen titel
er "ændring af ligningsloven (Forhøjelse af befordringsfradraget for indkomståret
2026)". Lovforslag ændrer titel undervejs i behandlingen. Koblingen skal derfor gå via
numre og datoer, aldrig via tekstsammenligning af titler.

**TLS.** Udviklingsmaskinen har TLS-inspektion, så Pythons certifi-bundle afvises med
"unable to get local issuer certificate". Brug pakken `truststore`, der validerer mod
OS'ets eget trust store. På en Linux-server uden inspektion er det ikke nødvendigt.

## Instrukserne er opmærkede, ikke fritekst

Antagelsen om, at ændringsinstrukser skal udtrækkes med regex fra løbende tekst, holder
ikke. Lex Dania opmærker dem strukturelt:

```xml
<AendringCentreretParagraf localId="1">
  <Explicatus>§ 1</Explicatus>
  <Exitus>I ligningsloven, jf. lovbekendtgørelse nr. 1500 …, foretages følgende ændringer:</Exitus>
  <AendringsNummer>
    <Explicatus>2.</Explicatus>
    <Aendring>
      <AendringDefinition>
        I <Char signiChar="AendringURN">§ 9 C, stk. 3,</Char> indsættes som <Char>5. pkt.:</Char>
      </AendringDefinition>
      <AendringAktion><AendringNyTekst>For indkomståret 2026 …</AendringNyTekst></AendringAktion>
    </Aendring>
  </AendringsNummer>
</AendringCentreretParagraf>
```

Målloven står i `<Exitus>` på ændringsparagraffen, punktnummeret i `<Explicatus>`,
målbestemmelsen i et `<Char signiChar="AendringURN">`, og den nye tekst i
`<AendringNyTekst>` adskilt fra instruksen. Parseren skal derfor kun udlede ét felt fra
fritekst: selve verbet.

## Udvundet testmængde

Alle 40 ændringslove i ligningslovens `consolidates` og `changed_by` er hentet og
gennemgået. 39 af dem indeholder en ændringsparagraf mod ligningsloven, med i alt **151
nummererede ændringspunkter**. Otte verbalmønstre dækker alle 151:

| Konstruktion | Punkter | Andel |
| --- | --- | --- |
| `ændres … til:` | 62 | 41 % |
| `indsættes efter` | 33 | 22 % |
| `indsættes som` | 23 | 15 % |
| omnummerering (`… bliver …`) | 21 | 14 % |
| `ophæves` | 15 | 10 % |
| `affattes således` / `affattes som` | 12 | 8 % |
| `udgår` | 9 | 6 % |
| `indsættes før` | 0 | 0 % |

Summen overstiger 151, fordi ét punkt kan indeholde flere operationer. Tallene er
optællinger på et enkelt lovområde og skal ikke læses som en generel fordeling.

Fire ting fra optællingen har direkte konsekvenser for modellen:

**Et punkt er ikke én operation.** 21 af 151 punkter (14 %) rammer mere end ét mål —
fx "I § 9 C, stk. 3, 1. pkt., ændres »4. pkt.« til: »4. og 5. pkt.«, og i 2. pkt.
indsættes efter »kilometertakst«: …". `operation`-tabellen skal kunne rumme flere rækker
med samme `amendment_path` ("§ 1, nr. 1"), og `amendment_path` kan altså ikke være unik.

**Tekstudskiftning har en multiplicitet.** To punkter siger "ændres to steder »X« til".
En `replace_text`-operation kan derfor ikke bare erstatte første forekomst; den skal bære
et eksplicit antal forekomster, og replay skal fejle hårdt, hvis det faktiske antal i
teksten afviger.

**Målopmærkningen er næsten, men ikke helt, komplet.** 142 punkter har målet i
`signiChar="AendringURN"`, 8 har det kun kursiveret uden `signiChar`. Parseren skal
acceptere begge. Det ene resterende punkt er "Efter § 2 A indsættes: § 2 B. …", hvor en
helt ny paragraf indsættes og ankeret står i almindelig tekst. Det er 150 af 151 (99 %)
med strukturelt mål og ét, der kræver tekstparsing.

**Klassifikation er ikke anvendelse.** At alle 151 punkter kan henføres til et verbum
betyder kun, at vi ved, *hvilken slags* operation der er tale om. Det siger intet om, at
operationen kan anvendes deterministisk på teksten — kun replay mod den næste
lovbekendtgørelse kan afgøre det. Forventningen er, at anvendelsesgraden bliver mærkbart
lavere end 100 %, især for `affattes` (12 punkter), hvor den nye tekst kan spænde over
flere stykker med egen intern struktur.

Analysen kan gentages med `python lovhistorik/probe.py mine eli/lta/2025/1500`, og
materialet kan gennemses instruks for instruks med `streamlit run lovhistorik/app.py`.
Begge bruger `lex_dania.py`, så de ikke kan komme til at måle forskellige ting.
Dokumenterne caches i `lovhistorik/.cache/`, så gentagne kørsler ikke belaster kilden.

Kursivering duer ikke alene som målangivelse. Den bruges også om den nye betegnelse
("indsættes som *stk. 2:*"), så antallet af kursiverede tekststykker siger intet om
antallet af mål. Kun `signiChar="AendringURN"` kan tælles.

## Numre er et selvstændigt niveau

Opremsninger ligger som `<Indentatio formaInd="Nummer">` inde i `<Stk>`, med eget
`<Explicatus>` ("1)") og egne `<Linea>`. Det afgørende er, at **punktumnummereringen
starter forfra inden for hvert nummer**. I § 7 P, stk. 7, nr. 3 henviser tredje punktum
til "1. pkt.", og det betyder nummerets første punktum — ikke stykkets.

Den atomare enhed er derfor (paragraf, stykke, nummer), hvor nummer kan være tomt.
Stykkets egen indledning ("Skattefriheden efter stk. 1 er betinget af følgende:") er en
enhed for sig, adskilt fra numrene. For ligningsloven vokser antallet af enheder fra 553
til 800, når numrene tælles med.

Behandler man et stykke som én tekst, slår "nr. 1, 1. pkt." fejl, fordi den peger på
stykkets indledning i stedet for nummerets første punktum. Fejlen er tavs: der findes
et punktum på pladsen, det er bare det forkerte.

Peger en instruks kun på et stykke, som har numre, er målet tvetydigt, og afspilningen
skal fejle frem for at gætte. Teksten kan stå i flere numre, og et punktumnummer betyder
noget forskelligt i hvert af dem.

## Testintervallet

Afspilningen prøves af på et lukket interval, hvor facit er kendt:

```text
LBK nr 42 af 13/01/2023      udgangspunkt
  + 32 ændringslove          alle med eli:changed_by på LBK 42
  = LBK nr 1500 af 24/11/2025   facit, jf. eli:consolidates
```

LBK 1500 angiver selv, at den konsoliderer præcis LBK 42 plus de 32 love, og LBK 42
peger tilbage med `eli:consolidated_by`. Mængden er altså ikke vores skøn, men kildens
egen afgrænsning. Det gør intervallet til et testorakel: afspiller vi de 32 love oven på
LBK 42 og rammer LBK 1500's ordlyd, er operationerne rigtige.

**Målangivelser kan læses.** En målangivelse som "§ 9 C, stk. 3, 1. pkt." omsættes til
paragraf, stykke og punktumnumre med simple regler, og paragrafnummeret sammensættes til
samme form som `Paragraf/@localId`, så det kan slås direkte op. Prøvet på de 38
ændringspunkter i de ni love, der ændrer LBK 1500: 37 mål kunne læses, og alle 37 pegede
på en paragraf og et stykke, der faktisk findes. Det ene resterende er punktet uden
opmærket mål, hvor en helt ny paragraf indsættes.

**Delvis ikrafttræden er ikke et særtilfælde.** LOV 749 af 2025 optræder i både
`consolidates` og `changed_by`, og dens § 1, nr. 4 vil indsætte et 6. punktum i § 12 B,
stk. 2 — men det punktum står der allerede i LBK 1500, ordret. Dele af loven er altså
konsolideret ind, mens andre dele endnu ikke er trådt i kraft. Samme lov affatter i nr. 7
og nr. 8 det samme stykke to gange med forskellig ordlyd, hvilket kun giver mening med
hver sin ikrafttrædelsesdato.

Konsekvensen er, at afspilningen ikke kan nøjes med at anvende alle operationer fra en
lov. Hver operation skal bære sin egen ikrafttrædelsesdato, og rækkefølgen skal følge
datoerne, ikke lovnumrene. Det er også derfor, en operation, hvis virkning allerede står
i teksten, ikke uden videre må regnes for en fejl.

## Første afspilning

Kørt med `python lovhistorik/probe.py replay eli/lta/2023/42 eli/lta/2025/1500`. Alle
151 ændringspunkter forsøges udført på LBK 42's tekst, og resultatet sammenlignes ordret
med LBK 1500.

| Mål | Ligningsloven | Afskrivningsloven | Skatteindberetningsloven |
| --- | --- | --- | --- |
| Ændringslove indarbejdet | 29 | 8 | 3 |
| Operationer udført | 55 af 104 (53 %) | 12 af 21 (57 %) | 1 af 3 |
| Berørte enheder der rammer ordret | 30 af 43 (70 %) | 9 af 12 (75 %) | 1 af 1 |
| Afviger trods lykkedes operationer | 7 | 2 | 0 |

De to sidste love er kørt uden en linje kode tilpasset til dem. Lovens navn udledes af
den fulde titel, fordi `title_short` er dokumentnummeret ("LBK nr 42 af 13/01/2023") og
ikke lovens kaldenavn.

## Lovbekendtgørelsen opregner selv sine ændringer

Det største enkeltstående fremskridt kom af at holde op med at gætte, hvilke
ændringslove der skal afspilles. `eli:changed_by` rummer alle love, der nogensinde
ændrer loven, også dem der endnu ikke er trådt i kraft. Afspiller man dem alle, bliver
teksten "for ny" på en måde, der er svær at få øje på: enkelte ord er skiftet ud, og
resten passer.

Lovbekendtgørelsens indledning siger det derimod præcist:

> Herved bekendtgøres skatteindberetningsloven, jf. lovbekendtgørelse nr. 15 af 8. januar
> 2024, med de ændringer, der følger af § 10 i lov nr. 1454 af 10. december 2024, § 13 i
> lov nr. 1473 af 10. december 2024 og § 3 i lov nr. 563 af 27. maj 2025.

Den angiver både udgangspunktet, de indarbejdede ændringslove **og hvilken paragraf i
hver af dem**. Det sidste er nødvendigt, fordi en lov kan ændre samme lov flere steder
med hver sin ikrafttræden. De efterfølgende afsnit begrunder oven i købet, hvad der ikke
er indarbejdet, og hvornår det træder i kraft.

Virkningen af at bruge listen frem for `changed_by`:

| Lov | Træfsikkerhed før | Efter |
| --- | --- | --- |
| Ligningsloven | 59 % | 70 % |
| Afskrivningsloven | 56 % | 75 % |
| Skatteindberetningsloven | 10 % | 100 % |

Skatteindberetningsloven viser, hvor galt det kan gå: 6 love blev afspillet, hvor kun 3
hørte til. Loven har et kort interval, hvor de fleste ændringer endnu ikke var trådt i
kraft, og motoren ramte derfor kun 1 af 10 enheder.

Kan sætningen ikke læses, falder afspilningen tilbage på `changed_by`, men det skal
betragtes som en nødløsning, og kilden oplyses i outputtet.

### Paragrafangivelsen mangler, når hele loven er indarbejdet

Listen er ikke ensartet. Ændrer hele ændringsloven kun den ene lov, udelades
paragrafangivelsen, og der står blot lovens navn:

> … § 2 i lov nr. 1061 af 22. november 2011, **lov nr. 1379 af 28. december 2011**, § 1 i
> lov nr. 1382 af 28. december 2011 …

Mit mønster krævede "§ N i" foran, så sådanne love forsvandt lydløst fra listen — ikke
med en fejl, men ved at ingen ændringer fra dem nogensinde blev fundet. Paragrafdelen er
nu valgfri, og paragraf `0` betyder "hele loven". Ligningslovens måltal ændrede sig ikke
af rettelsen, men fejlen ville ramme vilkårligt og usynligt på andre love.

**Det andet tal er det ærlige.** At 637 af 800 enheder er identiske med facit lyder
godt, men de fleste af dem er aldrig blevet rørt — de var ens i forvejen. Kun de
enheder, en operation faktisk har ændret, siger noget om, hvor god motoren er.

De 69 operationer, der ikke kunne udføres, fordeler sig sådan:

| Årsag | Antal | Vurdering |
| --- | --- | --- |
| Flere mål i samme punkt | 21 | Kendt begrænsning; kræver at hvert verbum knyttes til sit eget mål |
| Nyt stykke indsat, med omnummerering | 12 | Kræver at efterfølgende stykker kan flyttes |
| Ophævelse, med og uden omnummerering | 14 | Samme |
| Nyt nummer eller stykke indsat | 6 | Samme |
| Målet kunne ikke læses | 4 | Målangivelser uden paragrafnummer |
| Teksten kunne ikke findes | 4 | De alvorlige — se nedenfor |
| Forkert antal forekomster | 4 | Do. |

### To slags afvigelser

En berørt enhed kan afvige af to grunde, og de kræver helt forskelligt arbejde. Enten
fejlede en anden operation på samme enhed, så teksten kun er halvt opdateret — det er
manglende dækning. Eller også lykkedes alle operationer, og teksten er stadig forkert —
det er en fejl i motoren. Afspilningen skelner mellem de to.

Det tal skal ned først, for det er dér motoren tager fejl uden at sige det. Bemærk dog,
at det overvurderer antallet af egentlige motorfejl: når et ændringspunkt med flere mål
fejler, kender vi kun dets første mål, så forureningen af de øvrige er usynlig for
analysen. Den svaghed forsvinder først, når punkter med flere mål deles op.

Fejlklasser fundet og rettet:

- **Etiketten fulgte med ved genaffattelse.** Ny tekst indledes med "§ 5 D." eller
  "Stk. 4.", som er etiket og ikke lovtekst. Rettet.
- **Indsat frase manglede mellemrum.** Anker og ny tekst citeres hver for sig uden det
  mellemrum, der adskiller dem i loven. Rettet med en heuristik: der indsættes mellemrum,
  medmindre den nye tekst begynder med tegnsætning.
- **Sletning efterlod forkert mellemrum.** Rettet ved oprydning, der kun rører mellemrum.
- **Forskudte stykker.** Et indsat eller ophævet stykke forskyder alle de følgende. Ikke
  rettet; det er omnummereringsarbejdet.
- **Genaffattelse af flere stykker på én gang.** Ny tekst kan rumme både "Stk. 1." og
  "Stk. 2.", og hele klumpen havner i det første stykke. Ikke rettet.
- **Noter læses som lovtekst.** I facit optræder tekst som "Den bekendtgjorte lovtekst
  vedrørende § 8 X, stk. 4, 3. pkt., har virkning fra …" som var det en bestemmelse. Det
  er en fejl i udtrækket af lovbekendtgørelsen, ikke i afspilningen, og den gør facit
  forkert. Ikke rettet.

De to sidste er fundet ved at køre på flere love og optræder i mere end én af dem.

Skellet mellem de to grupper er vigtigt. De 53 første er funktioner, der ikke er bygget
endnu, og de fejler højlydt med en begrundelse. De sidste 8 er tilfælde, hvor vi mener
at have forstået instruksen, men ikke kan finde teksten — og det er dér, en stille fejl
kunne opstå. De skal undersøges enkeltvis, ikke afhjælpes med en løsere søgning.

Omnummerering går igen i 32 af de 69 fejl. Det er det største enkeltstående stykke
arbejde, og det bekræfter modellens valg om at behandle etiketter som tidsversionerede
attributter frem for identitet.

**Rækkefølgen er kun tilnærmet.** Lovene anvendes sorteret efter underskriftsdato, ikke
efter ikrafttrædelsesbestemmelse. Det er forkert for delvis ikrafttræden, hvor dele af en
lov virker på forskellige tidspunkter, og en del af afvigelserne skyldes formentlig det.
Ikrafttrædelsesbestemmelserne skal læses, før tallene kan tages for pålydende.

## Målt uden for skatteområdet

Alle tre testlove var skattelove. Det er en snæver base, og målingerne sagde derfor mere
om, hvordan Skatteministeriet skriver, end om motoren. Færdselsloven (LBK 118/2026,
transportområdet, 224 paragraffer, kæde tilbage til 2006) blev valgt som modprøve.

Første kørsel: **9 uforklarede lækager mod 0 på skattelovene**, og fire
lovbekendtgørelser, hvis liste over indarbejdede ændringer slet ikke kunne læses. Hver af
dem slugte en hel periode uden at noget fejlede.

Årsagen var den samme i alle fire: **indledningen er brudt over flere tekstblokke.**

    [3] "… med de ændringer, der følger af lov nr."
    [4] "1241 af 18. december 2012, § 1 i lov nr."
    [5] "1246 af 18. december 2012, lov nr. 1389 af 23. december 2012, …"
    [6] "De ændringer, der følger af § 1, nr. 5, … er ikke indarbejdet …"

Bruddet falder vilkårligt — midt i en dato, midt i "lov nr." — og læses blokkene hver
for sig, standser opremsningen ved det falske punktum. Skattelovene har indledningen i
én blok, så fejlen kunne ikke ses dér.

Blokkene sammenkædes nu, men kun så længe de tydeligt fortsætter opremsningen. Grænsen er
afgørende: umiddelbart efter listen står sætningerne om ændringer, der udtrykkeligt
*ikke* er indarbejdet, og de må aldrig havne i listen. Det ville være den værre fejl.

To detaljer kostede hver sin runde:

- **Det afsluttende punktum er ikke garanteret.** LBK 1320/2010 slutter opremsningen uden
  punktum, og kravet kostede hele listen.
- **Sammenkædningen ødelagde selv "lov nr."** Punktummet efter "af" er en artefakt af
  ombrydningen og skal væk; punktummet i "nr." er en del af henvisningen og skal blive.
  Første forsøg fjernede begge, og netop de to love, der var brudt over "lov nr.",
  forblev usynlige.

Efter rettelsen: **0 uforklarede lækager** på færdselsloven, 85 ændringslove mod 76 før.
Skattelovene er uændrede — samme antal love, samme bemærkninger, samme afspilning.

Tilbage står ét dokument fra 2006, hvis indledning ikke kan læses. Det samme gælder
ligningsloven (LBK 1061/2006) og afskrivningsloven (LBK 856/2006). Mønstret er
konsistent: 2006-årgangen er mærket op anderledes, og dér ender kæden.

Fundet siger noget generelt: **en måling på ét ressortområde måler ressortet, ikke
motoren.** Fejlen havde ligget der hele tiden og var usynlig på tre love i træk.

## Retsinformations egen tidslinje

Under hver forskrift viser Retsinformation en tidslinje. Den hentes fra

    /api/document/{UniqueDocumentId}/timeline

og `<UniqueDocumentId>` står i den XML, vi allerede henter. Endpointet svarer JSON uden
særlige headere. Ligningsloven har 633 poster tilbage til LBK 399/1979.

Hver post har `signatureDate`, `isOutOfOrder` og `errorsBeforeItem`, hvor Retsinformation
selv oplyser om huller — for ligningsloven at tidslinjen begynder i 1979, fordi ældre
dokumenter ikke er indlagt.

**Tidslinjen forklarer ikke afvigelserne i afspilningen.** For testintervallet LBK
42/2023 → LBK 1500/2025 er tidslinjens segment identisk med lovbekendtgørelsens egen
liste: samme 32 love, samme rækkefølge. Formodningen om, at en del af afvigelserne
skyldtes rækkefølgen, er dermed afkræftet for ligningsloven.

Tidslinjen kan heller ikke erstatte indledningen. For afskrivningsloven rummer segmentet
LOV 749/2025 og for skatteindberetningsloven yderligere LOV 198 og 409 — love, der ligger
i perioden, men ikke er indarbejdet. Indledningen er fortsat den eneste kilde til, *hvad
der er indarbejdet*.

Værdien er som **uafhængig krydskontrol**: vores liste skal være en delmængde af
tidslinjens segment. Den ville have fanget færdselslovsfejlen med det samme.

Alt før 2007 er tomme skaller. LBK 1061/2006 fylder 11 KB og giver 0 bestemmelser; det
samme gælder alle ældre. 2006-grænsen er altså kildens, ikke vores, og de 633 poster
giver ikke adgang til ældre lovtekst.

**Hvad afvigelserne så skyldes.** Af de 12 enheder, der afviger trods lykkedes
operationer, er 2 fejl i facit: noter som "Den bekendtgjorte lovtekst vedrørende § 8 X,
stk. 4, 3. pkt., har virkning fra …" læses som lovtekst. Resten er forkert valgt
forekomst — § 7 O får "stk. 7" hvor facit har "stk. 8", og § 12 B, stk. 4 får "efter stk.
10" hvor facit har "efter afskrivningslovens § 40, stk. 7". Endepunktet `reprintNotes`
kunne se ud til at løse det første, men er tomt for ligningsloven.

## Forarbejdssøgningens kvalitet, målt

Målt på 105 ændringer fordelt på syv paragraffer i ligningsloven (§§ 7, 7 P, 8 A, 9 C,
15, 16, 33 A):

| | antal | andel |
|---|---|---|
| ændringer fundet | 105 | |
| med bemærkning | 95 | 90,5 % |
| bekræftet ved at bemærkningen nævner paragraffen | 87 | 82,9 % |
| bemærkning dækker hele ændringsparagraffen, ikke punktet | 16 | 16,8 % af de fundne |

**De 10 manglende har alle samme årsag.** Punktet findes ikke i lovforslaget, fordi det
kom ved et ændringsforslag under behandlingen. Bemærkningen står da i betænkningen, som
vi ikke henter. Det er ikke spredte fejl, men én manglende funktion.

**Bekræftelsesmålet var for strengt.** Alle fire ubekræftede bemærkninger til § 9 C blev
efterprøvet, og alle fire er rigtige: de handler om befordringsfradrag, men nævner ikke
"§ 9 C", fordi hele ændringsparagraffen handler om den bestemmelse, så nummeret er
overflødigt. Målet talte dem som mistænkelige, og 19 af 23 underdrev kvaliteten.

### Bekræftelse ved ordoverlap

Bemærkningen citerer som regel den ordlyd, ændringen indsætter, så et langt fælles
ordforløb er et selvstændigt tegn på, at de hører sammen. Tærsklen blev valgt på en
måling af 49 bemærkninger, der nævner målparagraffen og derfor er sikkert koblet:

| længste fælles ordforløb | andel af de sikkert koblede |
|---|---|
| mindst 5 ord | 100 % |
| mindst 6 ord | 94 % |
| mindst 8 ord | 65 % |
| mindst 10 ord | 53 % |

Ingen af de sikkert koblede deler under 5 ord, og medianen er 10. Tærsklen blev sat til
**8 ord** — over minimum, fordi et kort forløb kan være almindeligt lovsprog frem for et
citat. En falsk bekræftelse er værre end en falsk alarm, da den får en forkert kobling
til at se efterprøvet ud.

Blandt de bemærkninger, der ikke nævner paragraffen, skiller tærsklen skarpt: de tydeligt
rigtige delte 9, 10 og 22 ord med ændringen, mens resten delte 0-2.

**Manglende overlap er kun mistænkeligt, hvis der var noget at genfinde.** En ophævelse
("§ 16, stk. 14, 2. pkt., ophæves") citerer ingen tekst, og en henvisningsændring citerer
kun »3. pkt.«. I begge tilfælde kan bemærkningen ikke gengive noget, og fraværet siger
intet. Længde alene dur ikke som kriterium — »3. eller 4. pkt.« fylder 16 tegn uden at
være lovtekst — så et citat regnes først for ordlyd, når det rummer mindst tre ord på tre
bogstaver eller mere.

Målt på de samme syv paragraffer, 94 bemærkninger:

| | antal | andel |
|---|---|---|
| bekræftet | 89 | 95 % |
| kan ikke efterprøves (ingen ordlyd at genfinde) | 4 | |
| mistænkelig — burde kunne bekræftes, men kan ikke | 1 | |

Antallet af koblinger, et menneske skal se efter, faldt fra 8 til 1. Den tilbageværende
er en grænsesag: LOV 1539/2014 § 9, nr. 1 deler 6 ord med sin bemærkning, som klart
handler om samme navneskifte, men falder under tærsklen. Den er markeret til eftersyn,
og det er den rigtige side at fejle til.

## Betænkninger kan ikke hentes

Alle ti manglende bemærkninger havde samme årsag: punktet stod ikke i det fremsatte
lovforslag, fordi det kom ved et ændringsforslag under udvalgsbehandlingen. Bemærkningen
står da i betænkningen. Vejen dertil blev undersøgt og er lukket.

Betænkningen findes i Folketingets åbne data, men kun som metadata. På sag 102023 (L 178)
ligger den som `Dokument` med typeid 12 — altså "Bilag", ikke en egen dokumenttype — og
kendes på titlen "Betænkning afgivet den 7. maj 2025". Selve teksten står ikke i
datamodellen. `Dokument` har intet tekstfelt, og `Fil` peger på

    https://www.ft.dk/samling/20241/lovforslag/l178/bilag/6/3019075.pdf

To forhold spærrer:

- **Formatet er PDF.** Af de undersøgte betænkninger findes ingen i XML, HTML, DOC eller
  andet. Lovforslagene er mærket op i Lex Dania; betænkningerne er det ikke.
- **www.ft.dk er beskyttet af Cloudflare.** Alle forespørgsler svarer HTTP 403, også på
  almindelige HTML-sider og uanset User-Agent, Accept eller Referer. En browser slipper
  igennem efter en JavaScript-udfordring med teksten "This website uses a security service
  to protect against malicious bots". Beskyttelsen er tilsigtet og omgås ikke. Bemærk at
  `oda.ft.dk` ikke er omfattet — det er kun filerne, der er utilgængelige.

Retsinformation har heller ikke betænkningen: `eli/ft/202412L00178` er det fremsatte
forslag og indeholder nul forekomster af "ændringsforslag", og et `…B`-opslag giver 404.

**Hvad der så blev gjort.** Svaret sagde tidligere "kom formentlig ved ændringsforslag" —
en formodning, ingen havde efterprøvet. Den slås nu op i Folketingets data, og svaret
oplyser betænkningens fulde titel og et link til den. Brugeren kan læse den selv; vi
foregiver ikke at have gjort det.

Vigtigere er, hvad opslaget kan afsløre. Findes der *ikke* et ændringsforslag på sagen,
er forklaringen forkert, og der gemmer sig en anden fejl. Svaret siger da "årsagen er
ukendt" i stedet for at gentage en formodning, der ikke holder. For alle ti undersøgte
punkter blev formodningen bekræftet, men det vides nu, i stedet for at være antaget.

Titlerne matches på begyndelsen, ikke som delstreng. "1. udkast til betænkning" er ikke
den afgivne, og et spørgsmål *om*, hvorfor der ikke blev stillet ændringsforslag, er ikke
et ændringsforslag. En delstrengssøgning forvekslede netop de to på L 129.

## Målt bredt på skatteretten

Motoren skal bruges til skatteret, og tre love er ikke skatteretten. De centrale love blev
derfor fundet ved at spørge en samlelov, hvad den ændrer: `probe.py laws eli/lta/2023/679`
opregner 49 love med deres nyeste lovbekendtgørelse, og `eli/lta/2023/1563` gav resten.
Det er hurtigere og mere pålideligt end at skrive listen selv.

Lækagetesten på 19 skattelove — 834 ændringslove, 3.638 ændringspunkter — fandt **25
uforklarede lækager**, altså ændringslove som ingen lovbekendtgørelse påtager sig. Tre
fejl stod bag dem, alle i den samme sætning: den indledning, hvor bekendtgørelsen opregner,
hvad den har indarbejdet.

| Formulering | Hvor | Kostede |
| --- | --- | --- |
| "med de ændringer **og tilføjelser**, der følger af" | personskattelovens LBK 143/2011 | 21 love |
| "med **den ændring**, der følger af" (ental) | fondsbeskatningslovens LBK 1192/2007 | 1 lov |
| Indledningen afbrudt af indskudte bemærkninger | kursgevinstlovens LBK 140/2008 | 3 love |

Den sidste er den mest lærerige. Sætningen begynder "Herved bekendtgøres … (kursgevinstloven)",
brydes af to blokke om ændringer, der *ikke* er indarbejdet, og tages op igen med ", jf.
lovbekendtgørelse nr. 978 …". Sammenkædning af nabolinjer hjælper ikke, når der står noget
imellem, så fortsættelsen genkendes på sin egen form: indledende komma efterfulgt af "jf.
lovbekendtgørelse". Kravet er ikke pynt. De indskudte blokke lyder "Lovbekendtgørelsen
indeholder ikke de ændringer, der følger af § 6 i lov nr. 1534 …", og en løsere søgning
ville føje netop den lov til listen. At mangle en lov er slemt; at tilføje en, der
udtrykkeligt ikke er indarbejdet, er værre.

Efter rettelserne står **2 lækager tilbage af 3.638 punkter**, begge samme lov, og de er
ikke vores. Lov 1052/2020 ændrer selskabsskattelovens § 23, stk. 1, fra "15,24 pct." til
"14,24 pct.". LBK 251/2021 siger 15,24; LBK 1241/2022 siger 14,24. Ændringen *er* altså
indarbejdet, men ingen bekendtgørelse i kæden nævner loven i sin indledning. Det er en
udeladelse i kilden, og den bør ikke skjules ved at udvide listen med gæt.

## Et plausibelt årstal er farligere end et umuligt

Opkrævningslovens LBK 569/2014 skriver "§ 8 i lov nr. 1634 af 26. december **2012**". Loven
er fra 2013. Det tidligere kendte tilfælde — "19. december 2207" — var ufarligt, netop
fordi året var umuligt: det kunne ikke slås op, og fejlen meldte sig selv. Her består
årstallet enhver rimelighedsprøve. Uden kontrol henter vi forarbejder til en anden lov,
eller til ingen, og intet ser forkert ud.

Derfor efterprøves nu hvert årstal mod `eli:changed_by` for den bekendtgørelse, der blev
konsolideret, ikke kun de umulige. Men rettelsen må ikke være automatisk: lovnumre genbruges
hvert år, og både lov 753/2023 og lov 753/2025 findes. Er en lov fraværende fra listen, kan
listen være ufuldstændig — det beviser ikke, at årstallet er forkert. Rettelsen kræver
derfor to ting: præcis én lov med samme nummer i listen, **og** at den angivne sti giver
404. Kun et bevist fravær gør omskrivningen forsvarlig. Derfor bærer `FetchError` nu sin
HTTP-status: 404 betyder "findes ikke", mens en afbrudt forbindelse intet betyder.

## Uden genforsøg er svaret ikke deterministisk

To ens opslag på ligningslovens § 16 gav 49, 48 og 49 bemærkninger. Forskellen var ikke
tilfældig støj i optællingen, men en hentning, der faldt undervejs og blev til "kunne ikke
hentes". Fejlen blev rapporteret — den var ikke tavs — men resultatet afhang af netværkets
luner, og det er uacceptabelt, når to jurister skal kunne stille samme spørgsmål og få
samme svar.

Med varm cache er systemet deterministisk: to fulde kørsler af § 16 gav byte for byte
samme output. Variationen opstår kun, mens cachen bygges. `fetch` genforsøger derfor tre
gange med voksende ventetid, men kun det, der kan gå over: 5xx og netværksfejl. 4xx
gentages ikke, for et 404 bliver ikke et andet svar af at blive spurgt igen — og et
manglende led er normalt i en kæde, så ventetid dér ville koste på hvert eneste opslag.

## "Ingen ændringer" må ikke betyde "fandt ikke paragraffen"

Et opslag på en paragraf, der ikke findes, svarede præcis som et opslag på en paragraf, der
aldrig er ændret: med ingenting. For en jurist er de to svar modsatte. Det ene siger
"bestemmelsen har stået uændret siden 2007", det andet "du har slået noget op, der ikke er
der". Motoren kontrollerer nu, om paragraffen står i den valgte bekendtgørelse, og siger
det ligeud, når den ikke gør.

Sammenligningen skal være uafhængig af versaler. Lex Danias `localId` staves ikke ens fra
lov til lov: ligningsloven skriver `9C`, personskatteloven `8a`. Et versalfølsomt opslag
ville melde "findes ikke" om en paragraf, der står der.

Undervejs blev det efterprøvet, at nul ændringer af personskattelovens § 8 a faktisk er
rigtigt: af 51 ændringslove i kæden rammer ingen § 8 a, kun § 8. Et tomt svar er altså ikke
i sig selv mistænkeligt — det skal bare kunne skelnes fra et fejlslagent opslag.

## Forarbejdskvaliteten målt bredt

258 ændringspunkter fordelt på 16 paragraffer i 10 skattelove:

| Mål | Antal | Andel |
| --- | --- | --- |
| Ændringspunkter | 258 | |
| Med bemærkning | 231 | 89,5 % |
| Bekræftet kobling | 196 | 84,8 % af dem med bemærkning |
| Mistænkelige | 6 | 2,3 % |

Af de 27 punkter uden bemærkning kom **26 ved ændringsforslag i en betænkning** — den
kendte, lukkede vej beskrevet ovenfor. Det sidste er L 43, som ikke har nogen bemærkning
til § 1, nr. 12. Manglerne er altså forklarede, ikke tavse, og det er den egenskab, der
afgør, om motoren kan bruges fagligt.

De 12 rapporterede problemer er alle kædens ende: en lovbekendtgørelse fra 2003-2007, hvis
indledning ikke kan læses, fordi Lex Dania-opmærkningen først begynder omkring 2007.

Tidsforbruget med kold cache er 2-141 sekunder pr. paragraf, gennemsnitligt omkring 48.
Det skaleres med kædens længde og antallet af ændringer, ikke med lovens størrelse. Med
varm cache svarer opslaget på under et sekund. ODA-opslag caches ikke og koster 0,58
sekunder hver.

## En håndholdt liste over lovbekendtgørelser forælder

Applisten pegede på faste lovbekendtgørelser, og to af dem var allerede overhalet, uden at
det kunne ses: skatteforvaltningsloven havde fået LBK 1228/2025 og tinglysningsafgiftsloven
LBK 307/2025. Den, der slog op, ville have fået svar om en forældet retstilstand uden
nogen antydning af, at der fandtes en nyere udgave.

Listen indeholder derfor nu kun et *holdepunkt* pr. lov, og `newest_consolidation` følger
`eli:consolidated_by` fremad til den seneste udgave. Det virker, fordi `fetch_metadata`
ikke har diskcache: en ny bekendtgørelse opdages med det samme. I appen caches opslaget i
seks timer, så det ikke gentages ved hvert klik.

Kun bekendtgørelser af *samme* lov må følges. På en ændringslov peger `consolidated_by`
nemlig på enhver bekendtgørelse, der har indarbejdet den — LOV 871/2022 peger blandt andet
på ligningslovens LBK 1500/2025 — så uden navnekontrollen ville et opslag ende i en helt
anden lov. Kontrollen er efterprøvet: to ændringslove føres ikke videre.

Ejendomsavancebeskatningsloven kunne ikke findes ved at søge på sit navn. Den hedder i
metadata "lov om beskatning af fortjeneste ved afståelse af fast ejendom", og kortformen
optræder ikke. Kortnavne er ikke en pålidelig nøgle.

## En bekendtgørelse uden ændringer er ikke altid en fejl

Tinglysningsafgiftslovens LBK 307/2025 har ingen opremsning af indarbejdede ændringer.
Indledningen slutter ved "jf. lovbekendtgørelse nr. 27 af 13. januar 2025." og fortsætter:
"De ændringer, der følger af § 1, nr. 11, i lov nr. 168 … var ved en fejl ikke indarbejdet
korrekt i lovbekendtgørelse nr. 27 … Disse fejl er nu rettet med denne lovbekendtgørelse."

Den er altså udsendt for at rette den forrige, ikke for at indarbejde noget nyt. Den tomme
liste er korrekt, og advarslen "ingen læselig liste over ændringer" var en falsk alarm.
Det er ikke en bagatel: falske alarmer lærer den, der læser svaret, at se bort fra
advarsler, og så overses den ægte. `restates_only` skelner nu de to, efterprøvet mod syv
bekendtgørelser — herunder kædens ende fra 2006, som stadig skal give en ægte advarsel.

## Grænsen for dokumentstørrelse ramte igen

LOV 1489/2024 fylder 85,4 MB og faldt uden for grænsen på 64 MB. Den ændrer
skatteforvaltningslovens § 32 a to steder, og begge bemærkninger var utilgængelige. Fejlen
var synlig — den blev rapporteret som et problem, ikke slugt — men den kostede indhold.

Prisen for at læse dokumentet blev målt før grænsen blev hævet: 3 sekunder at parse, spids
**1,1 GB hukommelse** under udtrækket, for at finde to ændringspunkter. Grænsen er nu 128
MB. Skal den længere op, bør `extract_instructions` skrives om til `iterparse`, for
hukommelsen vokser med dokumentets størrelse, ikke med det, vi leder efter.

## Målt på hele applisten

21 skattelove, 923 ændringslove, 4.126 ændringspunkter: **2 uforklarede lækager**, begge
den dokumenterede udeladelse af lov 1052/2020 i selskabsskattelovens indledninger, og
**ingen ulæselige indledninger efter 2007**. De resterende ulæselige bekendtgørelser er
alle fra 2003-2007, hvor Lex Dania-opmærkningen endnu ikke fandtes, og udgør kædens ende.

De to nye love blev målt for første gang: ejendomsavancebeskatningsloven (14 ændringslove,
25 punkter) og pensionsbeskatningsloven (67 ændringslove, 452 punkter), begge uden lækager.

## Motoren som fane i JAILA

Søgningen er lagt ind i JAILA som en selvstændig fane, "Forarbejder". Streamlit-appen
blev *ikke* lagt i en ramme inde i JAILA, selv om det var det nærliggende. Tre forhold
talte imod, og de er tekniske, ikke æstetiske:

* Streamlit sætter selv `X-Frame-Options` og taler med sin browserflade over en
  websocket. At vise den inde i JAILA kræver både en omvej uden om den beskyttelse og en
  websocket-viderestilling i nginx.
* Den ville være en proces mere at holde kørende, med sin egen session og sit eget udseende.
* Vigtigst: svaret ville blive siddende i rammen. Formålet er at give sprogmodellen et
  fortolkningsbidrag, og en ramme er netop det, der forhindrer data i at komme videre.

I stedet kalder fanen motoren gennem fire endepunkter. `forarbejder.py` og `lex_dania.py`
er uændrede som fagligt lag; `backend/services/forarbejder_service.py` oversætter kun
dataklasser til JSON. Kommer der forskellige svar i JAILA og i proben, er det en fejl i
oversættelseslaget — ikke en anden faglig vurdering.

Lovlisten er flyttet fra `app.py` til `forarbejder.py` af samme grund som søgelogikken:
to brugerflader, der hver har sin liste, kommer til at tilbyde hvert sit udvalg af love.

### Et enkelt opslag er for langsomt til et almindeligt svar

Et koldt opslag tager 20-140 sekunder. Svaret streames derfor, og `paragraph_history`
melder sin fremdrift gennem det `progress`-kald, den allerede havde. Målt på
ligningslovens § 9 C med tre led i kæden: 15 statuslinjer over 37 sekunder, 11 ændringer,
alle med bemærkning og alle bekræftet.

### Én ad gangen, og det skal siges

Motoren holder en fast pause mellem kald til Retsinformation og kan bruge op mod 1,1 GB
hukommelse på ét stort lovforslag. Kørte to opslag samtidig, ville begge dele fordobles,
og det er kilden, der betaler. Derfor slipper kun ét tungt opslag igennem ad gangen.

To forhold blev opdaget ved at prøve det frem for at antage det:

* **Ventetiden må ikke være tavs.** Ventes der i ét langt spring, ser nginx en forbindelse
  uden data og lukker den, længe før ventetiden er brugt. Der sendes derfor en linje hvert
  femte sekund om, at der ventes på tur.
* **En afbrudt forespørgsel afbryder ikke arbejdet.** Lukker browseren forbindelsen, kan
  kørslen ikke standses midt i et netværkskald. Gav vi turen fri med det samme, ville
  næste opslag ramme Retsinformation samtidig med et, vi troede var væk. Turen frigives
  derfor først, når den forladte kørsel er løbet ud. Arbejdet er ikke spildt: det, den når
  at hente, ligger i diskcachen bagefter.

### Cachen skrives nu atomisk

Så længe kun proben og Streamlit-appen brugte modulet, kørte der én hentning ad gangen, og
`cache_file.write_bytes(body)` var nok. Kaldes modulet fra en webserver, kan to
forespørgsler hente samme dokument samtidig, og en læser ville kunne ramme en halvskrevet
fil. Der skrives nu gennem en midlertidig fil, som byttes ind med `os.replace`. En læser
ser enten den gamle fil eller den færdige — aldrig noget derimellem.

### Fortolkningsbidraget formateres ét sted

Hver ændring får et færdigskrevet tekstafsnit med i svaret. Brugeren sætter flueben ved
dem, der er relevante, og sender dem til chatten, hvor de lægges ind sammen med
spørgsmålet. Formateringen sker i backend og ikke i browseren, så en kopiering, et
chat-spørgsmål og et eventuelt senere værktøjskald skriver det samme.

Forbeholdene står **inde i** teksten, ikke kun i brugerfladen: om koblingen er bekræftet,
om bemærkningen dækker hele ændringsparagraffen frem for det enkelte nummer, og om
ændringen kom ved et ændringsforslag, hvis bemærkning ikke kan hentes. En model, der kun
får bemærkningen, kan ikke selv vide, hvor sikker koblingen er.

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
  target_markup           TEXT NOT NULL,  -- signi_char | italic | text_parsed
                                          -- måler hvor meget vi læner os på fritekst
  payload_before          TEXT,
  payload_after           TEXT,
  occurrence_count        INTEGER,        -- kun replace_text: antal forekomster der
                                          -- skal rammes ("ændres to steder"). NULL
                                          -- betyder én. Replay skal fejle, hvis det
                                          -- faktiske antal i teksten afviger.
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
8. En `replace_text` anvendes kun, hvis antallet af forekomster i teksten er præcis det
   forventede — én, eller `occurrence_count`, hvis instruksen angiver et andet antal.
   Findes søgeteksten flere gange end forventet, er operationen tvetydig og skal fejle
   frem for at gætte på den første forekomst.
9. Koblingen til et lovforslag laves aldrig på `lovnummer` alene. Lovnumre genbruges
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

## Teststrategi

Prototypen bør ikke bindes op på én bestemmelse. Så længe testtilfælde vælges med
intuition, risikerer vi at vælge dem, motoren i forvejen kan klare, og så måler testen
ingenting. Strategien har derfor tre dele med hver sin rolle.

**Ende-til-ende: LL § 9 C, stk. 3.** Ændret ved LOV nr. 616 af 30/06/2026, som i én
ændringslov indeholder tre forskellige konstruktioner — fraseudskiftning inde i 1. pkt.,
indsættelse efter et bestemt ord i 2. pkt., og et nyt 5. pkt. Dokumentet er i Lex
Dania-XML, og forarbejdskæden er kendt: sag 105171, lovforslag L 4. Bruges til at
demonstrere hele kæden fra bestemmelse til specielle bemærkninger.

**Den egentlige måling: udvunden testmængde.** Hver ændringsinstruks mellem to
lovbekendtgørelser er et testtilfælde med automatisk facitliste — instruksen siger, hvad
der skal ske, og den næste lovbekendtgørelse viser resultatet. Testmængden udvindes
derfor maskinelt og stratificeres efter konstruktionstype (`ændres … til`,
`affattes således`, `indsættes som nyt punktum`, `ophæves`, `stk. X bliver stk. Y`).
Dækningsgraden måles pr. type, så vi ser hvor parseren er svag, i stedet for om den
lige akkurat klarer én paragraf.

**Grænsetest: LL § 9 A, stk. 3.** Ingen af de 9 ændringslove efter LBK nr. 1500 rører
bestemmelsen, så hele dens proveniens ligger før november 2025 og for de ældste
punktummer sandsynligvis før 2007. Den er derfor uegnet som første integrationstest —
en fejl ville ikke kunne skelnes fra manglende data. Den beholdes i stedet som test af,
at motoren melder ærligt om huller: den skal kunne sige, at 1. punktums oprindelse ikke
kan spores længere tilbage, frem for at gætte.

Acceptkriteriet formuleres herefter: motoren skal bestå på at *vide*, hvad den ikke kan
spore. En motor, der ærligt melder hul i historikken, er brugbar; en der gætter, er
værre end ingenting i juridisk sammenhæng.

## Åbne spørgsmål

Disse er empiriske og skal afklares med data, ikke med antagelser:

1. AFKLARET. Relationen findes ikke i ELI-metadata, men i Folketingets Åbne Data via
   parret `lovnummer` + `lovnummerdato`. Se afsnittet om verificeret adgang.
2. Hvor stor en andel af ændringsinstrukserne kan parses deterministisk?
   `operation.parse_status` måler det.
3. AFKLARET. Accessionen udledes som `{periodekode}2L{nummer:05d}`. Verificeret på ét
   lovforslag; mønsteret bør kontrolleres på et bredere udsnit, før det bruges blindt,
   særligt for delte lovforslag (fx "L 64 A") hvor nummeret ikke er rent numerisk.
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
