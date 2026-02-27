#!/usr/bin/env python3
"""Генерация манифестов api_endpoints и mcp_tools из исходного кода.

Запуск: python scripts/generate_manifests.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTERS_DIR = ROOT / "api/app/routers"
MCP_TOOLS_DIR = ROOT / "mcp/src/tools"
DOCS_DIR = ROOT / "docs/testing"


def generate_api_manifest() -> dict:
    """Сканирует api/app/routers/*.py и собирает все @router.* декораторы."""
    items: list[dict] = []
    pattern = re.compile(r'@router\.(get|post|put|delete|patch)\("([^"]+)"\)')
    for file_path in sorted(ROUTERS_DIR.glob("*.py")):
        text = file_path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            match = pattern.search(line)
            if not match:
                continue
            items.append({
                "method": match.group(1).upper(),
                "declared_path": match.group(2),
                "file": str(file_path.relative_to(ROOT)),
                "line": i,
            })
    return {
        "generated_from": "api/app/routers/*.py",
        "count": len(items),
        "items": items,
    }


def generate_mcp_manifest() -> dict:
    """Сканирует mcp/src/tools/*.ts и собирает все name: \"...\" определения."""
    items: list[dict] = []
    name_pattern = re.compile(r'name:\s*"([a-zA-Z0-9_.-]+)"')
    for ts_file in sorted(MCP_TOOLS_DIR.glob("*.ts")):
        text = ts_file.read_text(encoding="utf-8")
        rel_path = str(ts_file.relative_to(ROOT))
        for name in name_pattern.findall(text):
            items.append({"tool": name, "file": rel_path})
    return {
        "generated_from": "mcp/src/tools/*.ts",
        "count": len(items),
        "items": items,
    }


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    api = generate_api_manifest()
    api_path = DOCS_DIR / "api_endpoints_manifest.json"
    api_path.write_text(json.dumps(api, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"API endpoints: {api['count']} → {api_path}")

    mcp = generate_mcp_manifest()
    mcp_path = DOCS_DIR / "mcp_tools_manifest.json"
    mcp_path.write_text(json.dumps(mcp, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"MCP tools: {mcp['count']} → {mcp_path}")


if __name__ == "__main__":
    main()
