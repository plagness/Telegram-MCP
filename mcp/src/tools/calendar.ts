/**
 * MCP инструменты для модуля календаря.
 *
 * Управление календарями, событиями, задачами и напоминаниями.
 * Поддержка цепочек событий, повторений, массовых операций и истории изменений.
 */

import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    /* ── 1. calendar.create ──────────────────────────────────────── */
    {
      name: "calendar.create",
      description:
        "Создать новый календарь. Привязка к чату (chat_id) позволяет админам чата редактировать через Mini App.",
      parameters: z.object({
        slug: z.string().max(100).describe("Уникальный идентификатор календаря (URL-путь)"),
        title: z.string().max(200).describe("Название календаря"),
        description: z.string().optional().describe("Описание календаря"),
        owner_id: z.number().int().optional().describe("ID владельца"),
        chat_id: z
          .union([z.string(), z.number()])
          .optional()
          .describe("ID чата Telegram для привязки"),
        bot_id: z.number().int().optional().describe("ID бота"),
        timezone: z.string().optional().default("UTC").describe("Часовой пояс (по умолчанию UTC)"),
        is_public: z.boolean().optional().default(true).describe("Публичный календарь"),
        config: z.record(z.any()).optional().describe("Произвольная конфигурация"),
      }),
      execute: async (params) =>
        apiRequest("/v1/calendar/calendars", {
          method: "POST",
          body: JSON.stringify(params),
        }),
    },

    /* ── 2. calendar.list ────────────────────────────────────────── */
    {
      name: "calendar.list",
      description: "Список календарей с фильтрацией.",
      parameters: z.object({
        owner_id: z.number().int().optional().describe("Фильтр по владельцу"),
        chat_id: z
          .union([z.string(), z.number()])
          .optional()
          .describe("Фильтр по чату"),
        bot_id: z.number().int().optional().describe("Фильтр по боту"),
        limit: z.number().int().min(1).max(500).optional().default(50),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.owner_id !== undefined) qs.set("owner_id", String(params.owner_id));
        if (params.chat_id !== undefined) qs.set("chat_id", String(params.chat_id));
        if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(`/v1/calendar/calendars?${qs.toString()}`);
      },
    },

    /* ── 3. calendar.create_entry ────────────────────────────────── */
    {
      name: "calendar.create_entry",
      description:
        "Создать запись в календаре (событие, задачу, напоминание). parent_id связывает с предыдущим событием в цепочке. created_by — автор записи. ai_actionable — должна ли нейронка реагировать на это событие.",
      parameters: z.object({
        calendar_id: z.number().int().describe("ID календаря"),
        title: z.string().max(300).describe("Заголовок записи"),
        description: z.string().optional().describe("Подробное описание"),
        start_at: z.string().describe("Дата/время начала (ISO 8601)"),
        end_at: z.string().optional().describe("Дата/время окончания (ISO 8601)"),
        all_day: z.boolean().optional().default(false).describe("Событие на весь день"),
        status: z
          .enum(["active", "done", "cancelled", "archived"])
          .optional()
          .default("active")
          .describe("Статус записи"),
        priority: z
          .number()
          .int()
          .min(1)
          .max(5)
          .optional()
          .default(3)
          .describe("Приоритет от 1 (низкий) до 5 (критический)"),
        emoji: z.string().optional().describe("Эмодзи для визуального обозначения"),
        icon: z
          .string()
          .optional()
          .describe("Simple Icons slug для SVG-иконки (bitcoin, telegram, claude...). Проверить доступность: icons.resolve"),
        color: z.string().optional().describe("Цвет записи (hex или название)"),
        tags: z.array(z.string()).optional().describe("Теги для фильтрации"),
        attachments: z
          .array(
            z.object({
              type: z.string().describe("Тип вложения (file, image, link)"),
              url: z.string().describe("URL вложения"),
              title: z.string().optional().describe("Название вложения"),
            }),
          )
          .optional()
          .describe("Вложения"),
        metadata: z.record(z.any()).optional().describe("Произвольные метаданные (widgets: [{label, value, icon}])"),
        series_id: z.string().optional().describe("ID серии повторяющихся событий"),
        repeat: z
          .enum(["daily", "weekly", "biweekly", "monthly", "yearly", "weekdays"])
          .optional()
          .describe("Правило повторения"),
        repeat_until: z.string().optional().describe("Повторять до (ISO date)"),
        position: z.number().int().optional().default(0).describe("Позиция сортировки"),
        parent_id: z
          .number()
          .int()
          .optional()
          .describe("ID родительской записи (для цепочки событий)"),
        created_by: z.string().optional().describe("Автор записи"),
        ai_actionable: z
          .boolean()
          .optional()
          .default(true)
          .describe("Должна ли нейронка реагировать на событие"),
        performed_by: z.string().optional().describe("Кто выполнил действие"),
      }),
      execute: async (params) =>
        apiRequest("/v1/calendar/entries", {
          method: "POST",
          body: JSON.stringify(params),
        }),
    },

    /* ── 4. calendar.list_entries ────────────────────────────────── */
    {
      name: "calendar.list_entries",
      description:
        "Получить записи календаря с фильтрацией по дате, тегам, статусу, приоритету. Используй start и end для диапазона дат.",
      parameters: z.object({
        calendar_id: z.number().int().describe("ID календаря"),
        start: z.string().optional().describe("Начало диапазона (ISO date)"),
        end: z.string().optional().describe("Конец диапазона (ISO date)"),
        tags: z.array(z.string()).optional().describe("Фильтр по тегам"),
        status: z
          .enum(["active", "done", "cancelled", "archived"])
          .optional()
          .describe("Фильтр по статусу"),
        priority: z.number().int().min(1).max(5).optional().describe("Фильтр по приоритету"),
        ai_actionable: z.boolean().optional().describe("Фильтр по ai_actionable"),
        series_id: z.string().optional().describe("Фильтр по серии"),
        entry_type: z
          .enum(["event", "task", "trigger", "monitor", "vote", "routine"])
          .optional()
          .describe("Фильтр по типу записи"),
        trigger_status: z
          .enum(["pending", "scheduled", "fired", "success", "failed", "skipped", "expired"])
          .optional()
          .describe("Фильтр по статусу триггера"),
        source_module: z.string().optional().describe("Фильтр по модулю-источнику"),
        limit: z.number().int().min(1).max(500).optional().default(50),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        qs.set("calendar_id", String(params.calendar_id));
        if (params.start) qs.set("start", params.start);
        if (params.end) qs.set("end", params.end);
        if (params.tags?.length) qs.set("tags", params.tags.join(","));
        if (params.status) qs.set("status", params.status);
        if (params.priority !== undefined) qs.set("priority", String(params.priority));
        if (params.ai_actionable !== undefined)
          qs.set("ai_actionable", String(params.ai_actionable));
        if (params.series_id) qs.set("series_id", params.series_id);
        if (params.entry_type) qs.set("entry_type", params.entry_type);
        if (params.trigger_status) qs.set("trigger_status", params.trigger_status);
        if (params.source_module) qs.set("source_module", params.source_module);
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(`/v1/calendar/entries?${qs.toString()}`);
      },
    },

    /* ── 5. calendar.get_entry ───────────────────────────────────── */
    {
      name: "calendar.get_entry",
      description: "Получить полные данные записи, включая дочерние связанные записи.",
      parameters: z.object({
        entry_id: z.number().int().describe("ID записи"),
      }),
      execute: async (params) =>
        apiRequest(`/v1/calendar/entries/${params.entry_id}`),
    },

    /* ── 6. calendar.get_chain ───────────────────────────────────── */
    {
      name: "calendar.get_chain",
      description:
        "Получить цепочку связанных событий (от корневого до последнего). Полезно для анализа серии связанных мероприятий.",
      parameters: z.object({
        entry_id: z.number().int().describe("ID любой записи из цепочки"),
      }),
      execute: async (params) =>
        apiRequest(`/v1/calendar/entries/${params.entry_id}/chain`),
    },

    /* ── 7. calendar.update_entry ────────────────────────────────── */
    {
      name: "calendar.update_entry",
      description: "Обновить поля записи. Указывай только изменяемые поля.",
      parameters: z.object({
        entry_id: z.number().int().describe("ID записи"),
        title: z.string().max(300).optional().describe("Новый заголовок"),
        description: z.string().optional().describe("Новое описание"),
        start_at: z.string().optional().describe("Новое время начала (ISO 8601)"),
        end_at: z.string().optional().describe("Новое время окончания (ISO 8601)"),
        all_day: z.boolean().optional().describe("Событие на весь день"),
        status: z
          .enum(["active", "done", "cancelled", "archived"])
          .optional()
          .describe("Новый статус"),
        priority: z
          .number()
          .int()
          .min(1)
          .max(5)
          .optional()
          .describe("Новый приоритет (1-5)"),
        emoji: z.string().optional().describe("Эмодзи"),
        icon: z
          .string()
          .optional()
          .describe("Simple Icons slug для SVG-иконки (bitcoin, telegram, claude...)"),
        color: z.string().optional().describe("Новый цвет"),
        tags: z.array(z.string()).optional().describe("Новые теги (заменяют старые)"),
        attachments: z
          .array(
            z.object({
              type: z.string(),
              url: z.string(),
              title: z.string().optional(),
            }),
          )
          .optional()
          .describe("Новые вложения"),
        metadata: z.record(z.any()).optional().describe("Новые метаданные (widgets: [{label, value, icon}])"),
        series_id: z.string().optional().describe("ID серии"),
        repeat: z
          .enum(["daily", "weekly", "biweekly", "monthly", "yearly", "weekdays"])
          .optional()
          .describe("Правило повторения"),
        repeat_until: z.string().optional().describe("Повторять до (ISO date)"),
        position: z.number().int().optional().describe("Позиция сортировки"),
        parent_id: z.number().int().optional().describe("ID родительской записи"),
        ai_actionable: z.boolean().optional().describe("Должна ли нейронка реагировать"),
        performed_by: z.string().optional().describe("Кто выполнил действие"),
      }),
      execute: async (params) => {
        const { entry_id, ...body } = params;
        return apiRequest(`/v1/calendar/entries/${entry_id}`, {
          method: "PUT",
          body: JSON.stringify(body),
        });
      },
    },

    /* ── 8. calendar.move_entry ──────────────────────────────────── */
    {
      name: "calendar.move_entry",
      description: "Переместить запись на новое время/дату.",
      parameters: z.object({
        entry_id: z.number().int().describe("ID записи"),
        start_at: z.string().describe("Новое время начала (ISO 8601)"),
        end_at: z.string().optional().describe("Новое время окончания (ISO 8601)"),
        performed_by: z.string().optional().describe("Кто выполнил действие"),
      }),
      execute: async (params) => {
        const { entry_id, ...body } = params;
        return apiRequest(`/v1/calendar/entries/${entry_id}/move`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      },
    },

    /* ── 9. calendar.set_status ──────────────────────────────────── */
    {
      name: "calendar.set_status",
      description:
        "Быстро изменить статус записи (завершить, отменить, архивировать).",
      parameters: z.object({
        entry_id: z.number().int().describe("ID записи"),
        status: z
          .enum(["active", "done", "cancelled", "archived"])
          .describe("Новый статус"),
        performed_by: z.string().optional().describe("Кто выполнил действие"),
      }),
      execute: async (params) => {
        const { entry_id, ...body } = params;
        return apiRequest(`/v1/calendar/entries/${entry_id}/status`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      },
    },

    /* ── 10. calendar.delete_entry ───────────────────────────────── */
    {
      name: "calendar.delete_entry",
      description: "Удалить запись из календаря.",
      parameters: z.object({
        entry_id: z.number().int().describe("ID записи"),
        performed_by: z.string().optional().describe("Кто выполнил действие"),
      }),
      execute: async (params) => {
        const { entry_id, ...body } = params;
        return apiRequest(`/v1/calendar/entries/${entry_id}`, {
          method: "DELETE",
          body: JSON.stringify(body),
        });
      },
    },

    /* ── 11. calendar.entry_history ──────────────────────────────── */
    {
      name: "calendar.entry_history",
      description:
        "Посмотреть историю изменений записи (кто и когда менял).",
      parameters: z.object({
        entry_id: z.number().int().describe("ID записи"),
        limit: z.number().int().min(1).max(500).optional().default(50),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(
          `/v1/calendar/entries/${params.entry_id}/history?${qs.toString()}`,
        );
      },
    },

    /* ── 12. calendar.bulk_create ────────────────────────────────── */
    {
      name: "calendar.bulk_create",
      description:
        "Создать несколько записей за раз (до 100). Полезно для заполнения расписания.",
      parameters: z.object({
        calendar_id: z.number().int().describe("ID календаря"),
        entries: z
          .array(
            z.object({
              title: z.string().max(300),
              description: z.string().optional(),
              start_at: z.string().describe("ISO 8601"),
              end_at: z.string().optional(),
              all_day: z.boolean().optional().default(false),
              status: z.enum(["active", "done", "cancelled", "archived"]).optional().default("active"),
              priority: z.number().int().min(1).max(5).optional().default(3),
              emoji: z.string().optional(),
              icon: z.string().optional().describe("Simple Icons slug"),
              color: z.string().optional(),
              tags: z.array(z.string()).optional(),
              attachments: z
                .array(
                  z.object({
                    type: z.string(),
                    url: z.string(),
                    title: z.string().optional(),
                  }),
                )
                .optional(),
              metadata: z.record(z.any()).optional(),
              series_id: z.string().optional(),
              repeat: z
                .enum(["daily", "weekly", "biweekly", "monthly", "yearly", "weekdays"])
                .optional(),
              repeat_until: z.string().optional(),
              position: z.number().int().optional().default(0),
              parent_id: z.number().int().optional(),
              created_by: z.string().optional(),
              ai_actionable: z.boolean().optional().default(true),
              performed_by: z.string().optional(),
            }),
          )
          .min(1)
          .max(100)
          .describe("Массив записей для создания"),
      }),
      execute: async (params) =>
        apiRequest("/v1/calendar/entries/bulk", {
          method: "POST",
          body: JSON.stringify(params),
        }),
    },

    /* ── 13. calendar.bulk_delete ────────────────────────────────── */
    {
      name: "calendar.bulk_delete",
      description: "Удалить несколько записей за раз.",
      parameters: z.object({
        ids: z
          .array(z.number().int())
          .min(1)
          .max(100)
          .describe("Массив ID записей для удаления"),
        performed_by: z.string().optional().describe("Кто выполнил действие"),
      }),
      execute: async (params) =>
        apiRequest("/v1/calendar/entries/bulk-delete", {
          method: "POST",
          body: JSON.stringify(params),
        }),
    },

    /* ── 14. calendar.upcoming ───────────────────────────────────── */
    {
      name: "calendar.upcoming",
      description:
        "Получить ближайшие N активных событий. Полезно для создания превью или обзора.",
      parameters: z.object({
        calendar_id: z.number().int().describe("ID календаря"),
        limit: z
          .number()
          .int()
          .min(1)
          .max(100)
          .optional()
          .default(3)
          .describe("Количество ближайших событий"),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        qs.set("limit", String(params.limit));
        return apiRequest(
          `/v1/calendar/calendars/${params.calendar_id}/upcoming?${qs.toString()}`,
        );
      },
    },

    /* ── 15. calendar.get_due ──────────────────────────────────── */
    {
      name: "calendar.get_due",
      description:
        "Получить записи, готовые к исполнению (trigger_at <= сейчас, статус pending). Planner вызывает периодически, чтобы найти триггеры и мониторы для запуска.",
      parameters: z.object({
        calendar_id: z.number().int().optional().describe("Фильтр по календарю"),
        limit: z
          .number()
          .int()
          .min(1)
          .max(100)
          .optional()
          .default(10)
          .describe("Количество записей"),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.calendar_id !== undefined)
          qs.set("calendar_id", String(params.calendar_id));
        qs.set("limit", String(params.limit));
        return apiRequest(`/v1/calendar/entries/due?${qs.toString()}`);
      },
    },

    /* ── 16. calendar.fire ─────────────────────────────────────── */
    {
      name: "calendar.fire",
      description:
        "Записать результат исполнения триггера. Planner вызывает после выполнения действия, чтобы зафиксировать результат.",
      parameters: z.object({
        entry_id: z.number().int().describe("ID записи"),
        result: z.record(z.any()).describe("Результат выполнения: {status, output, error, actual_cost, ...}"),
        trigger_status: z
          .enum(["success", "failed"])
          .optional()
          .default("success")
          .describe("Итоговый статус"),
        performed_by: z.string().optional().describe("Кто выполнил"),
      }),
      execute: async (params) => {
        const { entry_id, ...body } = params;
        return apiRequest(`/v1/calendar/entries/${entry_id}/fire`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      },
    },

    /* ── 17. calendar.tick ─────────────────────────────────────── */
    {
      name: "calendar.tick",
      description:
        "Продвинуть тик монитора — увеличить счётчик, пересчитать next_tick_at. Если max_ticks достигнут, монитор завершается.",
      parameters: z.object({
        entry_id: z.number().int().describe("ID монитора"),
        result: z.record(z.any()).optional().describe("Результат текущего тика"),
        performed_by: z.string().optional().describe("Кто выполнил"),
      }),
      execute: async (params) => {
        const { entry_id, ...body } = params;
        return apiRequest(`/v1/calendar/entries/${entry_id}/tick`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      },
    },

    /* ── 18. calendar.budget ───────────────────────────────────── */
    {
      name: "calendar.budget",
      description:
        "Сводка бюджета: сумма стоимостей записей за период. Возвращает total_cost, entry_count, by_module, limit, remaining.",
      parameters: z.object({
        calendar_id: z.number().int().optional().describe("Фильтр по календарю"),
        period: z
          .enum(["day", "week", "month"])
          .optional()
          .default("day")
          .describe("Период: day ($1), week ($7), month ($20)"),
        date: z.string().optional().describe("Дата (ISO), по умолчанию = сегодня"),
        source_module: z.string().optional().describe("Фильтр по модулю-источнику"),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.calendar_id !== undefined)
          qs.set("calendar_id", String(params.calendar_id));
        qs.set("period", params.period);
        if (params.date) qs.set("date", params.date);
        if (params.source_module) qs.set("source_module", params.source_module);
        return apiRequest(`/v1/calendar/budget?${qs.toString()}`);
      },
    },

    /* ── 19. calendar.create_trigger ───────────────────────────── */
    {
      name: "calendar.create_trigger",
      description:
        "Создать одноразовый триггер — событие, которое исполнит действие в заданное время. Шорткат для create_entry с entry_type='trigger'.",
      parameters: z.object({
        calendar_id: z.number().int().describe("ID календаря"),
        title: z.string().max(300).describe("Описание триггера"),
        trigger_at: z.string().describe("Когда сработать (ISO 8601)"),
        action: z
          .record(z.any())
          .describe(
            "Определение действия: {type, module, tool, params, flags, on_success, on_failure}",
          ),
        description: z.string().optional().describe("Подробное описание"),
        emoji: z.string().optional().describe("Эмодзи"),
        icon: z
          .string()
          .optional()
          .describe("Simple Icons slug для SVG-иконки (bitcoin, telegram, claude...)"),
        priority: z
          .number()
          .int()
          .min(1)
          .max(5)
          .optional()
          .default(3)
          .describe("Приоритет (1-5)"),
        tags: z.array(z.string()).optional().describe("Теги"),
        cost_estimate: z.number().optional().default(0).describe("Оценка стоимости в USD"),
        source_module: z.string().optional().describe("Модуль-источник"),
        expires_at: z.string().optional().describe("Время протухания (ISO 8601)"),
        created_by: z.string().optional().describe("Автор"),
        performed_by: z.string().optional().describe("Кто выполнил"),
        parent_id: z.number().int().optional().describe("Родительская запись"),
        metadata: z.record(z.any()).optional().describe("Метаданные"),
      }),
      execute: async (params) => {
        const body = {
          ...params,
          entry_type: "trigger",
          start_at: params.trigger_at,
          trigger_status: "pending",
        };
        return apiRequest("/v1/calendar/entries", {
          method: "POST",
          body: JSON.stringify(body),
        });
      },
    },

    /* ── 20. calendar.create_monitor ───────────────────────────── */
    {
      name: "calendar.create_monitor",
      description:
        "Создать монитор — периодическую проверку с заданным интервалом. Planner будет вызывать tick для продвижения.",
      parameters: z.object({
        calendar_id: z.number().int().describe("ID календаря"),
        title: z.string().max(300).describe("Описание монитора"),
        start_at: z.string().describe("Начало мониторинга (ISO 8601)"),
        tick_interval: z
          .string()
          .regex(/^\d+(m|h|d)$/)
          .describe("Интервал тиков: 5m, 10m, 30m, 1h, 6h, 1d"),
        action: z
          .record(z.any())
          .describe(
            "Действие при каждом тике: {type, module, tool, params, ...}",
          ),
        description: z.string().optional().describe("Подробное описание"),
        emoji: z.string().optional().describe("Эмодзи"),
        icon: z
          .string()
          .optional()
          .describe("Simple Icons slug для SVG-иконки (bitcoin, telegram, claude...)"),
        priority: z
          .number()
          .int()
          .min(1)
          .max(5)
          .optional()
          .default(3)
          .describe("Приоритет (1-5)"),
        tags: z.array(z.string()).optional().describe("Теги"),
        cost_estimate: z.number().optional().default(0).describe("Оценка стоимости за тик (USD)"),
        source_module: z.string().optional().describe("Модуль-источник"),
        max_ticks: z
          .number()
          .int()
          .optional()
          .describe("Максимум тиков (null = безлимитно)"),
        expires_at: z.string().optional().describe("Время протухания (ISO 8601)"),
        created_by: z.string().optional().describe("Автор"),
        performed_by: z.string().optional().describe("Кто выполнил"),
        parent_id: z.number().int().optional().describe("Родительская запись"),
        metadata: z.record(z.any()).optional().describe("Метаданные"),
      }),
      execute: async (params) => {
        const body = {
          ...params,
          entry_type: "monitor",
          trigger_at: params.start_at,
          next_tick_at: params.start_at,
          trigger_status: "pending",
        };
        return apiRequest("/v1/calendar/entries", {
          method: "POST",
          body: JSON.stringify(body),
        });
      },
    },
  ];
}
