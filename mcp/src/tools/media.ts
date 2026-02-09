import { z } from "zod";
import type { ToolDef, ApiRequestFn } from "../types.js";

/** Инструменты для отправки медиа (фото, документы, видео, локации и т.д.) */
export function register(apiRequest: ApiRequestFn): ToolDef[] {
  return [
    {
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
    },
    {
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
    },

    // --- Восстановленные инструменты (были потеряны при реврайте) ---
    {
      name: "media.send_video",
      description: "Отправить видео в чат (по URL или file_id).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        video: z.string().describe("URL видео или file_id"),
        caption: z.string().optional(),
        parse_mode: z.string().optional(),
        duration: z.number().int().optional(),
        width: z.number().int().optional(),
        height: z.number().int().optional(),
        reply_to_message_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-video", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "media.send_animation",
      description: "Отправить GIF-анимацию в чат (по URL или file_id).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        animation: z.string().describe("URL анимации или file_id"),
        caption: z.string().optional(),
        parse_mode: z.string().optional(),
        duration: z.number().int().optional(),
        width: z.number().int().optional(),
        height: z.number().int().optional(),
        reply_to_message_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-animation", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "media.send_audio",
      description: "Отправить аудиофайл в чат (по URL или file_id).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        audio: z.string().describe("URL аудио или file_id"),
        caption: z.string().optional(),
        parse_mode: z.string().optional(),
        duration: z.number().int().optional(),
        performer: z.string().optional(),
        title: z.string().optional(),
        reply_to_message_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-audio", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "media.send_voice",
      description: "Отправить голосовое сообщение (по URL или file_id).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        voice: z.string().describe("URL голосового или file_id"),
        caption: z.string().optional(),
        parse_mode: z.string().optional(),
        duration: z.number().int().optional(),
        reply_to_message_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-voice", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "media.send_sticker",
      description: "Отправить стикер в чат (по URL или file_id).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        sticker: z.string().describe("URL стикера или file_id"),
        reply_to_message_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-sticker", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "media.send_media_group",
      description: "Отправить альбом (группу медиа) — от 2 до 10 элементов.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        media: z.array(z.record(z.any())).min(2).max(10).describe("Массив InputMedia объектов"),
        reply_to_message_id: z.number().int().optional(),
        message_thread_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-media-group", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },

    // === Batch 1: getFile ===
    {
      name: "media.get_file",
      description: "Получить file_path для скачивания файла по file_id.",
      parameters: z.object({
        file_id: z.string(),
        bot_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/get-file", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },

    // === Batch 3: Базовые send-методы ===
    {
      name: "media.send_location",
      description: "Отправить геолокацию (координаты). С live_period — живая геолокация.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        latitude: z.number(),
        longitude: z.number(),
        live_period: z.number().int().optional().describe("Период обновления (60-86400 сек)"),
        reply_to_message_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-location", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "media.send_venue",
      description: "Отправить место (venue) с названием, адресом и координатами.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        latitude: z.number(),
        longitude: z.number(),
        title: z.string(),
        address: z.string(),
        foursquare_id: z.string().optional(),
        google_place_id: z.string().optional(),
        reply_to_message_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-venue", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "media.send_contact",
      description: "Отправить контакт (телефон + имя).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        phone_number: z.string(),
        first_name: z.string(),
        last_name: z.string().optional(),
        vcard: z.string().optional(),
        reply_to_message_id: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-contact", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "media.send_dice",
      description: "Отправить анимированный эмодзи-кубик (🎲🎯🏀⚽🎳🎰).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        emoji: z.string().optional().describe("Эмодзи: 🎲, 🎯, 🏀, ⚽, 🎳, 🎰"),
      }),
      execute: async (params) => apiRequest("/v1/media/send-dice", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
    {
      name: "media.send_video_note",
      description: "Отправить видео-кружок (video note) по URL или file_id.",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        video_note: z.string().describe("URL или file_id видео-кружка"),
        duration: z.number().int().optional(),
        length: z.number().int().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-video-note", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },

    // === Batch 8: sendPaidMedia ===
    {
      name: "media.send_paid_media",
      description: "Отправить платный медиа-контент за звёзды (Bot API 7.6).",
      parameters: z.object({
        chat_id: z.union([z.string(), z.number()]),
        bot_id: z.number().int().optional(),
        star_count: z.number().int().describe("Цена в Stars"),
        media: z.array(z.record(z.any())).min(1).max(10),
        caption: z.string().optional(),
        parse_mode: z.string().optional(),
      }),
      execute: async (params) => apiRequest("/v1/media/send-paid-media", {
        method: "POST",
        body: JSON.stringify(params),
      }),
    },
  ];
}
