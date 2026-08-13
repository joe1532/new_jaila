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
- **Indledningen står ikke nødvendigvis i én tekstblok.** Færdselslovens bekendtgørelser
  bryder opremsningen vilkårligt — midt i en dato, midt i "lov nr." — og læses blokkene
  hver for sig, standser listen ved det falske punktum, og hele perioden forsvinder
  lydløst. `_join_continuations` samler dem. Grænsen for sammenkædningen er ikke til
  forhandling: lige efter listen står de ændringer, der udtrykkeligt *ikke* er
  indarbejdet, og de må aldrig med. Hverken det afsluttende punktum eller "§ N i" kan
  antages at være der.
- **En måling på ét ressortområde måler ressortet, ikke motoren.** De tre første testlove
  var alle skattelove, og de viste 0 lækager. Den første lov uden for området viste 9.
  Nye målinger skal derfor tages på tværs af ressort, ikke på flere love af samme slags.
- **Betænkninger kan ikke hentes, og der skal ikke bygges omgåelser.** De udgives kun som
  PDF på www.ft.dk, som er beskyttet af Cloudflare og svarer 403 på alt programmatisk —
  også HTML-sider. Beskyttelsen er tilsigtet. Kom et ændringspunkt ved ændringsforslag,
  oplyses betænkningens titel og link, så brugeren kan læse den selv.
- **En formodning skal slås op, ikke gentages.** Svaret sagde "kom formentlig ved
  ændringsforslag" uden at se efter. Findes der intet ændringsforslag på sagen, er
  forklaringen forkert, og svaret skal sige, at årsagen er ukendt. Et gæt, der rammer syv
  ud af otte gange, er værre end et opslag, for den ottende kan ikke skelnes fra de andre.
- **"Ubekræftet" og "mistænkelig" er ikke det samme.** En ophævelse eller en ren
  henvisningsændring indsætter ingen ordlyd, som bemærkningen kunne gengive, så et
  manglende overlap siger intet om koblingen. Kun når ændringen indsætter rigtig tekst,
  er et manglende overlap en grund til at se efter. Blandes de to, drukner de ægte fejl
  i forventelige tilfælde — det var netop derfor, målet før pegede på 8 og nu på 1.
- **Tærskler vælges på en måling, ikke på fornemmelse.** Grænsen på 8 fælles ord bygger
  på, at ingen af 49 sikkert koblede bemærkninger deler under 5 ord med deres ændring.
  Ændres tærsklen, skal målingen tages om. En falsk bekræftelse er værre end en falsk
  alarm: den får en forkert kobling til at se efterprøvet ud.

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

Forventet: 23 ændringer af § 9 C ved otte led, hvoraf 19 nævner bestemmelsen; 12 af 12 på
§ 7 P; 3 af 3 på § 33 A. Bredt: 97 af 104 punkter med bemærkning på ligningsloven
(95,9 % bekræftet) og 40 af 40 på skatteindberetningsloven. En bestemmelse kan sagtens
være uændret gennem flere lovbekendtgørelser, og "ikke ændret" må aldrig forveksles med
"ingen forarbejder".

**Mål også på ældre materiale.** Skrivemåden har ændret sig, og en måling, der kun rammer
de seneste år, viser grønt, selv om ældre lovforslag læses forkert. Et opslag i en gammel
udgave af loven afslører det:

```bash
python lovhistorik/probe.py motiver eli/lta/2015/1081 9C 7
```

Forventet: 13 ændringer, hvoraf 8 nævner § 9 C. Falder tallet, er et overskriftsmønster
blevet for snævert igen.

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

Forventet: 228 ændringslove og 771 punkter på ligningsloven, og **nul uforklarede** love i
lækagetesten på alle tre. Stiger tallet, taber kæden love, og det viser sig ikke andre
steder. Advarslen "har ingen laeselig liste over aendringer" skal kun optræde for det
ældste led, hvor XML'en slipper op.

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

**Et tomt svar skal kunne skelnes fra et fejlslagent opslag.** "Paragraffen er ikke
ændret" og "paragraffen findes ikke" er modsatte svar for en jurist, og de så ens ud.
Kontrollér, at bestemmelsen står i den valgte bekendtgørelse, og sig det, når den ikke gør.
Sammenlign uden hensyn til versaler: `localId` er `9C` i ligningsloven og `8a` i
personskatteloven.

**Et forkert årstal er farligst, når det ser rigtigt ud.** "af 26. december 2012" om en lov
fra 2013 består enhver rimelighedsprøve og henter forarbejder til en anden lov. Efterprøv
derfor alle årstal mod listen, ikke kun de umulige. Men ret kun, når rettelsen er bevist:
lovnumre genbruges hvert år, så der kræves både præcis én kandidat i listen og et 404 på
den angivne sti. Et fravær fra listen beviser intet — listen kan være ufuldstændig.

**Uden genforsøg afhænger svaret af netværket.** Samme opslag gav 48 og 49 bemærkninger,
fordi én hentning faldt. Genforsøg det, der kan gå over (5xx, netværksfejl), og kun det:
et 404 bliver ikke et andet svar, og et manglende led er normalt i en kæde, så ventetid dér
koster på hvert opslag.

**Indledningen kan være afbrudt, ikke bare ombrudt.** Kursgevinstlovens LBK 140/2008 skyder
to blokke ind midt i sætningen og tager den op igen med ", jf. lovbekendtgørelse …". Når du
leder efter fortsættelsen, så husk, at de indskudte blokke handler om ændringer, der
*ikke* er indarbejdet. En løs søgning føjer dem til listen, og det er værre end at mangle
dem. Sætningen varierer også i tal og indskud: "med den ændring", "med de ændringer og
tilføjelser".

**Mål på ressortet, ikke på tre love.** Find lovene ved at spørge en samlelov, hvad den
ændrer (`probe.py laws eli/lta/2023/679`), frem for at skrive listen selv. Målingen på 19
skattelove afslørede 25 lækager, som tre love aldrig ville have vist.

**Hardkod aldrig, hvad der er lovens nyeste udgave.** To poster i applisten var overhalet
af nye lovbekendtgørelser, uden at det kunne ses. Gem et holdepunkt, og følg
`eli:consolidated_by` fremad. Følg kun bekendtgørelser af *samme* lov: på en ændringslov
peger relationen på enhver bekendtgørelse, der har indarbejdet den, og fører ellers ud i en
tilfældig anden lov.

**Kortnavne er ikke en pålidelig nøgle.** Ejendomsavancebeskatningsloven hedder i metadata
"lov om beskatning af fortjeneste ved afståelse af fast ejendom", og kortformen findes
ikke. Søg på titlen, eller find loven gennem `eli:changes` på en lov, der ændrer den.

**En tom liste over ændringer er ikke altid en fejl.** En bekendtgørelse kan være udsendt
alene for at rette den forrige; så slutter indledningen ved henvisningen, og der *er*
ingen nye ændringer. Rapportér det som en oplysning, ikke som en advarsel. Falske alarmer
er ikke harmløse — de lærer læseren at se bort fra advarsler, og så overses den ægte.

## Om TLS

Udviklingsmaskinen har TLS-inspektion, så Pythons medfølgende certifikatbundt afvises.
Derfor bruges `truststore`, der validerer mod styresystemets eget trust store. Det er
ikke nødvendigt på en server uden inspektion. `tls_check.py` er til at fejlfinde det.
