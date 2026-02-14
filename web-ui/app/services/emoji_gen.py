"""Генерация тематических эмодзи для страницы через LLM.

При создании страницы вызывается generate_page_emojis(), которая
отправляет промпт в llmcore и получает JSON с 5 ролями:
star (ядро), orbit1-4 (планеты/спутники).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

_EMOJI_PROMPT = """Pick exactly 5 unique emojis that represent the topic "{title}" ({page_type}).

Each emoji MUST be different and specifically related to THIS topic.
Return JSON with keys: star, orbit1, orbit2, orbit3, orbit4.
Values must be quoted emoji strings.

Example format: {{"star": "🎵", "orbit1": "🎸", "orbit2": "🎤", "orbit3": "🎶", "orbit4": "🎧"}}

Your answer for "{title}":"""


async def generate_page_emojis(
    title: str, page_type: str
) -> dict[str, str] | None:
    """Запросить LLM подбор эмодзи. Возвращает dict или None при ошибке."""
    settings = get_settings()
    prompt = _EMOJI_PROMPT.format(title=title, page_type=page_type)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.llm_core_url}/v1/llm/request",
                json={
                    "task": "chat",
                    "provider": "ollama",
                    "model": "llama3:8b",
                    "prompt": prompt,
                    "temperature": 0.9,
                    "max_tokens": 80,
                    "priority": 1,
                    "source": "tgweb-emoji",
                    "constraints": {"prefer_local": True},
                },
            )
            job_id = resp.json().get("job_id")
            if not job_id:
                return None

            # Polling (макс 30с, шаг 1с)
            for _ in range(30):
                await asyncio.sleep(1)
                r = await client.get(
                    f"{settings.llm_core_url}/v1/jobs/{job_id}"
                )
                job = r.json()
                if job.get("status") == "done":
                    data = job.get("result", {}).get("data", "")
                    # Ollama возвращает dict с полем response
                    if isinstance(data, dict):
                        raw = data.get("response", "")
                    else:
                        raw = str(data)
                    parsed = _parse_emoji_response(raw)
                    if not parsed:
                        logger.warning(
                            "Не удалось распарсить эмодзи, raw: %.200s",
                            raw,
                        )
                    return parsed
                if job.get("status") == "error":
                    logger.warning(
                        "LLM emoji error для '%s': %s",
                        title,
                        job.get("error"),
                    )
                    return None
    except Exception:
        logger.warning(
            "Не удалось сгенерировать эмодзи для '%s'",
            title,
            exc_info=True,
        )
    return None


_EMOJI_KEYS = ("star", "orbit1", "orbit2", "orbit3", "orbit4")

# Regex: ключ + двоеточие + необязательные кавычки + эмодзи (1-4 символа)
_KV_PATTERN = re.compile(
    r'"(star|orbit[1-4])"\s*:\s*"?([^\s",}{]{1,4})"?'
)


def _parse_emoji_response(raw: str) -> dict[str, str] | None:
    """Извлечь эмодзи из ответа LLM (поддержка невалидного JSON)."""
    # Сначала пробуем стандартный JSON
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start < 0 or end <= start:
        return None

    fragment = raw[start:end]
    result = {}

    # Попытка 1: валидный JSON
    try:
        data = json.loads(fragment)
        for key in _EMOJI_KEYS:
            v = data.get(key, "")
            if v and len(v) <= 4:
                result[key] = v
        if result:
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Попытка 2: regex для невалидного JSON (эмодзи без кавычек)
    for match in _KV_PATTERN.finditer(fragment):
        key, val = match.group(1), match.group(2).strip()
        if val and len(val) <= 4:
            result[key] = val
    return result if result else None
