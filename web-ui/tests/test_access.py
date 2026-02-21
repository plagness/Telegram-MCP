"""Тесты контроля доступа: check_page_access, grant/revoke, get_accessible_pages."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_DSN", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("PUBLIC_URL", "https://test.example.com")

from app.services.access import (
    check_page_access,
    get_access_reasons,
    get_user_roles,
    group_pages_for_hub,
    filter_pages_by_chat,
)


# ── Хелперы для создания фейковых страниц ────────────────────────────


def _page(config: dict | None = None, **kw) -> dict:
    """Создать фейковую страницу для тестов."""
    return {"id": 1, "slug": "test", "page_type": "page", "config": config or {}, **kw}


# ── check_page_access (синхронные кейсы, без БД) ─────────────────────


@pytest.mark.asyncio
async def test_public_no_rules():
    """Страница без access_rules — публичная, доступна всем."""
    page = _page()
    assert await check_page_access(12345, page) is True


@pytest.mark.asyncio
async def test_public_explicit():
    """access_rules.public: true — доступна всем."""
    page = _page({"access_rules": {"public": True}})
    assert await check_page_access(12345, page) is True


@pytest.mark.asyncio
async def test_allowed_users_match():
    """user_id в allowed_users → доступ есть."""
    page = _page({"access_rules": {"allowed_users": [100, 200, 300]}})
    assert await check_page_access(200, page) is True


@pytest.mark.asyncio
async def test_allowed_users_no_match():
    """user_id НЕ в allowed_users, нет других правил → нет доступа."""
    page = _page({"access_rules": {"allowed_users": [100, 200]}})
    # check_page_access проверяет роли и чаты через БД — без БД вернёт False
    # Мокаем get_user_roles и is_chat_member не нужно — allowed_roles/chats пусты
    assert await check_page_access(999, page) is False


@pytest.mark.asyncio
async def test_legacy_allowed_users():
    """Обратная совместимость: config.allowed_users (без access_rules)."""
    page = _page({"allowed_users": [100, 200]})
    assert await check_page_access(100, page) is True
    assert await check_page_access(999, page) is False


# ── get_access_reasons ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_access_reasons_public():
    """Публичная страница — причина 'public'."""
    page = _page({"access_rules": {"public": True}})
    reasons = await get_access_reasons(1, page)
    assert "public" in reasons


@pytest.mark.asyncio
async def test_access_reasons_no_rules():
    """Нет правил — причина 'public (no rules)'."""
    page = _page()
    reasons = await get_access_reasons(1, page)
    assert "public (no rules)" in reasons


@pytest.mark.asyncio
async def test_access_reasons_allowed_users():
    """User в allowed_users."""
    page = _page({"access_rules": {"allowed_users": [42]}})
    reasons = await get_access_reasons(42, page)
    assert "allowed_users" in reasons


# ── group_pages_for_hub ──────────────────────────────────────────────


def test_group_pages_chat():
    """Страницы с allowed_chats группируются по чатам."""
    pages = [
        _page({"access_rules": {"allowed_chats": [-100123]}}, slug="a"),
        _page({"access_rules": {"allowed_chats": [-100123]}}, slug="b"),
        _page({"access_rules": {"allowed_chats": [-100456]}}, slug="c"),
    ]
    groups = group_pages_for_hub(pages)
    chat_groups = [g for g in groups if g["type"] == "chat"]
    assert len(chat_groups) == 2


def test_group_pages_system():
    """Страницы с системными ролями → группа 'system'."""
    pages = [
        _page({"access_rules": {"allowed_roles": ["project_owner"]}}, slug="sys1"),
    ]
    groups = group_pages_for_hub(pages)
    system_groups = [g for g in groups if g["type"] == "system"]
    assert len(system_groups) == 1
    assert len(system_groups[0]["pages"]) == 1


def test_group_pages_public():
    """Страницы без правил → группа 'public'."""
    pages = [
        _page(slug="pub1"),
        _page({"access_rules": {"public": True}}, slug="pub2"),
    ]
    groups = group_pages_for_hub(pages)
    public_groups = [g for g in groups if g["type"] == "public"]
    assert len(public_groups) == 1
    assert len(public_groups[0]["pages"]) == 2


# ── filter_pages_by_chat ────────────────────────────────────────────


def test_filter_pages_by_chat():
    """Фильтрация страниц по chat_id."""
    pages = [
        _page({"access_rules": {"allowed_chats": [-100123]}}, slug="a"),
        _page({"access_rules": {"allowed_chats": [-100456]}}, slug="b"),
        _page({"access_rules": {"allowed_chats": [-100123, -100456]}}, slug="c"),
    ]
    result = filter_pages_by_chat(pages, "-100123")
    slugs = {p["slug"] for p in result}
    assert slugs == {"a", "c"}


def test_filter_pages_by_chat_empty():
    """Нет страниц для чата → пустой список."""
    pages = [
        _page({"access_rules": {"allowed_chats": [-100123]}}, slug="a"),
    ]
    result = filter_pages_by_chat(pages, "-100999")
    assert result == []


# ── grant_access / revoke_access (unit-тесты логики) ────────────────


def test_grant_revoke_logic():
    """Проверка логики формирования access_rules (без БД)."""
    # Имитируем grant: добавление user_id в список
    rules: dict = {}
    users = list(rules.get("allowed_users") or [])
    users.append(42)
    rules["allowed_users"] = users
    assert 42 in rules["allowed_users"]

    # Имитируем revoke
    users.remove(42)
    rules["allowed_users"] = users
    assert 42 not in rules["allowed_users"]


def test_grant_role_logic():
    """Проверка логики grant роли."""
    rules: dict = {}
    roles = list(rules.get("allowed_roles") or [])
    roles.append("tester")
    rules["allowed_roles"] = roles
    assert "tester" in rules["allowed_roles"]

    # Не дублировать
    if "tester" not in roles:
        roles.append("tester")
    assert roles.count("tester") == 1


def test_grant_chat_logic():
    """Проверка логики grant чата."""
    rules: dict = {}
    chats = list(rules.get("allowed_chats") or [])
    chats.append(-100123)
    rules["allowed_chats"] = chats
    assert -100123 in rules["allowed_chats"]
