import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для интерактивных чек-листов (Bot API 9.1) */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "checklists.send",
      description: "Отправить чек-лист с интерактивными задачами (Bot API 9.1). До 30 задач с галочками.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        title: z.string().max(128).describe("Заголовок чек-листа"),
        tasks: z.array(z.object({
          text: z.string().max(256),
          is_completed: z.boolean().optional().default(false),
        })).min(1).max(30),
        message_thread_id: z.number().int().optional(),
        reply_to_message_id: z.number().int().optional(),
        request_id: z.string().optional(),
      }),
      execute: async (params) => apiRequest("/v1/checklists/send", {
        method: "POST",
        body: JSON.stringify({
          chat_id: params.chat_id,
          bot_id: params.bot_id,
          message_thread_id: params.message_thread_id,
          reply_to_message_id: params.reply_to_message_id,
          request_id: params.request_id,
          checklist: {
            title: params.title,
            tasks: params.tasks,
          },
        }),
      }),
    },
    {
      name: "checklists.edit",
      description: "Редактировать существующий чек-лист (обновить задачи).",
      parameters: z.object({
        message_id: z.number().int().describe("Внутренний ID сообщения с чек-листом"),
        bot_id: z.number().int().optional(),
        title: z.string().max(128),
        tasks: z.array(z.object({
          text: z.string().max(256),
          is_completed: z.boolean().optional().default(false),
        })).min(1).max(30),
      }),
      execute: async (params) => apiRequest(`/v1/messages/${params.message_id}/checklist`, {
        method: "PUT",
        body: JSON.stringify({
          bot_id: params.bot_id,
          checklist: {
            title: params.title,
            tasks: params.tasks,
          },
        }),
      }),
    },
  ];
}
