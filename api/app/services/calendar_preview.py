"""Генерация превью-изображения календаря (PNG 4K 19:9).

Стиль: тёмный фон, медовые акценты, премиум.
Используется для закрепа в чате с кнопкой Mini App.
"""

from __future__ import annotations

import io
import math
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

from . import calendar as cal_svc

# ── Размеры (4K, 19:9) ──────────────────────────────────
WIDTH = 3840
HEIGHT = WIDTH * 9 // 19  # ≈ 1818

# ── Тёмная тема — медовый стиль ─────────────────────────
BG = (18, 18, 22)             # почти чёрный
CARD_BG = (28, 28, 34)        # тёмно-серый
CARD_BORDER = (42, 42, 50)    # граница карточки
TEXT = (245, 245, 245)         # почти белый
HINT = (140, 140, 155)        # приглушённый
ACCENT = (255, 193, 7)        # медовый
ACCENT_DARK = (255, 160, 0)   # тёмный мёд
ACCENT_DIM = (255, 193, 7, 25)  # для паттерна
GLOW = (255, 193, 7, 15)      # свечение

# ── Цвета тегов и приоритетов ────────────────────────────
TAG_COLORS = {
    "work": (100, 170, 240),
    "personal": (175, 110, 210),
    "meeting": (70, 220, 140),
    "deadline": (240, 95, 80),
    "idea": (250, 175, 40),
}
PRIORITY_COLORS = {
    5: (240, 95, 80),
    4: (240, 145, 55),
    3: (255, 193, 7),
    2: (70, 220, 140),
    1: (160, 175, 185),
}

MONTH_NAMES = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _auto_color(tags: list[str] | None, priority: int) -> tuple[int, int, int]:
    """Детерминированный цвет как RGB."""
    if tags:
        for tag in tags:
            c = TAG_COLORS.get(tag.lower())
            if c:
                return c
    return PRIORITY_COLORS.get(priority, ACCENT[:3])


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Загрузить DejaVu шрифт."""
    paths = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/TTF/DejaVuSans{'-Bold' if bold else ''}.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _hex_pattern(
    draw: ImageDraw.ImageDraw,
    x0: int, y0: int, x1: int, y1: int,
    size: int = 32,
    color: tuple = ACCENT_DIM,
) -> None:
    """Гексагональный паттерн — медовые соты."""
    h = size * math.sqrt(3)
    row = 0
    y = y0
    while y < y1 + h:
        offset = size * 1.5 if row % 2 else 0
        x = x0 + offset
        while x < x1 + size * 3:
            _draw_hex(draw, x, y, size, color)
            x += size * 3
        y += h / 2
        row += 1


def _draw_hex(
    draw: ImageDraw.ImageDraw,
    cx: float, cy: float, r: int,
    color: tuple,
) -> None:
    """Один гексагон."""
    points = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(points, outline=color)


def _rounded_rect(
    draw: ImageDraw.ImageDraw,
    bbox: list,
    radius: int,
    fill: tuple | None = None,
    outline: tuple | None = None,
    width: int = 0,
) -> None:
    """Скруглённый прямоугольник с опциональной обводкой."""
    draw.rounded_rectangle(bbox, radius=radius, fill=fill, outline=outline, width=width)


def _format_time(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _format_date(dt: datetime) -> str:
    return f"{dt.day} {MONTH_NAMES[dt.month - 1]}"


def _gradient_rect(
    img: Image.Image,
    bbox: tuple[int, int, int, int],
    color_start: tuple[int, int, int, int],
    color_end: tuple[int, int, int, int],
    horizontal: bool = True,
) -> None:
    """Градиентный прямоугольник (альфа-наложение)."""
    x0, y0, x1, y1 = bbox
    w = x1 - x0
    h = y1 - y0
    if w <= 0 or h <= 0:
        return
    grad = Image.new("RGBA", (w, h))
    grad_draw = ImageDraw.Draw(grad)
    steps = w if horizontal else h
    for i in range(steps):
        t = i / max(steps - 1, 1)
        r = int(color_start[0] + (color_end[0] - color_start[0]) * t)
        g = int(color_start[1] + (color_end[1] - color_start[1]) * t)
        b = int(color_start[2] + (color_end[2] - color_start[2]) * t)
        a = int(color_start[3] + (color_end[3] - color_start[3]) * t)
        if horizontal:
            grad_draw.line([(i, 0), (i, h)], fill=(r, g, b, a))
        else:
            grad_draw.line([(0, i), (w, i)], fill=(r, g, b, a))
    img.paste(grad, (x0, y0), grad)


async def generate_preview(calendar_id: int) -> bytes:
    """Генерация PNG-превью 4K 19:9, тёмный фон, медовый стиль."""
    cal = await cal_svc.get_calendar(calendar_id)
    entries = await cal_svc.get_upcoming(calendar_id, limit=5)

    img = Image.new("RGBA", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img, "RGBA")

    # Шрифты (масштабированные для 4K)
    font_title = _font(88, bold=True)
    font_subtitle = _font(44)
    font_event_title = _font(56, bold=True)
    font_event_time = _font(42)
    font_tag = _font(36, bold=True)
    font_footer = _font(44, bold=True)
    font_footer_sm = _font(36)

    pad = 80  # отступ от краёв

    # ── Фоновый гексагональный паттерн (на всё изображение) ──
    _hex_pattern(draw, 0, 0, WIDTH, HEIGHT, size=48, color=(255, 193, 7, 10))

    # ── Верхняя полоса с градиентом мёда ──
    _gradient_rect(
        img,
        (0, 0, WIDTH, 8),
        (255, 193, 7, 200),
        (255, 143, 0, 200),
        horizontal=True,
    )

    # ── Заголовочная область ──
    header_y = pad
    cal_title = cal["title"] if cal else "Календарь"
    draw.text((pad, header_y), cal_title, fill=TEXT, font=font_title)

    subtitle = cal.get("description", "Ближайшие события") if cal else "Ближайшие события"
    if len(subtitle) > 70:
        subtitle = subtitle[:67] + "..."
    draw.text((pad, header_y + 105), subtitle, fill=HINT, font=font_subtitle)

    # Медовая линия-разделитель
    sep_y = header_y + 180
    _gradient_rect(
        img,
        (pad, sep_y, pad + 600, sep_y + 3),
        (255, 193, 7, 180),
        (255, 193, 7, 0),
        horizontal=True,
    )

    # ── Карточки событий ──
    card_top = sep_y + 40
    card_h = 260
    card_gap = 24
    card_radius = 28
    strip_w = 8

    if not entries:
        empty_y = card_top + 120
        draw.text(
            (WIDTH // 2 - 200, empty_y),
            "Нет ближайших событий",
            fill=HINT,
            font=font_event_title,
        )
    else:
        for i, entry in enumerate(entries):
            y = card_top + i * (card_h + card_gap)
            if y + card_h > HEIGHT - 120:
                break

            color = _auto_color(entry.get("tags"), entry.get("priority", 3))

            # Фон карточки
            _rounded_rect(
                draw,
                [pad, y, WIDTH - pad, y + card_h],
                card_radius,
                fill=CARD_BG,
                outline=CARD_BORDER,
                width=2,
            )

            # Цветная полоска слева (скруглённая)
            _rounded_rect(
                draw,
                [pad, y, pad + strip_w, y + card_h],
                4,
                fill=color,
            )

            tx = pad + strip_w + 48

            # Дата и время
            start_at = entry.get("start_at")
            if start_at:
                if isinstance(start_at, str):
                    dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
                else:
                    dt = start_at

                if entry.get("all_day"):
                    time_text = _format_date(dt) + "    весь день"
                else:
                    time_text = _format_date(dt) + "   " + _format_time(dt)
                    if entry.get("end_at"):
                        end = entry["end_at"]
                        if isinstance(end, str):
                            end = datetime.fromisoformat(end.replace("Z", "+00:00"))
                        time_text += " — " + _format_time(end)

                draw.text((tx, y + 28), time_text, fill=HINT, font=font_event_time)

            # Заголовок
            title = entry.get("title", "")
            if len(title) > 60:
                title = title[:57] + "..."
            draw.text((tx, y + 85), title, fill=TEXT, font=font_event_title)

            # Теги
            tags = entry.get("tags", [])
            if tags:
                tag_x = tx
                for tag in tags[:4]:
                    tc = TAG_COLORS.get(tag.lower(), HINT)
                    bbox = font_tag.getbbox(tag)
                    tw = bbox[2] - bbox[0] + 32
                    th = bbox[3] - bbox[1] + 16
                    tag_y = y + 165

                    _rounded_rect(
                        draw,
                        [tag_x, tag_y, tag_x + tw, tag_y + th],
                        12,
                        outline=(*tc, 140),
                        width=2,
                    )
                    draw.text((tag_x + 16, tag_y + 6), tag, fill=tc, font=font_tag)
                    tag_x += tw + 16

            # Индикатор приоритета (медовая точка справа)
            priority = entry.get("priority", 3)
            if priority >= 4:
                dot_x = WIDTH - pad - 80
                dot_y = y + card_h // 2 - 14
                draw.ellipse(
                    [dot_x, dot_y, dot_x + 28, dot_y + 28],
                    fill=color,
                )

    # ── Нижняя полоса ──
    footer_y = HEIGHT - 100
    # Градиентная линия
    _gradient_rect(
        img,
        (pad, footer_y - 20, WIDTH - pad, footer_y - 17),
        (255, 193, 7, 60),
        (255, 193, 7, 0),
        horizontal=True,
    )
    # Текст футера
    draw.text((pad, footer_y), "Открыть в Mini App", fill=ACCENT, font=font_footer)
    draw.text(
        (pad + font_footer.getbbox("Открыть в Mini App")[2] + 24, footer_y + 8),
        "Telegram MCP",
        fill=HINT,
        font=font_footer_sm,
    )

    # Нижняя градиентная полоса
    _gradient_rect(
        img,
        (0, HEIGHT - 6, WIDTH, HEIGHT),
        (255, 143, 0, 160),
        (255, 193, 7, 160),
        horizontal=True,
    )

    # Конвертируем в RGB для PNG
    result = Image.new("RGB", (WIDTH, HEIGHT), BG[:3])
    result.paste(img, mask=img.split()[3])

    buf = io.BytesIO()
    result.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
