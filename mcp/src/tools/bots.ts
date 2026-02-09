import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для управления ботами */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "bots.list",
      description: "Список зарегистрированных ботов.",
      parameters: z.object({
        include_inactive: z.boolean().optional().default(false),
      }).optional(),
      execute: async (params) => apiRequest(`/v1/bots?include_inactive=${params?.include_inactive ? "true" : "false"}`),
    },
    {
      name: "bots.register",
      description: "Зарегистрировать нового бота по токену.",
      parameters: z.object({
        token: z.string().min(10),
        is_default: z.boolean().optional(),
      }),
      execute: async (params) => apiRequest("/v1/bots", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "bots.default",
      description: "Получить или установить бота по умолчанию.",
      parameters: z.object({
        bot_id: z.number().int().optional().describe("Если задан — установить этого бота дефолтным"),
      }).optional(),
      execute: async (params) => {
        if (params?.bot_id !== undefined) {
          return apiRequest(`/v1/bots/${params.bot_id}/default`, {
            method: "PUT",
            body: JSON.stringify({}),
          });
        }
        return apiRequest("/v1/bots/default");
      },
    },
    {
      name: "bot.info",
      description: "Информация о боте (имя, username, поддерживаемые фичи).",
      parameters: z.object({
        bot_id: z.number().int().optional(),
      }).optional(),
      execute: async (params) => apiRequest(`/v1/bot/me${params?.bot_id !== undefined ? `?bot_id=${params.bot_id}` : ""}`),
    },

    // === Batch 10: Bot Profile ===
    {
      name: "bots.set_profile_photo",
      description: "Установить фото профиля бота (Bot API 9.4).",
      parameters: z.object({
        bot_id: z.number().int().optional(),
        photo: z.record(z.any()).describe("InputProfilePhoto объект"),
        is_public: z.boolean().optional(),
      }),
      execute: async (params) => apiRequest("/v1/bots/profile-photo", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "bots.remove_profile_photo",
      description: "Удалить фото профиля бота (Bot API 9.4).",
      parameters: z.object({
        bot_id: z.number().int().optional(),
      }).optional(),
      execute: async (params) => {
        const qs = params?.bot_id !== undefined ? `?bot_id=${params.bot_id}` : "";
        return apiRequest(`/v1/bots/profile-photo${qs}`, { method: "DELETE" });
      },
    },
    {
      name: "bots.user_profile_audios",
      description: "Получить аудио профиля пользователя (Bot API 9.4).",
      parameters: z.object({
        user_id: z.number().int(),
        bot_id: z.number().int().optional(),
        offset: z.number().int().optional(),
        limit: z.number().int().optional(),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        if (params.offset !== undefined) qs.set("offset", String(params.offset));
        if (params.limit !== undefined) qs.set("limit", String(params.limit));
        return apiRequest(`/v1/bots/users/${params.user_id}/profile-audios?${qs.toString()}`);
      },
    },
  ];
}
