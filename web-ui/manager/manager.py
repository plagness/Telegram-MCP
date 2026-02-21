"""Page Manager — standalone dashboard для мониторинга и управления страницами.

Запуск: python -m manager.manager
Порт: 8088
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from jinja2 import Environment, FileSystemLoader

# Подключаем модули из основного приложения
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.db import close_pool, execute, fetch_all, fetch_one, init_pool
from app.handlers.registry import discover_handlers, get_all_handlers, list_types
from app.services.access import check_page_access, get_access_reasons, get_page_access_summary

settings = get_settings()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent

# Все системные роли для симуляции доступа
ALL_ROLES = ["project_owner", "backend_dev", "tester", "moderator"]

# Внутренний URL tgweb для прокси (localhost:8443 через hostPort)
TGWEB_INTERNAL = os.environ.get("TGWEB_INTERNAL", "https://localhost:8443")

# Кэш bot_token из таблицы bots
_bot_token_cache: str | None = None


async def _get_bot_token() -> str:
    """Получить bot token из таблицы bots (кэшируется)."""
    global _bot_token_cache
    if _bot_token_cache:
        return _bot_token_cache
    row = await fetch_one(
        "SELECT token FROM bots WHERE is_active = TRUE ORDER BY id LIMIT 1"
    )
    if row and row["token"]:
        _bot_token_cache = row["token"]
        return _bot_token_cache
    # Fallback: env
    return settings.get_bot_token()


def _generate_init_data(bot_token: str, user_id: int,
                        first_name: str = "Manager",
                        last_name: str = "",
                        username: str = "manager") -> str:
    """Генерирует валидный Telegram initData для прокси-превью."""
    user = {"id": user_id, "first_name": first_name}
    if last_name:
        user["last_name"] = last_name
    if username:
        user["username"] = username
    auth_date = str(int(time.time()))
    user_json = json.dumps(user, separators=(",", ":"))
    data = {"auth_date": auth_date, "user": user_json}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()
    hash_val = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    data["hash"] = hash_val
    return urllib.parse.urlencode(data)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл: пул БД + handler discovery + httpx."""
    await init_pool()
    discover_handlers()
    app.state.http = httpx.AsyncClient(verify=False, timeout=15.0, follow_redirects=True)

    # Дефолтный пользователь для preview (первый project_owner)
    row = await fetch_one(
        """
        SELECT u.user_id, u.first_name, u.last_name, u.username
        FROM users u
        JOIN user_roles ur ON ur.user_id::text = u.user_id
        WHERE ur.role = 'project_owner'
        LIMIT 1
        """,
    )
    if row:
        app.state.preview_user = {
            "user_id": int(row["user_id"]),
            "first_name": row["first_name"] or "User",
            "last_name": row["last_name"] or "",
            "username": row["username"] or "",
        }
    else:
        app.state.preview_user = {
            "user_id": 0,
            "first_name": "Manager",
            "last_name": "",
            "username": "manager",
        }

    logger.info(
        "Page Manager started (proxy → %s, preview as %s)",
        TGWEB_INTERNAL, app.state.preview_user["user_id"],
    )
    yield
    await app.state.http.aclose()
    await close_pool()


app = FastAPI(title="Page Manager", version="1.0", lifespan=lifespan)

templates = Environment(
    loader=FileSystemLoader(str(BASE_DIR / "templates")),
    autoescape=True,
)


# ── Preview Proxy ────────────────────────────────────────────────────────
# Проксирует tgweb через manager — решает проблемы DNS/SSL/CORS для iframe


@app.get("/preview/{path:path}")
async def preview_proxy(path: str, request: Request):
    """Прокси к tgweb для iframe preview.

    Автоматически генерирует initData для текущего preview-пользователя,
    чтобы tgweb рендерил полные страницы (не base.html).
    """
    # Генерируем initData для авторизации
    bot_token = await _get_bot_token()
    pu = app.state.preview_user
    init_data = _generate_init_data(
        bot_token, pu["user_id"],
        first_name=pu["first_name"],
        last_name=pu["last_name"],
        username=pu["username"],
    )

    # Собираем URL с initData
    params = dict(request.query_params)
    params["initData"] = init_data
    qs = urllib.parse.urlencode(params)
    url = f"{TGWEB_INTERNAL}/{path}?{qs}"

    # Передаём X-Init-Data header (для JSON API которые проверяют через header)
    proxy_headers = {"X-Init-Data": init_data}

    try:
        r = await app.state.http.get(url, headers=proxy_headers)
    except Exception as exc:
        return Response(
            content=f"<pre>Proxy error: {exc}</pre>",
            media_type="text/html",
            status_code=502,
        )

    content_type = r.headers.get("content-type", "application/octet-stream")

    if "text/html" in content_type:
        text = r.text
        # Переписываем абсолютные пути чтобы ресурсы тоже шли через прокси
        text = re.sub(r'(href|src|action)="/', r'\1="/preview/', text)
        # Переписываем fetch/XHR URL'ы из JS (базовые случаи)
        text = text.replace("'/api/", "'/preview/api/")
        text = text.replace('"/api/', '"/preview/api/')

        # Инжектим fetch/XHR interceptor перед всеми скриптами —
        # перехватывает ВСЕ runtime запросы из iframe и направляет через /preview/
        # Также инжектим initData в фейковый Telegram.WebApp чтобы JS-код мог
        # передавать X-Init-Data header в API-запросах
        escaped_init_data = init_data.replace("\\", "\\\\").replace("'", "\\'")
        interceptor = f"""<script data-manager-interceptor>
(function(){{
  var _initData = '{escaped_init_data}';
  // Перехватываем fetch: все абсолютные пути / → /preview/
  var _f = window.fetch;
  window.fetch = function(url, opts) {{
    if (typeof url === 'string' && url.charAt(0) === '/' && url.indexOf('/preview/') !== 0) {{
      url = '/preview' + url;
    }}
    return _f.call(this, url, opts);
  }};
  // Перехватываем XMLHttpRequest.open
  var _xo = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {{
    if (typeof url === 'string' && url.charAt(0) === '/' && url.indexOf('/preview/') !== 0) {{
      url = '/preview' + url;
    }}
    return _xo.apply(this, [method, url].concat([].slice.call(arguments, 2)));
  }};
  // Фейковый Telegram WebApp с реальным initData для авторизации API-запросов
  window.Telegram = {{ WebApp: {{
    ready: function(){{}}, expand: function(){{}}, close: function(){{}},
    initData: _initData,
    initDataUnsafe: {{ user: {{ id: {pu["user_id"]} }} }},
    themeParams: {{}}, colorScheme: 'dark',
    BackButton: {{ show: function(){{}}, hide: function(){{}}, onClick: function(){{}}, offClick: function(){{}}, isVisible: false }},
    MainButton: {{ show: function(){{}}, hide: function(){{}}, onClick: function(){{}}, offClick: function(){{}}, setText: function(){{}}, isVisible: false }},
    HapticFeedback: {{
      impactOccurred: function(){{}}, notificationOccurred: function(){{}}, selectionChanged: function(){{}}
    }},
    isFullscreen: false, requestFullscreen: function(){{}}, exitFullscreen: function(){{}},
    openInvoice: function(u,cb){{ if(cb) cb('cancelled'); }},
    platform: 'manager_preview', version: '8.0'
  }}}};
  // Перехватываем навигацию window.location.replace
  var _lr = window.location.replace.bind(window.location);
  window.location.replace = function(url) {{
    if (typeof url === 'string' && url.charAt(0) === '/' && url.indexOf('/preview/') !== 0) {{
      url = '/preview' + url;
    }}
    return _lr(url);
  }};
}})();
</script>"""
        text = text.replace("<head>", "<head>" + interceptor, 1)
        return HTMLResponse(content=text, status_code=r.status_code)

    # POST-запросы тоже проксируем (для форм)
    return Response(
        content=r.content,
        media_type=content_type,
        status_code=r.status_code,
    )


# POST-прокси для форм и API-вызовов из iframe
@app.post("/preview/{path:path}")
async def preview_proxy_post(path: str, request: Request):
    """Прокси POST-запросов из iframe."""
    bot_token = await _get_bot_token()
    pu = app.state.preview_user
    init_data = _generate_init_data(
        bot_token, pu["user_id"],
        first_name=pu["first_name"],
        last_name=pu["last_name"],
        username=pu["username"],
    )

    url = f"{TGWEB_INTERNAL}/{path}"
    qs = str(request.query_params)
    if qs:
        url += "?" + qs

    body = await request.body()
    headers = {"X-Init-Data": init_data}
    ct = request.headers.get("content-type")
    if ct:
        headers["Content-Type"] = ct

    try:
        r = await app.state.http.post(url, content=body, headers=headers)
    except Exception as exc:
        return Response(
            content=json.dumps({"error": str(exc)}),
            media_type="application/json",
            status_code=502,
        )

    return Response(
        content=r.content,
        media_type=r.headers.get("content-type", "application/json"),
        status_code=r.status_code,
    )


# PUT/DELETE прокси для developer/marketplace API
@app.put("/preview/{path:path}")
@app.delete("/preview/{path:path}")
async def preview_proxy_mutate(path: str, request: Request):
    """Прокси PUT/DELETE-запросов из iframe."""
    bot_token = await _get_bot_token()
    pu = app.state.preview_user
    init_data = _generate_init_data(
        bot_token, pu["user_id"],
        first_name=pu["first_name"],
        last_name=pu["last_name"],
        username=pu["username"],
    )

    url = f"{TGWEB_INTERNAL}/{path}"
    qs = str(request.query_params)
    if qs:
        url += "?" + qs

    body = await request.body()
    headers = {"X-Init-Data": init_data}
    ct = request.headers.get("content-type")
    if ct:
        headers["Content-Type"] = ct

    try:
        r = await app.state.http.request(
            request.method, url, content=body, headers=headers,
        )
    except Exception as exc:
        return Response(
            content=json.dumps({"error": str(exc)}),
            media_type="application/json",
            status_code=502,
        )

    return Response(
        content=r.content,
        media_type=r.headers.get("content-type", "application/json"),
        status_code=r.status_code,
    )


# Catch-all для корня preview (hub)
@app.get("/preview")
@app.get("/preview/")
async def preview_root(request: Request):
    """Прокси к tgweb hub."""
    return await preview_proxy("", request)


# ── Dashboard ────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Главная: все страницы + handler'ы + summary."""
    pages = await fetch_all(
        """
        SELECT id, slug, title, page_type, is_active, created_at, updated_at,
               config, creator_id, bot_id
        FROM web_pages
        ORDER BY updated_at DESC NULLS LAST
        """,
    )

    # Статистика
    total = len(pages)
    active = sum(1 for p in pages if p.get("is_active"))
    by_type: dict[str, int] = {}
    for p in pages:
        pt = p.get("page_type", "unknown")
        by_type[pt] = by_type.get(pt, 0) + 1

    handlers = get_all_handlers()

    html = templates.get_template("dashboard.html").render(
        pages=pages,
        total=total,
        active=active,
        by_type=sorted(by_type.items(), key=lambda x: -x[1]),
        handlers=handlers,
        handler_types=list_types(),
        active_nav="dashboard",
    )
    return HTMLResponse(html)


@app.get("/pages/{slug}", response_class=HTMLResponse)
async def page_detail(slug: str, request: Request):
    """Детали страницы: config, access, history."""
    page = await fetch_one(
        "SELECT * FROM web_pages WHERE slug = %s",
        [slug],
    )
    if not page:
        return HTMLResponse("<h1>404 — Page not found</h1>", status_code=404)

    access = await get_page_access_summary(page)

    handler = get_all_handlers().get(page["page_type"])
    handler_info = handler.describe() if handler else None

    html = templates.get_template("page_detail.html").render(
        page=page,
        access=access,
        handler_info=handler_info,
    )
    return HTMLResponse(html)


@app.get("/access", response_class=HTMLResponse)
async def access_matrix(request: Request):
    """Матрица доступов: какие страницы кому доступны."""
    filter_type = request.query_params.get("type")
    filter_value = request.query_params.get("value")

    pages = await fetch_all(
        """
        SELECT id, slug, title, page_type, is_active, config
        FROM web_pages
        WHERE is_active = TRUE
        ORDER BY slug
        """,
    )

    # Собираем все chat_id для bulk-загрузки названий
    all_chat_ids: set[int] = set()
    for p in pages:
        rules = (p.get("config") or {}).get("access_rules") or {}
        for cid in rules.get("allowed_chats") or []:
            all_chat_ids.add(int(cid))

    chat_titles: dict[int, str] = {}
    if all_chat_ids:
        rows = await fetch_all(
            "SELECT chat_id, title FROM chats WHERE chat_id = ANY(%s)",
            [[str(c) for c in all_chat_ids]],
        )
        chat_titles = {abs(int(r["chat_id"])): r["title"] or str(r["chat_id"]) for r in rows}

    # Подсчёт cached members по чатам
    chat_member_counts: dict[int, int] = {}
    if all_chat_ids:
        rows = await fetch_all(
            """
            SELECT chat_id, COUNT(DISTINCT user_id) AS cnt
            FROM chat_members
            WHERE chat_id = ANY(%s) AND status NOT IN ('left', 'kicked')
            GROUP BY chat_id
            """,
            [[str(c) for c in all_chat_ids]],
        )
        chat_member_counts = {abs(int(r["chat_id"])): r["cnt"] for r in rows}

    # Обогащаем страницы
    public_count = role_count = chat_count = user_count = 0
    enriched = []
    for p in pages:
        rules = (p.get("config") or {}).get("access_rules") or {}
        p["_public"] = rules.get("public", False) or not rules
        p["_roles"] = rules.get("allowed_roles") or []
        p["_chats"] = [abs(int(c)) for c in (rules.get("allowed_chats") or [])]
        p["_users"] = rules.get("allowed_users") or []
        p["_chat_titles"] = chat_titles

        # Resolved members
        if p["_chats"]:
            p["_resolved_members"] = sum(chat_member_counts.get(c, 0) for c in p["_chats"])
        else:
            p["_resolved_members"] = None

        # Counters
        if p["_public"]:
            public_count += 1
        if p["_roles"]:
            role_count += 1
        if p["_chats"]:
            chat_count += 1
        if p["_users"]:
            user_count += 1

        # Фильтрация
        if filter_type == "role" and filter_value:
            if filter_value not in p["_roles"]:
                continue
        elif filter_type == "chat" and filter_value:
            if int(filter_value) not in p["_chats"] and abs(int(filter_value)) not in p["_chats"]:
                continue

        enriched.append(p)

    html = templates.get_template("access.html").render(
        pages=enriched,
        public_count=public_count,
        role_count=role_count,
        chat_count=chat_count,
        user_count=user_count,
        filter_type=filter_type,
        filter_value=filter_value,
        all_roles=ALL_ROLES,
        active_nav="access",
    )
    return HTMLResponse(html)


@app.get("/health", response_class=HTMLResponse)
async def health_view(request: Request):
    """Health Monitor: статус всех активных страниц."""
    pages = await fetch_all(
        """
        SELECT id, slug, title, page_type, is_active
        FROM web_pages
        WHERE is_active = TRUE
        ORDER BY slug
        """,
    )

    # Последний health-статус каждой страницы
    health_rows = await fetch_all(
        """
        SELECT DISTINCT ON (slug)
            slug, status, status_code, response_time_ms, error_message, checked_at
        FROM web_page_health
        ORDER BY slug, checked_at DESC
        """,
    )
    health_map = {r["slug"]: r for r in health_rows}

    healthy = errors = 0
    total_ms = 0
    ms_count = 0

    for p in pages:
        h = health_map.get(p["slug"])
        if h:
            p["_health_status"] = h["status"]
            p["_status_code"] = h["status_code"]
            p["_response_ms"] = h["response_time_ms"]
            p["_error"] = h["error_message"]
            p["_checked_at"] = str(h["checked_at"])[:19] if h["checked_at"] else None
            if h["status"] == "ok":
                healthy += 1
            else:
                errors += 1
            if h["response_time_ms"] is not None:
                total_ms += h["response_time_ms"]
                ms_count += 1
        else:
            p["_health_status"] = "unknown"
            p["_status_code"] = None
            p["_response_ms"] = None
            p["_error"] = None
            p["_checked_at"] = None

    # Сортируем: ошибки первыми, потом unknown, потом ok
    status_order = {"error": 0, "timeout": 1, "access_denied": 2, "unknown": 3, "ok": 4}
    pages.sort(key=lambda p: status_order.get(p["_health_status"], 3))

    last_check = None
    if health_rows:
        last_check = str(max(r["checked_at"] for r in health_rows if r["checked_at"]))[:19]

    html = templates.get_template("health.html").render(
        pages=pages,
        total=len(pages),
        healthy=healthy,
        errors=errors,
        avg_ms=round(total_ms / ms_count) if ms_count else 0,
        last_check=last_check,
        active_nav="health",
    )
    return HTMLResponse(html)


@app.get("/types", response_class=HTMLResponse)
async def page_types(request: Request):
    """Все зарегистрированные handler'ы и типы."""
    handlers = get_all_handlers()
    types = list_types()

    html = templates.get_template("types.html").render(
        handlers=handlers,
        types=types,
        active_nav="types",
    )
    return HTMLResponse(html)


# ── JSON API (для AJAX) ─────────────────────────────────────────────────


@app.get("/api/stats")
async def api_stats():
    """Быстрая статистика для дашборда."""
    row = await fetch_one(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE is_active) AS active,
            COUNT(DISTINCT page_type) AS types_used
        FROM web_pages
        """,
    )
    return {
        "total": row["total"] if row else 0,
        "active": row["active"] if row else 0,
        "types_used": row["types_used"] if row else 0,
        "types_registered": len(get_all_handlers()),
    }


@app.get("/api/health/{slug}")
async def api_health_slug(slug: str):
    """Последний health-check для страницы (для AJAX в preview)."""
    row = await fetch_one(
        """
        SELECT status, status_code, response_time_ms, error_message, checked_at
        FROM web_page_health
        WHERE slug = %s
        ORDER BY checked_at DESC
        LIMIT 1
        """,
        [slug],
    )
    if not row:
        return {"slug": slug, "status": None, "status_code": None,
                "response_time_ms": None, "error_message": None, "checked_at": None}
    return {
        "slug": slug,
        "status": row["status"],
        "status_code": row["status_code"],
        "response_time_ms": row["response_time_ms"],
        "error_message": row["error_message"],
        "checked_at": str(row["checked_at"]) if row["checked_at"] else None,
    }


@app.get("/api/users/search")
async def api_users_search(q: str = ""):
    """Поиск пользователей по имени, username или ID."""
    q = q.strip()
    if not q:
        return {"users": []}

    if q.isdigit():
        # Поиск по user_id (точное или prefix)
        rows = await fetch_all(
            """
            SELECT u.user_id, u.first_name, u.last_name, u.username,
                   COALESCE(r.roles, '{}') AS roles
            FROM users u
            LEFT JOIN LATERAL (
                SELECT array_agg(role) AS roles FROM user_roles WHERE user_id::text = u.user_id
            ) r ON true
            WHERE u.user_id LIKE %s
            ORDER BY u.last_seen_at DESC NULLS LAST
            LIMIT 10
            """,
            [q + "%"],
        )
    else:
        # Поиск по имени или username (case-insensitive)
        pattern = "%" + q + "%"
        rows = await fetch_all(
            """
            SELECT u.user_id, u.first_name, u.last_name, u.username,
                   COALESCE(r.roles, '{}') AS roles
            FROM users u
            LEFT JOIN LATERAL (
                SELECT array_agg(role) AS roles FROM user_roles WHERE user_id::text = u.user_id
            ) r ON true
            WHERE u.first_name ILIKE %s
               OR u.last_name ILIKE %s
               OR u.username ILIKE %s
            ORDER BY u.last_seen_at DESC NULLS LAST
            LIMIT 10
            """,
            [pattern, pattern, pattern],
        )

    return {
        "users": [
            {
                "user_id": int(r["user_id"]),
                "name": " ".join(filter(None, [r["first_name"], r["last_name"]])),
                "username": r["username"],
                "roles": list(r["roles"]) if r["roles"] else [],
            }
            for r in rows
        ],
    }


@app.get("/api/simulate")
async def api_simulate(user_id: int, roles: str = ""):
    """Симуляция доступа: проверить какие страницы доступны пользователю."""
    pages = await fetch_all(
        """
        SELECT id, slug, title, page_type, config
        FROM web_pages
        WHERE is_active = TRUE
        ORDER BY slug
        """,
    )

    result_pages = []
    accessible = 0
    blocked = 0

    for page in pages:
        has_access = await check_page_access(user_id, page)
        reasons = await get_access_reasons(user_id, page)

        result_pages.append({
            "slug": page["slug"],
            "has_access": has_access,
            "reasons": reasons,
        })
        if has_access:
            accessible += 1
        else:
            blocked += 1

    return {
        "user_id": user_id,
        "roles": roles.split(",") if roles else [],
        "accessible": accessible,
        "blocked": blocked,
        "pages": result_pages,
    }


@app.post("/api/preview-user")
async def api_set_preview_user(request: Request):
    """Установить пользователя для preview iframe."""
    body = await request.json()
    user_id = body.get("user_id")
    if not user_id:
        return JSONResponse({"ok": False, "error": "user_id required"}, status_code=400)

    row = await fetch_one(
        "SELECT user_id, first_name, last_name, username FROM users WHERE user_id = %s",
        [str(user_id)],
    )
    if row:
        app.state.preview_user = {
            "user_id": int(row["user_id"]),
            "first_name": row["first_name"] or "User",
            "last_name": row["last_name"] or "",
            "username": row["username"] or "",
        }
    else:
        app.state.preview_user = {
            "user_id": int(user_id),
            "first_name": "User",
            "last_name": "",
            "username": "",
        }

    global _bot_token_cache
    _bot_token_cache = None  # Сбросить кэш на случай смены бота

    return {
        "ok": True,
        "preview_user": app.state.preview_user,
    }


@app.get("/api/preview-user")
async def api_get_preview_user():
    """Текущий пользователь preview."""
    return app.state.preview_user


@app.post("/api/pages/{slug}/toggle")
async def api_toggle_page(slug: str):
    """Переключить is_active для страницы."""
    page = await fetch_one(
        "SELECT id, is_active FROM web_pages WHERE slug = %s",
        [slug],
    )
    if not page:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)

    new_state = not page["is_active"]
    await execute(
        "UPDATE web_pages SET is_active = %s, updated_at = NOW() WHERE slug = %s",
        [new_state, slug],
    )
    return {"ok": True, "slug": slug, "is_active": new_state}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MANAGER_PORT", "8088"))
    uvicorn.run(app, host="0.0.0.0", port=port)
