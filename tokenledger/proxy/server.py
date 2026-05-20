"""tokenledger proxy server.

Intercepts all Anthropic API traffic routed via ANTHROPIC_BASE_URL,
records each call to SQLite with cost attribution to the current work
context (git branch or manual label), then passes the request through
unchanged.

Start with: tokenledger serve [--host 127.0.0.1] [--port 8080]
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from tokenledger.config.cost_estimator import estimate_cost
from tokenledger.context.tracker import ensure_context
from tokenledger.proxy.observer import (
    RequestContext,
    build_request_context,
    extract_tokens_from_events,
    parse_sse_chunk,
)
from tokenledger.storage.db import default_db_path, init_db, record_call

ANTHROPIC_API_BASE = "https://api.anthropic.com"

_http_client: httpx.AsyncClient | None = None
_db_path: str | None = None
_workspace_cwd: str = os.getcwd()       # captured at import time, used for git detection
_manual_override: str | None = None     # set via /control/context, None = use git

_STRIP_REQUEST_HEADERS = frozenset(
    ["host", "content-length", "transfer-encoding", "connection"]
)
_STRIP_RESPONSE_HEADERS = frozenset(
    ["content-encoding", "transfer-encoding", "connection"]
)

# File written on startup so the CLI can find the running proxy
def _proxy_info_path() -> Path:
    return Path(default_db_path()).parent / "proxy.json"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _http_client, _db_path
    _db_path = init_db()
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(None),
        headers={"accept-encoding": "identity"},
    )
    try:
        yield
    finally:
        if _http_client is not None:
            await _http_client.aclose()
        _proxy_info_path().unlink(missing_ok=True)


app = FastAPI(title="tokenledger proxy", docs_url=None, redoc_url=None, lifespan=_lifespan)


# ---------------------------------------------------------------------------
# Control routes  (context switching without proxy restart)
# ---------------------------------------------------------------------------

@app.post("/control/context")
async def control_set_context(request: Request) -> JSONResponse:
    global _manual_override
    body = await request.json()
    label = body.get("label", "").strip()
    if not label:
        return JSONResponse({"error": "label required"}, status_code=400)
    _manual_override = label
    # Open in DB immediately so the change is visible before the next API call
    ensure_context(manual_label=_manual_override, cwd=_workspace_cwd, db_path=_db_path)
    return JSONResponse({"context": label, "source": "manual"})


@app.delete("/control/context")
async def control_clear_context() -> JSONResponse:
    global _manual_override
    _manual_override = None
    # Let next API call re-detect from git
    return JSONResponse({"context": None, "source": "git"})


@app.get("/control/context")
async def control_get_context() -> JSONResponse:
    from tokenledger.storage.db import get_open_context
    ctx = get_open_context(_db_path)
    return JSONResponse({
        "override": _manual_override,
        "active": dict(ctx) if ctx else None,
        "workspace_cwd": _workspace_cwd,
    })


# ---------------------------------------------------------------------------
# Proxy routes
# ---------------------------------------------------------------------------

@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy(request: Request, path: str) -> Response:
    if path == "v1/messages":
        return await _handle_messages(request)
    return await _passthrough(request, path)


# ---------------------------------------------------------------------------
# /v1/messages interception
# ---------------------------------------------------------------------------

async def _handle_messages(request: Request) -> Response:
    body_bytes = await request.body()
    try:
        body: dict[str, Any] = json.loads(body_bytes)
    except (json.JSONDecodeError, ValueError):
        return await _passthrough(request, "v1/messages")

    ctx = build_request_context(body)
    headers = _forward_headers(request.headers)

    if body.get("stream", False):
        return StreamingResponse(
            _stream_messages(ctx, headers, body_bytes),
            media_type="text/event-stream",
        )
    return await _non_stream_messages(ctx, headers, body_bytes, request)


async def _stream_messages(
    ctx: RequestContext,
    headers: dict[str, str],
    body_bytes: bytes,
) -> AsyncGenerator[bytes, None]:
    input_tokens = 0
    output_tokens = 0
    upstream_error = False
    buffer = b""
    request_id: str | None = None

    try:
        async with _http_client.stream(
            "POST",
            f"{ANTHROPIC_API_BASE}/v1/messages",
            headers=headers,
            content=body_bytes,
        ) as upstream:
            request_id = upstream.headers.get("request-id")
            if upstream.status_code != 200:
                content = await upstream.aread()
                yield content
                upstream_error = True
                return

            async for chunk in upstream.aiter_bytes():
                yield chunk
                buffer += chunk
                *complete_frames, buffer = buffer.split(b"\n\n")
                for frame in complete_frames:
                    events = parse_sse_chunk(frame + b"\n\n")
                    input_tokens, output_tokens = extract_tokens_from_events(
                        events, input_tokens, output_tokens
                    )

        if buffer.strip():
            events = parse_sse_chunk(buffer)
            input_tokens, output_tokens = extract_tokens_from_events(
                events, input_tokens, output_tokens
            )

    except httpx.RequestError:
        upstream_error = True

    if not upstream_error:
        ctx.request_id = request_id
        _persist_call(ctx, input_tokens, output_tokens if output_tokens > 0 else None)


async def _non_stream_messages(
    ctx: RequestContext,
    headers: dict[str, str],
    body_bytes: bytes,
    request: Request,
) -> Response:
    try:
        upstream = await _http_client.post(
            f"{ANTHROPIC_API_BASE}/v1/messages",
            headers=headers,
            content=body_bytes,
        )
    except httpx.RequestError as exc:
        return Response(content=str(exc).encode(), status_code=502)

    if upstream.status_code == 200:
        try:
            resp_body = upstream.json()
            usage = resp_body.get("usage", {})
            ctx.request_id = upstream.headers.get("request-id")
            _persist_call(
                ctx,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens"),
            )
        except Exception:
            pass

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_safe_response_headers(upstream.headers),
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _persist_call(
    ctx: RequestContext,
    input_tokens: int,
    output_tokens: int | None,
) -> None:
    try:
        context_id = ensure_context(
            manual_label=_manual_override,
            cwd=_workspace_cwd,
            db_path=_db_path,
        )
        cost = estimate_cost(
            model=ctx.model,
            input_tokens=input_tokens,
            max_tokens=ctx.max_tokens,
        )
        output_cost: float | None = None
        if output_tokens is not None:
            output_cost = estimate_cost(
                model=ctx.model,
                input_tokens=0,
                max_tokens=output_tokens,
            ).output_cost_worst
        total = cost.input_cost + (output_cost or cost.output_cost_worst)

        record_call(
            context_id=context_id,
            model=ctx.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost=cost.input_cost,
            output_cost=output_cost,
            total_cost=total,
            request_id=ctx.request_id,
            db_path=_db_path,
        )
        _print_status(ctx, input_tokens, output_tokens, total, context_id)
    except Exception as exc:
        print(f"[tokenledger] record error: {exc}", file=sys.stderr)


def _print_status(
    ctx: RequestContext,
    input_tokens: int,
    output_tokens: int | None,
    total_cost: float,
    context_id: int,
) -> None:
    out = f"{output_tokens:,}" if output_tokens is not None else "?"
    print(
        f"[tokenledger] ctx={context_id}"
        f"  {ctx.model}"
        f"  in={input_tokens:,} out={out}"
        f"  ${total_cost:.4f}",
        file=sys.stderr,
        flush=True,
    )


# ---------------------------------------------------------------------------
# Passthrough + header utilities
# ---------------------------------------------------------------------------

async def _passthrough(request: Request, path: str) -> Response:
    url = f"{ANTHROPIC_API_BASE}/{path}"
    try:
        upstream = await _http_client.request(
            method=request.method,
            url=url,
            headers=_forward_headers(request.headers),
            content=await request.body(),
            params=dict(request.query_params),
        )
    except httpx.RequestError as exc:
        return Response(content=str(exc).encode(), status_code=502)
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_safe_response_headers(upstream.headers),
    )


def _forward_headers(headers: Any) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _STRIP_REQUEST_HEADERS}


def _safe_response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in _STRIP_RESPONSE_HEADERS}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    import uvicorn
    # Write proxy info so CLI can find us for live context switching
    info_path = _proxy_info_path()
    info_path.parent.mkdir(parents=True, exist_ok=True)
    info_path.write_text(json.dumps({"host": host, "port": port, "pid": os.getpid()}))
    print(f"tokenledger proxy listening on http://{host}:{port}", file=sys.stderr)
    print(f"export ANTHROPIC_BASE_URL=http://{host}:{port}", file=sys.stderr, flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")
