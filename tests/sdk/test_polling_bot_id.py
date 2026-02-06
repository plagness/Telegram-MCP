from __future__ import annotations

import inspect
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sdk"))

from telegram_api_client.commands import PollingManager  # noqa: E402


def test_polling_manager_start_has_bot_id_parameter() -> None:
    sig = inspect.signature(PollingManager.start)
    assert "bot_id" in sig.parameters
    assert sig.parameters["bot_id"].default is None


def test_polling_manager_source_contains_bot_id_in_ack_payload() -> None:
    source = Path(ROOT / "sdk/telegram_api_client/commands.py").read_text(encoding="utf-8")
    assert "ack_payload[\"bot_id\"] = bot_id" in source
