import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для отправки медиа (фото, документы) */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "media.send_photo",
      description: "Отправить фото в чат (по URL или file_id). Поддерживает caption и parse_mode.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        photo: z.string().describe("URL фото или file_id"),
        caption: z.string().optional(),
        parse_mode: z.string().optional(),
        reply_to_message_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-photo", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "media.send_document",
      description: "Отправить документ/файл в чат (по URL или file_id).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        document: z.string().describe("URL документа или file_id"),
        caption: z.string().optional(),
        parse_mode: z.string().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-document", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
  ];
}
