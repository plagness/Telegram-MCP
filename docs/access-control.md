# Access Control — Design Doc

## Статус: Планирование

Документ описывает будущую архитектуру доступов для Telegram Mini App.

---

## Текущая реализация (v1 — Фаза 8)

Простая проверка `config.allowed_users` в конфиге страницы:

```json
{
  "allowed_users": [123456789]
}
```

- Проверка через `validate_init_data()` + сравнение `user.id` с массивом
- Используется в page_type `"infra"` — прокси-эндпоинт `/p/{slug}/infra/data`
- Проверка на бэкенде (не UI-only) — initData передаётся в `X-Init-Data` header

---

## Два уровня доступов (будущее)

### 1. Chat-based доступ

Пользователь — участник чата → видит страницы привязанные к этому чату.

**Уже есть:**
- Таблица `chat_members(chat_id, user_id, status)` — обновляется из Telegram updates
- Функция `_check_chat_admin(user_id, chat_id)` в `render.py`
- Поле `web_pages.config` может хранить `chat_id` привязку

**Примеры:**
- Чат "Ковенант" → страницы с шутками → доступ только участникам чата
- Чат "Трейдинг" → страницы с аналитикой → доступ участникам

**Нужно:**
- `config.allowed_chats: [-1001234567890]` — список chat_id
- Проверка: `user_id IN (SELECT user_id FROM chat_members WHERE chat_id = ANY(allowed_chats))`

### 2. Глобальные роли

Роли не привязанные к чатам — проектные/системные.

**Примеры ролей:**
| Роль | Описание | Доступы |
|------|----------|---------|
| `project_owner` | Владелец проекта | Все страницы, infra, admin |
| `tester` | Тестировщик | Отладочные страницы, логи |
| `backend_dev` | Бэкенд-разработчик | Infra, API docs, метрики |
| `moderator` | Модератор чатов | Календари, контент |

**Нужна новая таблица:**
```sql
CREATE TABLE IF NOT EXISTS user_roles (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    role TEXT NOT NULL,
    granted_by BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, role)
);
CREATE INDEX idx_user_roles_user ON user_roles(user_id);
```

---

## Единый формат access_rules

Расширение `web_pages.config`:

```json
{
  "access_rules": {
    "allowed_users": [123456789],
    "allowed_roles": ["project_owner", "tester"],
    "allowed_chats": [-1001234567890],
    "public": false
  }
}
```

**Логика (OR):** доступ если выполняется ХОТЯ БЫ одно:
- `public: true` → доступно всем
- `user_id IN allowed_users`
- Пользователь имеет роль из `allowed_roles`
- Пользователь — участник чата из `allowed_chats`

---

## Единая функция проверки

```python
async def check_page_access(user_id: int, page: dict) -> bool:
    """Единая точка проверки доступа к странице."""
    rules = page.get("config", {}).get("access_rules", {})

    # Обратная совместимость: старый формат allowed_users
    if not rules and page.get("config", {}).get("allowed_users"):
        return user_id in page["config"]["allowed_users"]

    if rules.get("public"):
        return True
    if user_id in rules.get("allowed_users", []):
        return True
    if rules.get("allowed_roles"):
        user_roles = await get_user_roles(user_id)
        if user_roles & set(rules["allowed_roles"]):
            return True
    if rules.get("allowed_chats"):
        member = await is_chat_member(user_id, rules["allowed_chats"])
        if member:
            return True
    return False
```

---

## Главный экран Mini App

Сейчас `/` (index) — пустой base.html с редиректом по start_param.

**Будущее:** Главный экран показывает все доступные страницы для текущего пользователя:
- Авторизация через initData
- Запрос всех активных `web_pages`
- Фильтрация по `check_page_access()`
- Отображение карточками: иконка, название, тип, описание
- Группировка: по чату / по роли / личные

---

## Миграция

1. Текущий `config.allowed_users` продолжает работать (обратная совместимость)
2. Новые страницы используют `config.access_rules`
3. `check_page_access()` поддерживает оба формата
4. Миграция: одноразовый скрипт переносит `allowed_users` → `access_rules.allowed_users`
