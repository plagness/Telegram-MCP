import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для prediction markets (Polymarket-style ставки) */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "predictions.create_event",
      description: "Создать событие для ставок (Polymarket-style). Поддерживает несколько валют: XTR (Stars), AC (виртуальная), TON.",
      parameters: z.object({
        bot_id: z.number().int().optional(),
        title: z.string().max(200),
        description: z.string().max(1000),
        options: z.array(z.object({
          id: z.string(),
          text: z.string().max(100),
          value: z.string().optional().describe("Числовое значение (например, '16.5%')"),
        })).min(2).max(10),
        creator_id: z.number().int(),
        chat_id: z.union([z.string(), z.number()]).optional().describe("Чат для публикации (null = личное)"),
        deadline: z.string().optional().describe("ISO datetime дедлайна"),
        resolution_date: z.string().optional().describe("ISO datetime разрешения"),
        currency: z.enum(["XTR", "AC", "TON"]).optional().default("XTR").describe("Валюта: XTR (Stars), AC (виртуальная), TON"),
        min_bet: z.number().int().min(1).optional().default(1),
        max_bet: z.number().int().min(1).optional().default(1000),
        is_anonymous: z.boolean().optional().default(true).describe("Обезличенные ставки"),
      }),
      execute: async (params) => apiRequest("/v1/predictions/events", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "predictions.place_bet",
      description: "Разместить ставку на событие. Оплата зависит от валюты события: XTR → invoice, AC → с баланса.",
      parameters: z.object({
        event_id: z.number().int(),
        option_id: z.string(),
        amount: z.number().int().min(1).describe("Сумма ставки"),
        user_id: z.number().int(),
        source: z.enum(["auto", "balance", "payment"]).optional().default("auto").describe("Источник оплаты: auto (по валюте), balance, payment"),
      }),
      execute: async (params) => apiRequest("/v1/predictions/bets", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "predictions.resolve",
      description: "Разрешить событие и выплатить выигрыши. Определяет победителей и рассчитывает мультипликаторы.",
      parameters: z.object({
        event_id: z.number().int(),
        winning_option_ids: z.array(z.string()),
        resolution_source: z.enum(["llm-mcp", "ollama", "openrouter", "manual"]),
        resolution_data: z.record(z.any()).optional().describe("Данные от LLM/новости"),
      }),
      execute: async (params) => apiRequest(`/v1/predictions/events/${params.event_id}/resolve`, {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "predictions.list",
      description: "Список событий для ставок с фильтрацией.",
      parameters: z.object({
        status: z.enum(["active", "closed", "resolved", "cancelled"]).optional(),
        chat_id: z.union([z.string(), z.number()]).optional(),
        limit: z.number().int().min(1).max(500).optional().default(50),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.status) qs.set("status", params.status);
        if (params.chat_id) qs.set("chat_id", String(params.chat_id));
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(`/v1/predictions/events?${qs.toString()}`);
      },
    },
    {
      name: "predictions.get",
      description: "Детали события со ставками и коэффициентами.",
      parameters: z.object({
        event_id: z.number().int(),
      }),
      execute: async (params) => apiRequest(`/v1/predictions/events/${params.event_id}`),
    },
    {
      name: "predictions.user_bets",
      description: "Ставки пользователя с фильтрацией.",
      parameters: z.object({
        user_id: z.number().int(),
        event_id: z.number().int().optional(),
        status: z.enum(["active", "won", "lost", "refunded"]).optional(),
        limit: z.number().int().min(1).max(500).optional().default(50),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        qs.set("user_id", String(params.user_id));
        if (params.event_id) qs.set("event_id", String(params.event_id));
        if (params.status) qs.set("status", params.status);
        qs.set("limit", String(params.limit));
        return apiRequest(`/v1/predictions/bets?${qs.toString()}`);
      },
    },
    {
      name: "predictions.currencies",
      description: "Список доступных валют для ставок (XTR, AC, TON).",
      parameters: z.object({}).optional(),
      execute: async () => apiRequest("/v1/predictions/currencies"),
    },
  ];
}
