/**
 * TypeScript type definitions for the WhatsApp Receipt Extraction Bot.
 */

/** Response from FastAPI /extract-receipt endpoint */
export interface ExtractReceiptResponse {
  success: boolean;
  receipt_id: string;
  status: string;
  formatted_text: string;
  data: Record<string, unknown>;
  error: string;
  latency_seconds: number;
  cached: boolean;
  used_account_id: string;
  attempts: number;
}

/** Response from FastAPI /register-reply-id endpoint */
export interface RegisterReplyResponse {
  success: boolean;
  error?: string;
}

/** Response from FastAPI /confirm-receipt endpoint */
export interface ConfirmReceiptResponse {
  success: boolean;
  receipt_id: string;
  status: string;
  updated_text: string;
  error?: string;
}

/** Request body for FastAPI /extract-receipt */
export interface ExtractReceiptRequest {
  image_base64: string;
  mime_type: string;
  whatsapp_message_id?: string;
  chat_id?: string;
}

/** Request body for FastAPI /register-reply-id */
export interface RegisterReplyRequest {
  receipt_id: string;
  reply_message_id: string;
}

/** Request body for FastAPI /confirm-receipt */
export interface ConfirmReceiptRequest {
  receipt_id?: string;
  reply_message_id?: string;
  chat_id?: string;
}

/** Bot configuration */
export interface BotConfig {
  apiBaseUrl: string;
  proxyServer?: string;
  proxyBypassList?: string;
  sessionDataPath: string;
  apiRequestTimeoutMs: number;
}
