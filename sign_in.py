"""Connects the plugin to the human's Laso account with the OAuth device flow (RFC 8628).

There is no key to paste. The first Laso call starts a sign-in and returns a link and a short code
for the agent to hand its human. The human approves on any device, and the next Laso call polls once,
receives the key, saves it as LASO_API_KEY in ~/.hermes/.env, and goes ahead. Nothing waits in the
background and nothing blocks: every call returns at once, so cron and gateway runs never hang.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from agent.secret_scope import get_secret

ISSUER = "https://laso.finance"
# A client ID metadata document Laso hosts, so the approval page names this client.
CLIENT_ID = f"{ISSUER}/oauth/clients/hermes.json"
KEY_NAME = "LASO_API_KEY"
USER_AGENT = "Hermes (laso-finance plugin)"
TIMEOUT_SECONDS = 15
DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
PENDING_STATE_KEY = "pending_sign_in"

# Set by register(). The pending sign-in waits between calls in the plugin's own ctx.state, read on
# first use rather than at registration.
_ctx = None
# The key this process just received, used until the .env write is visible to get_secret.
_fresh_key = None


def bind(ctx) -> None:
    global _ctx
    _ctx = ctx


def current_key() -> str:
    return _fresh_key or (get_secret(KEY_NAME, "") or "").strip()


def forget_key() -> None:
    """Drop a key Laso rejected, so the next call signs in again."""
    global _fresh_key
    _fresh_key = None
    from hermes_cli.config import remove_env_value

    remove_env_value(KEY_NAME)


def _post_form(path: str, fields: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"{ISSUER}{path}",
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except ValueError:
            return exc.code, {}


def _save_key(key: str) -> None:
    global _fresh_key
    _fresh_key = key
    from hermes_cli.config import save_env_value

    save_env_value(KEY_NAME, key)


def _not_connected(pending: dict, note: str) -> str:
    return json.dumps(
        {
            "error": "laso_not_connected",
            "message_for_human": (
                f"{note} Open {pending['verification_uri_complete']} and approve. "
                f"Check that the page shows the code {pending['user_code']}."
            ),
            "verification_uri_complete": pending["verification_uri_complete"],
            "user_code": pending["user_code"],
            "expires_at": pending["expires_at"],
            "next_step": "Give message_for_human to your human verbatim. After they approve, call this tool again.",
        }
    )


def _start() -> str:
    status, body = _post_form("/oauth/device_authorization", {"client_id": CLIENT_ID})
    if status != 200 or "device_code" not in body:
        detail = body.get("error_description") or f"HTTP {status}"
        return json.dumps({"error": f"Could not start the Laso sign-in: {detail}"})
    pending = {
        "device_code": body["device_code"],
        "user_code": body["user_code"],
        "verification_uri_complete": body["verification_uri_complete"],
        "interval": int(body.get("interval", 5)),
        "expires_at": int(time.time()) + int(body["expires_in"]),
        # RFC 8628 §3.5: wait one interval before the first poll too.
        "last_polled_at": int(time.time()),
    }
    _ctx.state.set(PENDING_STATE_KEY, pending)
    return _not_connected(pending, "To connect Laso Finance,")


def connect() -> str | None:
    """Return None once a key is available, or a JSON tool result that tells the agent what to do."""
    if current_key():
        return None
    pending = _ctx.state.get(PENDING_STATE_KEY, default=None)
    now = int(time.time())
    if not pending or pending["expires_at"] <= now:
        return _start()
    # Stay under the server's polling interval: a call that comes too soon repeats the link.
    if now - pending["last_polled_at"] < pending["interval"]:
        return _not_connected(pending, "Still waiting for approval.")

    status, body = _post_form(
        "/oauth/token",
        {"grant_type": DEVICE_GRANT_TYPE, "device_code": pending["device_code"], "client_id": CLIENT_ID},
    )
    if status == 200 and body.get("access_token"):
        _ctx.state.set(PENDING_STATE_KEY, None)
        _save_key(body["access_token"])
        return None

    error = body.get("error")
    if error in ("authorization_pending", "slow_down"):
        pending["last_polled_at"] = now
        if error == "slow_down":
            pending["interval"] += 5
        _ctx.state.set(PENDING_STATE_KEY, pending)
        return _not_connected(pending, "Still waiting for approval.")
    _ctx.state.set(PENDING_STATE_KEY, None)
    if error == "access_denied":
        return json.dumps(
            {
                "error": "laso_connection_declined",
                "message_for_human": "The Laso connection was declined. Ask me again if you want to connect.",
            }
        )
    # Expired or unknown: start over with a fresh code.
    return _start()
