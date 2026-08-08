import axios, { AxiosError } from 'axios';
import type {
  ExtractReceiptRequest,
  ExtractReceiptResponse,
  RegisterReplyRequest,
  RegisterReplyResponse,
  ConfirmReceiptRequest,
  ConfirmReceiptResponse,
} from './types.js';

const API_BASE = process.env.API_BASE_URL ?? 'http://127.0.0.1:8000';
const TIMEOUT_MS = 60_000;

/**
 * Shared axios instance that bypasses any system proxy for localhost.
 */
const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: TIMEOUT_MS,
  proxy: false,          // bypass system HTTP_PROXY for all requests
  headers: { 'Content-Type': 'application/json' },
});

// ─── Helper ──────────────────────────────────────────────────────────────────

function extractErrorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    if (err.response?.data) return JSON.stringify(err.response.data);
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}

// ─── Health check ─────────────────────────────────────────────────────────────

export async function checkApiHealth(): Promise<boolean> {
  try {
    const { data } = await apiClient.get<{ status: string }>('/health');
    return data.status === 'ok';
  } catch {
    return false;
  }
}

// ─── Extract receipt ──────────────────────────────────────────────────────────

export async function extractReceipt(
  payload: ExtractReceiptRequest
): Promise<ExtractReceiptResponse> {
  try {
    const { data } = await apiClient.post<ExtractReceiptResponse>(
      '/extract-receipt',
      payload
    );
    return data;
  } catch (err) {
    throw new Error(`extractReceipt failed: ${extractErrorMessage(err)}`);
  }
}

// ─── Register reply message ID ────────────────────────────────────────────────

export async function registerReplyId(
  payload: RegisterReplyRequest
): Promise<void> {
  try {
    const { data } = await apiClient.post<RegisterReplyResponse>(
      '/register-reply-id',
      payload
    );
    if (!data.success) {
      console.warn(`⚠️  registerReplyId returned success=false: ${data.error ?? ''}`);
    }
  } catch (err) {
    console.error(`⚠️  registerReplyId failed: ${extractErrorMessage(err)}`);
  }
}

// ─── Confirm receipt ──────────────────────────────────────────────────────────

export async function confirmReceipt(
  payload: ConfirmReceiptRequest
): Promise<ConfirmReceiptResponse> {
  try {
    const { data } = await apiClient.post<ConfirmReceiptResponse>(
      '/confirm-receipt',
      payload,
      { timeout: 15_000 }
    );
    return data;
  } catch (err) {
    throw new Error(`confirmReceipt failed: ${extractErrorMessage(err)}`);
  }
}
