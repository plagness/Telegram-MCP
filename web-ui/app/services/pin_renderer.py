"""Генерация изображений для закрепов (Playwright HTML→PNG).

Рендерит Jinja2 HTML-шаблоны в PNG через headless Chromium.
Используется для создания баннеров в закреплённых сообщениях Telegram.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

# Директория с шаблонами для закрепов
_PINS_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "pins"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_PINS_TEMPLATE_DIR)),
    autoescape=False,
)

# Размер баннера (px) — горизонтальный формат для Telegram
PIN_WIDTH = 800
PIN_HEIGHT = 400

# Playwright browser — инициализируется лениво
_browser = None
_playwright = None


async def _ensure_browser():
    """Ленивая инициализация Playwright Chromium."""
    global _browser, _playwright
    if _browser is not None:
        return _browser

    try:
        from playwright.async_api import async_playwright
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
            ],
        )
        logger.info("Playwright browser initialized")
        return _browser
    except Exception as e:
        logger.error("Не удалось инициализировать Playwright: %s", e)
        raise


async def render_pin_image(
    template_name: str,
    data: dict[str, Any],
    width: int = PIN_WIDTH,
    height: int = PIN_HEIGHT,
) -> bytes:
    """Рендерит HTML-шаблон в PNG байты.

    Args:
        template_name: имя файла шаблона (например 'pin_default.html')
        data: контекст для Jinja2 рендера
        width: ширина баннера
        height: высота баннера

    Returns:
        PNG-изображение как bytes
    """
    template = _jinja_env.get_template(template_name)
    html = template.render(**data)

    browser = await _ensure_browser()
    page = await browser.new_page(
        viewport={"width": width, "height": height},
        device_scale_factor=2,
    )
    try:
        await page.set_content(html, wait_until="networkidle")
        png_bytes = await page.screenshot(
            type="png",
            clip={"x": 0, "y": 0, "width": width, "height": height},
        )
        return png_bytes
    finally:
        await page.close()


async def close_browser():
    """Закрыть Playwright browser (вызывается при shutdown)."""
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    logger.info("Playwright browser closed")


def get_available_templates() -> list[str]:
    """Список доступных шаблонов для закрепов."""
    return [f.name for f in _PINS_TEMPLATE_DIR.glob("pin_*.html")]
