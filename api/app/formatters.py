"""
Универсальная система форматирования для Telegram-сообщений.

Включает:
- Прогресс-бары (несколько стилей)
- Эмодзи-градации (health, status, priority, zone, sentiment)
- Блоки состояния железа (CPU, RAM, GPU, Disk, Network)
- Утилиты форматирования (время, длительность, размеры)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

# ═══════════════════════════════════════════════════════════════════════════════
# ПРОГРЕСС-БАРЫ
# ═══════════════════════════════════════════════════════════════════════════════

ProgressStyle = Literal[
    "classic",  # [####....] 40%
    "blocks",   # ▓▓▓▓░░░░░░ 40%
    "circles",  # ●●●●○○○○○○ 40%
    "squares",  # ■■■■□□□□□□ 40%
    "dots",     # ⣿⣿⣿⣿⣀⣀⣀⣀⣀⣀ 40%
    "minimal",  # 4/10
    "percent",  # 40%
    "fraction", # 4 из 10
]


def progress_bar(
    current: int | float,
    total: int | float,
    width: int = 10,
    style: ProgressStyle = "classic",
    show_percent: bool = True,
    show_numbers: bool = False,
) -> str:
    """
    Универсальный прогресс-бар с несколькими стилями.

    Args:
        current: Текущее значение
        total: Максимальное значение
        width: Ширина бара (количество символов)
        style: Стиль отображения
        show_percent: Показывать процент
        show_numbers: Показывать числа (current/total)

    Returns:
        Отформатированный прогресс-бар

    Examples:
        >>> progress_bar(4, 10, style="classic")
        '[####......] 40%'

        >>> progress_bar(7, 10, style="blocks", show_numbers=True)
        '▓▓▓▓▓▓▓░░░ 70% (7/10)'

        >>> progress_bar(3, 8, style="circles")
        '●●●●○○○○ 37%'
    """
    if total <= 0:
        total = 1
    current = max(0, min(current, total))

    # Вычисляем заполненность
    filled = int(round((current / total) * width))
    empty = width - filled
    percent = int((current / total) * 100)

    # Генерируем бар в зависимости от стиля
    if style == "classic":
        bar = "[" + ("#" * filled) + ("." * empty) + "]"
    elif style == "blocks":
        bar = ("▓" * filled) + ("░" * empty)
    elif style == "circles":
        bar = ("●" * filled) + ("○" * empty)
    elif style == "squares":
        bar = ("■" * filled) + ("□" * empty)
    elif style == "dots":
        bar = ("⣿" * filled) + ("⣀" * empty)
    elif style == "minimal":
        return f"{int(current)}/{int(total)}"
    elif style == "percent":
        return f"{percent}%"
    elif style == "fraction":
        return f"{int(current)} из {int(total)}"
    else:
        bar = ("█" * filled) + ("░" * empty)

    # Добавляем процент и числа
    result = bar
    if show_percent:
        result += f" {percent}%"
    if show_numbers:
        result += f" ({int(current)}/{int(total)})"

    return result


def spinner_frame(index: int, style: Literal["braille", "dots", "arrow", "box"] = "braille") -> str:
    """
    Анимированный спиннер (возвращает один кадр).

    Args:
        index: Индекс кадра (увеличивайте при каждом обновлении)
        style: Стиль спиннера

    Returns:
        Символ текущего кадра

    Examples:
        >>> spinner_frame(0, "braille")
        '⠋'
        >>> spinner_frame(5, "arrow")
        '↗'
    """
    frames = {
        "braille": ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
        "dots": ["⠁", "⠂", "⠄", "⡀", "⢀", "⠠", "⠐", "⠈"],
        "arrow": ["|", "/", "-", "\\"],
        "box": ["◰", "◳", "◲", "◱"],
    }
    sequence = frames.get(style, frames["braille"])
    return sequence[index % len(sequence)]


# ═══════════════════════════════════════════════════════════════════════════════
# ЭМОДЗИ-ГРАДАЦИИ
# ═══════════════════════════════════════════════════════════════════════════════


def emoji_health(value: float, max_value: float = 100.0) -> str:
    """
    Эмодзи для здоровья/HP (градация по цвету сердца).

    Args:
        value: Текущее значение (0-max_value)
        max_value: Максимальное значение

    Returns:
        Эмодзи (💚💛🧡❤️💔)

    Examples:
        >>> emoji_health(95)
        '💚'
        >>> emoji_health(45)
        '🧡'
    """
    percent = (value / max_value) * 100 if max_value > 0 else 0

    if percent >= 80:
        return "💚"  # Зелёное сердце (80-100%)
    elif percent >= 60:
        return "💛"  # Жёлтое сердце (60-80%)
    elif percent >= 40:
        return "🧡"  # Оранжевое сердце (40-60%)
    elif percent >= 20:
        return "❤️"  # Красное сердце (20-40%)
    else:
        return "💔"  # Разбитое сердце (<20%)


def emoji_status(value: float, max_value: float = 100.0, inverted: bool = False) -> str:
    """
    Эмодзи для статуса (градация по цвету круга).

    Args:
        value: Текущее значение
        max_value: Максимальное значение
        inverted: Инвертировать (высокое значение = плохо)

    Returns:
        Эмодзи (🟢🟡🟠🔴⚫)

    Examples:
        >>> emoji_status(85)
        '🟢'
        >>> emoji_status(85, inverted=True)
        '🔴'
    """
    percent = (value / max_value) * 100 if max_value > 0 else 0

    if inverted:
        if percent >= 80:
            return "🔴"  # Красный (критично)
        elif percent >= 60:
            return "🟠"  # Оранжевый (высоко)
        elif percent >= 40:
            return "🟡"  # Жёлтый (средне)
        elif percent >= 20:
            return "🟢"  # Зелёный (низко)
        else:
            return "⚫"  # Чёрный (отлично)
    else:
        if percent >= 80:
            return "🟢"  # Зелёный (отлично)
        elif percent >= 60:
            return "🟡"  # Жёлтый (хорошо)
        elif percent >= 40:
            return "🟠"  # Оранжевый (средне)
        elif percent >= 20:
            return "🔴"  # Красный (плохо)
        else:
            return "⚫"  # Чёрный (критично)


def emoji_priority(level: int | str) -> str:
    """
    Эмодзи для приоритета.

    Args:
        level: Уровень приоритета (1-5 или "low"/"medium"/"high"/"critical")

    Returns:
        Эмодзи (⬇️➡️⬆️🔺🔴)

    Examples:
        >>> emoji_priority(5)
        '🔴'
        >>> emoji_priority("high")
        '🔺'
    """
    if isinstance(level, str):
        mapping = {
            "lowest": "⬇️",
            "low": "➡️",
            "medium": "⬆️",
            "high": "🔺",
            "critical": "🔴",
        }
        return mapping.get(level.lower(), "➡️")

    if level >= 5:
        return "🔴"  # Критический
    elif level >= 4:
        return "🔺"  # Высокий
    elif level >= 3:
        return "⬆️"  # Средний
    elif level >= 2:
        return "➡️"  # Низкий
    else:
        return "⬇️"  # Минимальный


def emoji_zone(zone: str) -> str:
    """
    Эмодзи для зоны/категории.

    Args:
        zone: Название зоны

    Returns:
        Эмодзи

    Examples:
        >>> emoji_zone("market")
        '📈'
        >>> emoji_zone("network")
        '🌐'
    """
    mapping = {
        "market": "📈",
        "mesh": "📡",
        "network": "🌐",
        "risk": "⚠️",
        "cpu": "🔥",
        "ram": "💾",
        "gpu": "🎮",
        "disk": "💿",
        "temperature": "🌡️",
        "power": "⚡",
        "battery": "🔋",
    }
    return mapping.get(zone.lower(), "❓")


def emoji_sentiment(value: float) -> str:
    """
    Эмодзи для сентимента (-1.0 до 1.0).

    Args:
        value: Значение сентимента

    Returns:
        Эмодзи (😡😠😐🙂😊)

    Examples:
        >>> emoji_sentiment(-0.8)
        '😡'
        >>> emoji_sentiment(0.6)
        '😊'
    """
    if value >= 0.6:
        return "😊"  # Очень позитивно
    elif value >= 0.2:
        return "🙂"  # Позитивно
    elif value >= -0.2:
        return "😐"  # Нейтрально
    elif value >= -0.6:
        return "😠"  # Негативно
    else:
        return "😡"  # Очень негативно


def emoji_boolean(value: bool, true_emoji: str = "✅", false_emoji: str = "❌") -> str:
    """
    Эмодзи для булевого значения.

    Args:
        value: Булево значение
        true_emoji: Эмодзи для True
        false_emoji: Эмодзи для False

    Returns:
        Эмодзи

    Examples:
        >>> emoji_boolean(True)
        '✅'
        >>> emoji_boolean(False, "🟢", "🔴")
        '🔴'
    """
    return true_emoji if value else false_emoji


def emoji_connection(status: str) -> str:
    """
    Эмодзи для статуса подключения.

    Args:
        status: Статус ("online", "offline", "degraded", "unknown")

    Returns:
        Эмодзи (🟢🔴🟡⚪)

    Examples:
        >>> emoji_connection("online")
        '🟢'
        >>> emoji_connection("degraded")
        '🟡'
    """
    mapping = {
        "online": "🟢",
        "offline": "🔴",
        "degraded": "🟡",
        "maintenance": "🟠",
        "unknown": "⚪",
    }
    return mapping.get(status.lower(), "⚪")


# ═══════════════════════════════════════════════════════════════════════════════
# БЛОКИ СОСТОЯНИЯ ЖЕЛЕЗА
# ═══════════════════════════════════════════════════════════════════════════════


def format_hardware_cpu(
    usage: float,
    cores: int | None = None,
    freq: float | None = None,
    temp: float | None = None,
    style: ProgressStyle = "blocks",
) -> str:
    """
    Форматирование информации о CPU.

    Args:
        usage: Загрузка CPU (0-100%)
        cores: Количество ядер
        freq: Частота в GHz
        temp: Температура в °C
        style: Стиль прогресс-бара

    Returns:
        Отформатированная строка

    Examples:
        >>> format_hardware_cpu(45.2, cores=8, freq=3.6, temp=58)
        '🔥 CPU: ▓▓▓▓░░░░░░ 45% | 8 cores @ 3.6GHz | 🌡️ 58°C'
    """
    parts = [f"{emoji_zone('cpu')} CPU:"]

    # Прогресс-бар загрузки
    bar = progress_bar(usage, 100, width=10, style=style, show_percent=True, show_numbers=False)
    parts.append(bar)

    # Характеристики
    specs = []
    if cores:
        specs.append(f"{cores} cores")
    if freq:
        specs.append(f"@ {freq:.1f}GHz")
    if specs:
        parts.append(" | " + " ".join(specs))

    # Температура
    if temp is not None:
        temp_emoji = emoji_status(temp, max_value=100, inverted=True) if temp > 60 else "🌡️"
        parts.append(f" | {temp_emoji} {temp:.0f}°C")

    return "".join(parts)


def format_hardware_ram(
    used: float,
    total: float,
    cached: float | None = None,
    style: ProgressStyle = "blocks",
) -> str:
    """
    Форматирование информации о RAM.

    Args:
        used: Использовано GB
        total: Всего GB
        cached: Кешировано GB
        style: Стиль прогресс-бара

    Returns:
        Отформатированная строка

    Examples:
        >>> format_hardware_ram(12.5, 32.0, cached=4.2)
        '💾 RAM: ▓▓▓░░░░░░░ 39% | 12.5/32.0 GB | cache 4.2 GB'
    """
    parts = [f"{emoji_zone('ram')} RAM:"]

    # Прогресс-бар
    bar = progress_bar(used, total, width=10, style=style, show_percent=True, show_numbers=False)
    parts.append(bar)

    # Размеры
    parts.append(f" | {used:.1f}/{total:.1f} GB")

    # Кеш
    if cached is not None:
        parts.append(f" | cache {cached:.1f} GB")

    return "".join(parts)


def format_hardware_gpu(
    usage: float,
    memory_used: float | None = None,
    memory_total: float | None = None,
    temp: float | None = None,
    name: str | None = None,
    style: ProgressStyle = "blocks",
) -> str:
    """
    Форматирование информации о GPU.

    Args:
        usage: Загрузка GPU (0-100%)
        memory_used: Использовано VRAM GB
        memory_total: Всего VRAM GB
        temp: Температура °C
        name: Название GPU
        style: Стиль прогресс-бара

    Returns:
        Отформатированная строка

    Examples:
        >>> format_hardware_gpu(78, memory_used=6.2, memory_total=8.0, temp=72, name="RTX 3070")
        '🎮 GPU (RTX 3070): ▓▓▓▓▓▓▓░░░ 78% | VRAM 6.2/8.0 GB | 🔴 72°C'
    """
    label = f"{emoji_zone('gpu')} GPU"
    if name:
        label += f" ({name})"
    parts = [label + ":"]

    # Прогресс-бар загрузки
    bar = progress_bar(usage, 100, width=10, style=style, show_percent=True, show_numbers=False)
    parts.append(bar)

    # VRAM
    if memory_used is not None and memory_total is not None:
        parts.append(f" | VRAM {memory_used:.1f}/{memory_total:.1f} GB")

    # Температура
    if temp is not None:
        temp_emoji = emoji_status(temp, max_value=100, inverted=True) if temp > 70 else "🌡️"
        parts.append(f" | {temp_emoji} {temp:.0f}°C")

    return "".join(parts)


def format_hardware_disk(
    used: float,
    total: float,
    read_speed: float | None = None,
    write_speed: float | None = None,
    style: ProgressStyle = "blocks",
) -> str:
    """
    Форматирование информации о диске.

    Args:
        used: Использовано GB
        total: Всего GB
        read_speed: Скорость чтения MB/s
        write_speed: Скорость записи MB/s
        style: Стиль прогресс-бара

    Returns:
        Отформатированная строка

    Examples:
        >>> format_hardware_disk(450, 1000, read_speed=250, write_speed=180)
        '💿 Disk: ▓▓▓▓░░░░░░ 45% | 450/1000 GB | R: 250 MB/s W: 180 MB/s'
    """
    parts = [f"{emoji_zone('disk')} Disk:"]

    # Прогресс-бар
    bar = progress_bar(used, total, width=10, style=style, show_percent=True, show_numbers=False)
    parts.append(bar)

    # Размеры
    parts.append(f" | {used:.0f}/{total:.0f} GB")

    # Скорость I/O
    if read_speed is not None or write_speed is not None:
        io_parts = []
        if read_speed is not None:
            io_parts.append(f"R: {read_speed:.0f} MB/s")
        if write_speed is not None:
            io_parts.append(f"W: {write_speed:.0f} MB/s")
        parts.append(" | " + " ".join(io_parts))

    return "".join(parts)


def format_hardware_network(
    rx_speed: float,
    tx_speed: float,
    rx_total: float | None = None,
    tx_total: float | None = None,
    latency: float | None = None,
) -> str:
    """
    Форматирование информации о сети.

    Args:
        rx_speed: Скорость приёма MB/s
        tx_speed: Скорость передачи MB/s
        rx_total: Всего принято GB
        tx_total: Всего передано GB
        latency: Задержка ms

    Returns:
        Отформатированная строка

    Examples:
        >>> format_hardware_network(12.5, 3.2, rx_total=450, tx_total=120, latency=25)
        '🌐 Network: ↓ 12.5 MB/s ↑ 3.2 MB/s | Total: ↓ 450 GB ↑ 120 GB | ⏱️ 25 ms'
    """
    parts = [f"{emoji_zone('network')} Network:"]

    # Скорость
    parts.append(f"↓ {rx_speed:.1f} MB/s ↑ {tx_speed:.1f} MB/s")

    # Всего трафика
    if rx_total is not None or tx_total is not None:
        total_parts = []
        if rx_total is not None:
            total_parts.append(f"↓ {rx_total:.0f} GB")
        if tx_total is not None:
            total_parts.append(f"↑ {tx_total:.0f} GB")
        parts.append(" | Total: " + " ".join(total_parts))

    # Задержка
    if latency is not None:
        parts.append(f" | ⏱️ {latency:.0f} ms")

    return "".join(parts)


def format_hardware_summary(
    devices: list[dict[str, Any]],
    title: str = "Hardware Status",
) -> str:
    """
    Сводка по всем устройствам.

    Args:
        devices: Список устройств с характеристиками
        title: Заголовок

    Returns:
        HTML-форматированная сводка

    Examples:
        >>> devices = [
        ...     {"name": "server1", "cpu": 45, "ram_used": 12, "ram_total": 32, "status": "online"},
        ...     {"name": "server2", "cpu": 78, "ram_used": 28, "ram_total": 32, "status": "online"},
        ... ]
        >>> format_hardware_summary(devices)
        '<b>Hardware Status</b>\\n\\n🟢 server1: CPU 45% | RAM 12/32 GB\\n🟢 server2: CPU 78% | RAM 28/32 GB'
    """
    lines = [f"<b>{title}</b>", ""]

    for device in devices:
        name = device.get("name", "unknown")
        status = device.get("status", "unknown")
        status_emoji = emoji_connection(status)

        parts = [f"{status_emoji} {name}:"]

        # CPU
        if "cpu" in device:
            parts.append(f"CPU {device['cpu']:.0f}%")

        # RAM
        if "ram_used" in device and "ram_total" in device:
            parts.append(f"RAM {device['ram_used']:.0f}/{device['ram_total']:.0f} GB")

        # GPU
        if "gpu" in device:
            parts.append(f"GPU {device['gpu']:.0f}%")

        # Температура
        if "temp" in device:
            temp = device["temp"]
            temp_emoji = emoji_status(temp, max_value=100, inverted=True) if temp > 60 else "🌡️"
            parts.append(f"{temp_emoji} {temp:.0f}°C")

        lines.append(" | ".join(parts))

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# УТИЛИТЫ ФОРМАТИРОВАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════


def format_duration(seconds: float) -> str:
    """
    Форматирование длительности.

    Args:
        seconds: Секунды

    Returns:
        Отформатированная строка

    Examples:
        >>> format_duration(45)
        '45s'
        >>> format_duration(3665)
        '1h01m'
        >>> format_duration(90125)
        '1d01h'
    """
    if seconds < 60:
        return f"{int(seconds)}s"

    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    if days > 0:
        return f"{days}d{hours:02d}h"
    elif hours > 0:
        return f"{hours}h{minutes:02d}m"
    else:
        return f"{minutes}m{sec:02d}s"


def format_timestamp(
    dt: datetime | None,
    format_str: str = "%H:%M:%S",
    timezone_info: timezone | None = None,
) -> str:
    """
    Форматирование времени.

    Args:
        dt: Время (datetime)
        format_str: Формат вывода
        timezone_info: Часовой пояс

    Returns:
        Отформатированное время

    Examples:
        >>> from datetime import datetime
        >>> dt = datetime(2025, 2, 6, 14, 30, 45)
        >>> format_timestamp(dt)
        '14:30:45'
    """
    if dt is None:
        return "-"

    if timezone_info and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    if timezone_info:
        dt = dt.astimezone(timezone_info)

    return dt.strftime(format_str)


def format_bytes(size: float) -> str:
    """
    Форматирование размера файла.

    Args:
        size: Размер в байтах

    Returns:
        Отформатированная строка

    Examples:
        >>> format_bytes(1024)
        '1.0 KB'
        >>> format_bytes(1536000)
        '1.5 MB'
        >>> format_bytes(5368709120)
        '5.0 GB'
    """
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    return f"{size:.1f} {units[unit_index]}"


def trim_text(text: str, limit: int, suffix: str = "...") -> str:
    """
    Обрезка текста с многоточием.

    Args:
        text: Исходный текст
        limit: Максимальная длина
        suffix: Суффикс (по умолчанию "...")

    Returns:
        Обрезанный текст

    Examples:
        >>> trim_text("Very long text that needs to be trimmed", 20)
        'Very long text th...'
    """
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(suffix))] + suffix


def escape_html(text: str) -> str:
    """
    Экранирование HTML-символов для Telegram.

    Args:
        text: Исходный текст

    Returns:
        Экранированный текст

    Examples:
        >>> escape_html("<script>alert('xss')</script>")
        '&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;'
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
