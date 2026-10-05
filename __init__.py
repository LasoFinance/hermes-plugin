"""Laso Finance plugin for Hermes Agent: registers the Laso tools."""

import json
from pathlib import Path

from . import sign_in
from .approvals import make_hook
from .mcp_client import call_tool

TOOLSET = "laso"
TOOL_PREFIX = "laso_"
PLUGIN_DIR = Path(__file__).parent


def _handler(mcp_name: str):
    def handle(args: dict, **kwargs) -> str:
        del kwargs
        return call_tool(mcp_name, args or {})

    return handle


def register(ctx):
    sign_in.bind(ctx)
    catalog = json.loads((PLUGIN_DIR / "tools.json").read_text(encoding="utf-8"))
    for tool in catalog["tools"]:
        schema = {key: tool[key] for key in ("name", "description", "parameters")}
        ctx.register_tool(
            name=tool["name"],
            toolset=TOOLSET,
            schema=schema,
            handler=_handler(tool["name"].removeprefix(TOOL_PREFIX)),
        )
    needs_approval = {tool["name"] for tool in catalog["tools"] if tool["requires_approval"]}
    ctx.register_hook("pre_tool_call", make_hook(needs_approval))
    ctx.register_system_prompt_section("laso-finance", catalog["instructions"])
    for skill_dir in sorted((PLUGIN_DIR / "skills").iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            ctx.register_skill(skill_dir.name, skill_md)
