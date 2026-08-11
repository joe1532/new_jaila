# JAILA Remote MCP

MCP-servicen er bevidst adskilt fra hjemmesidens FastAPI-proces.

## Isolation

| Del | Hoved-backend | MCP |
|---|---|---|
| systemd-service | `jaila-backend` | `jaila-mcp` |
| lokal port | `8010` | `8020` |
| app-mappe | `/opt/jaila_backend` | `/opt/jaila_mcp` |
| Python-miljø | eget `.venv` | eget `.venv` |
| miljøfil | `/etc/jaila-backend.env` | `/etc/jaila-mcp.env` |
| offentlig route | `/api/` | `/mcp` |

MCP importerer ikke `backend.main` og genererer ikke svar. Tool'et
`search_jaila` kalder kun OpenAI Vector Store Search og returnerer kildestykker.
En fejl eller genstart i `jaila-mcp` genstarter derfor ikke `jaila-backend`.

OpenAI-konto, vector stores og eventuelle API-kvoter er stadig fælles. Brug en
separat OpenAI-projektnøgle med eget budget, hvis også denne afhængighed skal
isoleres.

## Lokal start

```powershell
pip install -r requirements-mcp.txt
$env:OPENAI_API_KEY = "sk-proj-..."
$env:MCP_API_TOKEN = "et-langt-tilfældigt-token"
python -m uvicorn backend.mcp_server:app --host 127.0.0.1 --port 8020
```

Endpoints:

- Health: `http://127.0.0.1:8020/health`
- MCP Streamable HTTP: `http://127.0.0.1:8020/mcp`

Alle MCP-kald kræver:

```text
Authorization: Bearer <MCP_API_TOKEN>
```

Den statiske bearer-tokenløsning er egnet til en afgrænset integration, hvor
klienten kan sende en fast header. Hvis ChatGPT-integrationen kræver OAuth 2.1,
skal tokenlaget erstattes med en rigtig OAuth-udsteder; MCP-tool og retrieval
kan beholdes uændret.

## Serveropsætning

1. Kopiér `backend/deploy/jaila-mcp.env.example` til
   `/etc/jaila-mcp.env`, udfyld værdierne, og sæt `root:root` samt mode `600`.
2. Kør `backend/deploy/DEPLOY_MCP.bat`.
3. Tilføj `backend/deploy/nginx-mcp-snippet.conf` til TLS-serverblokken.
4. Kør `sudo nginx -t` før `sudo systemctl reload nginx`.
5. Registrér `https://skat-chat.dk/mcp` i MCP-klienten.

MCP-deployment er ikke en del af `DEPLOY_ALL.bat`. Det er bevidst, så en
MCP-deployment ikke ændrer eller genstarter hjemmesidens backend.
