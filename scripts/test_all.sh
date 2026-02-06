#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[1/4] Python syntax checks"
python -m py_compile "$ROOT_DIR"/api/app/*.py
python -m py_compile "$ROOT_DIR"/api/app/routers/*.py
python -m py_compile "$ROOT_DIR"/api/app/services/*.py
python -m py_compile "$ROOT_DIR"/sdk/telegram_api_client/*.py

echo "[2/4] TypeScript build check"
if command -v npm >/dev/null 2>&1; then
  (cd "$ROOT_DIR/mcp" && npm run build >/dev/null)
else
  echo "npm is not installed; skipping TypeScript build check"
fi

echo "[3/4] Contract tests"
if command -v pytest >/dev/null 2>&1; then
  pytest -q "$ROOT_DIR/tests"
else
  echo "pytest is not installed; skipping contract tests"
fi

echo "[4/4] Optional smoke scripts"
if [[ "${RUN_SMOKE:-0}" == "1" ]]; then
  python "$ROOT_DIR/scripts/test_updates.py"
else
  echo "set RUN_SMOKE=1 to run smoke scripts"
fi

echo "test_all: done"
