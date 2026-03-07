# JAILA Clean Start Frontend

Denne mappe er frontend til JAILA.

Maalet er at holde frontend simpel, mens backend-haandtering af OpenAI/vector stores sker server-side.

## Status lige nu

- Frontend sender forespoergsler til backend endpoint: `/api/analyze`.
- Backend returnerer svar, citations, retrieval-resultater og PDF-log link.
- Frontend viser svar, citations og link til log.

## Hvor den koerer

- Primaar forside peger paa clean-start:
  - `https://skat-chat.dk/`
- Clean-start direkte:
  - `https://skat-chat.dk/clean-start/index.html`

## Mappestruktur

- `index.html`
  - Minimal HTML-side.
  - Loader CSS og JS fra `/clean-start/...` absolute paths.
- `css/styles.css`
  - Enkel styling til kort/layout/status.
- `js/app.js`
  - Kalder backend API (`POST /api/analyze`) med brugerens spoergsmaal.
  - Renderer svar, citations og PDF-log link i UI.
- `DEPLOY_CLEAN_START.bat`
  - Deploy-script til produktion.
- `REQUIREMENTS.md`
  - Miljoe- og driftskrav.
- `README.md`
  - Denne fil.

## Arkitekturprincipper

1. Keep it simple:
   - Ingen frameworks, ingen bundler.
   - Kun statiske filer (HTML/CSS/JS).
2. Ingen skjult magi:
   - Alt er eksplicit i de tre filer.
3. Sikkerhed:
   - Ingen API-noegler i frontend.
   - OpenAI-integrering sker via backend API.

## Lokal udvikling

Du kan redigere filer direkte i:

- `JAILA FRONTEND/clean-start/index.html`
- `JAILA FRONTEND/clean-start/css/styles.css`
- `JAILA FRONTEND/clean-start/js/app.js`

Der er ingen build-step.

## Deploy (produktion)

### Hurtig metode

Koer:

`JAILA FRONTEND/clean-start/DEPLOY_CLEAN_START.bat`

Scriptet:

1. uploader filer via `scp`
2. kopierer til `/var/www/site/clean-start`
3. kan opdatere root-forsiden (afhaengigt af serverkommando)
4. reloader `nginx`

### Manuel metode (hvis noedvendigt)

Eksempel:

```bash
scp -i C:/Users/micro/.ssh/id_ed25519 index.html maestro@168.119.63.168:~/clean-start-index.html
scp -i C:/Users/micro/.ssh/id_ed25519 css/styles.css maestro@168.119.63.168:~/clean-start-styles.css
scp -i C:/Users/micro/.ssh/id_ed25519 js/app.js maestro@168.119.63.168:~/clean-start-app.js

ssh -i C:/Users/micro/.ssh/id_ed25519 maestro@168.119.63.168
echo '<SUDO_PASSWORD>' | sudo -S mkdir -p /var/www/site/clean-start/css /var/www/site/clean-start/js
echo '<SUDO_PASSWORD>' | sudo -S cp ~/clean-start-index.html /var/www/site/clean-start/index.html
echo '<SUDO_PASSWORD>' | sudo -S cp ~/clean-start-styles.css /var/www/site/clean-start/css/styles.css
echo '<SUDO_PASSWORD>' | sudo -S cp ~/clean-start-app.js /var/www/site/clean-start/js/app.js
echo '<SUDO_PASSWORD>' | sudo -S systemctl reload nginx
```

## Hvordan man bygger videre (foreslaaet retning)

1. Behold frontend tynd:
   - UI-input, rendering, state.
2. Udbyg backend endpoint-kontrakt:
   - Tilfoej evt. filters, dokumentvalg eller sessions-id.
3. Tilfoej features trinvis:
   - En ny funktion ad gangen.
   - Smalle, testbare ændringer.
4. Logik:
   - Valider input.
   - Haandter fejl eksplicit.
   - Vis tydelig status i UI.

## Kendte begraensninger

- Ingen auth-flow endnu.
- Ingen data persistence i browser.
- Enkelt endpoint-flow uden multi-turn sessions.

## Handover-checkliste til ny udvikler

- [ ] Læs `REQUIREMENTS.md`
- [ ] Bekraeft at `https://skat-chat.dk/` viser clean-start
- [ ] Bekraeft at `js/app.js` kalder korrekt API-base (`/api`)
- [ ] Aftal API-kontrakt for eventuelle nye felter
- [ ] Byg foerste feature i separat, lille PR
