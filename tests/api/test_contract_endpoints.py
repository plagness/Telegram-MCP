from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTERS_DIR = ROOT / "api/app/routers"
MANIFEST_PATH = ROOT / "docs/testing/api_endpoints_manifest.json"


def _collect_routes() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    pattern = re.compile(r'@router\.(get|post|put|delete|patch)\("([^"]+)"\)')
    for file_path in sorted(ROUTERS_DIR.glob("*.py")):
        text = file_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            match = pattern.search(line)
            if not match:
                continue
            items.append((match.group(1).upper(), match.group(2)))
    return items


def test_api_manifest_exists() -> None:
    assert MANIFEST_PATH.exists(), "api_endpoints_manifest.json is missing"


def test_api_manifest_matches_routes_count() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_items = manifest.get("items") or []
    routes = _collect_routes()
    assert routes, "No routes discovered in routers"
    assert len(manifest_items) == len(routes)


def test_api_manifest_has_unique_method_path_file_tuples() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    tuples = [
        (item["method"], item.get("declared_path", item.get("path")), item["file"])
        for item in manifest.get("items", [])
    ]
    assert len(tuples) == len(set(tuples))
