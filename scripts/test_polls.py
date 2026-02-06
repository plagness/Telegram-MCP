#!/usr/bin/env python3
"""
Тестовый скрипт: работа с опросами и викторинами.

Использование:
    python scripts/test_polls.py --chat-id -100123456789
    python scripts/test_polls.py --chat-id -100123456789 --quiz

Переменные окружения:
    TELEGRAM_API_URL — базовый URL (по умолчанию http://localhost:8081)
    TEST_CHAT_ID     — chat_id для тестов
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))

from telegram_api_client import TelegramAPI, TelegramAPIError


async def test_regular_poll(api: TelegramAPI, chat_id: int | str, bot_id: int | None = None) -> None:
    """Обычный опрос с множественным выбором."""
    print("\n=== Обычный опрос ===")
    try:
        poll = await api.send_poll(
            chat_id=chat_id,
            bot_id=bot_id,
            question="Какие языки программирования вы используете?",
            options=["Python", "JavaScript", "Go", "Rust", "C++", "Java"],
            is_anonymous=True,
            type="regular",
            allows_multiple_answers=True,
            open_period=60,  # 1 минута
        )
        poll_id = poll.get("id")
        telegram_msg_id = poll.get("telegram_message_id")
        print(f"   Опрос создан: internal_id={poll_id}, telegram_message_id={telegram_msg_id}")
        print(f"   Вопрос: {poll.get('text', 'N/A')}")
        print(f"   Опрос будет открыт 60 секунд")

        # Ждём 10 секунд
        print("\n   Ждём 10 секунд, можно проголосовать...")
        await asyncio.sleep(10)

        # Останавливаем опрос
        print(f"\n   Остановка опроса...")
        stopped = await api.stop_poll(chat_id, telegram_msg_id, bot_id=bot_id)
        print(f"   Опрос остановлен")
        print(f"   Всего голосов: {stopped.get('total_voter_count', 0)}")

    except TelegramAPIError as e:
        print(f"   Ошибка: {e}")


async def test_quiz(api: TelegramAPI, chat_id: int | str, bot_id: int | None = None) -> None:
    """Викторина с правильным ответом."""
    print("\n=== Викторина ===")
    try:
        quiz = await api.send_poll(
            chat_id=chat_id,
            bot_id=bot_id,
            question="Какой язык программирования был выпущен первым?",
            options=["Python", "Java", "C", "Fortran"],
            is_anonymous=False,
            type="quiz",
            correct_option_id=3,  # Fortran (индекс 3)
            explanation="Fortran был создан в 1957 году, задолго до остальных языков в списке.",
            explanation_parse_mode="HTML",
            open_period=30,
        )
        quiz_id = quiz.get("id")
        telegram_msg_id = quiz.get("telegram_message_id")
        print(f"   Викторина создана: internal_id={quiz_id}, telegram_message_id={telegram_msg_id}")
        print(f"   Правильный ответ: Fortran (индекс 3)")
        print(f"   Викторина будет открыта 30 секунд")

        await asyncio.sleep(5)
        print("\n   (Можете ответить в Telegram)")

    except TelegramAPIError as e:
        print(f"   Ошибка: {e}")


async def test_list_polls(api: TelegramAPI, chat_id: int | str, bot_id: int | None = None) -> None:
    """Список опросов."""
    print("\n=== Список опросов ===")
    try:
        polls = await api.list_polls(chat_id=str(chat_id), limit=5, bot_id=bot_id)
        print(f"   Найдено опросов: {len(polls)}")
        for p in polls[:3]:
            print(f"   - [{p.get('poll_id')}] {p.get('question')} (type={p.get('type')}, closed={p.get('is_closed')})")
    except TelegramAPIError as e:
        print(f"   Ошибка: {e}")


async def main(
    base_url: str,
    chat_id: int | str,
    quiz_only: bool = False,
    bot_id: int | None = None,
) -> None:
    async with TelegramAPI(base_url) as api:
        print(f"Тестирование опросов в чате {chat_id}")
        print(f"API: {base_url}")

        if not quiz_only:
            await test_regular_poll(api, chat_id, bot_id=bot_id)

        await test_quiz(api, chat_id, bot_id=bot_id)
        await test_list_polls(api, chat_id, bot_id=bot_id)

        print("\nГотово!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Тест опросов через telegram-api SDK")
    parser.add_argument(
        "--chat-id",
        default=os.environ.get("TEST_CHAT_ID"),
        help="Telegram chat_id",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("TELEGRAM_API_URL", "http://localhost:8081"),
        help="Базовый URL telegram-api",
    )
    parser.add_argument("--bot-id", type=int, default=None, help="Явный bot_id для мультибот-теста")
    parser.add_argument("--quiz", action="store_true", dest="quiz_only", help="Только викторина (без обычного опроса)")
    args = parser.parse_args()

    if not args.chat_id:
        parser.error("Укажите --chat-id или TEST_CHAT_ID")

    bot_id = args.bot_id or (int(os.environ["TEST_BOT_ID"]) if os.environ.get("TEST_BOT_ID") else None)
    asyncio.run(main(args.base_url, args.chat_id, args.quiz_only, bot_id=bot_id))
