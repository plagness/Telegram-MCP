"""Авторизация Telegram Web App (initData HMAC-SHA256).

Валидация initData, полученной от Telegram Web App SDK.
Алгоритм: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, unquote


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age: int = 86400,
) -> dict | None:
    """Валидация initData от Telegram Web App.

    Args:
        init_data: Строка initData из Telegram.WebApp.initData
        bot_token: Токен бота для генерации secret key
        max_age: Максимальный возраст данных в секундах (по умолчанию 24ч)

    Returns:
        dict с данными пользователя или None если валидация не прошла.
        Содержит: id, first_name, last_name, username, language_code, is_premium
    """
    if not init_data or not bot_token:
        return None

    # Парсим initData как query string
    parsed = parse_qs(init_data, keep_blank_values=True)
    received_hash = parsed.pop("hash", [None])[0]
    if not received_hash:
        return None

    # Формируем data-check-string (sorted key=value, разделённые \n)
    data_check_string = "\n".join(
        f"{k}={v[0]}" for k, v in sorted(parsed.items())
    )

    # secret_key = HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()

    # Сравниваем HMAC-SHA256(data_check_string, secret_key) с hash
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    # Проверка возраста
    auth_date = int(parsed.get("auth_date", ["0"])[0])
    if time.time() - auth_date > max_age:
        return None

    # Извлекаем user
    user_raw = parsed.get("user", [None])[0]
    if user_raw:
        return json.loads(unquote(user_raw))

    return {"auth_date": auth_date}
