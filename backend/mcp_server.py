"""Standalone remote MCP service for JAILA.

Run this module in its own process. It intentionally imports neither
``backend.main`` nor the website's answer-generation workflow.
"""

from __future__ import annotations

import hmac
import os
from typing import Any

import anyio
from mcp.server import MCPServer
from openai import OpenAI
from starlette.responses import JSONResponse

from backend.services.legal_search import search_legal_sources


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} mangler")
    return value


OPENAI_API_KEY = _required_env("OPENAI_API_KEY")
MCP_API_TOKEN = _required_env("MCP_API_TOKEN")

mcp = MCPServer(
    name="jaila-legal-search",
    title="JAILA retskildesøgning",
    description="Retrieval-only søgning i JAILAs danske skatteretlige kilder.",
    instructions=(
        "Brug search_jaila til at finde relevante kildestykker. "
        "Foretag selv den juridiske analyse, og angiv de konkrete filnavne."
    ),
    version="1.0.0",
)


@mcp.tool(
    name="search_jaila",
    description=(
        "Søg semantisk i JAILAs danske skatteretlige retskilder. "
        "Returnerer rå kildestykker og metadata, ikke et modelgenereret svar."
    ),
    structured_output=True,
)
async def search_jaila(query: str, max_results: int = 8) -> dict[str, Any]:
    """Return source chunks so the MCP client can perform the legal analysis."""
    client = OpenAI(api_key=OPENAI_API_KEY)
    results = await anyio.to_thread.run_sync(
        lambda: search_legal_sources(
            client=client,
            query=query,
            max_results=max_results,
        )
    )
    return {
        "query": query.strip(),
        "result_count": len(results),
        "results": results,
    }


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health(_request):
    return JSONResponse({"status": "ok", "service": "jaila-mcp"})


class BearerTokenMiddleware:
    """Small ASGI boundary for a pre-shared MCP bearer token.

    This keeps credentials out of tool arguments. Replace it with OAuth 2.1
    before exposing the service to clients that cannot send a static bearer
    token.
    """

    def __init__(self, wrapped_app, token: str) -> None:
        self.wrapped_app = wrapped_app
        self.expected = f"Bearer {token}".encode("utf-8")

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope.get("path") != "/health":
            headers = dict(scope.get("headers", []))
            supplied = headers.get(b"authorization", b"")
            if not hmac.compare_digest(supplied, self.expected):
                response = JSONResponse(
                    {"error": "unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await self.wrapped_app(scope, receive, send)


_mcp_app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    host="127.0.0.1",
)
app = BearerTokenMiddleware(_mcp_app, MCP_API_TOKEN)
