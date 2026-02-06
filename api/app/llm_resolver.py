"""
LLM Resolver для Prediction Markets.

Интеграция с llm-mcp, Ollama, OpenRouter для принятия решений о результатах событий.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# === Providers Configuration ===

LLM_MCP_URL = "http://localhost:3336"  # llm-mcp server
OLLAMA_URL = "http://localhost:11434"  # Ollama API
OPENROUTER_URL = "https://openrouter.ai/api/v1"


# === LLM Provider Clients ===


async def call_llm_mcp(
    prompt: str,
    model: str = "claude-3-5-sonnet-20241022",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Вызов llm-mcp для принятия решения.

    Args:
        prompt: Промпт с описанием события и вопросом
        model: Модель LLM
        context: Дополнительный контекст (новости, данные)

    Returns:
        {"decision": str, "confidence": float, "reasoning": str}
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{LLM_MCP_URL}/chat",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ты эксперт по анализу событий и принятию решений в prediction markets. Анализируй факты и делай взвешенные выводы.",
                        },
                        {
                            "role": "user",
                            "content": prompt + (f"\n\nКонтекст: {context}" if context else ""),
                        },
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()

            # Парсинг ответа
            content = data.get("content", "")
            return {
                "decision": content,
                "confidence": 0.9,  # TODO: извлечь из ответа
                "reasoning": content,
                "provider": "llm-mcp",
            }

    except Exception as e:
        logger.error(f"Ошибка вызова llm-mcp: {e}")
        raise


async def call_ollama(
    prompt: str,
    model: str = "llama3.3:70b",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Вызов Ollama для принятия решения.

    Args:
        prompt: Промпт с описанием события
        model: Модель Ollama
        context: Дополнительный контекст

    Returns:
        {"decision": str, "confidence": float, "reasoning": str}
    """
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": f"""Ты эксперт по анализу событий. Проанализируй следующую ситуацию и определи результат.

{prompt}

{f"Контекст: {context}" if context else ""}

Ответь в формате JSON:
{{
  "decision": "ID варианта или несколько через запятую",
  "confidence": 0.95,
  "reasoning": "Обоснование решения"
}}
""",
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Парсинг ответа
            response_text = data.get("response", "")

            # Простой парсинг JSON из ответа
            import json
            try:
                parsed = json.loads(response_text)
                return {
                    "decision": parsed.get("decision", ""),
                    "confidence": parsed.get("confidence", 0.8),
                    "reasoning": parsed.get("reasoning", ""),
                    "provider": "ollama",
                }
            except json.JSONDecodeError:
                return {
                    "decision": response_text,
                    "confidence": 0.7,
                    "reasoning": response_text,
                    "provider": "ollama",
                }

    except Exception as e:
        logger.error(f"Ошибка вызова Ollama: {e}")
        raise


async def call_openrouter(
    prompt: str,
    model: str = "anthropic/claude-3.5-sonnet",
    context: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """
    Вызов OpenRouter для принятия решения.

    Args:
        prompt: Промпт с описанием события
        model: Модель OpenRouter
        context: Дополнительный контекст
        api_key: OpenRouter API key

    Returns:
        {"decision": str, "confidence": float, "reasoning": str}
    """
    if not api_key:
        api_key = settings.openrouter_api_key  # type: ignore

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OPENROUTER_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ты эксперт по анализу событий и принятию решений. Анализируй факты объективно.",
                        },
                        {
                            "role": "user",
                            "content": prompt + (f"\n\nКонтекст: {context}" if context else ""),
                        },
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()

            # Парсинг ответа
            content = data["choices"][0]["message"]["content"]
            return {
                "decision": content,
                "confidence": 0.9,
                "reasoning": content,
                "provider": "openrouter",
            }

    except Exception as e:
        logger.error(f"Ошибка вызова OpenRouter: {e}")
        raise


# === Main Resolver ===


async def resolve_prediction_event(
    event: dict[str, Any],
    options: list[dict[str, Any]],
    provider: str = "llm-mcp",
    model: str | None = None,
    news_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Разрешение события через LLM.

    Args:
        event: Данные события (title, description, resolution_date)
        options: Варианты ответов
        provider: llm-mcp / ollama / openrouter
        model: Модель LLM (опционально)
        news_data: Данные новостей из channel-mcp

    Returns:
        {
            "winning_option_ids": ["1", "2"],
            "confidence": 0.95,
            "reasoning": "...",
            "provider": "llm-mcp"
        }
    """
    # Формирование промпта
    options_text = "\n".join(
        [f"{i+1}. {opt['text']}" + (f" ({opt['value']})" if opt.get('value') else "") for i, opt in enumerate(options)]
    )

    prompt = f"""
Событие для ставок:
**{event['title']}**

Описание: {event['description']}

Варианты ответов:
{options_text}

Текущая дата: {datetime.now().isoformat()}
Дата разрешения: {event.get('resolution_date', 'Не указана')}

Проанализируй доступную информацию и определи какой вариант(ы) является правильным.
Если точного совпадения нет, выбери ближайшие варианты.
Если ни один вариант не подходит, верни пустой список (полный возврат ставок).

Ответь в формате JSON:
{{
  "winning_option_ids": ["id1", "id2"],
  "confidence": 0.95,
  "reasoning": "Подробное объяснение решения"
}}
""".strip()

    # Вызов провайдера
    if provider == "llm-mcp":
        result = await call_llm_mcp(prompt, model or "claude-3-5-sonnet-20241022", news_data)
    elif provider == "ollama":
        result = await call_ollama(prompt, model or "llama3.3:70b", news_data)
    elif provider == "openrouter":
        result = await call_openrouter(prompt, model or "anthropic/claude-3.5-sonnet", news_data)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    # Парсинг decision → winning_option_ids
    # TODO: более умный парсинг ответа LLM
    decision = result.get("decision", "")

    # Простой парсинг: ищем ID вариантов в тексте
    winning_ids = []
    for opt in options:
        if opt["id"] in decision or opt["text"] in decision:
            winning_ids.append(opt["id"])

    return {
        "winning_option_ids": winning_ids,
        "confidence": result.get("confidence", 0.8),
        "reasoning": result.get("reasoning", ""),
        "provider": provider,
        "raw_response": result,
    }


# === News Aggregation (via channel-mcp) ===


async def fetch_news_from_channel_mcp(
    sources: list[str],
    keywords: list[str],
    date_range: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """
    Агрегация новостей через channel-mcp.

    Args:
        sources: Источники новостей (каналы Telegram)
        keywords: Ключевые слова для поиска
        date_range: Диапазон дат (start, end) в ISO format

    Returns:
        {"news": [...], "total": N}
    """
    try:
        # TODO: Интеграция с channel-mcp MCP server
        # Предполагается что channel-mcp работает на localhost:3337
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "http://localhost:3337/tools/news.search",
                json={
                    "sources": sources,
                    "keywords": keywords,
                    "date_range": date_range,
                },
            )
            response.raise_for_status()
            return response.json()

    except Exception as e:
        logger.warning(f"Ошибка агрегации новостей: {e}")
        return {"news": [], "total": 0}
