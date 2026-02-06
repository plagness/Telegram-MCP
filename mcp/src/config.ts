import dotenv from "dotenv";

dotenv.config();

export const config = {
  port: Number.parseInt(process.env.MCP_HTTP_PORT || "3335", 10),
  apiBase: process.env.TELEGRAM_API_URL || "http://telegram-api:8000",
  mcpHttpToken: process.env.MCP_HTTP_TOKEN || "",
  logLevel: process.env.LOG_LEVEL || "info",
};
