import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для опросов, реакций и входящих обновлений */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "polls.send",
      description: "Создать опрос или викторину. Поддерживает quiz-режим с правильным ответом и пояснением.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        question: z.string().min(1).max(300),
        options: z.array(z.string()).min(2).max(10),
        is_anonymous: z.boolean().optional().default(true),
        type: z.enum(["regular", "quiz"]).optional().default("regular"),
        allows_multiple_answers: z.boolean().optional().default(false),
        correct_option_id: z.number().int().optional().describe("Индекс правильного ответа для quiz (0-based)"),
        explanation: z.string().max(200).optional().describe("Пояснение для quiz"),
        explanation_parse_mode: z.string().optional(),
        open_period: z.number().int().min(5).max(600).optional().describe("Время жизни опроса в секундах"),
        message_thread_id: z.number().int().optional(),
        reply_to_message_id: z.number().int().optional(),
        dry_run: z.boolean().optional(),
      }),
      execute: async (params) => apiRequest("/v1/polls/send", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "polls.stop",
      description: "Остановить опрос и показать результаты.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        message_id: z.number().int().describe("telegram_message_id"),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest(`/v1/polls/${params.chat_id}/${params.message_id}/stop${params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : ""}`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    },
    {
      name: "polls.list",
      description: "Получить список опросов.",
      parameters: z.object({
        chat_id: z.string().optional(),
        bot_id: z.number().int().optional(),
        limit: z.number().int().min(1).max(500).optional().default(50),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.chat_id) qs.set("chat_id", params.chat_id);
        if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(`/v1/polls?${qs.toString()}`);
      },
    },
    {
      name: "reactions.set",
      description: "Установить реакцию на сообщение (👍/👎/🔥 и другие эмодзи). Можно удалить реакцию, передав null.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        message_id: z.number().int().describe("telegram_message_id"),
        reaction: z.array(z.object({
          type: z.enum(["emoji", "custom_emoji", "paid"]),
          emoji: z.string().optional(),
          custom_emoji_id: z.string().optional(),
        })).optional().describe("Список реакций, null — удалить все"),
        is_big: z.boolean().optional().default(false).describe("Большая анимация реакции"),
      }),
      execute: async (params) => apiRequest("/v1/reactions/set", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "updates.fetch",
      description: "Получить входящие обновления от Telegram (вебхуки). Фильтрация по типу обновления.",
      parameters: z.object({
        limit: z.number().int().min(1).max(500).optional().default(100),
        offset: z.number().int().min(0).optional().default(0),
        update_type: z.string().optional().describe("Тип обновления: message, callback_query, edited_message и т.д."),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        if (params.update_type) qs.set("update_type", params.update_type);
        return apiRequest(`/v1/updates?${qs.toString()}`);
      },
    },
  ];
}
