import dotenv from "dotenv";

dotenv.config();

const explicitApiBase = process.env.TELEGRAM_API_URL || process.env.TELEGRAM_API_BASE || "";
const defaultApiBase = "http://tgapi:8000";
const legacyApiBase = "http://telegram-api:8000";

export const config = {
  port: Number.parseInt(process.env.MCP_HTTP_PORT || "3335", 10),
  apiBase: explicitApiBase || defaultApiBase,
  apiBaseExplicit: explicitApiBase.length > 0,
  defaultApiBase,
  legacyApiBase,
  webBase: process.env.TGWEB_URL || "https://tgweb:8000",
  mcpHttpToken: process.env.MCP_HTTP_TOKEN || "",
  logLevel: process.env.LOG_LEVEL || "info",
};
