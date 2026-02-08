import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";
import { config } from "../config.js";

/** Инструменты для настройки вебхуков Telegram */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "webhook.setup",
      description: "Настроить вебхук для получения обновлений от Telegram.",
      parameters: z.object({
        bot_id: z.number().int().optional(),
        url: z.string().url(),
        secret_token: z.string().optional(),
        allowed_updates: z.array(z.string()).optional(),
      }),
      execute: async (params) => apiRequest("/v1/webhook/set", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "webhook.info",
      description: "Получить текущую конфигурацию вебхука.",
      parameters: z.object({
        bot_id: z.number().int().optional(),
      }).optional(),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params?.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        return apiRequest(`/v1/webhook/info${qs.toString() ? `?${qs.toString()}` : ""}`);
      },
    },
    {
      // NOTE: использует raw fetch напрямую с config.apiBase
      name: "webhook.delete",
      description: "Удалить вебхук.",
      parameters: z.object({
        bot_id: z.number().int().optional(),
      }).optional(),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params?.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        const resp = await fetch(`${config.apiBase}/v1/webhook${qs.toString() ? `?${qs.toString()}` : ""}`, { method: "DELETE" });
        const text = await resp.text();
        return text ? JSON.parse(text) : {};
      },
    },
  ];
}
