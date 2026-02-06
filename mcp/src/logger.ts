export function log(level: string, message: string, meta: Record<string, unknown> = {}) {
  const payload = {
    level,
    message,
    time: new Date().toISOString(),
    ...meta,
  };
  console.log(JSON.stringify(payload));
}

export const logger = {
  info: (message: string, meta?: Record<string, unknown>) => log("info", message, meta),
  warn: (message: string, meta?: Record<string, unknown>) => log("warn", message, meta),
  error: (message: string, meta?: Record<string, unknown>) => log("error", message, meta),
};
