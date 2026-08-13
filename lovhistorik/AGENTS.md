# Retningslinjer for agenter i lovhistorik/

Denne mappe sporer dansk lovtekst tilbage til den ændringslov, der indsatte den, og
videre til lovforslagets specielle bemærkninger. Læs [DATAMODEL.md](DATAMODEL.md), før
du ændrer på datamodellen — den indeholder de empiriske målinger, beslutningerne bygger
på, og de er dyre at genskabe.

## Sprog og stil

Skriv på dansk: kommentarer, docstrings, commit-beskeder og svar til brugeren. Kode,
variabelnavne og databasefelter er på engelsk, som resten af projektet.

Foretræk realistisk og vedligeholdelsesvenlig kode frem for smarte konstruktioner. Undgå
unødvendige abstraktioner. Hvis noget er usikkert, så skriv antagelsen eksplicit i en
kommentar frem for at bygge videre på den i stilhed.

## Hvad der ikke må antages

Disse punkter er målt og har kostet tid at finde ud af. De må ikke gættes om igen:

- **Retsinformation er en single page-app.** Almindelige HTML-kald giver en tom React-
  skal. Brug `.rdfa` for metadata som JSON og `/dan/xml` for fuld Lex Dania-XML.
- **Ændringsinstrukser er strukturelt opmærkede.** Hvert nummereret punkt er et
  `<AendringsNummer>`, målbestemmelsen står typisk i `<Char signiChar="AendringURN">`,
  og den nye tekst ligger adskilt i `<AendringNyTekst>`. Skriv ikke en fritekstparser,
  der ignorerer den opmærkning.
- **`<Linea>` er ikke et punktum.** Ét `<Linea>` kan rumme flere punktummer; i LBK 1500
  gælder det 58 af 1.639. En `<Linea>`-grænse er altid en punktumgrænse, men ikke den
  eneste, så punktummer skal segmenteres med `split_sentences`. "pkt." må ikke behandles
  som en forkortelse, der forhindrer opdeling — "jf. dog 4. pkt. For befordring …" er den
  hyppigste sætningsafslutning i loven.
- **Numre har deres egen punktumnummerering.** Opremsninger ligger som
  `<Indentatio formaInd="Nummer">` inde i `<Stk>`. I § 7 P, stk. 7, nr. 3 betyder
  "1. pkt." nummerets første punktum, ikke stykkets. Den atomare enhed er derfor
  (paragraf, stykke, nummer). Slår man numrene sammen med stykket, rammer "nr. 1, 1. pkt."
  stykkets indledning i stedet — og fejlen er tavs, fordi der findes et punktum på
  pladsen. For ligningsloven er der 800 enheder mod 553, når numrene tælles med.
- **Kursivering er ikke en pålidelig målangivelse.** Den bruges også om den nye
  betegnelse ("indsættes som *stk. 2:*"), så antallet af kursiverede tekststykker siger
  intet om antallet af mål. Kun `signiChar`-mål kan tælles.
- **Ét ændringspunkt kan indeholde flere operationer.** 21 af 151 målte punkter rammer
  mere end ét mål, så et punktnummer som "§ 1, nr. 1" kan ikke bruges som unik nøgle.
- **Lovnummer alene identificerer ikke en lov.** Lovnumre genbruges hvert år. Koblingen
  til Folketingets data skal altid ske på lovnummer *og* dato, aldrig på titel, som
  ændrer sig undervejs i lovbehandlingen.
- **Konsoliderede og efterfølgende ændringslove er ikke disjunkte mængder.** En lov kan
  optræde i både `eli:consolidates` og `eli:changed_by` ved delvis ikrafttræden.
- **`eli:changed_by` må ikke bruges til at afgøre, hvad der skal afspilles.** Den rummer
  også love, der endnu ikke er trådt i kraft. Lovbekendtgørelsen opregner selv sine
  ændringer i indledningen ("med de ændringer, der følger af § 10 i lov nr. 1454 …"), og
  den angiver tilmed hvilken paragraf i hver ændringslov. Brug `consolidated_amendments`.
  Uden den ramte skatteindberetningsloven kun 1 af 10 enheder; med den 1 af 1.

## Ufravigelige regler for motoren

- Kun tekst, der stammer fra en lovbekendtgørelse, må vises som gældende ret. Tekst, vi
  selv har afspillet os frem til, bruges til at fastslå proveniens og må aldrig forlade
  motoren som lovtekst.
- En mislykket parsning gemmes som en række med fejlstatus, aldrig som en manglende
  række. Ellers kan dækningsgraden ikke måles, og problemet bliver usynligt.
- En tekstudskiftning anvendes kun, hvis antallet af forekomster i teksten er præcis det
  forventede. Ved tvetydighed skal operationen fejle frem for at gætte på den første
  forekomst.
- Sprogmodeller må ikke indgå i afspilningen eller i koblingen mellem bestemmelse og
  forarbejde. De er forbeholdt juridisk fortolkning oven på et færdigt, deterministisk
  resultat, og deres output er afledt data.

De fulde invarianter står i DATAMODEL.md.

## Kildeadgang

Vær varsom med Retsinformation og Folketingets Åbne Data. Der er ingen offentliggjorte
rate limits, så koden venter bevidst et sekund mellem kald. Hentede dokumenter caches i
`lovhistorik/.cache/`. Cachen har ingen udløbstid, fordi udgivelserne er uforanderlige.
Slet ikke cachen uden grund — en fuld genhentning tager cirka et minut pr. lov.

Al ny hentning og alt udtræk skal gå gennem `lex_dania.py`. Skriv ikke et parallelt
udtræk et andet sted; hele pointen med modulet er, at værktøjerne ikke kan komme til at
måle to forskellige ting.

## Verifikation

Efter ændringer i udtrækket skal denne kommando give uændrede tal, medmindre du bevidst
har ændret klassifikationen:

```bash
python lovhistorik/probe.py mine eli/lta/2025/1500
```

Forventet: 151 ændringspunkter fordelt på 39 love, 142 med mål i `signiChar`, 8 kun
kursiveret, 1 uden opmærket mål, 21 med flere mål, 2 med forekomstantal, og nul
uklassificerede. Ændrer tallene sig uventet, er det en regression — undersøg den frem
for at opdatere det forventede resultat.

Punktumsegmenteringen har to kontroller, som begge skal være rene:

```bash
python lovhistorik/probe.py sentences eli/lta/2025/1500
python lovhistorik/probe.py validate eli/lta/2025/1500
```

Forventet: 0 stykker med færre punktummer end de selv henviser til, og 20 af 20 korrekte
punkthenvisninger fra ændringslovene. To punkter fra LOV 749 fremstår som fejl under
"indsættes som N. pkt.", men er det ikke: deres virkning er allerede konsolideret ind i
LBK 1500.

Afspilningen måles med:

```bash
python lovhistorik/probe.py replay eli/lta/2023/42 eli/lta/2025/1500
```

Forventet: 55 af 104 operationer udført, og 30 af 43 berørte enheder rammer LBK 1500
ordret. Det andet tal er det, der tæller — det første kan hæves ved at udføre flere
operationer forkert. At de fleste enheder er identiske med facit siger intet, da de
aldrig er blevet rørt.

Enhver ændring skal køres på alle tre love, ellers bygger vi til ligningsloven alene:

```bash
python lovhistorik/probe.py replay eli/lta/2021/242 eli/lta/2025/1222
python lovhistorik/probe.py replay eli/lta/2024/15 eli/lta/2025/1059
```

Forventet: 9 af 12 berørte enheder rammer på afskrivningsloven, 1 af 1 på
skatteindberetningsloven. De to fandt fejl, ligningsloven ikke afslørede — blandt andet
at etiketten "§ 5 D." fulgte med ved genaffattelse, og at ikrafttrædelsesproblemet var
langt alvorligere, end ligningsloven lod ane.

Hold især øje med linjen "afviger, selv om alle operationer lykkedes". Den tæller de
tilfælde, hvor motoren tager fejl uden at sige det, og den er vigtigere end
dækningsgraden. Stiger den, mens antallet af udførte operationer stiger, er en ny
operation begyndt at ødelægge tekst.

Forarbejdskoblingen måles med:

```bash
python lovhistorik/probe.py motiver eli/lta/2025/1500 9C
python lovhistorik/probe.py motiver eli/lta/2025/1500 7P 8
python lovhistorik/probe.py motiver eli/lta/2025/1500 33A 14
python lovhistorik/probe.py motiver eli/lta/2025/1500 alle
python lovhistorik/probe.py motiver eli/lta/2024/15 alle
```

Forventet: 18 ændringer af § 9 C ved seks led, hvoraf 17 nævner bestemmelsen, og 23 ved
otte led, hvoraf 18 nævner den; 12 af 12 på § 7 P; 3 af 3 på § 33 A. Bredt: 96 af 104
punkter med bemærkning på ligningsloven (95,8 % bekræftet) og 38 af 40 på
skatteindberetningsloven. En bestemmelse kan sagtens være uændret gennem flere
lovbekendtgørelser, og "ikke ændret" må aldrig forveksles med "ingen forarbejder".

**Søgelogikken ligger i `forarbejder.py`, ikke i `probe.py`.** Både proben og
Streamlit-appen kalder `paragraph_history`, så de ikke kan nå frem til forskellige svar
på samme spørgsmål. Lægger man ny logik i proben, opstår netop den forskel. Efter en
ændring skal begge veje give samme tal — sammenlign `probe.py motiver` med appen.

**Et kald, der fejler, må aldrig ligne et kald, der intet fandt.** En ændringslov, der
ikke kan hentes, ligner ellers en lov, der ikke rørte paragraffen, og svaret bliver
tavst ufuldstændigt. `instructions_of` returnerer derfor `(punkter, problem)`, og
problemet skal med i `History.problems` og vises. Samme skel gælder mod Folketingets
data: `LookupFailed` betyder "opslaget lykkedes ikke", ikke "der er intet forarbejde".

**Alt hentet indhold skal kontrolleres, før det caches.** Cachen har ingen udløbstid, så
et ødelagt dokument bliver en permanent fejl. `is_complete_document` kontrollerer ved
både skrivning og læsning. Hæves `MAX_BYTES`, skal `fetch` blive ved med at læse én byte
mere end grænsen, så et for stort svar afvises frem for at blive skåret over.

Cachen kan efterses uden netværk:

```bash
python -c "import sys; sys.path.insert(0,'lovhistorik'); import lex_dania; print([p.name for p in lex_dania.CACHE_DIRECTORY.glob('*.xml') if not lex_dania.is_complete_document(p.read_bytes())])"
```

Dækning og lækage måles med:

```bash
python lovhistorik/probe.py daekning eli/lta/2025/1500 14
python lovhistorik/probe.py daekning eli/lta/2025/1222 14
python lovhistorik/probe.py daekning eli/lta/2025/1059 14
```

Forventet: 227 ændringslove og 768 punkter på ligningsloven, og **nul uforklarede** love i
lækagetesten på alle tre — bortset fra den ene, der rammer 2006, hvor XML'en slipper op.
Stiger tallet, taber kæden love, og det viser sig ikke andre steder. Advarslen "har ingen
laeselig liste over aendringer" skal kun optræde for det ældste led.

**Lovforslagets paragrafnumre er ikke lovens.** Ligningsloven er § 6 i LOV 84/2019, men
§ 5 i lovforslag L 114. Slår man bemærkningen op på lovens numre, får man en anden
bestemmelses bemærkning — et forkert svar, der ser rigtigt ud. Punktet skal genfindes i
lovforslaget på sin tekst. Kan det ikke, er det formentlig kommet til ved et
ændringsforslag, og så skal der ikke svares.

**Sammenlign aldrig lange tekster med `difflib` uden `autojunk=False`.** Over 200 tegn
behandles hyppige tegn som støj, og to næsten ens instrukser fik lighed 0,74 i stedet for
0,97.

Søgningen for én paragraf skal gå hele kæden igennem, ikke stoppe ved første ændring.
Ældre ændringer bærer ofte fortolkningen af den oprindelige regel.

**En indsat paragraf står ikke som mål for sin egen indsættelse.** Målet er den
foregående paragraf ("Efter § 33 indsættes: § 33 A"), så paragrafbetegnelser skal også
læses i den nye tekst. Ellers mangler netop den ændring, der indførte bestemmelsen.
Ligningslovens § 33 A blev ophævet i 2012 og genindført samme år med tilbagevirkende
kraft; kun målsøgning fandt ophævelsen, ikke genindførelsen. Historikken skal desuden
sorteres efter (år, lovnummer), for lovbekendtgørelsens egen liste er ikke kronologisk.

**Lovbekendtgørelsens liste udelader paragrafangivelsen, når hele ændringsloven er
indarbejdet** ("… , lov nr. 1379 af 28. december 2011, …"). Kræver mønsteret "§ N i",
forsvinder sådanne love lydløst. Paragraf `0` betyder hele loven.

Den sidste linje er den vigtige. Bemærkningen citerer selv den bestemmelse, den
forklarer, så nævner den ikke målet, er koblingen sandsynligvis forkert. Stiger det tal,
er noget gået galt i koblingen — undersøg det frem for at sænke kravet.

## Om TLS

Udviklingsmaskinen har TLS-inspektion, så Pythons medfølgende certifikatbundt afvises.
Derfor bruges `truststore`, der validerer mod styresystemets eget trust store. Det er
ikke nødvendigt på en server uden inspektion. `tls_check.py` er til at fejlfinde det.
