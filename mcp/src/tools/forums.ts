import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для работы с форум-топиками (Bot API 7.0+) */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "forums.create",
      description: "Создать новый топик в форум-группе.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        name: z.string().max(128).describe("Название топика"),
        icon_color: z.number().int().optional().describe("Цвет иконки топика"),
        icon_custom_emoji_id: z.string().optional().describe("Custom emoji для иконки"),
      }),
      execute: async (params) => apiRequest("/v1/forums/create", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "forums.edit",
      description: "Редактировать имя или иконку топика.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        message_thread_id: z.number().int(),
        bot_id: z.number().int().optional(),
        name: z.string().max(128).optional(),
        icon_custom_emoji_id: z.string().optional(),
      }),
      execute: async (params) => apiRequest("/v1/forums/edit", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "forums.close",
      description: "Закрыть топик (запретить новые сообщения).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        thread_id: z.number().int(),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : "";
        return apiRequest(`/v1/forums/${params.chat_id}/${params.thread_id}/close${qs}`, {
          method: "POST",
        });
      },
    },
    {
      name: "forums.reopen",
      description: "Повторно открыть закрытый топик.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        thread_id: z.number().int(),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : "";
        return apiRequest(`/v1/forums/${params.chat_id}/${params.thread_id}/reopen${qs}`, {
          method: "POST",
        });
      },
    },
    {
      name: "forums.delete",
      description: "Удалить топик вместе со всеми сообщениями.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        thread_id: z.number().int(),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : "";
        return apiRequest(`/v1/forums/${params.chat_id}/${params.thread_id}${qs}`, {
          method: "DELETE",
        });
      },
    },
    {
      name: "forums.unpin_all",
      description: "Открепить все сообщения в топике.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        thread_id: z.number().int(),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : "";
        return apiRequest(`/v1/forums/${params.chat_id}/${params.thread_id}/unpin-all${qs}`, {
          method: "POST",
        });
      },
    },
  ];
}
