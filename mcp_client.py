"""Forwards one tool call to the Laso MCP server with the human's Laso key."""

import json
import urllib.error
import urllib.request

from . import sign_in

MCP_URL = "https://laso.finance/mcp"
USER_AGENT = "Hermes (laso-finance plugin)"

# Paid tools settle on-chain before they answer, so allow well past a normal
# HTTP round trip.
TIMEOUT_SECONDS = 120


def _error(message: str) -> str:
    return json.dumps({"error": message})


def _post(api_key: str, body: dict) -> dict:
    request = urllib.request.Request(
        MCP_URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def call_tool(name: str, arguments: dict) -> str:
    """Call MCP tool ``name`` and return its result as a JSON string."""
    not_connected = sign_in.connect()
    if not_connected:
        return not_connected

    # The server is stateless, so a tools/call needs no initialize handshake.
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    try:
        reply = _post(sign_in.current_key(), body)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            # The key was revoked from the dashboard. Drop it and sign in again.
            sign_in.forget_key()
            return sign_in.connect() or _error("Laso rejected the saved key. Try again.")
        detail = exc.read().decode("utf-8", "replace")[:500]
        return _error(f"Laso returned HTTP {exc.code}: {detail}")
    except (urllib.error.URLError, TimeoutError) as exc:
        return _error(f"Could not reach Laso: {exc}")

    if "error" in reply:
        return _error(reply["error"].get("message", "Unknown error"))

    result = reply.get("result", {})
    text = "\n".join(
        part.get("text", "") for part in result.get("content", []) if part.get("type") == "text"
    )
    if result.get("isError"):
        return _error(text)
    try:
        json.loads(text)
    except ValueError:
        return json.dumps({"result": text})
    return text
