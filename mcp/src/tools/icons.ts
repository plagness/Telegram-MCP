/**
 * MCP инструменты для Simple Icons — проверка и резолв иконок.
 *
 * Позволяет LLM проверить доступность иконки перед использованием в записях
 * календаря, виджетах и аватарках. Обращается к tgweb API.
 */

import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
      name: "icons.resolve",
      description:
        "Проверить, существует ли SVG-иконка для заданного имени. Поддерживает бренды, крипту, AI-модели, платформы (3300+ иконок). Полезно перед указанием icon в calendar.create_entry.",
      parameters: z.object({
        name: z
          .string()
          .describe(
            "Имя для резолва: slug (bitcoin), алиас (btc), ключевое слово (claude-opus-4-6). Регистронезависимо.",
          ),
      }),
      execute: async (params) =>
        apiRequest(`/api/icons/resolve?name=${encodeURIComponent(params.name)}`),
    },
  ];
}
