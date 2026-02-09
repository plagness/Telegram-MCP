"""Роутер календаря — CRUD для календарей и записей."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from ..models import (
    BulkCreateEntriesIn,
    BulkDeleteEntriesIn,
    CreateCalendarIn,
    CreateEntryIn,
    CreateMonitorIn,
    CreateTriggerIn,
    FireEntryIn,
    MoveEntryIn,
    SetStatusIn,
    TickEntryIn,
    UpdateCalendarIn,
    UpdateEntryIn,
)
from ..services import calendar as cal_svc
from ..services import calendar_preview

router = APIRouter(prefix="/v1/calendar", tags=["calendar"])
logger = logging.getLogger(__name__)


# --- Календари ---


@router.post("/calendars")
async def create_calendar(payload: CreateCalendarIn):
    """Создать календарь."""
    try:
        cal = await cal_svc.create_calendar(
            slug=payload.slug,
            title=payload.title,
            description=payload.description,
            owner_id=payload.owner_id,
            chat_id=str(payload.chat_id) if payload.chat_id else None,
            bot_id=payload.bot_id,
            timezone=payload.timezone,
            is_public=payload.is_public,
            config=payload.config or {},
        )
        return {"ok": True, "calendar": cal}
    except Exception as e:
        logger.error("Ошибка создания календаря: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calendars")
async def list_calendars(
    owner_id: int | None = Query(None),
    chat_id: str | None = Query(None),
    bot_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Список календарей."""
    cals = await cal_svc.list_calendars(
        owner_id=owner_id, chat_id=chat_id, bot_id=bot_id,
        limit=limit, offset=offset,
    )
    return {"ok": True, "calendars": cals, "count": len(cals)}


@router.get("/calendars/{calendar_id}")
async def get_calendar(calendar_id: int):
    """Получить календарь."""
    cal = await cal_svc.get_calendar(calendar_id)
    if not cal:
        raise HTTPException(status_code=404, detail="Calendar not found")
    return {"ok": True, "calendar": cal}


@router.put("/calendars/{calendar_id}")
async def update_calendar(calendar_id: int, payload: UpdateCalendarIn):
    """Обновить календарь."""
    cal = await cal_svc.get_calendar(calendar_id)
    if not cal:
        raise HTTPException(status_code=404, detail="Calendar not found")

    updates = payload.model_dump(exclude_none=True)
    if "chat_id" in updates and updates["chat_id"] is not None:
        updates["chat_id"] = str(updates["chat_id"])
    if updates:
        await cal_svc.update_calendar(calendar_id, **updates)
    return {"ok": True, "calendar": await cal_svc.get_calendar(calendar_id)}


@router.delete("/calendars/{calendar_id}")
async def delete_calendar(calendar_id: int):
    """Удалить календарь."""
    await cal_svc.delete_calendar(calendar_id)
    return {"ok": True}


# --- Записи ---


@router.post("/entries")
async def create_entry(payload: CreateEntryIn):
    """Создать запись в календаре."""
    try:
        entry = await cal_svc.create_entry(
            calendar_id=payload.calendar_id,
            parent_id=payload.parent_id,
            title=payload.title,
            description=payload.description,
            emoji=payload.emoji,
            icon=payload.icon,
            start_at=payload.start_at,
            end_at=payload.end_at,
            all_day=payload.all_day,
            status=payload.status,
            priority=payload.priority,
            color=payload.color,
            tags=payload.tags,
            attachments=payload.attachments,
            metadata=payload.metadata,
            series_id=payload.series_id,
            repeat=payload.repeat,
            repeat_until=payload.repeat_until,
            position=payload.position,
            created_by=payload.created_by,
            ai_actionable=payload.ai_actionable,
            performed_by=payload.performed_by,
            # v3
            entry_type=payload.entry_type,
            trigger_at=payload.trigger_at,
            trigger_status=payload.trigger_status,
            action=payload.action,
            result=payload.result,
            source_module=payload.source_module,
            cost_estimate=payload.cost_estimate,
            tick_interval=payload.tick_interval,
            next_tick_at=payload.next_tick_at,
            tick_count=payload.tick_count,
            max_ticks=payload.max_ticks,
            expires_at=payload.expires_at,
        )
        return {"ok": True, "entry": entry}
    except Exception as e:
        logger.error("Ошибка создания записи: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entries/due")
async def get_due_entries(
    calendar_id: int | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
):
    """Записи, готовые к исполнению (trigger_at <= NOW, pending)."""
    entries = await cal_svc.get_due_entries(calendar_id=calendar_id, limit=limit)
    return {"ok": True, "entries": entries, "count": len(entries)}


@router.post("/entries/expire")
async def expire_entries():
    """Пометить протухшие записи (expires_at <= NOW)."""
    count = await cal_svc.expire_entries()
    return {"ok": True, "expired_count": count}


@router.get("/budget")
async def get_budget(
    calendar_id: int | None = Query(None),
    period: str = Query("day", pattern="^(day|week|month)$"),
    date: str | None = Query(None, description="ISO date, дефолт = сегодня"),
    source_module: str | None = Query(None),
):
    """Сводка бюджета за период."""
    result = await cal_svc.get_budget(
        calendar_id=calendar_id, period=period,
        date=date, source_module=source_module,
    )
    return {"ok": True, **result}


@router.get("/entries")
async def list_entries(
    calendar_id: int = Query(...),
    start: str | None = Query(None),
    end: str | None = Query(None),
    tags: str | None = Query(None, description="Теги через запятую"),
    status: str | None = Query(None),
    priority: int | None = Query(None, ge=1, le=5),
    ai_actionable: bool | None = Query(None),
    series_id: str | None = Query(None),
    entry_type: str | None = Query(None, description="Тип записи: event, task, trigger, monitor, vote, routine"),
    trigger_status: str | None = Query(None, description="Статус триггера"),
    source_module: str | None = Query(None, description="Модуль-источник"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Список записей с фильтрами."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    entries = await cal_svc.list_entries(
        calendar_id=calendar_id,
        start=start, end=end,
        tags=tag_list, status=status, priority=priority,
        ai_actionable=ai_actionable, series_id=series_id,
        entry_type=entry_type, trigger_status=trigger_status,
        source_module=source_module,
        limit=limit, offset=offset,
    )
    return {"ok": True, "entries": entries, "count": len(entries)}


@router.get("/entries/{entry_id}")
async def get_entry(entry_id: int):
    """Получить запись."""
    entry = await cal_svc.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"ok": True, "entry": entry}


@router.get("/entries/{entry_id}/chain")
async def get_chain(entry_id: int):
    """Цепочка связанных событий."""
    chain = await cal_svc.get_linked_chain(entry_id)
    return {"ok": True, "chain": chain, "count": len(chain)}


@router.put("/entries/{entry_id}")
async def update_entry(entry_id: int, payload: UpdateEntryIn):
    """Обновить запись."""
    entry = await cal_svc.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    updates = payload.model_dump(exclude_none=True)
    performed_by = updates.pop("performed_by", None)
    if updates:
        await cal_svc.update_entry(entry_id, performed_by=performed_by, **updates)
    return {"ok": True, "entry": await cal_svc.get_entry(entry_id)}


@router.post("/entries/{entry_id}/move")
async def move_entry(entry_id: int, payload: MoveEntryIn):
    """Переместить запись на новое время."""
    entry = await cal_svc.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    await cal_svc.move_entry(
        entry_id,
        start_at=payload.start_at,
        end_at=payload.end_at,
        performed_by=payload.performed_by,
    )
    return {"ok": True, "entry": await cal_svc.get_entry(entry_id)}


@router.post("/entries/{entry_id}/status")
async def set_entry_status(entry_id: int, payload: SetStatusIn):
    """Изменить статус записи."""
    entry = await cal_svc.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    await cal_svc.set_status(
        entry_id,
        status=payload.status,
        performed_by=payload.performed_by,
    )
    return {"ok": True, "entry": await cal_svc.get_entry(entry_id)}


@router.post("/entries/{entry_id}/fire")
async def fire_entry(entry_id: int, payload: FireEntryIn):
    """Записать результат исполнения триггера."""
    entry = await cal_svc.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    await cal_svc.fire_entry(
        entry_id,
        result=payload.result,
        trigger_status=payload.trigger_status,
        performed_by=payload.performed_by,
    )
    return {"ok": True, "entry": await cal_svc.get_entry(entry_id)}


@router.post("/entries/{entry_id}/tick")
async def tick_entry(entry_id: int, payload: TickEntryIn):
    """Продвинуть тик монитора."""
    entry = await cal_svc.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.get("entry_type") != "monitor":
        raise HTTPException(status_code=400, detail="Entry is not a monitor")

    updated = await cal_svc.tick_entry(
        entry_id,
        result=payload.result,
        performed_by=payload.performed_by,
    )
    return {"ok": True, "entry": updated}


@router.delete("/entries/{entry_id}")
async def delete_entry(entry_id: int, performed_by: str | None = Query(None)):
    """Удалить запись."""
    entry = await cal_svc.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    await cal_svc.delete_entry(entry_id, performed_by=performed_by)
    return {"ok": True}


@router.get("/entries/{entry_id}/history")
async def get_entry_history(
    entry_id: int,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """История изменений записи."""
    history = await cal_svc.get_entry_history(entry_id, limit=limit, offset=offset)
    return {"ok": True, "history": history, "count": len(history)}


# --- Массовые операции ---


@router.post("/entries/bulk")
async def bulk_create_entries(payload: BulkCreateEntriesIn):
    """Массовое создание записей."""
    entries = await cal_svc.bulk_create_entries(
        calendar_id=payload.calendar_id,
        entries=[e.model_dump() for e in payload.entries],
    )
    return {"ok": True, "entries": entries, "count": len(entries)}


@router.post("/entries/bulk-delete")
async def bulk_delete_entries(payload: BulkDeleteEntriesIn):
    """Массовое удаление записей."""
    await cal_svc.bulk_delete_entries(
        ids=payload.ids,
        performed_by=payload.performed_by,
    )
    return {"ok": True}


# --- Ближайшие ---


@router.get("/calendars/{calendar_id}/upcoming")
async def get_upcoming(
    calendar_id: int,
    limit: int = Query(3, ge=1, le=20),
):
    """Ближайшие активные события."""
    entries = await cal_svc.get_upcoming(calendar_id, limit=limit)
    return {"ok": True, "entries": entries, "count": len(entries)}


# --- Превью ---


@router.get("/calendars/{calendar_id}/preview.png")
async def get_preview(calendar_id: int):
    """Превью-изображение календаря (PNG 800x420)."""
    cal = await cal_svc.get_calendar(calendar_id)
    if not cal:
        raise HTTPException(status_code=404, detail="Calendar not found")

    png_data = await calendar_preview.generate_preview(calendar_id)
    return Response(
        content=png_data,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300"},
    )
