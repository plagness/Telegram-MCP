import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для шаблонов и команд бота */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "templates.list",
      description: "Список сохранённых Jinja2-шаблонов.",
      parameters: z.object({}).optional(),
      execute: async () => apiRequest("/v1/templates"),
    },
    {
      name: "templates.render",
      description: "Отрендерить шаблон с переменными (без отправки).",
      parameters: z.object({
        name: z.string(),
        variables: z.record(z.any()).optional(),
      }),
      execute: async (params) => apiRequest(`/v1/templates/${params.name}/render`, {
        method: "POST",
        body: JSON.stringify({ variables: params.variables || {} }),
      }),
    },
    {
      name: "commands.sync",
      description: "Синхронизировать набор команд с Telegram (setMyCommands).",
      parameters: z.object({
        command_set_id: z.number().int(),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/commands/sync", {
        method: "POST",
        body: JSON.stringify({ command_set_id: params.command_set_id, bot_id: params.bot_id }),
      }),
    },
    {
      name: "commands.create",
      description: "Создать набор команд бота для определённого скоупа (пользователь, чат, глобально).",
      parameters: z.object({
        bot_id: z.number().int().optional(),
        scope_type: z.string().optional().default("default").describe("default, chat, chat_member, all_private_chats и т.д."),
        chat_id: z.number().int().optional(),
        user_id: z.number().int().optional(),
        language_code: z.string().optional(),
        commands: z.array(z.object({
          command: z.string(),
          description: z.string(),
        })),
      }),
      execute: async (params) => apiRequest("/v1/commands", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "commands.list",
      description: "Получить все сохранённые наборы команд.",
      parameters: z.object({}).optional(),
      execute: async () => apiRequest("/v1/commands"),
    },
  ];
}
