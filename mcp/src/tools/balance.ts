import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для виртуальных балансов пользователей */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "balance.get",
      description: "Получить баланс пользователя (виртуальный).",
      parameters: z.object({
        user_id: z.number().int(),
      }),
      execute: async (params) => apiRequest(`/v1/balance/${params.user_id}`),
    },
    {
      name: "balance.deposit",
      description: "Начислить средства на баланс пользователя.",
      parameters: z.object({
        user_id: z.number().int(),
        amount: z.number().int().min(1).describe("Сумма начисления"),
        description: z.string().optional().default("Начисление"),
        source: z.enum(["manual", "arena", "reward", "initial"]).optional().default("manual"),
      }),
      execute: async (params) => apiRequest(`/v1/balance/${params.user_id}/deposit`, {
        method: "POST",
        body: JSON.stringify({
          amount: params.amount,
          description: params.description,
          source: params.source,
        }),
      }),
    },
    {
      name: "balance.history",
      description: "История транзакций баланса пользователя.",
      parameters: z.object({
        user_id: z.number().int(),
        limit: z.number().int().min(1).max(500).optional().default(50),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => apiRequest(`/v1/balance/${params.user_id}/history?limit=${params.limit}&offset=${params.offset}`),
    },
    {
      name: "balance.top",
      description: "Топ пользователей по балансу.",
      parameters: z.object({
        limit: z.number().int().min(1).max(100).optional().default(10),
      }),
      execute: async (params) => apiRequest(`/v1/balance/top?limit=${params.limit}`),
    },
  ];
}
