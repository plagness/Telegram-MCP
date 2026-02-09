import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для отправки, редактирования, удаления и получения сообщений */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
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
    },
    {
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
    },
    {
      name: "messages.delete",
      description: "Удалить ранее отправленное сообщение по внутреннему ID.",
      parameters: z.object({
        message_id: z.number().int(),
      }),
      execute: async (params) => apiRequest(`/v1/messages/${params.message_id}/delete`, {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
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
    },

    // === Batch 1: Bulk Operations ===
    {
      name: "messages.delete_batch",
      description: "Массовое удаление до 100 сообщений по Telegram message_id (Bot API 7.0).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        message_ids: z.array(z.number().int()).min(1).max(100),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/messages/delete-batch", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "messages.forward_batch",
      description: "Массовая пересылка до 100 сообщений (Bot API 7.0).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        from_chat_id: z.union([z.string(), z.number()]),
        message_ids: z.array(z.number().int()).min(1).max(100),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/messages/forward-batch", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "messages.copy_batch",
      description: "Массовое копирование до 100 сообщений (Bot API 7.0).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        from_chat_id: z.union([z.string(), z.number()]),
        message_ids: z.array(z.number().int()).min(1).max(100),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/messages/copy-batch", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },

    // === Batch 1: Core Edits ===
    {
      name: "messages.edit_caption",
      description: "Редактировать подпись к медиа-сообщению по внутреннему ID.",
      parameters: z.object({
        message_id: z.number().int(),
        bot_id: z.number().int().optional(),
        caption: z.string().optional(),
        parse_mode: z.string().optional(),
        reply_markup: z.record(z.any()).optional(),
      }),
      execute: async (params) => apiRequest(`/v1/messages/${params.message_id}/edit-caption`, {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "messages.edit_markup",
      description: "Изменить inline-клавиатуру существующего сообщения по внутреннему ID.",
      parameters: z.object({
        message_id: z.number().int(),
        bot_id: z.number().int().optional(),
        reply_markup: z.record(z.any()).optional(),
      }),
      execute: async (params) => apiRequest(`/v1/messages/${params.message_id}/edit-markup`, {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "messages.edit_media",
      description: "Заменить медиа в существующем сообщении по внутреннему ID.",
      parameters: z.object({
        message_id: z.number().int(),
        bot_id: z.number().int().optional(),
        media: z.record(z.any()).describe("InputMedia объект"),
        reply_markup: z.record(z.any()).optional(),
      }),
      execute: async (params) => apiRequest(`/v1/messages/${params.message_id}/edit-media`, {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },

    // === Batch 2: sendMessageDraft ===
    {
      name: "messages.draft",
      description: "Отправить черновик сообщения (стриминг LLM, Bot API 9.3). Эфемерный, без записи в БД.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        text: z.string().optional(),
        business_connection_id: z.string().optional(),
        message_thread_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/messages/draft", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },

    // === Batch 4: Live Location ===
    {
      name: "messages.edit_live_location",
      description: "Обновить живую геолокацию по внутреннему ID сообщения.",
      parameters: z.object({
        message_id: z.number().int(),
        bot_id: z.number().int().optional(),
        latitude: z.number(),
        longitude: z.number(),
        horizontal_accuracy: z.number().optional(),
        heading: z.number().int().optional(),
        proximity_alert_radius: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest(`/v1/messages/${params.message_id}/edit-live-location`, {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "messages.stop_live_location",
      description: "Остановить живую геолокацию по внутреннему ID сообщения.",
      parameters: z.object({
        message_id: z.number().int(),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest(`/v1/messages/${params.message_id}/stop-live-location`, {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
  ];
}
