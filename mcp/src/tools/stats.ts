import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты статистики: активные пользователи, чаты, объём сообщений */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "stats.overview",
      description: "Общая статистика Telegram: количество чатов, пользователей, сообщений (inbound/outbound), обновлений.",
      parameters: z.object({
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        return apiRequest(`/v1/stats/overview?${qs.toString()}`);
      },
    },
    {
      name: "stats.active_users",
      description: "Самые активные пользователи по количеству сообщений. Можно фильтровать по чату и периоду.",
      parameters: z.object({
        chat_id: z.string().optional().describe("Фильтр по чату"),
        period: z.enum(["1d", "7d", "30d", "all"]).optional().default("7d"),
        limit: z.number().int().min(1).max(100).optional().default(20),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.chat_id) qs.set("chat_id", params.chat_id);
        qs.set("period", params.period);
        qs.set("limit", String(params.limit));
        return apiRequest(`/v1/stats/active-users?${qs.toString()}`);
      },
    },
    {
      name: "stats.active_chats",
      description: "Самые активные чаты по количеству входящих сообщений.",
      parameters: z.object({
        period: z.enum(["1d", "7d", "30d", "all"]).optional().default("7d"),
        limit: z.number().int().min(1).max(100).optional().default(20),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        qs.set("period", params.period);
        qs.set("limit", String(params.limit));
        return apiRequest(`/v1/stats/active-chats?${qs.toString()}`);
      },
    },
    {
      name: "stats.message_volume",
      description: "Объём сообщений по времени (inbound/outbound/total по часам или дням). Для графиков и дашбордов.",
      parameters: z.object({
        chat_id: z.string().optional(),
        period: z.enum(["1d", "7d", "30d"]).optional().default("7d"),
        granularity: z.enum(["1h", "1d"]).optional().default("1h"),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.chat_id) qs.set("chat_id", params.chat_id);
        qs.set("period", params.period);
        qs.set("granularity", params.granularity);
        return apiRequest(`/v1/stats/message-volume?${qs.toString()}`);
      },
    },
    {
      name: "stats.update_types",
      description: "Распределение типов входящих обновлений (message, callback_query, edited_message и т.д.).",
      parameters: z.object({
        period: z.enum(["1d", "7d", "30d", "all"]).optional().default("7d"),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        qs.set("period", params.period);
        return apiRequest(`/v1/stats/update-types?${qs.toString()}`);
      },
    },
  ];
}
