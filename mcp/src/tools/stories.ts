import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для работы с историями (Bot API 9.0+). Требуют Telegram Business подключение. */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "stories.post",
      description: "Опубликовать историю (Bot API 9.0). Требует Telegram Business подключение (business_connection_id). Фото/видео передаётся как файл.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        content: z.record(z.any()).describe("InputStoryContent объект"),
        caption: z.string().optional(),
        parse_mode: z.string().optional(),
        areas: z.array(z.record(z.any())).optional(),
        post_to_chat_page: z.boolean().optional(),
        protect_content: z.boolean().optional(),
      }),
      execute: async (params) => apiRequest("/v1/stories/post", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "stories.edit",
      description: "Редактировать опубликованную историю. Требует Telegram Business подключение.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        story_id: z.number().int(),
        bot_id: z.number().int().optional(),
        content: z.record(z.any()).optional(),
        caption: z.string().optional(),
        parse_mode: z.string().optional(),
        areas: z.array(z.record(z.any())).optional(),
      }),
      execute: async (params) => apiRequest(`/v1/stories/${params.chat_id}/${params.story_id}`, {
        method: "PUT",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "stories.delete",
      description: "Удалить историю. Требует Telegram Business подключение.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        story_id: z.number().int(),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : "";
        return apiRequest(`/v1/stories/${params.chat_id}/${params.story_id}${qs}`, {
          method: "DELETE",
        });
      },
    },
  ];
}
