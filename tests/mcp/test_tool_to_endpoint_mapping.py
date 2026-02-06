from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MCP_INDEX = ROOT / "mcp/src/index.ts"
MANIFEST_PATH = ROOT / "docs/testing/mcp_tools_manifest.json"


def _collect_tools_from_source() -> list[str]:
    text = MCP_INDEX.read_text(encoding="utf-8")
    return re.findall(r'name:\s*"([a-zA-Z0-9_.-]+)"', text)


def test_mcp_tool_manifest_exists() -> None:
    assert MANIFEST_PATH.exists(), "mcp_tools_manifest.json is missing"


def test_mcp_tool_manifest_matches_source_count() -> None:
    tools = _collect_tools_from_source()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_tools = [item["tool"] for item in manifest.get("items", [])]
    assert len(manifest_tools) == len(tools)


def test_critical_tool_names_present() -> None:
    tools = set(_collect_tools_from_source())
    required = {
        "messages.send",
        "chats.list",
        "chats.alias",
        "chats.history",
        "bots.list",
        "bots.default",
    }
    assert required.issubset(tools)
