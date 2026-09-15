# JAILA Backend API

FastAPI backend that exposes vector-store powered legal analysis for the `skat-chat` frontend.

## Endpoints

- `GET /api/health`
- `GET /api/skat/search/status`
- `POST /api/skat/search` (read-only SKAT-retrieval; requires `JAILA_SKAT_SEARCH_API`)
- `GET /api/skat/document/original` (scraped HTML; requires `JAILA_SKAT_SEARCH_API` and `JAILA_SKAT_RAW_HTML_DIR`)
- `POST /api/analyze`
- `GET /api/logs/{filename}`

## Required environment variables

- `OPENAI_API_KEY` (required)
- `FRONTEND_ORIGINS` (optional, comma-separated; default includes `https://skat-chat.dk`)
- `STRICT_SOURCING` (optional, `true/false`; default `false`)
- `JAILA_SKAT_DATABASE_URL` (required when PostgreSQL decision retrieval is enabled)
- `JAILA_SKAT_RETRIEVAL_ENABLED` (`true` enables read-only PostgreSQL decisions alongside vector stores)
- `JAILA_SKAT_SEARCH_API` (`true` enables POST /api/skat/search for the live search test page; does not enable chat retrieval)
- `JAILA_SKAT_RAW_HTML_DIR` (optional; folder with `{year}/raw_html/{SKM}__oid-{oid}.html`. Local default: `data/skat_info`. Production: `/var/lib/jaila/skat_info`)

Example:

```
OPENAI_API_KEY=sk-...
FRONTEND_ORIGINS=https://skat-chat.dk,http://localhost:3000
STRICT_SOURCING=true
```

## Local run

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
```

## Integration contract for frontend

### Request

`POST /api/analyze`

```json
{
  "question": "Kan grænsegængere benytte reglerne om lempelse efter ligningslovens § 33 A?"
}
```

### Response

```json
{
  "answer": "...",
  "used_model": "gpt-5.6-sol",
  "response_id": "resp_...",
  "citations": [{"file_id":"file_...","filename":"...pdf"}],
  "retrieval_results": [{"filename":"...pdf","score":"0.95","text":"..."}],
  "log_pdf_filename": "query_log_....pdf",
  "log_pdf_url": "/api/logs/query_log_....pdf"
}
```

## Server deployment (summary)

1. Ensure `/etc/jaila-backend.env` exists with required env vars.
2. Run `backend/deploy/DEPLOY_BACKEND.bat` from project root.
3. Add `backend/deploy/nginx-api-snippet.conf` to nginx site config and reload nginx.
4. Validate:
   - `https://skat-chat.dk/api/health`
