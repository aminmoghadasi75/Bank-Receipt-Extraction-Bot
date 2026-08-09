import path from 'path';
import fs from 'fs';
import pino from 'pino';
import qrcodeTerminal from 'qrcode-terminal';
import QRCode from 'qrcode';
import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  downloadContentFromMessage,
  proto,
  WASocket,
  WAMessage,
  Browsers,
  fetchLatestBaileysVersion,
} from '@whiskeysockets/baileys';
import {
  extractReceipt,
  registerReplyId,
  confirmReceipt,
  checkApiHealth,
} from './apiClient.js';

// ─── Paths & Folders ──────────────────────────────────────────────────────────

const AUTH_INFO_DIR = path.join(__dirname, '..', 'auth_info_baileys');
const DOWNLOADS_DIR = path.join(__dirname, '..', 'downloaded_test_images');

if (!fs.existsSync(DOWNLOADS_DIR)) {
  fs.mkdirSync(DOWNLOADS_DIR, { recursive: true });
}

// ─── State Management for Web UI ──────────────────────────────────────────────

export interface SavedImageInfo {
  id: string;
  sender: string;
  timestamp: string;
  fileName: string;
  filePath: string;
  mimeType: string;
  sizeKB: number;
  imageBase64: string;
  fromMe: boolean;
  extractionResult?: any;
}

export interface BotState {
  connectionStatus: 'connecting' | 'qr_ready' | 'connected' | 'disconnected';
  qrDataUrl: string | null;
  userJid: string | null;
  recentImages: SavedImageInfo[];
  logs: Array<{ timestamp: string; level: 'info' | 'warn' | 'error'; text: string }>;
}

const botState: BotState = {
  connectionStatus: 'connecting',
  qrDataUrl: null,
  userJid: null,
  recentImages: [],
  logs: [],
};

function addLog(level: 'info' | 'warn' | 'error', text: string) {
  const timestamp = new Date().toLocaleTimeString('fa-IR');
  botState.logs.unshift({ timestamp, level, text });
  if (botState.logs.length > 50) botState.logs.pop();
  console.log(`[${timestamp}] [${level.toUpperCase()}] ${text}`);
}

export function getBotState(): BotState {
  return botState;
}

// Cache to prevent duplicate processing of messages
const processedMsgIds = new Set<string>();
const MAX_PROCESSED_CACHE = 1000;

function trackProcessedMsg(id: string): boolean {
  if (processedMsgIds.has(id)) {
    return true;
  }
  processedMsgIds.add(id);
  if (processedMsgIds.size > MAX_PROCESSED_CACHE) {
    const firstKey = processedMsgIds.values().next().value;
    if (firstKey) processedMsgIds.delete(firstKey);
  }
  return false;
}

// ─── Media Downloader ─────────────────────────────────────────────────────────

async function downloadImageBuffer(
  imageMsg: proto.IMessage['imageMessage']
): Promise<{ buffer: Buffer; mimeType: string }> {
  if (!imageMsg) {
    throw new Error('Image message is undefined');
  }

  const stream = await downloadContentFromMessage(imageMsg, 'image');
  const chunks: Buffer[] = [];
  for await (const chunk of stream) {
    chunks.push(chunk);
  }
  const buffer = Buffer.concat(chunks);
  const mimeType = imageMsg.mimetype ?? 'image/jpeg';
  return { buffer, mimeType };
}

// ─── Image Processing Handler ─────────────────────────────────────────────────

async function handleImage(
  sock: WASocket,
  msg: WAMessage,
  imageMsg: proto.IMessage['imageMessage']
): Promise<void> {
  const remoteJid = msg.key.remoteJid;
  if (!remoteJid) return;

  const msgId = msg.key.id ?? `msg_${Date.now()}`;
  const fromMe = msg.key.fromMe ?? false;

  addLog('info', `📷 دریافت تصویر از ${remoteJid} (fromMe=${fromMe})`);

  let media: { buffer: Buffer; mimeType: string };
  try {
    media = await downloadImageBuffer(imageMsg);
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    addLog('error', `❌ دانلود تصویر ناموفق بود: ${errorMsg}`);
    await sock.sendMessage(
      remoteJid,
      { text: '❌ خطا در دانلود تصویر از واتساپ. لطفاً پس از چند ثانیه مجدداً تصویر را ارسال کنید.' },
      { quoted: msg }
    );
    return;
  }

  if (!media.buffer || media.buffer.length === 0) {
    addLog('error', '❌ بفر تصویر خالی است.');
    await sock.sendMessage(
      remoteJid,
      { text: '❌ فایل تصویر خالی یا نامعتبر بود.' },
      { quoted: msg }
    );
    return;
  }

  // Save image copy locally in isolated folder
  const ext = media.mimeType.includes('png') ? 'png' : 'jpg';
  const fileName = `receipt_${Date.now()}_${msgId.replace(/[^a-zA-Z0-9]/g, '_')}.${ext}`;
  const filePath = path.join(DOWNLOADS_DIR, fileName);

  fs.writeFileSync(filePath, media.buffer);
  const sizeKB = Math.round((media.buffer.length / 1024) * 10) / 10;
  const base64Data = media.buffer.toString('base64');

  const savedInfo: SavedImageInfo = {
    id: msgId,
    sender: remoteJid,
    timestamp: new Date().toLocaleTimeString('fa-IR'),
    fileName,
    filePath,
    mimeType: media.mimeType,
    sizeKB,
    imageBase64: base64Data,
    fromMe,
  };

  botState.recentImages.unshift(savedInfo);
  if (botState.recentImages.length > 20) botState.recentImages.pop();

  addLog('info', `💾 تصویر با موفقیت ذخیره شد: ${fileName} (${sizeKB} KB)`);

  // Call FastAPI backend
  let result;
  try {
    addLog('info', '⏳ ارسال تصویر به سرور FastAPI جهت استخراج اطلاعات...');
    result = await extractReceipt({
      image_base64: base64Data,
      mime_type: media.mimeType,
      whatsapp_message_id: msgId,
      chat_id: remoteJid,
    });
    savedInfo.extractionResult = result;
  } catch (err) {
    const errMessage = err instanceof Error ? err.message : String(err);
    addLog('error', `❌ خطا در سرور FastAPI: ${errMessage}`);

    const isDown = errMessage.includes('ECONNREFUSED');
    await sock.sendMessage(
      remoteJid,
      {
        text: isDown
          ? '❌ سرور پردازش خاموش است. لطفاً ابتدا `python main.py` را اجرا کنید.'
          : `❌ خطا در پردازش فیش:\n${errMessage}`,
      },
      { quoted: msg }
    );
    return;
  }

  if (!result.success || !result.formatted_text) {
    addLog('warn', `⚠️ استخراج اطلاعات ناموفق: ${result.error ?? 'علت نامشخص'}`);
    await sock.sendMessage(
      remoteJid,
      { text: `❌ خطا در استخراج اطلاعات:\n${result.error ?? 'ناشناخته'}` },
      { quoted: msg }
    );
    return;
  }

  addLog('info', `✅ استخراج موفق فیش شماره #${result.receipt_id}`);
  const sentMsg = await sock.sendMessage(
    remoteJid,
    { text: result.formatted_text },
    { quoted: msg }
  );

  if (sentMsg?.key?.id && result.receipt_id) {
    await registerReplyId({
      receipt_id: result.receipt_id,
      reply_message_id: sentMsg.key.id,
    });
  }
}

// ─── Confirmation Command Handler ─────────────────────────────────────────────

async function handleConfirmation(
  sock: WASocket,
  msg: WAMessage,
  contextInfo?: proto.IContextInfo | null
): Promise<void> {
  const remoteJid = msg.key.remoteJid;
  if (!remoteJid) return;

  addLog('info', `🔄 دستور تایید فیش از ${remoteJid}`);

  const replyMsgId = contextInfo?.stanzaId ?? undefined;

  let result;
  try {
    result = await confirmReceipt({
      reply_message_id: replyMsgId,
      chat_id: remoteJid,
    });
  } catch (err) {
    addLog('error', `❌ خطا در ثبت تایید: ${err}`);
    await sock.sendMessage(
      remoteJid,
      { text: '❌ خطا در تایید فیش در پایگاه داده.' },
      { quoted: msg }
    );
    return;
  }

  if (!result.success) {
    addLog('warn', `⚠️ عدم وجود فیش تایید نشده: ${result.error}`);
    await sock.sendMessage(
      remoteJid,
      { text: `⚠️ فیش در انتظار تایید یافت نشد.\n${result.error ?? ''}` },
      { quoted: msg }
    );
    return;
  }

  addLog('info', `✅ فیش #${result.receipt_id} با موفقیت تایید شد.`);

  let edited = false;
  if (replyMsgId) {
    try {
      await sock.sendMessage(remoteJid, {
        text: result.updated_text,
        edit: {
          remoteJid,
          fromMe: true,
          id: replyMsgId,
        },
      });
      edited = true;
      addLog('info', '✏️ متن پیام قبلی ادیت شد.');
    } catch (editErr) {
      addLog('warn', `⚠️ امکان ویرایش پیام قبلی وجود نداشت: ${editErr}`);
    }
  }

  if (!edited) {
    await sock.sendMessage(
      remoteJid,
      { text: '✅ اطلاعات فیش بانکی با موفقیت تایید شد.' },
      { quoted: msg }
    );
  }
}

// ─── Baileys Client Lifecycle ─────────────────────────────────────────────────

let activeSocket: WASocket | null = null;

export async function startBot(): Promise<WASocket> {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_INFO_DIR);
  const logger = pino({ level: 'silent' });

  botState.connectionStatus = 'connecting';
  addLog('info', '🔄 در حال راه‌اندازی بات واتساپ (Baileys)...');

  let version: [number, number, number] | undefined;
  try {
    const fetched = await fetchLatestBaileysVersion();
    version = fetched.version;
    addLog('info', `📱 نسخه‌ پروتکل واتساپ: v${version.join('.')} (جدیدترین: ${fetched.isLatest})`);
  } catch (err) {
    addLog('warn', `⚠️ خطا در دریافت نسخه‌ اخیر پروتکل واتساپ، استفاده از نسخه پیش‌فرض: ${err}`);
  }

  const sock = makeWASocket({
    version,
    auth: state,
    logger,
    browser: Browsers.macOS('Desktop'),
    printQRInTerminal: false,
    connectTimeoutMs: 60000,
    defaultQueryTimeoutMs: 60000,
    keepAliveIntervalMs: 25000,
    qrTimeout: 60000,
    syncFullHistory: false,
    generateHighQualityLinkPreview: false,
  });

  activeSocket = sock;

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      botState.connectionStatus = 'qr_ready';
      try {
        botState.qrDataUrl = await QRCode.toDataURL(qr);
      } catch (e) {
        botState.qrDataUrl = null;
      }
      addLog('info', '📲 کد QR آماده اسکن است! در مرورگر یا ترمینال اسکن کنید.');
      qrcodeTerminal.generate(qr, { small: true });
    }

    if (connection === 'open') {
      botState.connectionStatus = 'connected';
      botState.qrDataUrl = null;
      botState.userJid = sock.user?.id ?? null;

      addLog('info', `✅ بات واتساپ متصل شد! حساب کاربری: ${sock.user?.id ?? 'فعال'}`);

      const apiOk = await checkApiHealth();
      if (!apiOk) {
        addLog('warn', '⚠️ سرور FastAPI در 127.0.0.1:8000 در دسترس نیست.');
      } else {
        addLog('info', '✅ ارتباط با سرور FastAPI برقرار است.');
      }
    }

    if (connection === 'close') {
      botState.connectionStatus = 'disconnected';
      const statusCode =
        (lastDisconnect?.error as any)?.output?.statusCode ??
        (lastDisconnect?.error as any)?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      addLog('warn', `⚠️ قطع ارتباط (کد: ${statusCode}). تلاش مجدد: ${shouldReconnect}`);

      if (shouldReconnect) {
        setTimeout(() => {
          startBot().catch((err) =>
            addLog('error', `❌ خطا در اتصال مجدد: ${err}`)
          );
        }, 3000);
      } else {
        addLog('error', '❌ جلسه کاری منقضی شد. پوشه auth_info_baileys را حذف کرده و مجدداً تلاش کنید.');
      }
    }
  });

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify' && type !== 'append') return;

    for (const msg of messages) {
      if (!msg.key || !msg.message) continue;

      const remoteJid = msg.key.remoteJid;
      if (
        !remoteJid ||
        remoteJid === 'status@broadcast' ||
        remoteJid.endsWith('@broadcast') ||
        remoteJid.endsWith('@newsletter')
      ) {
        continue;
      }

      const msgId = msg.key.id;
      if (msgId && trackProcessedMsg(msgId)) {
        continue;
      }

      const messageContent = msg.message;

      // Extract image message
      const imageMsg =
        messageContent.imageMessage ||
        messageContent.viewOnceMessage?.message?.imageMessage ||
        messageContent.viewOnceMessageV2?.message?.imageMessage ||
        messageContent.ephemeralMessage?.message?.imageMessage ||
        messageContent.documentWithCaptionMessage?.message?.imageMessage;

      // Extract text body
      const body = (
        messageContent.conversation ||
        messageContent.extendedTextMessage?.text ||
        imageMsg?.caption ||
        ''
      ).trim();

      const isConfirm = ['/تایید', '/confirm', 'تایید', '/تایید شده'].includes(
        body.toLowerCase()
      );

      const contextInfo =
        messageContent.extendedTextMessage?.contextInfo ||
        messageContent.imageMessage?.contextInfo ||
        (messageContent as any)[Object.keys(messageContent)[0]]?.contextInfo;

      try {
        if (imageMsg) {
          await handleImage(sock, msg, imageMsg);
        } else if (isConfirm) {
          await handleConfirmation(sock, msg, contextInfo);
        }
      } catch (err) {
        const detail = err instanceof Error ? err.stack ?? err.message : String(err);
        addLog('error', `❌ خطا در پردازش پیام: ${detail}`);
      }
    }
  });

  return sock;
}

export function getSocket(): WASocket | null {
  return activeSocket;
}
