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
        metadata: z.record(z.any()).optional().describe("Произвольные метаданные"),
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
        metadata: z.record(z.any()).optional().describe("Новые метаданные"),
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
  ];
}
