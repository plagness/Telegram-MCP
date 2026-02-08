import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для Stars-платежей, подарков, историй (Bot API 9.1+) */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "stars.balance",
      description: "Получить баланс звёзд бота (Bot API 9.1). Возвращает star_count.",
      parameters: z.object({
        bot_id: z.number().int().optional(),
      }).optional(),
      execute: async (params) => apiRequest(`/v1/stars/balance${params?.bot_id !== undefined ? `?bot_id=${params.bot_id}` : ""}`),
    },
    {
      name: "stars.invoice",
      description: "Создать счёт (invoice) на оплату Stars.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        title: z.string().max(32),
        description: z.string().max(255),
        amount: z.number().int().min(1).describe("Сумма в Stars"),
        payload: z.string().max(128).describe("Внутренний ID для идентификации"),
      }),
      execute: async (params) => apiRequest("/v1/stars/invoice", {
        method: "POST",
        body: JSON.stringify({
          ...params,
          currency: "XTR",
          prices: [{ label: params.title, amount: params.amount }],
        }),
      }),
    },
    {
      name: "stars.refund",
      description: "Возврат Stars платежа пользователю.",
      parameters: z.object({
        bot_id: z.number().int().optional(),
        user_id: z.number().int(),
        telegram_payment_charge_id: z.string(),
      }),
      execute: async (params) => apiRequest("/v1/stars/refund", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "stars.transactions",
      description: "История транзакций Stars с фильтрацией.",
      parameters: z.object({
        bot_id: z.number().int().optional(),
        user_id: z.number().int().optional(),
        limit: z.number().int().min(1).max(500).optional().default(100),
        offset: z.number().int().min(0).optional().default(0),
      }),
      execute: async (params) => {
        const qs = new URLSearchParams();
        if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
        if (params.user_id) qs.set("user_id", String(params.user_id));
        qs.set("limit", String(params.limit));
        qs.set("offset", String(params.offset));
        return apiRequest(`/v1/stars/transactions?${qs.toString()}`);
      },
    },
    {
      name: "gifts.premium",
      description: "Подарить премиум-подписку пользователю за звёзды (Bot API 9.3). Списывает звёзды с баланса бота.",
      parameters: z.object({
        bot_id: z.number().int().optional(),
        user_id: z.number().int(),
        duration_months: z.number().int().min(1).max(12).describe("Длительность подписки (1-12 месяцев)"),
        star_count: z.number().int().describe("Стоимость в звёздах"),
      }),
      execute: async (params) => apiRequest("/v1/gifts/premium", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "gifts.user",
      description: "Получить список подарков пользователя (Bot API 9.3).",
      parameters: z.object({
        user_id: z.number().int(),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest(`/v1/gifts/user/${params.user_id}${params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : ""}`),
    },
    {
      name: "gifts.chat",
      description: "Получить список подарков в чате (Bot API 9.3).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest(`/v1/gifts/chat/${params.chat_id}${params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : ""}`),
    },
    {
      name: "stories.repost",
      description: "Репостнуть историю из одного канала в другой (Bot API 9.3).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]).describe("ID канала-получателя"),
        from_chat_id: z.union([z.string(), z.number()]).describe("ID канала-источника"),
        story_id: z.number().int().describe("ID истории"),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/stories/repost", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
  ];
}
