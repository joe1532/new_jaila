# Opslagsværk (lag A)

Strukturerede paragrafnoder fra Retsinfo-høsten. Ligger her og ikke i `data/`,
fordi den mappe er gitignored og derfor ikke kommer med i deploy.

Kun ligningsloven i første snit. Tre LBKG'er: 1735 (2021), 42 (2023), 1500
(2025). Opslaget bruger altid 1500. De to ældre er til stabilitetstest.

`aendringer-2021-2025.json` er de to hop 1735→42 og 42→1500 fra høstens
`rapport.jsonl`. `oldText`/`newText` er ikke med; bindestreg er forudberegnet
som `cosmetic`.

Genimport når høsten opdateres:

```
python -m backend.tools.import_opslagsvaerk
```
