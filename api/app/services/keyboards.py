"""Билдеры inline-клавиатур для предсказаний.

Вынесено из routers/predictions.py — формирование reply_markup
для публичных анонсов, персональных сообщений и web-app кнопок.
"""

from __future__ import annotations

from ..config import get_settings

settings = get_settings()


def bet_event_button(event_id: int) -> list[list[dict]]:
    """Кнопка «Предсказать» для публичного анонса в чате.

    Если web-ui включён и зарегистрирован Mini App — ссылка через
    t.me Direct Link (открывается как Mini App внутри Telegram).
    Если web-ui включён без Mini App — обычный url.
    Иначе — callback_data.
    """
    if settings.webui_enabled and settings.webui_bot_username and settings.webui_app_name:
        # Direct Link Mini App: открывается внутри Telegram
        return [[{
            "text": "\U0001f3af Предсказать",
            "url": f"https://t.me/{settings.webui_bot_username}/{settings.webui_app_name}?startapp=predict-{event_id}",
        }]]
    if settings.webui_enabled and settings.webui_public_url:
        return [[{
            "text": "\U0001f3af Предсказать",
            "url": f"{settings.webui_public_url}/p/predict-{event_id}",
        }]]
    return [[{
        "text": "\U0001f4b0 Поставить",
        "callback_data": f"bet_event_{event_id}",
    }]]


def bet_options_keyboard(
    event_id: int,
    options: list[dict],
    *,
    with_stats: bool = True,
) -> list[list[dict]]:
    """Кнопки выбора варианта для персонального сообщения.

    Каждый вариант — отдельная строка.
    В конце — кнопка статистики.
    """
    keyboard: list[list[dict]] = []
    for opt in options:
        keyboard.append([{
            "text": f"💰 {opt['text'] if isinstance(opt, dict) else opt.text}",
            "callback_data": f"bet_{event_id}_{opt['id'] if isinstance(opt, dict) else opt.id}",
        }])

    if with_stats:
        keyboard.append([{
            "text": "📊 Статистика события",
            "callback_data": f"stats_{event_id}",
        }])
    return keyboard
