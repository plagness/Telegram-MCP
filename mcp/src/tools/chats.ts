import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для работы с чатами и callback queries */
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
  ];
}
