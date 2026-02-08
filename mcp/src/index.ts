import express from "express";
import type { Request, Response, NextFunction } from "express";
import cors from "cors";
import crypto from "node:crypto";
import { zodToJsonSchema } from "zod-to-json-schema";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

import { config } from "./config.js";
import { logger } from "./logger.js";
import type { ToolDef } from "./types.js";

// --- Импорт модулей инструментов ---
import * as messagesModule from "./tools/messages.js";
import * as templatesModule from "./tools/templates.js";
import * as mediaModule from "./tools/media.js";
import * as chatsModule from "./tools/chats.js";
import * as botsModule from "./tools/bots.js";
import * as webhooksModule from "./tools/webhooks.js";
import * as pollsModule from "./tools/polls.js";
import * as checklistsModule from "./tools/checklists.js";
import * as starsModule from "./tools/stars.js";
import * as predictionsModule from "./tools/predictions.js";
import * as balanceModule from "./tools/balance.js";
import * as webuiModule from "./tools/webui.js";

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

const tools: ToolDef[] = [];

function addTool(tool: ToolDef) {
  tools.push(tool);
}

function findTool(name: string) {
  return tools.find((t) => t.name === name);
}

async function apiRequest(path: string, options: RequestInit = {}) {
  const headers = {
    "content-type": "application/json",
    ...(options.headers || {}),
  };

  const call = async (baseUrl: string) => {
    const url = `${baseUrl}${path}`;
    const resp = await fetch(url, { ...options, headers });
    const text = await resp.text();
    let data: any = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { raw: text };
      }
    }
    if (!resp.ok) {
      const error = data?.detail || data?.error || `HTTP ${resp.status}`;
      throw new Error(error);
    }
    return data;
  };

  try {
    return await call(config.apiBase);
  } catch (err: any) {
    const useLegacyFallback =
      !config.apiBaseExplicit && config.apiBase === config.defaultApiBase;
    if (!useLegacyFallback) {
      throw err;
    }
    logger.warn("api.base.fallback_legacy", {
      from: config.defaultApiBase,
      to: config.legacyApiBase,
      reason: err?.message || String(err),
    });
    return call(config.legacyApiBase);
  }
}

// --- Регистрация инструментов из модулей ---
const modules = [
  messagesModule,
  templatesModule,
  mediaModule,
  chatsModule,
  botsModule,
  webhooksModule,
  pollsModule,
  checklistsModule,
  starsModule,
  predictionsModule,
  balanceModule,
  webuiModule,
];

for (const mod of modules) {
  for (const tool of mod.register(apiRequest)) {
    addTool(tool);
  }
}

// --- HTTP-эндпоинты ---

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

// --- MCP stdio ---
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
