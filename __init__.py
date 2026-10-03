"""Laso Finance plugin for Hermes Agent: registers the Laso tools."""

import json
from pathlib import Path

from .mcp_client import call_tool

TOOLSET = "laso"
TOOL_PREFIX = "laso_"


def _handler(mcp_name: str):
    def handle(args: dict, **kwargs) -> str:
        del kwargs
        return call_tool(mcp_name, args or {})

    return handle


def register(ctx):
    catalog = json.loads((Path(__file__).parent / "tools.json").read_text(encoding="utf-8"))
    for schema in catalog["tools"]:
        ctx.register_tool(
            name=schema["name"],
            toolset=TOOLSET,
            schema=schema,
            handler=_handler(schema["name"].removeprefix(TOOL_PREFIX)),
        )
    ctx.register_system_prompt_section("laso-finance", catalog["instructions"])
