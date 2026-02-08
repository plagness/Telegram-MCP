import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для отправки, редактирования, удаления и получения сообщений */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "messages.send",
      description: "Отправить текстовое сообщение в Telegram (текст или шаблон). Поддерживает parse_mode и dry_run.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        text: z.string().optional(),
        template: z.string().optional(),
        variables: z.record(z.any()).optional(),
        parse_mode: z.string().optional(),
        dry_run: z.boolean().optional(),
      }),
      execute: async (params) => apiRequest("/v1/messages/send", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "messages.edit",
      description: "Редактировать ранее отправленное сообщение по внутреннему ID.",
      parameters: z.object({
        message_id: z.number().int(),
        bot_id: z.number().int().optional(),
        text: z.string().optional(),
        template: z.string().optional(),
        variables: z.record(z.any()).optional(),
        parse_mode: z.string().optional(),
      }),
      execute: async (params) => apiRequest(`/v1/messages/${params.message_id}/edit`, {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "messages.delete",
      description: "Удалить ранее отправленное сообщение по внутреннему ID.",
      parameters: z.object({
        message_id: z.number().int(),
      }),
      execute: async (params) => apiRequest(`/v1/messages/${params.message_id}/delete`, {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "messages.fetch",
      description: "Получить сообщения из хранилища. Фильтрация по chat_id и статусу.",
      parameters: z.object({
        chat_id: z.string().optional(),
        bot_id: z.number().int().optional(),
        status: z.string().optional(),
        limit: z.number().int().min(1).max(500).optional().default(50),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.chat_id) qs.set("chat_id", params.chat_id);
        if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        if (params.status) qs.set("status", params.status);
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(`/v1/messages?${qs.toString()}`);
      },
    },
  ];
}
