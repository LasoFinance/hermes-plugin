"""Asks the human to approve every Laso call that moves money, before it runs.

A ``pre_tool_call`` hook returns Hermes's ``approve`` directive for the tools ``tools.json`` marks
``requires_approval``: paid tools, withdrawals, transfers, cancels, deletes, and minting an API key. Hermes shows the message in
its own approval prompt, and a denial, a timeout, or an unattended run with nobody to ask blocks the
call. Read-only tools are never interrupted.
"""

import json

from . import sign_in

# Scalar arguments are what a human needs to judge a payment (amount, recipient, product); nested
# objects are left out so the prompt stays one readable line.
MAX_MESSAGE_LENGTH = 400


def _summarize(args: dict) -> str:
    parts = [
        f"{key}={json.dumps(value) if isinstance(value, str) else value}"
        for key, value in args.items()
        if isinstance(value, (str, int, float, bool)) and value != ""
    ]
    return ", ".join(parts)


def make_hook(approval_tools: set[str]):
    def pre_tool_call(tool_name: str = "", args: dict | None = None, **kwargs):
        del kwargs
        # Not connected yet: the call only returns the sign-in link, so there is nothing to approve.
        if tool_name not in approval_tools or not sign_in.current_key():
            return None
        summary = _summarize(args or {})
        message = f"Laso: {tool_name} moves money or changes your account."
        if summary:
            message = f"{message} {summary}"
        return {"action": "approve", "message": message[:MAX_MESSAGE_LENGTH]}

    return pre_tool_call
