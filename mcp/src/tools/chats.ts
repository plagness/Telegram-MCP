import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для работы с чатами, callback queries и администрирования */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "chats.get",
      description: "Получить информацию о чате от Telegram API (название, тип, описание).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        return apiRequest(`/v1/chats/${params.chat_id}${qs.toString() ? `?${qs.toString()}` : ""}`);
      },
    },
    {
      name: "chats.member",
      description: "Получить статус участника чата (admin, member, restricted и т.д.).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        user_id: z.number().int(),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        return apiRequest(`/v1/chats/${params.chat_id}/members/${params.user_id}${qs.toString() ? `?${qs.toString()}` : ""}`);
      },
    },
    {
      name: "chats.list",
      description: "Список чатов из локальной БД с фильтрацией по bot_id и типу.",
      parameters: z.object({
        bot_id: z.number().int().optional(),
        chat_type: z.string().optional(),
        limit: z.number().int().min(1).max(500).optional().default(100),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        if (params.chat_type) qs.set("chat_type", params.chat_type);
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(`/v1/chats?${qs.toString()}`);
      },
    },
    {
      name: "chats.alias",
      description: "Установить алиас для чата в локальной БД.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        alias: z.string().min(2).max(120),
      }),
      execute: async (params) => apiRequest(`/v1/chats/${params.chat_id}/alias`, {
        method: "PUT",
        body: JSON.stringify({ alias: params.alias }),
      }),
    },
    {
      name: "chats.history",
      description: "Получить историю сообщений чата из локальной БД.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        limit: z.number().int().min(1).max(500).optional().default(100),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(`/v1/chats/${params.chat_id}/history?${qs.toString()}`);
      },
    },
    {
      name: "callbacks.answer",
      description: "Ответить на нажатие inline-кнопки (callback_query).",
      parameters: z.object({
        bot_id: z.number().int().optional(),
        callback_query_id: z.string(),
        text: z.string().optional().describe("Текст уведомления"),
        show_alert: z.boolean().optional().describe("Показать alert вместо toast"),
      }),
      execute: async (params) => apiRequest("/v1/callbacks/answer", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "callbacks.list",
      description: "Получить список полученных callback queries.",
      parameters: z.object({
        chat_id: z.string().optional(),
        user_id: z.string().optional(),
        answered: z.boolean().optional(),
        limit: z.number().int().min(1).max(500).optional().default(50),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.chat_id) qs.set("chat_id", params.chat_id);
        if (params.user_id) qs.set("user_id", params.user_id);
        if (params.answered !== undefined) qs.set("answered", String(params.answered));
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(`/v1/callbacks?${qs.toString()}`);
      },
    },

    // === Batch 7: Chat Administration ===
    {
      name: "chats.set_title",
      description: "Установить название чата.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        title: z.string().max(128),
      }),
      execute: async (params) => apiRequest(`/v1/chats/${params.chat_id}/title`, {
        method: "PUT",
        body: JSON.stringify({ bot_id: params.bot_id, title: params.title }),
      }),
    },
    {
      name: "chats.set_description",
      description: "Установить описание чата.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        description: z.string().max(255).optional(),
      }),
      execute: async (params) => apiRequest(`/v1/chats/${params.chat_id}/description`, {
        method: "PUT",
        body: JSON.stringify({ bot_id: params.bot_id, description: params.description }),
      }),
    },
    {
      name: "chats.delete_photo",
      description: "Удалить фото чата.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : "";
        return apiRequest(`/v1/chats/${params.chat_id}/photo${qs}`, { method: "DELETE" });
      },
    },
    {
      name: "chats.leave",
      description: "Выйти из чата.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : "";
        return apiRequest(`/v1/chats/${params.chat_id}/leave${qs}`, { method: "POST" });
      },
    },
    {
      name: "chats.unpin_all",
      description: "Открепить все сообщения в чате.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : "";
        return apiRequest(`/v1/chats/${params.chat_id}/unpin-all${qs}`, { method: "POST" });
      },
    },
    {
      name: "chats.create_invite_link",
      description: "Создать пригласительную ссылку для чата.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        name: z.string().max(32).optional(),
        expire_date: z.number().int().optional(),
        member_limit: z.number().int().min(1).max(99999).optional(),
        creates_join_request: z.boolean().optional(),
      }),
      execute: async (params) => apiRequest(`/v1/chats/${params.chat_id}/invite-links`, {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "chats.edit_invite_link",
      description: "Редактировать пригласительную ссылку чата.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        invite_link: z.string(),
        bot_id: z.number().int().optional(),
        name: z.string().max(32).optional(),
        expire_date: z.number().int().optional(),
        member_limit: z.number().int().min(1).max(99999).optional(),
        creates_join_request: z.boolean().optional(),
      }),
      execute: async (params) => apiRequest(`/v1/chats/${params.chat_id}/invite-links`, {
        method: "PUT",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "chats.revoke_invite_link",
      description: "Отозвать пригласительную ссылку чата.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        invite_link: z.string(),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest(`/v1/chats/${params.chat_id}/invite-links`, {
        method: "DELETE",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "chats.export_invite_link",
      description: "Экспорт основной пригласительной ссылки чата.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : "";
        return apiRequest(`/v1/chats/${params.chat_id}/export-invite-link${qs}`, { method: "POST" });
      },
    },
    {
      name: "chats.create_subscription_invite_link",
      description: "Создать подписочную пригласительную ссылку (Bot API 7.9).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        name: z.string().max(32).optional(),
        subscription_period: z.number().int().describe("Период подписки в секундах"),
        subscription_price: z.number().int().describe("Цена подписки в Stars"),
      }),
      execute: async (params) => apiRequest(`/v1/chats/${params.chat_id}/subscription-links`, {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "chats.edit_subscription_invite_link",
      description: "Редактировать подписочную пригласительную ссылку (Bot API 7.9).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        invite_link: z.string(),
        bot_id: z.number().int().optional(),
        name: z.string().max(32).optional(),
      }),
      execute: async (params) => apiRequest(`/v1/chats/${params.chat_id}/subscription-links`, {
        method: "PUT",
        body: JSON.stringify(params),
      }),
    },
  ];
}
