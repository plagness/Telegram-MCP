from __future__ import annotations

import inspect
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

from app.models import UpdatesAckIn  # noqa: E402
from app.routers import updates as updates_router  # noqa: E402


def test_ack_model_has_optional_bot_id() -> None:
    fields = UpdatesAckIn.model_fields
    assert "offset" in fields
    assert "bot_id" in fields
    assert fields["bot_id"].default is None


def test_poll_updates_accepts_bot_id() -> None:
    sig = inspect.signature(updates_router.poll_updates)
    assert "bot_id" in sig.parameters
    default = sig.parameters["bot_id"].default
    # FastAPI wraps defaults with Query(None), so check both raw None and wrapped None.
    if default is not None:
        assert getattr(default, "default", object()) is None


def test_get_current_offset_accepts_bot_id() -> None:
    sig = inspect.signature(updates_router.get_current_offset)
    assert "bot_id" in sig.parameters
