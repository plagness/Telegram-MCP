from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MCP_TOOLS_DIR = ROOT / "mcp/src/tools"
MANIFEST_PATH = ROOT / "docs/testing/mcp_tools_manifest.json"


def _collect_tools_from_source() -> list[str]:
    """Собирает имена инструментов из всех файлов mcp/src/tools/*.ts."""
    tools: list[str] = []
    for ts_file in sorted(MCP_TOOLS_DIR.glob("*.ts")):
        text = ts_file.read_text(encoding="utf-8")
        tools.extend(re.findall(r'name:\s*"([a-zA-Z0-9_.-]+)"', text))
    return tools


def test_mcp_tool_manifest_exists() -> None:
    assert MANIFEST_PATH.exists(), "mcp_tools_manifest.json is missing"


def test_mcp_tool_manifest_matches_source_count() -> None:
    tools = _collect_tools_from_source()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_tools = [item["tool"] for item in manifest.get("items", [])]
    assert len(manifest_tools) == len(tools), (
        f"Manifest has {len(manifest_tools)} tools, source has {len(tools)}"
    )


def test_mcp_tool_manifest_matches_source_names() -> None:
    tools = set(_collect_tools_from_source())
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_tools = {item["tool"] for item in manifest.get("items", [])}
    missing_in_manifest = tools - manifest_tools
    extra_in_manifest = manifest_tools - tools
    assert not missing_in_manifest, f"Tools in source but not in manifest: {missing_in_manifest}"
    assert not extra_in_manifest, f"Tools in manifest but not in source: {extra_in_manifest}"


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
