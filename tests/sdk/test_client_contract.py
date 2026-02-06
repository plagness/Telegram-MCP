from __future__ import annotations

import inspect
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sdk"))

from telegram_api_client.client import TelegramAPI  # noqa: E402


def test_start_polling_has_bot_id_parameter() -> None:
    sig = inspect.signature(TelegramAPI.start_polling)
    assert "bot_id" in sig.parameters
    assert sig.parameters["bot_id"].default is None


def test_list_updates_has_bot_id_parameter() -> None:
    sig = inspect.signature(TelegramAPI.list_updates)
    assert "bot_id" in sig.parameters
    assert sig.parameters["bot_id"].default is None
