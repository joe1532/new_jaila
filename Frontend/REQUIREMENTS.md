# Clean-Start Requirements / Dependencies

## Formaal
Denne mappe indeholder frontend for JAILA uden legacy UI.

## Runtime dependencies (frontend)
- Moderne browser (Chrome, Edge, Firefox, Safari).
- JavaScript aktiveret.
- Ingen npm/pip packages paakraevet til selve frontend-filerne.

## Backend dependencies
- Frontend forventer en backend API paa samme host under `/api`.
- Paakraevet endpoint: `POST /api/analyze`.
- Backend skal haandtere OpenAI Vector Store, modelkald og logging server-side,
  saa API-noegler ikke eksponeres i browseren.

## Server / drift dependencies
- Nginx (eller tilsvarende webserver), der serverer fra `/var/www/site`.
- SSH adgang til server (`maestro@168.119.63.168`).
- Sudo-rettighed for deploy-brugeren til:
  - `mkdir -p /var/www/site/clean-start/...`
  - `cp ... /var/www/site/clean-start/...`
  - `systemctl reload nginx`

## Lokal deploy tooling (Windows)
- `scp` og `ssh` tilgaengeligt i terminal (OpenSSH client).
- Gyldig SSH private key:
  - `C:\Users\micro\.ssh\id_ed25519`

## Filer der skal deployes
- `clean-start/index.html`
- `clean-start/css/styles.css`
- `clean-start/js/**` (hele JS-mappen inkl. undermapper)
- `clean-start/REQUIREMENTS.md`
- `clean-start/VERIFY_CLEAN_START.bat`

## Deploy script i mappen
- `clean-start/DEPLOY_CLEAN_START.bat`
- Scriptet:
  1. uploader filer til staging i home-folder paa server
  2. kopierer dem til `/var/www/site/clean-start`
  3. reloader nginx
- `clean-start/VERIFY_CLEAN_START.bat`
  - tjekker live URL'er og simple markoerer i index/css/js

## Verifikation efter deploy
- Side loader: `https://skat-chat.dk/clean-start/index.html`
- Statisk assets loader:
  - `https://skat-chat.dk/clean-start/css/styles.css`
  - `https://skat-chat.dk/clean-start/js/app.js`
- Backend health (via nginx proxy): `https://skat-chat.dk/api/health`
- Anbefalet: koer `VERIFY_CLEAN_START.bat`
