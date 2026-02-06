import express from "express";
import type { Request, Response, NextFunction } from "express";
import cors from "cors";
import crypto from "node:crypto";
import { z } from "zod";
import { zodToJsonSchema } from "zod-to-json-schema";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

import { config } from "./config.js";
import { logger } from "./logger.js";

const app = express();
app.use(cors());
app.use(express.json({ limit: "1mb" }));

app.use((req: Request, res: Response, next: NextFunction) => {
  const start = Date.now();
  const requestId = crypto.randomUUID();
  (req as any).requestId = requestId;
  logger.info("http.request", { id: requestId, method: req.method, path: req.path });
  res.on("finish", () => {
    logger.info("http.response", {
      id: requestId,
      method: req.method,
      path: req.path,
      status: res.statusCode,
      ms: Date.now() - start,
    });
  });
  next();
});

const authMiddleware = (req: any, res: any, next: any) => {
  if (!config.mcpHttpToken) return next();
  const token = req.headers.authorization?.replace("Bearer ", "");
  if (token !== config.mcpHttpToken) {
    return res.status(401).json({ error: "unauthorized" });
  }
  return next();
};

interface ToolDef {
  name: string;
  description: string;
  parameters: z.ZodTypeAny;
  execute: (params: any) => Promise<any>;
}

const tools: ToolDef[] = [];

function addTool(tool: ToolDef) {
  tools.push(tool);
}

function findTool(name: string) {
  return tools.find((t) => t.name === name);
}

async function apiRequest(path: string, options: RequestInit = {}) {
  const url = `${config.apiBase}${path}`;
  const resp = await fetch(url, {
    ...options,
    headers: {
      "content-type": "application/json",
      ...(options.headers || {}),
    },
  });
  const text = await resp.text();
  const data = text ? JSON.parse(text) : {};
  if (!resp.ok) {
    const error = data?.detail || data?.error || `HTTP ${resp.status}`;
    throw new Error(error);
  }
  return data;
}

app.get("/health", (_req: Request, res: Response) => {
  res.json({ status: "ok", time: new Date().toISOString() });
});

app.get("/tools", authMiddleware, (_req: Request, res: Response) => {
  res.json(
    tools.map((t) => ({
      name: t.name,
      description: t.description,
      inputSchema: (zodToJsonSchema as any)(t.parameters, t.name),
    }))
  );
});

app.post("/tools/:name", authMiddleware, async (req: Request, res: Response) => {
  const requestId = (req as any).requestId;
  const tool = findTool(req.params.name);
  if (!tool) return res.status(404).json({ error: "tool not found" });
  const parsed = tool.parameters.safeParse(req.body || {});
  if (!parsed.success) {
    logger.warn("http.tool.invalid", {
      id: requestId,
      tool: req.params.name,
      error: parsed.error.message,
    });
    return res.status(400).json({ error: parsed.error.message });
  }
  try {
    const result = await tool.execute(parsed.data);
    return res.json(result);
  } catch (err: any) {
    logger.error("http.tool.error", {
      id: requestId,
      tool: req.params.name,
      error: err?.message || String(err),
    });
    return res.status(500).json({ error: err?.message || String(err) });
  }
});

// MCP stdio
const server = new Server(
  { name: "telegram-mcp", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: tools.map((t) => ({
    name: t.name,
    description: t.description,
    inputSchema: (zodToJsonSchema as any)(t.parameters, t.name),
  })),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const tool = findTool(request.params.name);
  if (!tool) {
    return {
      content: [
        {
          type: "text",
          text: `tool not found: ${request.params.name}`,
        },
      ],
      isError: true,
    };
  }
  const parsed = tool.parameters.safeParse(request.params.arguments || {});
  if (!parsed.success) {
    return {
      content: [{ type: "text", text: parsed.error.message }],
      isError: true,
    };
  }
  try {
    const result = await tool.execute(parsed.data);
    return { content: [{ type: "text", text: JSON.stringify(result) }] };
  } catch (err: any) {
    return {
      content: [{ type: "text", text: err?.message || String(err) }],
      isError: true,
    };
  }
});

addTool({
  name: "messages.send",
  description: "Отправить текстовое сообщение в Telegram (текст или шаблон). Поддерживает parse_mode и dry_run.",
  parameters: z.object({
    chat_id: z.union([z.string(), z.number()]),
    bot_id: z.number().int().optional(),
    text: z.string().optional(),
    template: z.string().optional(),
    variables: z.record(z.any()).optional(),
    parse_mode: z.string().optional(),
    dry_run: z.boolean().optional(),
  }),
  execute: async (params) => apiRequest("/v1/messages/send", {
    method: "POST",
    body: JSON.stringify(params),
  }),
});

addTool({
  name: "messages.edit",
  description: "Редактировать ранее отправленное сообщение по внутреннему ID.",
  parameters: z.object({
    message_id: z.number().int(),
    bot_id: z.number().int().optional(),
    text: z.string().optional(),
    template: z.string().optional(),
    variables: z.record(z.any()).optional(),
    parse_mode: z.string().optional(),
  }),
  execute: async (params) => apiRequest(`/v1/messages/${params.message_id}/edit`, {
    method: "POST",
    body: JSON.stringify(params),
  }),
});

addTool({
  name: "messages.delete",
  description: "Удалить ранее отправленное сообщение по внутреннему ID.",
  parameters: z.object({
    message_id: z.number().int(),
  }),
  execute: async (params) => apiRequest(`/v1/messages/${params.message_id}/delete`, {
    method: "POST",
    body: JSON.stringify(params),
  }),
});

addTool({
  name: "messages.fetch",
  description: "Получить сообщения из хранилища. Фильтрация по chat_id и статусу.",
  parameters: z.object({
    chat_id: z.string().optional(),
    bot_id: z.number().int().optional(),
    status: z.string().optional(),
    limit: z.number().int().min(1).max(500).optional().default(50),
    offset: z.number().int().min(0).optional().default(0),
  }),
  execute: async (params) => {
    const qs = new URLSearchParams();
    if (params.chat_id) qs.set("chat_id", params.chat_id);
    if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
    if (params.status) qs.set("status", params.status);
    qs.set("limit", String(params.limit));
    qs.set("offset", String(params.offset));
    return apiRequest(`/v1/messages?${qs.toString()}`);
  },
});

addTool({
  name: "templates.list",
  description: "Список сохранённых Jinja2-шаблонов.",
  parameters: z.object({}).optional(),
  execute: async () => apiRequest("/v1/templates"),
});

addTool({
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
});

addTool({
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
});

addTool({
  name: "updates.fetch",
  description: "Получить входящие обновления от Telegram (вебхуки). Фильтрация по типу обновления.",
  parameters: z.object({
    limit: z.number().int().min(1).max(500).optional().default(100),
    offset: z.number().int().min(0).optional().default(0),
    update_type: z.string().optional().describe("Тип обновления: message, callback_query, edited_message и т.д."),
  }),
  execute: async (params) => {
    const qs = new URLSearchParams();
    qs.set("limit", String(params.limit));
    qs.set("offset", String(params.offset));
    if (params.update_type) qs.set("update_type", params.update_type);
    return apiRequest(`/v1/updates?${qs.toString()}`);
  },
});

// --- Медиа ---

addTool({
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
});

addTool({
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
});

// --- Callback Queries ---

addTool({
  name: "callbacks.answer",
  description: "Ответить на нажатие inline-кнопки (callback_query).",
  parameters: z.object({
    bot_id: z.number().int().optional(),
    callback_query_id: z.string(),
    text: z.string().optional().describe("Текст уведомления"),
    show_alert: z.boolean().optional().describe("Показать alert вместо toast"),
  }),
  execute: async (params) => apiRequest("/v1/callbacks/answer", {
    method: "POST",
    body: JSON.stringify(params),
  }),
});

addTool({
  name: "callbacks.list",
  description: "Получить список полученных callback queries.",
  parameters: z.object({
    chat_id: z.string().optional(),
    user_id: z.string().optional(),
    answered: z.boolean().optional(),
    limit: z.number().int().min(1).max(500).optional().default(50),
    offset: z.number().int().min(0).optional().default(0),
  }),
  execute: async (params) => {
    const qs = new URLSearchParams();
    if (params.chat_id) qs.set("chat_id", params.chat_id);
    if (params.user_id) qs.set("user_id", params.user_id);
    if (params.answered !== undefined) qs.set("answered", String(params.answered));
    qs.set("limit", String(params.limit));
    qs.set("offset", String(params.offset));
    return apiRequest(`/v1/callbacks?${qs.toString()}`);
  },
});

// --- Чаты ---

addTool({
  name: "chats.get",
  description: "Получить информацию о чате от Telegram API (название, тип, описание).",
  parameters: z.object({
    chat_id: z.union([z.string(), z.number()]),
    bot_id: z.number().int().optional(),
  }),
  execute: async (params) => {
    const qs = new URLSearchParams();
    if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
    return apiRequest(`/v1/chats/${params.chat_id}${qs.toString() ? `?${qs.toString()}` : ""}`);
  },
});

addTool({
  name: "chats.member",
  description: "Получить статус участника чата (admin, member, restricted и т.д.).",
  parameters: z.object({
    chat_id: z.union([z.string(), z.number()]),
    user_id: z.number().int(),
    bot_id: z.number().int().optional(),
  }),
  execute: async (params) => {
    const qs = new URLSearchParams();
    if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
    return apiRequest(`/v1/chats/${params.chat_id}/members/${params.user_id}${qs.toString() ? `?${qs.toString()}` : ""}`);
  },
});

addTool({
  name: "chats.list",
  description: "Список чатов из локальной БД с фильтрацией по bot_id и типу.",
  parameters: z.object({
    bot_id: z.number().int().optional(),
    chat_type: z.string().optional(),
    limit: z.number().int().min(1).max(500).optional().default(100),
    offset: z.number().int().min(0).optional().default(0),
  }),
  execute: async (params) => {
    const qs = new URLSearchParams();
    if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
    if (params.chat_type) qs.set("chat_type", params.chat_type);
    qs.set("limit", String(params.limit));
    qs.set("offset", String(params.offset));
    return apiRequest(`/v1/chats?${qs.toString()}`);
  },
});

addTool({
  name: "chats.alias",
  description: "Установить алиас для чата в локальной БД.",
  parameters: z.object({
    chat_id: z.union([z.string(), z.number()]),
    alias: z.string().min(2).max(120),
  }),
  execute: async (params) => apiRequest(`/v1/chats/${params.chat_id}/alias`, {
    method: "PUT",
    body: JSON.stringify({ alias: params.alias }),
  }),
});

addTool({
  name: "chats.history",
  description: "Получить историю сообщений чата из локальной БД.",
  parameters: z.object({
    chat_id: z.union([z.string(), z.number()]),
    bot_id: z.number().int().optional(),
    limit: z.number().int().min(1).max(500).optional().default(100),
    offset: z.number().int().min(0).optional().default(0),
  }),
  execute: async (params) => {
    const qs = new URLSearchParams();
    if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
    qs.set("limit", String(params.limit));
    qs.set("offset", String(params.offset));
    return apiRequest(`/v1/chats/${params.chat_id}/history?${qs.toString()}`);
  },
});

// --- Bots ---

addTool({
  name: "bots.list",
  description: "Список зарегистрированных ботов.",
  parameters: z.object({
    include_inactive: z.boolean().optional().default(false),
  }).optional(),
  execute: async (params) => apiRequest(`/v1/bots?include_inactive=${params?.include_inactive ? "true" : "false"}`),
});

addTool({
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
});

addTool({
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
});

// --- Вебхук ---

addTool({
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
});

addTool({
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
});

addTool({
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
});

// --- Команды (расширение) ---

addTool({
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
});

addTool({
  name: "commands.list",
  description: "Получить все сохранённые наборы команд.",
  parameters: z.object({}).optional(),
  execute: async () => apiRequest("/v1/commands"),
});

// --- Опросы ---

addTool({
  name: "polls.send",
  description: "Создать опрос или викторину. Поддерживает quiz-режим с правильным ответом и пояснением.",
  parameters: z.object({
    chat_id: z.union([z.string(), z.number()]),
    bot_id: z.number().int().optional(),
    question: z.string().min(1).max(300),
    options: z.array(z.string()).min(2).max(10),
    is_anonymous: z.boolean().optional().default(true),
    type: z.enum(["regular", "quiz"]).optional().default("regular"),
    allows_multiple_answers: z.boolean().optional().default(false),
    correct_option_id: z.number().int().optional().describe("Индекс правильного ответа для quiz (0-based)"),
    explanation: z.string().max(200).optional().describe("Пояснение для quiz"),
    explanation_parse_mode: z.string().optional(),
    open_period: z.number().int().min(5).max(600).optional().describe("Время жизни опроса в секундах"),
    message_thread_id: z.number().int().optional(),
    reply_to_message_id: z.number().int().optional(),
    dry_run: z.boolean().optional(),
  }),
  execute: async (params) => apiRequest("/v1/polls/send", {
    method: "POST",
    body: JSON.stringify(params),
  }),
});

addTool({
  name: "polls.stop",
  description: "Остановить опрос и показать результаты.",
  parameters: z.object({
    chat_id: z.union([z.string(), z.number()]),
    message_id: z.number().int().describe("telegram_message_id"),
    bot_id: z.number().int().optional(),
  }),
  execute: async (params) => apiRequest(`/v1/polls/${params.chat_id}/${params.message_id}/stop${params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : ""}`, {
    method: "POST",
    body: JSON.stringify({}),
  }),
});

addTool({
  name: "polls.list",
  description: "Получить список опросов.",
  parameters: z.object({
    chat_id: z.string().optional(),
    bot_id: z.number().int().optional(),
    limit: z.number().int().min(1).max(500).optional().default(50),
    offset: z.number().int().min(0).optional().default(0),
  }),
  execute: async (params) => {
    const qs = new URLSearchParams();
    if (params.chat_id) qs.set("chat_id", params.chat_id);
    if (params.bot_id !== undefined) qs.set("bot_id", String(params.bot_id));
    qs.set("limit", String(params.limit));
    qs.set("offset", String(params.offset));
    return apiRequest(`/v1/polls?${qs.toString()}`);
  },
});

// --- Реакции ---

addTool({
  name: "reactions.set",
  description: "Установить реакцию на сообщение (👍/👎/🔥 и другие эмодзи). Можно удалить реакцию, передав null.",
  parameters: z.object({
    chat_id: z.union([z.string(), z.number()]),
    bot_id: z.number().int().optional(),
    message_id: z.number().int().describe("telegram_message_id"),
    reaction: z.array(z.object({
      type: z.enum(["emoji", "custom_emoji", "paid"]),
      emoji: z.string().optional(),
      custom_emoji_id: z.string().optional(),
    })).optional().describe("Список реакций, null — удалить все"),
    is_big: z.boolean().optional().default(false).describe("Большая анимация реакции"),
  }),
  execute: async (params) => apiRequest("/v1/reactions/set", {
    method: "POST",
    body: JSON.stringify(params),
  }),
});

// --- Чеклисты (Bot API 9.1) ---

addTool({
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
});

addTool({
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
});

// --- Звёзды и Подарки (Bot API 9.1+) ---

addTool({
  name: "stars.balance",
  description: "Получить баланс звёзд бота (Bot API 9.1). Возвращает star_count.",
  parameters: z.object({
    bot_id: z.number().int().optional(),
  }).optional(),
  execute: async (params) => apiRequest(`/v1/stars/balance${params?.bot_id !== undefined ? `?bot_id=${params.bot_id}` : ""}`),
});

addTool({
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
});

addTool({
  name: "gifts.user",
  description: "Получить список подарков пользователя (Bot API 9.3).",
  parameters: z.object({
    user_id: z.number().int(),
    bot_id: z.number().int().optional(),
  }),
  execute: async (params) => apiRequest(`/v1/gifts/user/${params.user_id}${params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : ""}`),
});

addTool({
  name: "gifts.chat",
  description: "Получить список подарков в чате (Bot API 9.3).",
  parameters: z.object({
    chat_id: z.union([z.string(), z.number()]),
    bot_id: z.number().int().optional(),
  }),
  execute: async (params) => apiRequest(`/v1/gifts/chat/${params.chat_id}${params.bot_id !== undefined ? `?bot_id=${params.bot_id}` : ""}`),
});

// --- Истории (Bot API 9.3) ---

addTool({
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
});

// --- Prediction Markets (Betting) ---

addTool({
  name: "predictions.create_event",
  description: "Создать событие для ставок (Polymarket-style). Ставки Stars с мультипликатором.",
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
    min_bet: z.number().int().min(1).optional().default(1),
    max_bet: z.number().int().min(1).optional().default(1000),
    is_anonymous: z.boolean().optional().default(true).describe("Обезличенные ставки"),
  }),
  execute: async (params) => apiRequest("/v1/predictions/events", {
    method: "POST",
    body: JSON.stringify(params),
  }),
});

addTool({
  name: "predictions.place_bet",
  description: "Разместить ставку Stars на событие. Создаёт invoice для оплаты.",
  parameters: z.object({
    event_id: z.number().int(),
    option_id: z.string(),
    amount: z.number().int().min(1).describe("Сумма ставки в Stars"),
    user_id: z.number().int(),
  }),
  execute: async (params) => apiRequest("/v1/predictions/bets", {
    method: "POST",
    body: JSON.stringify(params),
  }),
});

addTool({
  name: "predictions.resolve",
  description: "Разрешить событие и выплатить выигрыши. Определяет победителей и рассчитывает мультипликаторы.",
  parameters: z.object({
    event_id: z.number().int(),
    winning_option_ids: z.array(z.string()).min(1),
    resolution_source: z.enum(["llm-mcp", "ollama", "openrouter", "manual"]),
    resolution_data: z.record(z.any()).optional().describe("Данные от LLM/новости"),
  }),
  execute: async (params) => apiRequest(`/v1/predictions/events/${params.event_id}/resolve`, {
    method: "POST",
    body: JSON.stringify(params),
  }),
});

addTool({
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
});

addTool({
  name: "predictions.get",
  description: "Детали события со ставками и коэффициентами.",
  parameters: z.object({
    event_id: z.number().int(),
  }),
  execute: async (params) => apiRequest(`/v1/predictions/events/${params.event_id}`),
});

addTool({
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
});

// --- Stars Payments ---

addTool({
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
});

addTool({
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
});

addTool({
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
});

// --- Бот ---

addTool({
  name: "bot.info",
  description: "Информация о боте (имя, username, поддерживаемые фичи).",
  parameters: z.object({
    bot_id: z.number().int().optional(),
  }).optional(),
  execute: async (params) => apiRequest(`/v1/bot/me${params?.bot_id !== undefined ? `?bot_id=${params.bot_id}` : ""}`),
});

async function start() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  app.listen(config.port, () => {
    logger.info("mcp.server.started", { port: config.port });
  });
}

start().catch((err) => {
  logger.error("mcp.server.failed", { error: err?.message || String(err) });
  process.exit(1);
});
