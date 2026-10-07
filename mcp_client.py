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
        text = response.read().decode("utf-8")
        content_type = response.headers.get("Content-Type", "")
    if content_type.startswith("text/event-stream"):
        return _last_sse_message(text)
    return json.loads(text)


def _last_sse_message(text: str) -> dict:
    """The JSON-RPC reply from a Streamable HTTP response sent as server-sent events.

    MCP clients must accept both JSON and an event stream, and the server picks. The reply is the
    last ``message`` event; each event's ``data:`` lines join with newlines into one JSON document.
    """
    reply = None
    data: list[str] = []
    for line in text.splitlines() + [""]:
        if line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
        elif line == "" and data:
            reply = json.loads("\n".join(data))
            data = []
    if reply is None:
        raise ValueError("The event stream carried no message.")
    return reply


def call_tool(name: str, arguments: dict) -> str:
    """Call MCP tool ``name`` and return its result as a JSON string."""
    had_key = bool(sign_in.current_key())
    not_connected = sign_in.connect()
    if not_connected:
        return not_connected
    # The approval hook ran before this call had a key, so it let the call through ungated. Stop
    # here and let the agent call again, so that call passes through the approval prompt.
    if not had_key:
        return json.dumps(
            {
                "connected": True,
                "next_step": "Laso is now connected. Call the tool again to run it.",
            }
        )

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
