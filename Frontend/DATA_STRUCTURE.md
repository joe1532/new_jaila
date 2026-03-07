# Frontend datastruktur (JAILA)

Dette dokument beskriver, hvordan frontend-data skal struktureres for fanerne:

- Analyse
- Sagsbehandling
- Chat

Målet er en enkel, stabil struktur uden spredte globale variabler.

---

## Princip

Brug én central `state` som eneste sandhedskilde for UI-data.

Det betyder:

- Ingen tilfældige `let` variabler i toppen af filer til forretningsdata
- Alle data læses og opdateres via `state`
- UI renderes ud fra `state`

---

## Foreslået state-model

```js
const state = {
  auth: {
    user: null,              // "jonas" | "allan" | null
    isLoggedIn: false
  },

  ui: {
    activeTab: "analyse",    // "analyse" | "sagsbehandling" | "chat"
    loading: false,
    error: null,             // string | null
    statusMessage: "Klar"
  },

  analyse: {
    question: "",
    answer: "",
    usedModel: null,         // "gpt-5.4" | "gpt-5.2" | null
    citations: [],           // [{ file_id, filename }]
    retrievalResults: [],    // [{ filename, score, text }]
    logPdfUrl: null,         // "/api/logs/....pdf"
    lastRunAt: null          // ISO timestamp eller null
  },

  sagsbehandling: {
    selectedCaseId: null,
    cases: [],               // [{ id, title, status, assignedTo, updatedAt }]
    filters: {
      status: "all",
      assignedTo: "all",
      search: ""
    },
    form: {
      title: "",
      note: ""
    }
  },

  chat: {
    threadId: null,
    inputText: "",
    messages: [              // append-only liste
      // { id, role: "user" | "assistant" | "system", text, createdAt }
    ],
    lastResponseAt: null
  }
};
```

---

## Filstruktur (anbefalet)

```text
Frontend/
  js/
    app.js
    state/
      store.js
      session.js
    tabs/
      analyseTab.js
      sagsbehandlingTab.js
      chatTab.js
    api/
      client.js
      analyzeApi.js
      caseApi.js
      chatApi.js
```

### Ansvar pr. modul

- `state/store.js`
  - indeholder `state`
  - eksporterer `getState()`, `setState(patch)`, `resetState()`
- `state/session.js`
  - login/logout persistence (fx localStorage)
- `tabs/*.js`
  - tab-specifik render + events
- `api/*.js`
  - alle HTTP-kald samlet ét sted

---

## Opdateringsregler

1. Alle ændringer går gennem en update-funktion.
2. Undgå direkte mutation dybt i koden.
3. Efter state-opdatering kaldes render for relevant område.

Eksempel:

```js
function setState(patch) {
  state = {
    ...state,
    ...patch
  };
}
```

Ved nested felter:

```js
setState({
  ui: {
    ...state.ui,
    loading: true,
    error: null
  }
});
```

---

## Dataflow for Analyse-fanen

1. Bruger skriver spørgsmål (`state.analyse.question`)
2. Klik på "Kør analyse"
3. Sæt:
   - `ui.loading = true`
   - `ui.error = null`
4. Kald `POST /api/analyze`
5. Ved succes opdater:
   - `analyse.answer`
   - `analyse.usedModel`
   - `analyse.citations`
   - `analyse.retrievalResults`
   - `analyse.logPdfUrl`
   - `analyse.lastRunAt`
6. Sæt `ui.loading = false`
7. Render Analyse-sektionen

Ved fejl:

- `ui.loading = false`
- `ui.error = <fejltekst>`
- bevar sidste gyldige svar i `analyse.*`

---

## Dataflow for faneskift

Ved klik på faneknap:

- opdater `ui.activeTab`
- render kun aktiv fane
- bevar data i øvrige faner (ingen reset ved faneskift)

---

## Persistens (hvad gemmes lokalt)

Gem kun nødvendigt i browser:

- `auth.user`
- `auth.isLoggedIn`
- evt. `ui.activeTab`

Undgå at gemme:

- API-responser med personfølsomme data
- komplette retrieval-resultater

---

## API-kontrakter (frontend forventning)

### `POST /api/analyze`

Request:

```json
{
  "question": "..."
}
```

Response:

```json
{
  "answer": "...",
  "used_model": "gpt-5.4",
  "citations": [{ "file_id": "file_x", "filename": "x.pdf" }],
  "retrieval_results": [{ "filename": "x.pdf", "score": "0.95", "text": "..." }],
  "log_pdf_filename": "query_log_....pdf",
  "log_pdf_url": "/api/logs/query_log_....pdf"
}
```

Mapping til state:

- `used_model` -> `state.analyse.usedModel`
- `retrieval_results` -> `state.analyse.retrievalResults`
- `log_pdf_url` -> `state.analyse.logPdfUrl`

---

## Naming conventions

- Brug camelCase i JS (`activeTab`, `logPdfUrl`)
- Brug engelske nøgler i dataobjekter for teknisk konsistens
- Brug danske labels i UI-tekst

---

## Minimum acceptance criteria

- Der findes kun én central `state`
- Analyse, Sagsbehandling og Chat læser/skriver via `state`
- Ingen direkte API-kald i UI-komponenter uden for `api/` moduler
- Fejl og loading håndteres via `state.ui`
- Faneskift nulstiller ikke data i andre faner

---

## Kendte tradeoffs

- Uden framework bliver manuel render-styring mere kode ved større UI
- Ved kompleksitet kan man senere flytte samme state-model til React/Vue
- Lokal login i frontend er ikke stærk sikkerhed; backend-auth bør indføres senere

