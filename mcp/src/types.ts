import { z } from "zod";

/** Определение инструмента MCP */
export interface ToolDef {
  name: string;
  description: string;
  parameters: z.ZodTypeAny;
  execute: (params: any) => Promise<any>;
}

/** Функция запроса к API */
export type ApiRequestFn = (path: string, options?: RequestInit) => Promise<any>;
