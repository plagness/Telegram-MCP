"""Сервис для обработки входящих вебхук-обновлений от Telegram."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from ..db import execute, execute_returning, fetch_all, fetch_one
from ..telegram_client import (
    send_message,
    answer_callback_query,
    edit_message_text,
    send_invoice,
    answer_pre_checkout_query,
)
from . import user_state, balance

logger = logging.getLogger(__name__)


def _detect_update_type(update: dict[str, Any]) -> str:
    for key in (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
        "my_chat_member",
        "chat_member",
        "chat_join_request",
        "message_reaction",
        "message_reaction_count",
        "poll",
        "poll_answer",
        "inline_query",
        "chosen_inline_result",
        "shipping_query",
        "pre_checkout_query",
        "purchased_paid_media",
        "business_connection",
        "business_message",
        "edited_business_message",
        "deleted_business_messages",
    ):
        if key in update:
            return key
    return "unknown"


def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
        if key in update:
            return update[key]
    return None


async def _upsert_user(user: dict[str, Any]) -> None:
    await execute(
        """
        INSERT INTO users (
            user_id,
            is_bot,
            first_name,
            last_name,
            username,
            language_code,
            is_premium,
            added_to_attachment_menu,
            last_seen_at,
            first_seen_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (user_id) DO UPDATE
        SET is_bot = EXCLUDED.is_bot,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            username = EXCLUDED.username,
            language_code = EXCLUDED.language_code,
            is_premium = EXCLUDED.is_premium,
            added_to_attachment_menu = COALESCE(EXCLUDED.added_to_attachment_menu, users.added_to_attachment_menu),
            last_seen_at = NOW(),
            updated_at = NOW()
        """,
        [
            str(user.get("id")),
            bool(user.get("is_bot")),
            user.get("first_name"),
            user.get("last_name"),
            user.get("username"),
            user.get("language_code"),
            bool(user.get("is_premium")) if user.get("is_premium") is not None else None,
            bool(user.get("added_to_attachment_menu")) if user.get("added_to_attachment_menu") is not None else None,
        ],
    )


async def _upsert_chat(chat: dict[str, Any], bot_id: int | None = None) -> None:
    photo = chat.get("photo") or {}
    chat_id = str(chat.get("id"))

    await execute(
        """
        INSERT INTO chats (
            chat_id,
            type,
            title,
            username,
            description,
            is_forum,
            member_count,
            invite_link,
            photo_file_id,
            bot_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (chat_id) DO UPDATE
        SET type = EXCLUDED.type,
            title = EXCLUDED.title,
            username = EXCLUDED.username,
            description = COALESCE(EXCLUDED.description, chats.description),
            is_forum = COALESCE(EXCLUDED.is_forum, chats.is_forum),
            member_count = COALESCE(EXCLUDED.member_count, chats.member_count),
            invite_link = COALESCE(EXCLUDED.invite_link, chats.invite_link),
            photo_file_id = COALESCE(EXCLUDED.photo_file_id, chats.photo_file_id),
            bot_id = COALESCE(EXCLUDED.bot_id, chats.bot_id),
            updated_at = NOW()
        """,
        [
            chat_id,
            chat.get("type"),
            chat.get("title"),
            chat.get("username"),
            chat.get("description"),
            chat.get("is_forum"),
            chat.get("member_count"),
            chat.get("invite_link"),
            photo.get("big_file_id") or photo.get("small_file_id"),
            bot_id,
        ],
    )

    # Авто-sync: запустить фоновую синхронизацию если member_count или photo_file_id не заполнены
    if chat_id not in _syncing_chats:
        _syncing_chats.add(chat_id)
        asyncio.create_task(_auto_sync_chat_if_needed(chat_id, bot_id))


# Множество чатов, для которых уже запущен/выполнен авто-sync (в рамках этого процесса)
_syncing_chats: set[str] = set()


async def _auto_sync_chat_if_needed(chat_id: str, bot_id: int | None) -> None:
    """Фоновая синхронизация чата, если не хватает member_count или photo_file_id."""
    try:
        row = await fetch_one(
            "SELECT member_count, photo_file_id FROM chats WHERE chat_id = %s",
            [chat_id],
        )
        if not row:
            return
        if row.get("member_count") is not None and row.get("photo_file_id") is not None:
            return  # Данные уже есть

        from .sync import sync_chat_info, sync_chat_admins
        info = await sync_chat_info(chat_id, bot_id=bot_id)
        logger.info("Авто-sync для чата %s: member_count=%s, photo=%s",
                     chat_id, info.get("member_count"), info.get("photo_file_id"))

        # Если есть photo_file_id, попробуем скачать аватарку
        if info.get("photo_file_id"):
            from .sync import sync_chat_avatar
            await sync_chat_avatar(chat_id, bot_id=bot_id)

        # Синхронизируем администраторов (если их ещё нет)
        admin_row = await fetch_one(
            "SELECT 1 FROM chat_members WHERE chat_id = %s AND status IN ('administrator', 'creator') LIMIT 1",
            [chat_id],
        )
        if not admin_row:
            await sync_chat_admins(chat_id, bot_id=bot_id)

    except Exception:
        logger.debug("Авто-sync для чата %s не удался", chat_id, exc_info=True)


async def _upsert_chat_member(
    chat_id: str | int | None,
    user_id: str | int | None,
    bot_id: int | None = None,
    status: str | None = None,
    member_data: dict[str, Any] | None = None,
) -> None:
    if chat_id is None or user_id is None:
        return

    # Извлечь расширенные поля из ChatMember object
    md = member_data or {}
    custom_title = md.get("custom_title")
    is_anonymous = md.get("is_anonymous")
    until_date_ts = md.get("until_date")
    until_date = None
    if until_date_ts and isinstance(until_date_ts, (int, float)):
        from datetime import datetime, timezone
        until_date = datetime.fromtimestamp(until_date_ts, tz=timezone.utc).isoformat()

    # Собрать все can_* permissions в JSONB
    permissions = {k: v for k, v in md.items() if k.startswith("can_") and isinstance(v, bool)} or None

    await execute(
        """
        INSERT INTO chat_members (chat_id, user_id, bot_id, status, custom_title,
                                  is_anonymous, until_date, permissions, last_seen_at,
                                  first_seen_at, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW(), NOW(), %s::jsonb)
        ON CONFLICT (chat_id, user_id) DO UPDATE
        SET bot_id = COALESCE(EXCLUDED.bot_id, chat_members.bot_id),
            status = COALESCE(EXCLUDED.status, chat_members.status),
            custom_title = COALESCE(EXCLUDED.custom_title, chat_members.custom_title),
            is_anonymous = COALESCE(EXCLUDED.is_anonymous, chat_members.is_anonymous),
            until_date = COALESCE(EXCLUDED.until_date, chat_members.until_date),
            permissions = COALESCE(EXCLUDED.permissions, chat_members.permissions),
            last_seen_at = NOW(),
            metadata = EXCLUDED.metadata,
            updated_at = NOW()
        """,
        [
            str(chat_id), str(user_id), bot_id, status or "member",
            custom_title, is_anonymous, until_date,
            json.dumps(permissions) if permissions else None,
            json.dumps({}),
        ],
    )


async def _increment_message_count(user_id: str, chat_id: str) -> None:
    """Инкремент счётчика сообщений в users и chat_members."""
    await execute(
        "UPDATE users SET message_count = COALESCE(message_count, 0) + 1 WHERE user_id = %s",
        [user_id],
    )
    await execute(
        """UPDATE chat_members SET message_count = COALESCE(message_count, 0) + 1
           WHERE user_id = %s AND chat_id = %s""",
        [user_id, chat_id],
    )


def _extract_media_type(message: dict[str, Any]) -> str | None:
    """Определить тип медиа из сообщения Telegram."""
    for media in (
        "photo", "video", "document", "audio", "voice",
        "sticker", "animation", "video_note", "contact",
        "location", "venue", "poll", "dice",
    ):
        if media in message:
            return media
    return None


def _extract_forward_origin(message: dict[str, Any]) -> dict[str, Any] | None:
    """Извлечь информацию о пересылке (forward)."""
    if "forward_origin" in message:
        return message["forward_origin"]
    if "forward_from" in message:
        return {"type": "user", "sender_user": message["forward_from"]}
    if "forward_from_chat" in message:
        return {"type": "channel", "chat": message["forward_from_chat"]}
    return None


async def _insert_inbound_message(message: dict[str, Any], update_type: str, bot_id: int | None = None) -> None:
    message_id = message.get("message_id")

    # Если нет message_id, пропускаем сохранение
    if not message_id:
        return

    media_type = _extract_media_type(message)
    forward_origin = _extract_forward_origin(message)
    sender_chat = message.get("sender_chat")
    entities = message.get("entities") or message.get("caption_entities")

    await execute(
        """
        INSERT INTO messages (
            chat_id,
            telegram_message_id,
            bot_id,
            direction,
            text,
            parse_mode,
            status,
            payload_json,
            media_type,
            caption,
            forward_origin,
            sender_chat_id,
            entities,
            has_media,
            is_topic_message
        )
        VALUES (%s, %s, %s, 'inbound', %s, NULL, %s, %s::jsonb,
                %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s)
        ON CONFLICT (chat_id, telegram_message_id) WHERE telegram_message_id IS NOT NULL DO NOTHING
        """,
        [
            str(message.get("chat", {}).get("id")),
            message_id,
            bot_id,
            message.get("text"),
            update_type,
            json.dumps(message),
            media_type,
            message.get("caption"),
            json.dumps(forward_origin) if forward_origin else None,
            str(sender_chat["id"]) if sender_chat else None,
            json.dumps(entities) if entities else None,
            media_type is not None,
            bool(message.get("is_topic_message")),
        ],
    )


async def _insert_chat_event(
    chat_id: str | int,
    bot_id: int | None,
    event_type: str,
    actor_user_id: str | int | None = None,
    target_user_id: str | int | None = None,
    tg_msg_id: int | None = None,
    event_data: dict[str, Any] | None = None,
) -> None:
    """Записать системное событие чата (join, leave, pin, title_change и т.д.)."""
    await execute(
        """
        INSERT INTO chat_events
            (chat_id, bot_id, event_type, actor_user_id, target_user_id,
             telegram_message_id, event_data)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        [
            str(chat_id),
            bot_id,
            event_type,
            str(actor_user_id) if actor_user_id is not None else None,
            str(target_user_id) if target_user_id is not None else None,
            tg_msg_id,
            json.dumps(event_data or {}),
        ],
    )


async def _handle_message_reaction(update: dict[str, Any], bot_id: int | None = None) -> None:
    """Обработка message_reaction: diff old/new реакций, upsert в message_reactions."""
    reaction_update = update.get("message_reaction", {})
    reaction_chat = reaction_update.get("chat", {})
    reaction_user = reaction_update.get("user")
    chat_id = str(reaction_chat["id"]) if reaction_chat.get("id") else None
    tg_msg_id = reaction_update.get("message_id")

    if not chat_id or not tg_msg_id:
        return

    # Upsert чат и юзер
    if reaction_chat:
        await _upsert_chat(reaction_chat, bot_id=bot_id)
    user_id: str | None = None
    if reaction_user:
        user_id = str(reaction_user["id"])
        await _upsert_user(reaction_user)
        await _upsert_chat_member(chat_id, user_id, bot_id=bot_id)

    # Найти внутренний message_id
    msg_row = await fetch_one(
        "SELECT id FROM messages WHERE chat_id = %s AND telegram_message_id = %s",
        [chat_id, tg_msg_id],
    )
    internal_msg_id = msg_row["id"] if msg_row else 0

    old_reactions = reaction_update.get("old_reaction", [])
    new_reactions = reaction_update.get("new_reaction", [])

    # Собрать ключи для diff
    def _reaction_key(r: dict) -> tuple:
        return (r.get("type", ""), r.get("emoji", ""), r.get("custom_emoji_id", ""))

    old_set = {_reaction_key(r) for r in old_reactions}
    new_set = {_reaction_key(r) for r in new_reactions}

    # Удалить исчезнувшие реакции
    removed = old_set - new_set
    for rtype, emoji, custom_id in removed:
        if user_id:
            await execute(
                """
                DELETE FROM message_reactions
                WHERE chat_id = %s AND telegram_message_id = %s
                  AND user_id = %s AND reaction_type = %s
                  AND COALESCE(reaction_emoji, '') = %s
                """,
                [chat_id, tg_msg_id, user_id, rtype, emoji],
            )

    # Добавить новые реакции
    added = new_set - old_set
    for rtype, emoji, custom_id in added:
        await execute(
            """
            INSERT INTO message_reactions
                (message_id, chat_id, telegram_message_id, user_id,
                 reaction_type, reaction_emoji, reaction_custom_emoji_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            [internal_msg_id, chat_id, tg_msg_id, user_id, rtype, emoji, custom_id or None],
        )


async def _handle_system_events(
    message: dict[str, Any],
    chat_id: str,
    from_user_id: str | None,
    bot_id: int | None,
) -> None:
    """Обработка системных событий внутри message (join, leave, pin, photo, title)."""
    tg_msg_id = message.get("message_id")

    # Новые участники чата
    if message.get("new_chat_members"):
        for new_member in message["new_chat_members"]:
            await _upsert_user(new_member)
            await _upsert_chat_member(
                chat_id, new_member.get("id"), bot_id=bot_id, status="member",
            )
            await _insert_chat_event(
                chat_id, bot_id, "join",
                actor_user_id=from_user_id,
                target_user_id=new_member.get("id"),
                tg_msg_id=tg_msg_id,
            )

    # Участник вышел / был удалён
    if message.get("left_chat_member"):
        left = message["left_chat_member"]
        await _upsert_user(left)
        await _upsert_chat_member(
            chat_id, left.get("id"), bot_id=bot_id, status="left",
        )
        await _insert_chat_event(
            chat_id, bot_id, "leave",
            actor_user_id=from_user_id,
            target_user_id=left.get("id"),
            tg_msg_id=tg_msg_id,
        )

    # Закреплённое сообщение
    if message.get("pinned_message"):
        pinned = message["pinned_message"]
        await _insert_chat_event(
            chat_id, bot_id, "pin",
            actor_user_id=from_user_id,
            tg_msg_id=tg_msg_id,
            event_data={"pinned_message_id": pinned.get("message_id")},
        )

    # Новая фотография чата
    if message.get("new_chat_photo"):
        await _insert_chat_event(
            chat_id, bot_id, "new_photo",
            actor_user_id=from_user_id,
            tg_msg_id=tg_msg_id,
        )

    # Удаление фотографии чата
    if message.get("delete_chat_photo"):
        await _insert_chat_event(
            chat_id, bot_id, "delete_photo",
            actor_user_id=from_user_id,
            tg_msg_id=tg_msg_id,
        )

    # Смена названия чата
    if message.get("new_chat_title"):
        await _insert_chat_event(
            chat_id, bot_id, "title_change",
            actor_user_id=from_user_id,
            tg_msg_id=tg_msg_id,
            event_data={"new_title": message["new_chat_title"]},
        )

    # Миграция чата (supergroup upgrade)
    if message.get("migrate_to_chat_id"):
        await _insert_chat_event(
            chat_id, bot_id, "migrate",
            tg_msg_id=tg_msg_id,
            event_data={"migrate_to_chat_id": message["migrate_to_chat_id"]},
        )


async def _insert_callback_query(callback_query: dict[str, Any], bot_id: int | None = None) -> None:
    """Сохранение callback_query в БД."""
    cq_id = str(callback_query.get("id"))
    cq_from = callback_query.get("from", {})
    message = callback_query.get("message", {})
    chat = message.get("chat", {})

    # Upsert пользователя
    if cq_from:
        await _upsert_user(cq_from)

    await execute(
        """
        INSERT INTO callback_queries (
            callback_query_id, chat_id, user_id, message_id,
            inline_message_id, data, payload_json, bot_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (callback_query_id) DO NOTHING
        """,
        [
            cq_id,
            str(chat.get("id")) if chat else None,
            str(cq_from.get("id")) if cq_from else None,
            message.get("message_id"),
            callback_query.get("inline_message_id"),
            callback_query.get("data"),
            json.dumps(callback_query),
            bot_id,
        ],
    )


async def _update_event_announcement(event_id: int) -> None:
    """
    Обновить публичный анонс события с текущими коэффициентами и распределением.

    Вызывается после каждой новой ставки.
    """
    # Получить событие с полной информацией
    event = await fetch_one(
        """
        SELECT
            e.*,
            (SELECT json_agg(json_build_object(
                'id', option_id,
                'text', text,
                'value', value,
                'total_bets', total_bets,
                'total_amount', total_amount
            )) FROM prediction_options WHERE event_id = e.id) as options
        FROM prediction_events e
        WHERE e.id = %s
        """,
        [event_id]
    )

    if not event or not event.get("telegram_message_id") or not event.get("chat_id"):
        return  # Нет сообщения для обновления

    def escape_html(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Форматирование опций с распределением
    options_lines = []
    total_pool = event["total_pool"]

    for opt in (event.get("options") or []):
        opt_text = opt['text']
        opt_amount = opt.get("total_amount", 0)
        opt_bets = opt.get("total_bets", 0)

        # Расчёт коэффициента
        if opt_amount > 0 and total_pool > 0:
            coef = round(total_pool / opt_amount, 2)
            coef_str = f" • x{coef}"
        else:
            coef_str = ""

        # Процент от банка
        if total_pool > 0:
            percentage = round((opt_amount / total_pool) * 100)
            bar_length = min(10, int(percentage / 10))
            bar = "█" * bar_length + "░" * (10 - bar_length)
            percentage_str = f" {bar} {percentage}%"
        else:
            percentage_str = ""

        value_str = f" <code>({escape_html(opt.get('value', ''))})</code>" if opt.get('value') else ""

        options_lines.append(
            f"  • {opt_text}{value_str}\n    {opt_bets} ставок, {opt_amount} ⭐{coef_str}{percentage_str}"
        )

    options_text = "\n\n".join(options_lines)

    updated_message_text = f"""
<b>🎯 Событие для ставок</b>

<b>{event['title']}</b>

{event['description']}

<b>Варианты:</b>
{options_text}

<b>Общий банк:</b> {total_pool} ⭐
<b>Комиссия:</b> {event.get('bot_commission', 0)} ⭐
<b>Ставка:</b> {event['min_bet']}-{event['max_bet']} ⭐
<b>Дедлайн:</b> {event.get('deadline') or "Не указан"}
<b>Статус:</b> {event['status']}
    """.strip()

    # Inline кнопка для ставки
    inline_keyboard = [[
        {
            "text": "💰 Поставить",
            "callback_data": f"bet_event_{event_id}"
        }
    ]]

    try:
        # Получить внутренний ID сообщения из БД
        msg_record = await fetch_one(
            "SELECT id FROM messages WHERE telegram_message_id = %s AND chat_id = %s",
            [event["telegram_message_id"], str(event["chat_id"])]
        )

        if msg_record:
            await edit_message_text({
                "message_id": msg_record["id"],
                "text": updated_message_text,
                "parse_mode": "HTML",
                "reply_markup": {
                    "inline_keyboard": inline_keyboard
                }
            })
            logger.info(f"Updated event {event_id} announcement")
    except Exception as e:
        logger.warning(f"Failed to update event announcement: {e}")


async def _handle_bet_command(user_id: int, text: str, chat_id: int) -> None:
    """
    Обработка команды /bet_{event_id}.

    Отправляет пользователю интерактивное сообщение с кнопками для ставки.
    """
    # Парсинг event_id из команды
    try:
        event_id = int(text.replace("/bet_", ""))
    except ValueError:
        await send_message({
            "chat_id": chat_id,
            "text": "❌ Неверный формат команды. Используйте /bet_{event_id}",
            "parse_mode": "HTML"
        })
        return

    # Получить событие с опциями
    event = await fetch_one(
        """
        SELECT
            e.*,
            (SELECT json_agg(json_build_object(
                'id', option_id,
                'text', text,
                'value', value,
                'total_bets', total_bets,
                'total_amount', total_amount
            )) FROM prediction_options WHERE event_id = e.id) as options
        FROM prediction_events e
        WHERE e.id = %s
        """,
        [event_id]
    )

    if not event:
        await send_message({
            "chat_id": chat_id,
            "text": "❌ Событие не найдено",
            "parse_mode": "HTML"
        })
        return

    if event["status"] != "active":
        await send_message({
            "chat_id": chat_id,
            "text": "❌ Событие уже завершено",
            "parse_mode": "HTML"
        })
        return

    # Получить баланс пользователя
    user_balance = await balance.get_user_balance(user_id)

    # Форматирование опций
    def escape_html(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    options_text = "\n".join([
        f"  • {opt['text']}" + (f" <code>({escape_html(opt['value'])})</code>" if opt.get('value') else "")
        for opt in (event.get("options") or [])
    ])

    # Расчёт коэффициентов
    total_pool = event["total_pool"]
    coefficients_text = ""

    if total_pool > 0:
        coefficients = []
        for opt in (event.get("options") or []):
            opt_amount = opt.get("total_amount", 0)
            if opt_amount > 0:
                coef = round(total_pool / opt_amount, 2)
                coefficients.append(f"  • {opt['text']}: x{coef}")

        if coefficients:
            coefficients_text = f"\n\n<b>Текущие коэффициенты:</b>\n{chr(10).join(coefficients)}"

    # Формируем кнопки для каждого варианта
    inline_keyboard = []
    for opt in (event.get("options") or []):
        inline_keyboard.append([
            {
                "text": f"💰 {opt['text']}",
                "callback_data": f"bet_{event_id}_{opt['id']}"
            }
        ])

    # Кнопка для просмотра статистики
    inline_keyboard.append([
        {
            "text": "📊 Статистика события",
            "callback_data": f"stats_{event_id}"
        }
    ])

    message_text = f"""
💰 <b>Размещение ставки</b>

<b>{event['title']}</b>

{event['description']}

<b>Варианты:</b>
{options_text}

<b>Ставка:</b> {event['min_bet']}-{event['max_bet']} ⭐
<b>Общий банк:</b> {total_pool} ⭐
<b>Ваш баланс:</b> {user_balance} ⭐{coefficients_text}

<i>Выберите вариант для ставки:</i>
    """.strip()

    await send_message({
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": inline_keyboard
        }
    })

    logger.info(f"User {user_id} requested betting interface for event {event_id}")


async def _handle_bet_event_callback(callback_query: dict[str, Any]) -> None:
    """
    Обработка нажатия кнопки "Поставить" из публичного анонса.

    Callback data формата: "bet_event_{event_id}"
    Отправляет пользователю в личку интерактивное сообщение с выбором вариантов.
    """
    cq_id = callback_query.get("id")
    cq_data = callback_query.get("data", "")
    user = callback_query.get("from", {})
    user_id = user.get("id")

    if not user_id:
        return

    # Парсинг event_id
    try:
        event_id = int(cq_data.replace("bet_event_", ""))
    except ValueError:
        await answer_callback_query({
            "callback_query_id": cq_id,
            "text": "❌ Неверный формат данных",
            "show_alert": True
        })
        return

    # Получить событие с опциями
    event = await fetch_one(
        """
        SELECT
            e.*,
            (SELECT json_agg(json_build_object(
                'id', option_id,
                'text', text,
                'value', value,
                'total_bets', total_bets,
                'total_amount', total_amount
            )) FROM prediction_options WHERE event_id = e.id) as options
        FROM prediction_events e
        WHERE e.id = %s
        """,
        [event_id]
    )

    if not event:
        await answer_callback_query({
            "callback_query_id": cq_id,
            "text": "❌ Событие не найдено",
            "show_alert": True
        })
        return

    if event["status"] != "active":
        await answer_callback_query({
            "callback_query_id": cq_id,
            "text": "❌ Событие уже завершено",
            "show_alert": True
        })
        return

    # Получить баланс пользователя
    user_balance = await balance.get_user_balance(user_id)

    # Форматирование опций
    def escape_html(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    options_text = "\n".join([
        f"  • {opt['text']}" + (f" <code>({escape_html(opt['value'])})</code>" if opt.get('value') else "")
        for opt in (event.get("options") or [])
    ])

    # Расчёт коэффициентов
    total_pool = event["total_pool"]
    coefficients_text = ""

    if total_pool > 0:
        coefficients = []
        for opt in (event.get("options") or []):
            opt_amount = opt.get("total_amount", 0)
            if opt_amount > 0:
                coef = round(total_pool / opt_amount, 2)
                coefficients.append(f"  • {opt['text']}: x{coef}")

        if coefficients:
            coefficients_text = f"\n\n<b>Текущие коэффициенты:</b>\n{chr(10).join(coefficients)}"

    # Формируем кнопки для каждого варианта
    inline_keyboard = []
    for opt in (event.get("options") or []):
        inline_keyboard.append([
            {
                "text": f"💰 {opt['text']}",
                "callback_data": f"bet_{event_id}_{opt['id']}"
            }
        ])

    # Кнопка для просмотра статистики
    inline_keyboard.append([
        {
            "text": "📊 Статистика события",
            "callback_data": f"stats_{event_id}"
        }
    ])

    message_text = f"""
💰 <b>Размещение ставки</b>

<b>{event['title']}</b>

{event['description']}

<b>Варианты:</b>
{options_text}

<b>Ставка:</b> {event['min_bet']}-{event['max_bet']} ⭐
<b>Общий банк:</b> {total_pool} ⭐
<b>Ваш баланс:</b> {user_balance} ⭐{coefficients_text}

<i>Выберите вариант для ставки:</i>
    """.strip()

    await send_message({
        "chat_id": user_id,
        "text": message_text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": inline_keyboard
        }
    })

    # Ответить на callback
    await answer_callback_query({
        "callback_query_id": cq_id,
        "text": "✅ Открыто в личных сообщениях"
    })

    logger.info(f"User {user_id} opened betting interface for event {event_id}")


async def _handle_bet_callback(callback_query: dict[str, Any]) -> None:
    """
    Обработка callback для размещения ставки.

    Callback data формата: "bet_{event_id}_{option_id}"
    """
    cq_id = callback_query.get("id")
    cq_data = callback_query.get("data", "")
    user = callback_query.get("from", {})
    user_id = user.get("id")

    if not user_id:
        return

    # Парсинг callback_data
    parts = cq_data.split("_")
    if len(parts) != 3 or parts[0] != "bet":
        return

    try:
        event_id = int(parts[1])
        option_id = parts[2]
    except (ValueError, IndexError):
        await answer_callback_query({
            "callback_query_id": cq_id,
            "text": "❌ Неверный формат данных",
            "show_alert": True
        })
        return

    # Проверка события
    event = await fetch_one(
        "SELECT * FROM prediction_events WHERE id = %s",
        [event_id]
    )

    if not event:
        await answer_callback_query({
            "callback_query_id": cq_id,
            "text": "❌ Событие не найдено",
            "show_alert": True
        })
        return

    if event["status"] != "active":
        await answer_callback_query({
            "callback_query_id": cq_id,
            "text": "❌ Событие уже завершено",
            "show_alert": True
        })
        return

    # Проверка варианта
    option = await fetch_one(
        "SELECT * FROM prediction_options WHERE event_id = %s AND option_id = %s",
        [event_id, option_id]
    )

    if not option:
        await answer_callback_query({
            "callback_query_id": cq_id,
            "text": "❌ Вариант не найден",
            "show_alert": True
        })
        return

    # Получить текущий баланс
    user_balance = await balance.get_user_balance(user_id)

    # Установить состояние FSM
    await user_state.set_user_state(
        user_id=user_id,
        state=user_state.UserStates.WAITING_BET_AMOUNT,
        data={
            "event_id": event_id,
            "option_id": option_id,
            "event_title": event["title"],
            "option_text": option["text"],
            "min_bet": event["min_bet"],
            "max_bet": event["max_bet"],
        },
        expires_in_seconds=300  # 5 минут
    )

    # Отправить сообщение с ForceReply для ввода суммы
    min_bet = event["min_bet"]
    max_bet = event["max_bet"]

    message_text = f"""
💰 <b>Размещение ставки</b>

<b>Событие:</b> {event['title']}
<b>Вариант:</b> {option['text']}

<b>Ваш баланс:</b> {user_balance} ⭐
<b>Лимиты:</b> {min_bet}-{max_bet} ⭐

<i>Введите сумму ставки (минимум {min_bet} ⭐):</i>
    """.strip()

    await send_message({
        "chat_id": user_id,
        "text": message_text,
        "parse_mode": "HTML",
        "reply_markup": {
            "force_reply": True,
            "input_field_placeholder": f"Например: {min_bet}"
        }
    })

    # Ответить на callback
    await answer_callback_query({
        "callback_query_id": cq_id,
        "text": f"✅ Размещение ставки на '{option['text']}'"
    })

    logger.info(f"User {user_id} initiated bet on event {event_id}, option {option_id}")


async def _handle_stats_callback(callback_query: dict[str, Any]) -> None:
    """
    Показать статистику события.

    Callback data формата: "stats_{event_id}"
    """
    cq_id = callback_query.get("id")
    cq_data = callback_query.get("data", "")
    user = callback_query.get("from", {})
    user_id = user.get("id")

    if not user_id:
        return

    # Парсинг callback_data
    parts = cq_data.split("_")
    if len(parts) != 2 or parts[0] != "stats":
        return

    try:
        event_id = int(parts[1])
    except ValueError:
        return

    # Получить событие с опциями
    event = await fetch_one(
        """
        SELECT
            e.*,
            (SELECT json_agg(json_build_object(
                'id', option_id,
                'text', text,
                'value', value,
                'total_bets', total_bets,
                'total_amount', total_amount
            )) FROM prediction_options WHERE event_id = e.id) as options
        FROM prediction_events e
        WHERE e.id = %s
        """,
        [event_id]
    )

    if not event:
        await answer_callback_query({
            "callback_query_id": cq_id,
            "text": "❌ Событие не найдено",
            "show_alert": True
        })
        return

    # Форматирование статистики
    options_stats = []
    for opt in (event.get("options") or []):
        total_bets = opt.get("total_bets", 0)
        total_amount = opt.get("total_amount", 0)
        options_stats.append(f"  • {opt['text']}: {total_bets} ставок, {total_amount} ⭐")

    stats_text = f"""
📊 <b>Статистика события</b>

<b>{event['title']}</b>

<b>Общий банк:</b> {event['total_pool']} ⭐
<b>Статус:</b> {event['status']}

<b>Распределение ставок:</b>
{chr(10).join(options_stats) if options_stats else "Нет ставок"}
    """.strip()

    await send_message({
        "chat_id": user_id,
        "text": stats_text,
        "parse_mode": "HTML"
    })

    await answer_callback_query({
        "callback_query_id": cq_id,
        "text": "📊 Статистика отправлена"
    })


async def _process_callback_query(callback_query: dict[str, Any]) -> None:
    """Обработка логики callback_query для системы ставок."""
    cq_data = callback_query.get("data", "")

    # Роутинг callback_data
    if cq_data.startswith("bet_event_"):
        # Кнопка "Поставить" из публичного анонса
        await _handle_bet_event_callback(callback_query)
    elif cq_data.startswith("bet_"):
        # Кнопка выбора конкретного варианта
        await _handle_bet_callback(callback_query)
    elif cq_data.startswith("stats_"):
        await _handle_stats_callback(callback_query)
    # Можно добавить другие обработчики


async def _handle_balance_command(user_id: int, chat_id: int) -> None:
    """Обработка команды /balance — показать баланс и статистику."""
    try:
        # Получить баланс
        user_balance = await balance.get_user_balance(user_id)

        # Получить статистику транзакций
        history = await balance.get_balance_history(user_id, limit=5, transaction_type=None)

        # Посчитать итоги
        total_deposits = sum(
            t.get("amount", 0)
            for t in history
            if t.get("transaction_type") == "payment"
        )
        total_bets = sum(
            t.get("amount", 0)
            for t in history
            if t.get("transaction_type") == "bet"
        )
        total_wins = sum(
            t.get("amount", 0)
            for t in history
            if t.get("transaction_type") == "win"
        )

        # Получить активные ставки
        active_bets = await fetch_all(
            """
            SELECT pb.*, pe.title as event_title, po.text as option_text
            FROM prediction_bets pb
            JOIN prediction_events pe ON pb.event_id = pe.id
            JOIN prediction_options po ON pb.event_id = po.event_id AND pb.option_id = po.option_id
            WHERE pb.user_id = %s AND pb.status = 'active'
            ORDER BY pb.created_at DESC
            """,
            [user_id]
        )

        # Сформировать сообщение
        text = f"""
💰 <b>Ваш баланс</b>

<b>Текущий баланс:</b> {user_balance} ⭐

<b>Статистика:</b>
• Пополнений: {total_deposits} ⭐
• Сделано ставок: {total_bets} ⭐
• Выиграно: {total_wins} ⭐

<b>Активные ставки:</b> {len(active_bets)}
        """.strip()

        if active_bets:
            text += "\n\n"
            for bet in active_bets[:3]:  # Показать первые 3
                event_title = bet.get("event_title", "")[:40]
                option_text = bet.get("option_text", "")[:30]
                bet_amount = bet.get("amount", 0)
                text += f"\n• <i>{event_title}</i>\n  Вариант: {option_text} • {bet_amount} ⭐"

            if len(active_bets) > 3:
                text += f"\n\n<i>...и ещё {len(active_bets) - 3}</i>"

        await send_message({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        })

        logger.info(f"Balance command executed for user {user_id}: balance={user_balance}")

    except Exception as exc:
        logger.error(f"Failed to handle /balance command: {exc}")
        await send_message({
            "chat_id": chat_id,
            "text": "❌ Ошибка получения баланса. Попробуйте позже.",
            "parse_mode": "HTML"
        })


async def _process_text_message(message: dict[str, Any]) -> None:
    """
    Обработка текстовых сообщений для команд и FSM (ввод суммы ставки и т.д.).
    """
    user = message.get("from", {})
    user_id = user.get("id")
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")

    if not user_id or not text:
        return

    # Обработка команды /balance
    if text == "/balance" or text.startswith("/balance@"):
        await _handle_balance_command(user_id, chat_id)
        return

    # Проверить состояние пользователя
    state_data = await user_state.get_user_state(user_id)

    if not state_data:
        return  # Нет активного состояния

    state = state_data.get("state")

    # Обработка ввода суммы ставки
    if state == user_state.UserStates.WAITING_BET_AMOUNT:
        await _handle_bet_amount_input(user_id, text, state_data, chat_id)


async def _handle_bet_amount_input(
    user_id: int,
    text: str,
    state_data: dict[str, Any],
    chat_id: int
) -> None:
    """Обработка ввода суммы ставки."""
    data = state_data.get("data", {})
    event_id = data.get("event_id")
    option_id = data.get("option_id")
    min_bet = data.get("min_bet", 10)
    max_bet = data.get("max_bet", 1000)
    event_title = data.get("event_title", "")
    option_text = data.get("option_text", "")

    # Парсинг суммы
    try:
        amount = int(text)
    except ValueError:
        await send_message({
            "chat_id": chat_id,
            "text": f"❌ Неверный формат. Введите число от {min_bet} до {max_bet}",
            "parse_mode": "HTML"
        })
        return

    # Валидация лимитов
    if amount < min_bet or amount > max_bet:
        await send_message({
            "chat_id": chat_id,
            "text": f"❌ Сумма должна быть от {min_bet} до {max_bet} ⭐",
            "parse_mode": "HTML"
        })
        return

    # Получить баланс
    user_balance = await balance.get_user_balance(user_id)

    if user_balance < amount:
        # Недостаточно средств — создать Stars invoice для пополнения
        shortage = amount - user_balance

        # Сохранить состояние с данными ставки для автоматического размещения после оплаты
        await user_state.set_user_state(
            user_id=user_id,
            state=user_state.UserStates.WAITING_PAYMENT,
            data={
                "event_id": event_id,
                "option_id": option_id,
                "bet_amount": amount,
                "event_title": event_title,
                "option_text": option_text,
            },
            expires_in_seconds=600  # 10 минут на оплату
        )

        # Создать invoice
        invoice_payload = {
            "chat_id": chat_id,
            "title": f"Пополнение для ставки",
            "description": f"Пополнение баланса на {amount} ⭐ для ставки в событии '{event_title}'",
            "payload": json.dumps({
                "type": "bet_topup",
                "user_id": user_id,
                "amount": amount,
                "event_id": event_id,
                "option_id": option_id
            }),
            "currency": "XTR",  # Telegram Stars
            "prices": [{"label": "Пополнение баланса", "amount": amount}]
        }

        try:
            await send_invoice(invoice_payload)
            logger.info(f"Invoice created for user {user_id}, amount={amount} Stars")

            # Отправить дополнительное объяснение
            await send_message({
                "chat_id": chat_id,
                "text": f"""
💳 <b>Требуется пополнение</b>

<b>Ваш баланс:</b> {user_balance} ⭐
<b>Требуется для ставки:</b> {amount} ⭐
<b>Недостаёт:</b> {shortage} ⭐

Нажмите кнопку выше для оплаты.
После успешной оплаты ставка будет размещена автоматически.
                """.strip(),
                "parse_mode": "HTML"
            })
        except Exception as exc:
            logger.error(f"Failed to create invoice: {exc}")
            await send_message({
                "chat_id": chat_id,
                "text": "❌ Ошибка создания счёта. Попробуйте позже.",
                "parse_mode": "HTML"
            })
        return

    # Проверить что событие ещё активно
    event = await fetch_one(
        "SELECT * FROM prediction_events WHERE id = %s AND status = 'active'",
        [event_id]
    )

    if not event:
        await send_message({
            "chat_id": chat_id,
            "text": "❌ Событие уже завершено или не найдено",
            "parse_mode": "HTML"
        })
        await user_state.clear_user_state(user_id)
        return

    # Расчёт комиссии (5%)
    commission_rate = event.get("commission_rate", 0.05)
    commission = int(amount * commission_rate)
    net_amount = amount - commission

    # Списать с баланса
    success = await balance.deduct_from_balance(
        user_id=user_id,
        amount=amount,
        transaction_type="bet",
        reference_type="prediction_event",
        reference_id=event_id,
        description=f"Ставка на '{option_text}' в событии '{event_title}'"
    )

    if not success:
        await send_message({
            "chat_id": chat_id,
            "text": "❌ Ошибка списания средств. Попробуйте снова.",
            "parse_mode": "HTML"
        })
        return

    # Создать ставку
    bet = await execute_returning(
        """
        INSERT INTO prediction_bets
        (event_id, option_id, user_id, amount, status, source)
        VALUES (%s, %s, %s, %s, 'active', 'balance')
        RETURNING id
        """,
        [event_id, option_id, user_id, net_amount]
    )

    # Обновить статистику события
    await execute(
        """
        UPDATE prediction_events
        SET total_pool = total_pool + %s,
            bot_commission = bot_commission + %s
        WHERE id = %s
        """,
        [net_amount, commission, event_id]
    )

    # Обновить статистику опции
    await execute(
        """
        UPDATE prediction_options
        SET total_bets = total_bets + 1,
            total_amount = total_amount + %s
        WHERE event_id = %s AND option_id = %s
        """,
        [net_amount, event_id, option_id]
    )

    # Очистить состояние
    await user_state.clear_user_state(user_id)

    # Отправить подтверждение
    new_balance = await balance.get_user_balance(user_id)

    confirmation_text = f"""
✅ <b>Ставка принята!</b>

<b>Событие:</b> {event_title}
<b>Вариант:</b> {option_text}

<b>Сумма ставки:</b> {amount} ⭐
<b>Комиссия (5%):</b> {commission} ⭐
<b>В банк:</b> {net_amount} ⭐

<b>Новый баланс:</b> {new_balance} ⭐

<i>ID ставки: {bet['id']}</i>
<i>Вы получите уведомление о результатах после завершения события.</i>
    """.strip()

    await send_message({
        "chat_id": chat_id,
        "text": confirmation_text,
        "parse_mode": "HTML"
    })

    logger.info(
        f"Bet placed: user={user_id}, event={event_id}, option={option_id}, "
        f"amount={amount}, commission={commission}, bet_id={bet['id']}"
    )

    # Обновить публичный анонс события
    await _update_event_announcement(event_id)


async def _handle_pre_checkout_query(pre_checkout: dict[str, Any]) -> None:
    """
    Обработка pre_checkout_query — подтверждение перед оплатой.

    Telegram требует ответить на этот запрос в течение 10 секунд.
    """
    query_id = pre_checkout.get("id")

    if not query_id:
        logger.error("pre_checkout_query without id")
        return

    # Всегда подтверждаем (можно добавить проверки, если нужно)
    try:
        await answer_pre_checkout_query({"pre_checkout_query_id": query_id, "ok": True})
        logger.info(f"Confirmed pre_checkout_query: {query_id}")
    except Exception as exc:
        logger.error(f"Failed to answer pre_checkout_query: {exc}")


async def _handle_successful_payment(message: dict[str, Any]) -> None:
    """
    Обработка successful_payment — успешная оплата Stars.

    После успешной оплаты:
    1. Зачислить сумму на баланс пользователя
    2. Если это оплата для ставки — автоматически разместить ставку
    """
    payment = message.get("successful_payment", {})
    user_id = message.get("from", {}).get("id")
    chat_id = message.get("chat", {}).get("id")

    if not user_id or not chat_id:
        logger.error("successful_payment without user_id or chat_id")
        return

    # Парсинг payload
    payload_str = payment.get("invoice_payload", "{}")
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        logger.error(f"Invalid payment payload: {payload_str}")
        return

    payment_type = payload.get("type")
    amount = payload.get("amount", 0)

    if payment_type != "bet_topup":
        logger.warning(f"Unknown payment type: {payment_type}")
        return

    # Зачислить на баланс
    await balance.add_to_balance(
        user_id=user_id,
        amount=amount,
        transaction_type="payment",
        reference_type="stars_payment",
        reference_id=None,
        description=f"Оплата Stars: {amount} ⭐"
    )

    logger.info(f"Credited {amount} Stars to user {user_id} from payment")

    # Получить состояние пользователя для автоматического размещения ставки
    state_data = await user_state.get_user_state(user_id)

    if not state_data or state_data.get("state") != user_state.UserStates.WAITING_PAYMENT:
        # Просто пополнение без автоставки
        new_balance = await balance.get_user_balance(user_id)
        await send_message({
            "chat_id": chat_id,
            "text": f"✅ Баланс пополнен на {amount} ⭐\n\n<b>Новый баланс:</b> {new_balance} ⭐",
            "parse_mode": "HTML"
        })
        return

    # Автоматически разместить ставку
    data = state_data.get("data", {})
    event_id = data.get("event_id")
    option_id = data.get("option_id")
    bet_amount = data.get("bet_amount")
    event_title = data.get("event_title", "")
    option_text = data.get("option_text", "")

    # Проверить что баланса теперь достаточно
    user_balance = await balance.get_user_balance(user_id)

    if user_balance < bet_amount:
        await send_message({
            "chat_id": chat_id,
            "text": f"⚠️ Баланс пополнен, но всё ещё недостаточно для ставки.\n\n<b>Баланс:</b> {user_balance} ⭐\n<b>Требуется:</b> {bet_amount} ⭐",
            "parse_mode": "HTML"
        })
        return

    # Проверить что событие активно
    event = await fetch_one(
        "SELECT * FROM prediction_events WHERE id = %s AND status = 'active'",
        [event_id]
    )

    if not event:
        await send_message({
            "chat_id": chat_id,
            "text": "❌ Событие уже завершено. Средства зачислены на баланс.",
            "parse_mode": "HTML"
        })
        await user_state.clear_user_state(user_id)
        return

    # Расчёт комиссии
    commission_rate = event.get("commission_rate", 0.05)
    commission = int(bet_amount * commission_rate)
    net_amount = bet_amount - commission

    # Списать с баланса
    success = await balance.deduct_from_balance(
        user_id=user_id,
        amount=bet_amount,
        transaction_type="bet",
        reference_type="prediction_event",
        reference_id=event_id,
        description=f"Ставка на '{option_text}' в событии '{event_title}'"
    )

    if not success:
        await send_message({
            "chat_id": chat_id,
            "text": "❌ Ошибка размещения ставки. Средства остались на балансе.",
            "parse_mode": "HTML"
        })
        await user_state.clear_user_state(user_id)
        return

    # Создать ставку
    bet = await execute_returning(
        """
        INSERT INTO prediction_bets
        (event_id, option_id, user_id, amount, status, source)
        VALUES (%s, %s, %s, %s, 'active', 'payment')
        RETURNING id
        """,
        [event_id, option_id, user_id, net_amount]
    )

    # Обновить статистику события
    await execute(
        """
        UPDATE prediction_events
        SET total_pool = total_pool + %s,
            bot_commission = bot_commission + %s
        WHERE id = %s
        """,
        [net_amount, commission, event_id]
    )

    # Обновить статистику опции
    await execute(
        """
        UPDATE prediction_options
        SET total_bets = total_bets + 1,
            total_amount = total_amount + %s
        WHERE event_id = %s AND option_id = %s
        """,
        [net_amount, event_id, option_id]
    )

    # Очистить состояние
    await user_state.clear_user_state(user_id)

    # Отправить подтверждение
    new_balance = await balance.get_user_balance(user_id)

    confirmation_text = f"""
✅ <b>Оплата успешна! Ставка размещена!</b>

<b>Событие:</b> {event_title}
<b>Вариант:</b> {option_text}

<b>Сумма ставки:</b> {bet_amount} ⭐
<b>Комиссия (5%):</b> {commission} ⭐
<b>В банк:</b> {net_amount} ⭐

<b>Новый баланс:</b> {new_balance} ⭐

<i>ID ставки: {bet['id']}</i>
<i>Вы получите уведомление о результатах после завершения события.</i>
    """.strip()

    await send_message({
        "chat_id": chat_id,
        "text": confirmation_text,
        "parse_mode": "HTML"
    })

    logger.info(
        f"Auto-bet placed after payment: user={user_id}, event={event_id}, "
        f"option={option_id}, amount={bet_amount}, bet_id={bet['id']}"
    )

    # Обновить публичный анонс события
    await _update_event_announcement(event_id)


async def ingest_update(update: dict[str, Any], bot_id: int | None = None) -> dict[str, Any]:
    update_id = update.get("update_id")
    update_type = _detect_update_type(update)
    message = _extract_message(update)

    update_chat_id: str | None = None
    update_user_id: str | None = None
    update_message_id: int | None = None

    if message:
        chat = message.get("chat") or {}
        update_chat_id = str(chat.get("id")) if chat.get("id") is not None else None
        update_message_id = message.get("message_id")
        await _upsert_chat(chat, bot_id=bot_id)
        from_user_id: str | None = None
        if message.get("from"):
            from_user = message.get("from") or {}
            from_user_id = str(from_user.get("id")) if from_user.get("id") is not None else None
            update_user_id = from_user_id
            await _upsert_user(from_user)
            await _upsert_chat_member(chat.get("id"), from_user.get("id"), bot_id=bot_id)
            # Счётчик сообщений (только для inbound от реальных юзеров)
            if update_type == "message" and from_user_id and update_chat_id:
                await _increment_message_count(from_user_id, update_chat_id)
        await _insert_inbound_message(message, update_type, bot_id=bot_id)
        # Системные события (join, leave, pin, photo, title)
        if update_chat_id:
            await _handle_system_events(message, update_chat_id, from_user_id, bot_id)
        # Обработка текстовых сообщений для FSM
        if update_type == "message" and message.get("text"):
            await _process_text_message(message)

    # Обработка callback_query
    if update_type == "callback_query":
        callback_query = update.get("callback_query", {})
        callback_message = callback_query.get("message", {})
        callback_chat = callback_message.get("chat", {})
        callback_user = callback_query.get("from", {})

        if callback_chat:
            update_chat_id = str(callback_chat.get("id")) if callback_chat.get("id") is not None else update_chat_id
            await _upsert_chat(callback_chat, bot_id=bot_id)
        if callback_user:
            update_user_id = str(callback_user.get("id")) if callback_user.get("id") is not None else update_user_id
            await _upsert_user(callback_user)
            await _upsert_chat_member(callback_chat.get("id"), callback_user.get("id"), bot_id=bot_id)
        if callback_message:
            update_message_id = callback_message.get("message_id") or update_message_id

        await _insert_callback_query(callback_query, bot_id=bot_id)
        # Бизнес-логика обработки callback
        await _process_callback_query(callback_query)

    # Обработка chat_member / my_chat_member (вступление/выход из чата)
    if update_type in ("chat_member", "my_chat_member"):
        member_update = update.get(update_type, {})
        cm_chat = member_update.get("chat") or {}
        cm_new = member_update.get("new_chat_member") or {}
        cm_user = cm_new.get("user") or {}
        cm_status = cm_new.get("status")  # member, administrator, creator, left, kicked, restricted

        if cm_chat.get("id") and cm_user.get("id"):
            update_chat_id = str(cm_chat["id"])
            update_user_id = str(cm_user["id"])
            await _upsert_chat(cm_chat, bot_id=bot_id)
            await _upsert_user(cm_user)
            await _upsert_chat_member(
                cm_chat["id"], cm_user["id"],
                bot_id=bot_id,
                status=cm_status,
                member_data=cm_new,
            )

    # Обработка message_reaction
    if update_type == "message_reaction":
        await _handle_message_reaction(update, bot_id=bot_id)
        reaction_update = update.get("message_reaction", {})
        rc = reaction_update.get("chat", {})
        ru = reaction_update.get("user", {})
        if rc.get("id"):
            update_chat_id = str(rc["id"])
        if ru.get("id"):
            update_user_id = str(ru["id"])

    # Обработка pre_checkout_query (подтверждение перед оплатой)
    if update_type == "pre_checkout_query":
        pre_checkout = update.get("pre_checkout_query", {})
        await _handle_pre_checkout_query(pre_checkout)

    # Обработка successful_payment (успешная оплата)
    if update_type == "message" and message and message.get("successful_payment"):
        await _handle_successful_payment(message)

    await execute_returning(
        """
        INSERT INTO webhook_updates (update_id, update_type, chat_id, user_id, message_id, payload_json, bot_id)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (update_id) DO UPDATE
        SET update_type = EXCLUDED.update_type,
            chat_id = EXCLUDED.chat_id,
            user_id = EXCLUDED.user_id,
            message_id = EXCLUDED.message_id,
            payload_json = EXCLUDED.payload_json,
            bot_id = EXCLUDED.bot_id,
            received_at = NOW()
        RETURNING id
        """,
        [
            update_id,
            update_type,
            update_chat_id,
            update_user_id,
            update_message_id,
            json.dumps(update),
            bot_id,
        ],
    )

    return {"ok": True, "update_type": update_type}


async def list_updates(
    limit: int = 100,
    offset: int = 0,
    update_type: str | None = None,
    bot_id: int | None = None,
) -> list[dict]:
    where: list[str] = []
    values: list[Any] = []
    if update_type:
        where.append("update_type = %s")
        values.append(update_type)
    if bot_id is not None:
        where.append("bot_id = %s")
        values.append(bot_id)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    return await fetch_all(
        f"SELECT * FROM webhook_updates {where_sql} ORDER BY received_at DESC LIMIT %s OFFSET %s",
        [*values, limit, offset],
    )
