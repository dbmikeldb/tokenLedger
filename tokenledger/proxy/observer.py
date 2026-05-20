"""Parse Anthropic request/response data into structured records.

Pure functions only: no I/O, no async, no FastAPI imports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class RequestContext:
    model: str
    max_tokens: int
    messages: list[dict[str, Any]]
    system: str | None
    tool_tokens_hint: int       # rough estimate from tools list length
    request_id: str | None = None


def build_request_context(body: dict[str, Any]) -> RequestContext:
    messages = body.get("messages", [])
    raw_system = body.get("system")
    system: str | None = None
    if isinstance(raw_system, str):
        system = raw_system or None
    elif isinstance(raw_system, list):
        parts = [b.get("text","") for b in raw_system if isinstance(b, dict) and b.get("type")=="text"]
        system = " ".join(parts).strip() or None

    tools = body.get("tools", [])
    # Rough estimate: each tool definition is ~200 tokens
    tool_tokens_hint = len(tools) * 200

    return RequestContext(
        model=body.get("model", "unknown"),
        max_tokens=int(body.get("max_tokens", 1024)),
        messages=messages,
        system=system,
        tool_tokens_hint=tool_tokens_hint,
    )


def parse_sse_chunk(raw: bytes) -> list[dict[str, Any]]:
    """Parse a raw SSE chunk into a list of event dicts. Never raises."""
    events: list[dict[str, Any]] = []
    text = raw.decode("utf-8", errors="replace")
    for frame in text.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        data_lines = [
            line[len("data:"):].strip()
            for line in frame.split("\n")
            if line.startswith("data:")
        ]
        if not data_lines:
            continue
        raw_data = " ".join(data_lines)
        if raw_data == "[DONE]":
            continue
        try:
            parsed = json.loads(raw_data)
            if isinstance(parsed, dict):
                events.append(parsed)
        except (json.JSONDecodeError, ValueError):
            pass
    return events


def extract_tokens_from_events(
    events: list[dict[str, Any]],
    current_input: int,
    current_output: int,
) -> tuple[int, int]:
    """Update running token tallies from parsed SSE events."""
    input_tokens = current_input
    output_tokens = current_output
    for event in events:
        event_type = event.get("type")
        if event_type == "message_start":
            try:
                input_tokens = event["message"]["usage"]["input_tokens"]
            except (KeyError, TypeError):
                pass
        elif event_type == "message_delta":
            try:
                output_tokens = event["usage"]["output_tokens"]
            except (KeyError, TypeError):
                pass
    return input_tokens, output_tokens
