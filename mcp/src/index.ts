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
    status: z.string().optional(),
    limit: z.number().int().min(1).max(500).optional().default(50),
    offset: z.number().int().min(0).optional().default(0),
  }),
  execute: async (params) => {
    const qs = new URLSearchParams();
    if (params.chat_id) qs.set("chat_id", params.chat_id);
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
  }),
  execute: async (params) => apiRequest("/v1/commands/sync", {
    method: "POST",
    body: JSON.stringify({ command_set_id: params.command_set_id }),
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
  }),
  execute: async (params) => apiRequest(`/v1/chats/${params.chat_id}`),
});

addTool({
  name: "chats.member",
  description: "Получить статус участника чата (admin, member, restricted и т.д.).",
  parameters: z.object({
    chat_id: z.union([z.string(), z.number()]),
    user_id: z.number().int(),
  }),
  execute: async (params) => apiRequest(`/v1/chats/${params.chat_id}/members/${params.user_id}`),
});

// --- Вебхук ---

addTool({
  name: "webhook.setup",
  description: "Настроить вебхук для получения обновлений от Telegram.",
  parameters: z.object({
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
  parameters: z.object({}).optional(),
  execute: async () => apiRequest("/v1/webhook/info"),
});

addTool({
  name: "webhook.delete",
  description: "Удалить вебхук.",
  parameters: z.object({}).optional(),
  execute: async () => {
    const resp = await fetch(`${config.apiBase}/v1/webhook`, { method: "DELETE" });
    const text = await resp.text();
    return text ? JSON.parse(text) : {};
  },
});

// --- Команды (расширение) ---

addTool({
  name: "commands.create",
  description: "Создать набор команд бота для определённого скоупа (пользователь, чат, глобально).",
  parameters: z.object({
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
  }),
  execute: async (params) => apiRequest(`/v1/polls/${params.chat_id}/${params.message_id}/stop`, {
    method: "POST",
    body: JSON.stringify({}),
  }),
});

addTool({
  name: "polls.list",
  description: "Получить список опросов.",
  parameters: z.object({
    chat_id: z.string().optional(),
    limit: z.number().int().min(1).max(500).optional().default(50),
    offset: z.number().int().min(0).optional().default(0),
  }),
  execute: async (params) => {
    const qs = new URLSearchParams();
    if (params.chat_id) qs.set("chat_id", params.chat_id);
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

// --- Бот ---

addTool({
  name: "bot.info",
  description: "Информация о боте (имя, username, поддерживаемые фичи).",
  parameters: z.object({}).optional(),
  execute: async () => apiRequest("/v1/bot/me"),
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
