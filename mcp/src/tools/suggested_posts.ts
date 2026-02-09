import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для работы с предложенными постами (Bot API 9.2) */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "suggested_posts.approve",
      description: "Одобрить предложенный пост в бизнес-канале (Bot API 9.2).",
      parameters: z.object({
        business_connection_id: z.string(),
        message_id: z.number().int(),
        bot_id: z.number().int().optional(),
        is_scheduled: z.boolean().optional(),
      }),
      execute: async (params) => apiRequest("/v1/suggested-posts/approve", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "suggested_posts.decline",
      description: "Отклонить предложенный пост в бизнес-канале (Bot API 9.2).",
      parameters: z.object({
        business_connection_id: z.string(),
        message_id: z.number().int(),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/suggested-posts/decline", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
  ];
}
