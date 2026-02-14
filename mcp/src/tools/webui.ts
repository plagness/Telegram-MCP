/**
 * MCP инструменты для web-ui модуля.
 *
 * Управление веб-страницами, индивидуальными ссылками и ответами на формы.
 */

import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "webui.create_page",
      description: "Создать веб-страницу (page, survey или prediction). Возвращает slug и URL.",
      parameters: z.object({
        slug: z.string().max(100).describe("Уникальный идентификатор страницы (URL-путь)"),
        title: z.string().max(200),
        page_type: z.enum(["page", "survey", "prediction"]).default("page"),
        config: z.record(z.any()).optional().describe("Конфигурация страницы (поля формы, кнопки и т.д.)"),
        template: z.string().optional().describe("Имя HTML-шаблона"),
        creator_id: z.number().int().optional(),
        bot_id: z.number().int().optional(),
        event_id: z.number().int().optional().describe("ID события для prediction-страниц"),
        expires_at: z.string().optional().describe("ISO datetime истечения"),
      }),
      execute: async (params) => apiRequest("/v1/web/pages", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "webui.list_pages",
      description: "Список веб-страниц с фильтрацией по типу и боту.",
      parameters: z.object({
        page_type: z.enum(["page", "survey", "prediction"]).optional(),
        bot_id: z.number().int().optional(),
        limit: z.number().int().min(1).max(500).optional().default(50),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.page_type) qs.set("page_type", params.page_type);
        if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(`/v1/web/pages?${qs.toString()}`);
      },
    },
    {
      name: "webui.create_link",
      description: "Создать индивидуальную ссылку на страницу. Возвращает URL с уникальным токеном.",
      parameters: z.object({
        slug: z.string().describe("Slug страницы"),
        user_id: z.number().int().optional().describe("ID пользователя Telegram"),
        chat_id: z.number().int().optional().describe("ID чата"),
        metadata: z.record(z.any()).optional().describe("Произвольные метаданные"),
        expires_at: z.string().optional().describe("ISO datetime истечения ссылки"),
      }),
      execute: async (params) => apiRequest(`/v1/web/pages/${params.slug}/links`, {
        method: "POST",
        body: JSON.stringify({
          user_id: params.user_id,
          chat_id: params.chat_id,
          metadata: params.metadata,
          expires_at: params.expires_at,
        }),
      }),
    },
    {
      name: "webui.get_submissions",
      description: "Получить ответы на форму/предсказания для страницы.",
      parameters: z.object({
        slug: z.string().describe("Slug страницы"),
        limit: z.number().int().min(1).max(500).optional().default(100),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(`/v1/web/pages/${params.slug}/submissions?${qs.toString()}`);
      },
    },
    {
      name: "webui.create_prediction",
      description: "Создать prediction-страницу для события (shortcut). Автоматически формирует slug predict-{event_id}.",
      parameters: z.object({
        event_id: z.number().int().describe("ID события из predictions"),
        title: z.string().max(200).optional().describe("Заголовок (если не указан — берётся из события)"),
        bot_id: z.number().int().optional(),
        creator_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/web/pages", {
        method: "POST",
        body: JSON.stringify({
          slug: `predict-${params.event_id}`,
          title: params.title || `Предсказание #${params.event_id}`,
          page_type: "prediction",
          event_id: params.event_id,
          bot_id: params.bot_id,
          creator_id: params.creator_id,
        }),
      }),
    },
    {
      name: "webui.create_survey",
      description: "Создать опросник (shortcut). Принимает поля формы в config.fields.",
      parameters: z.object({
        slug: z.string().max(100),
        title: z.string().max(200),
        description: z.string().optional(),
        fields: z.array(z.object({
          name: z.string(),
          label: z.string(),
          type: z.enum(["text", "textarea", "number", "select", "radio", "checkbox"]),
          required: z.boolean().optional(),
          options: z.array(z.any()).optional().describe("Варианты для select/radio"),
          placeholder: z.string().optional(),
          min: z.number().optional(),
          max: z.number().optional(),
        })).min(1),
        bot_id: z.number().int().optional(),
        creator_id: z.number().int().optional(),
        expires_at: z.string().optional(),
      }),
      execute: async (params) => apiRequest("/v1/web/pages", {
        method: "POST",
        body: JSON.stringify({
          slug: params.slug,
          title: params.title,
          page_type: "survey",
          config: {
            description: params.description,
            fields: params.fields,
          },
          bot_id: params.bot_id,
          creator_id: params.creator_id,
          expires_at: params.expires_at,
        }),
      }),
    },

    // ── Роли и доступ ──────────────────────────────────────
    {
      name: "webui.list_roles",
      description: "Список глобальных ролей. Фильтр по user_id или role.",
      parameters: z.object({
        user_id: z.number().int().optional().describe("Фильтр по Telegram user ID"),
        role: z.string().optional().describe("Фильтр по названию роли"),
        limit: z.number().int().min(1).max(500).optional().default(100),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.user_id !== undefined) qs.set("user_id", String(params.user_id));
        if (params.role) qs.set("role", params.role);
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(`/v1/web/roles?${qs.toString()}`);
      },
    },
    {
      name: "webui.grant_role",
      description: "Назначить глобальную роль пользователю (project_owner, tester, backend_dev, moderator).",
      parameters: z.object({
        user_id: z.number().int().describe("Telegram user ID"),
        role: z.string().describe("Роль: project_owner, tester, backend_dev, moderator"),
        granted_by: z.number().int().optional().describe("Кто назначил (user_id)"),
        note: z.string().optional().describe("Комментарий"),
      }),
      execute: async (params) => apiRequest("/v1/web/roles", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "webui.revoke_role",
      description: "Отозвать глобальную роль у пользователя.",
      parameters: z.object({
        user_id: z.number().int().describe("Telegram user ID"),
        role: z.string().describe("Роль для отзыва"),
      }),
      execute: async (params) => apiRequest(`/v1/web/roles/${params.user_id}/${params.role}`, {
        method: "DELETE",
      }),
    },
    {
      name: "webui.check_access",
      description: "Проверить доступ пользователя к странице. Возвращает has_access и причины.",
      parameters: z.object({
        user_id: z.number().int().describe("Telegram user ID"),
        slug: z.string().describe("Slug страницы"),
      }),
      execute: async (params) => apiRequest("/v1/web/roles/check-access", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
  ];
}
