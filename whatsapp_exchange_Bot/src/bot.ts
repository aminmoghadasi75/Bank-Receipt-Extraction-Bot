import fs from 'fs';
import path from 'path';
import qrcode from 'qrcode-terminal';
import { Client, LocalAuth, Message, MessageMedia } from 'whatsapp-web.js';
import {
  extractReceipt,
  registerReplyId,
  confirmReceipt,
  checkApiHealth,
} from './apiClient.js';

// ─── Config ───────────────────────────────────────────────────────────────────

const SESSION_DATA_PATH = path.join(__dirname, '..', '.wwebjs_auth');
const CACHE_DATA_PATH = path.join(__dirname, '..', '.wwebjs_cache');
const WEB_VERSION_CACHE_URL =
  process.env.WEB_VERSION_CACHE_URL ??
  'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.3000.1018949068-alpha.html';
const HTTP_PROXY =
  process.env.HTTP_PROXY ?? process.env.http_proxy ?? 'http://127.0.0.1:10808';
const RESET_WHATSAPP_SESSION = process.env.RESET_WHATSAPP_SESSION === 'true';

// ─── Clean up stale Chromium singleton lock files from previous runs ──────────

function cleanStaleLocks(): void {
  const sessionDir = path.join(SESSION_DATA_PATH, 'session');
  for (const file of ['SingletonLock', 'SingletonCookie', 'SingletonSocket']) {
    const lockPath = path.join(sessionDir, file);
    if (fs.existsSync(lockPath)) {
      try {
        fs.unlinkSync(lockPath);
        console.log(`🧹 Removed stale lock: ${file}`);
      } catch {
        // ignore
      }
    }
  }
}

function removeSessionCache(): void {
  if (!RESET_WHATSAPP_SESSION) return;

  if (fs.existsSync(SESSION_DATA_PATH)) {
    try {
      fs.rmSync(SESSION_DATA_PATH, { recursive: true, force: true });
      console.log('🧹 Removed old WhatsApp session directory (.wwebjs_auth).');
    } catch (err) {
      console.warn('⚠️ Could not remove .wwebjs_auth:', err);
    }
  }

  if (fs.existsSync(CACHE_DATA_PATH)) {
    try {
      fs.rmSync(CACHE_DATA_PATH, { recursive: true, force: true });
      console.log('🧹 Removed old WhatsApp cache directory (.wwebjs_cache).');
    } catch (err) {
      console.warn('⚠️ Could not remove .wwebjs_cache:', err);
    }
  }
}

// ─── Build WhatsApp client ────────────────────────────────────────────────────

export function buildClient(): Client {
  cleanStaleLocks();

  const puppeteerArgs = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-accelerated-2d-canvas',
    '--no-first-run',
    '--no-zygote',
    '--disable-gpu',
    // اضافه کردن User-Agent استاندارد برای جلوگیری از مسدود شدن دانلودها توسط واتساپ
    '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
  ];

  const proxy = process.env.HTTP_PROXY || process.env.HTTPS_PROXY || 'http://127.0.0.1:10808';
  if (proxy) {
    puppeteerArgs.push(`--proxy-server=${proxy}`);
  }

  return new Client({
    authStrategy: new LocalAuth({ dataPath: SESSION_DATA_PATH }),
    // اضافه کردن مجدد webVersionCache که در فرآیند تبدیل به TS حذف شده بود
    webVersionCache: {
      type: 'remote',
      remotePath: 'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.2412.54.html',
    },
    puppeteer: {
      headless: true, // استفاده از true به جای 'new'
      timeout: 120000,
      args: puppeteerArgs,
    },
  });
}

// ─── Event handlers ───────────────────────────────────────────────────────────

async function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function customDownloadMedia(
  client: Client,
  msg: Message,
): Promise<MessageMedia | undefined> {
  try {
    const standardMedia = await msg.downloadMedia();
    if (standardMedia && standardMedia.data) {
      return standardMedia;
    }
  } catch (err) {
    console.warn('⚠️ Standard downloadMedia failed, trying browser fallback extraction...');
  }

  const msgId = msg.id._serialized;
  if (!client.pupPage) {
    return undefined;
  }

  try {
    const fallback = await client.pupPage.evaluate(async (targetId) => {
      const globalAny = globalThis as any;
      const win = globalAny.window || globalAny;
      const doc: any = win.document;
      const Store = win.Store ?? win?.Store;

      let msgObj = Store?.Msg?.get?.(targetId);
      if (!msgObj && win?.require) {
        try {
          msgObj = win.require('WAWebCollections')?.Msg?.get?.(targetId);
        } catch {
          // ignore
        }
      }

      if (!msgObj && Store?.Msg?.models) {
        try {
          for (const value of Store.Msg.models.values()) {
            const candidateId =
              value?.id?._serialized ?? value?.id?.serialized ?? value?.id;
            if (candidateId === targetId || String(candidateId) === targetId) {
              msgObj = value;
              break;
            }
          }
        } catch {
          // ignore
        }
      }

      if (msgObj) {
        let blob = msgObj?.mediaData?.blob;
        if (!blob && typeof msgObj.downloadMedia === 'function') {
          try {
            await msgObj.downloadMedia({
              downloadEvenIfExpensive: true,
              rmrReason: 1,
            });
            blob = msgObj?.mediaData?.blob;
          } catch {
            // ignore
          }
        }

        if (blob) {
          const buffer = await blob.arrayBuffer();
          const bytes = new Uint8Array(buffer);
          let binary = '';
          for (let i = 0; i < bytes.length; i += 1) {
            binary += String.fromCharCode(bytes[i]);
          }
          const base64 = win.btoa ? win.btoa(binary) : '';
          return {
            data: base64,
            mimetype: msgObj?.mimetype || blob.type || 'image/jpeg',
            filename: msgObj?.filename,
          };
        }
      }

      const selectors = [
        `[data-id="${targetId}"] img[src^="blob:"], [data-id="${targetId}"] source[src^="blob:"], [data-id="${targetId}"] [style*="blob:"]`,
        'img[src^="blob:"], source[src^="blob:"], [style*="blob:"]',
      ];

      let blobUrl: string | null = null;
      for (const selector of selectors) {
        const element = doc?.querySelector(selector) as any;
        if (!element) continue;

        if (element?.src && typeof element.src === 'string') {
          blobUrl = element.src;
        } else if (element?.getAttribute) {
          const style = element.getAttribute('style') || '';
          const match = style.match(/(blob:[^"'\s]+)/);
          if (match) {
            blobUrl = match[1];
          }
        }

        if (blobUrl) break;
      }

      if (!blobUrl && doc?.querySelector) {
        const img = doc.querySelector('img[src^="blob:"]') as any;
        if (img?.src) {
          blobUrl = img.src;
        }
      }

      if (blobUrl && typeof win.fetch === 'function') {
        const resp = await win.fetch(blobUrl);
        const fetchedBlob = await resp.blob();
        const buffer = await fetchedBlob.arrayBuffer();
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.length; i += 1) {
          binary += String.fromCharCode(bytes[i]);
        }
        const base64 = win.btoa ? win.btoa(binary) : '';
        return {
          data: base64,
          mimetype: fetchedBlob.type || 'image/jpeg',
        };
      }

      return null;
    }, msgId);

    if (fallback && fallback.data) {
      return new MessageMedia(
        fallback.mimetype ?? 'image/jpeg',
        fallback.data,
        fallback.filename ?? 'receipt.jpg',
      );
    }
  } catch (fallbackErr) {
    console.error('❌ Fallback media extraction error:', fallbackErr);
  }

  return undefined;
}

async function downloadMediaWithRetry(
  client: Client,
  msg: Message,
  retries = 8,
  delayMs = 2500
): Promise<MessageMedia | undefined> {
  await wait(2200);

  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      console.log(`⏳ Downloading media (attempt ${attempt}/${retries})...`);
      const media = await customDownloadMedia(client, msg);
      const length = media?.data?.length ?? 0;
      if (media && length > 0) {
        return media;
      }

      console.warn(
        `⚠️ Attempt ${attempt}/${retries}: Media not ready. ` +
          `from=${msg.from} hasMedia=${msg.hasMedia} type=${msg.type} dataLength=${length}`
      );
    } catch (err) {
      const errStr = err instanceof Error ? err.message : String(err);
      console.warn(`⚠️ Download media attempt ${attempt}/${retries} failed:`, errStr);
    }

    if (attempt < retries) {
      await wait(delayMs * attempt);
    }
  }
  return undefined;
}

async function handleImage(client: Client, msg: Message): Promise<void> {
  console.log(`📷 Image from ${msg.from} (fromMe=${msg.fromMe})`);

  let media: MessageMedia | undefined;
  try {
    media = await downloadMediaWithRetry(client, msg);
  } catch (err) {
    console.error('❌ Failed to download media after retries:', err);
    await msg.reply('❌ خطا در دانلود تصویر از واتساپ. لطفاً پس از چند ثانیه مجدداً تصویر را ارسال کنید.');
    return;
  }

  if (!media?.data) {
    console.error('❌ Media data is empty.');
    await msg.reply('❌ فایل تصویر خالی یا نامعتبر بود.');
    return;
  }

  console.log(`⏳ Sending ${media.data.length} chars to FastAPI...`);

  let result;
  try {
    result = await extractReceipt({
      image_base64: media.data,
      mime_type: media.mimetype ?? 'image/jpeg',
      whatsapp_message_id: msg.id._serialized,
      chat_id: msg.from,
    });
  } catch (err) {
    const msg2 = err instanceof Error ? err.message : String(err);
    console.error('❌ extractReceipt error:', msg2);

    const isDown = msg2.includes('ECONNREFUSED');
    await msg.reply(
      isDown
        ? '❌ سرور پردازش خاموش است. لطفاً ابتدا `python main.py` را اجرا کنید.'
        : `❌ خطا در پردازش فیش:\n${msg2}`
    );
    return;
  }

  if (!result.success || !result.formatted_text) {
    console.warn('⚠️  Extraction failed:', result.error);
    await msg.reply(`❌ خطا در استخراج اطلاعات:\n${result.error ?? 'ناشناخته'}`);
    return;
  }

  console.log(`✅ Extracted (ID: ${result.receipt_id})`);
  const sentMsg = await msg.reply(result.formatted_text);

  if (sentMsg?.id?._serialized) {
    await registerReplyId({
      receipt_id: result.receipt_id,
      reply_message_id: sentMsg.id._serialized,
    });
  }
}

async function handleConfirmation(msg: Message): Promise<void> {
  console.log(`🔄 Confirmation command from ${msg.from}`);

  let replyMsgId: string | undefined;
  let quotedMsg: Message | undefined;

  if (msg.hasQuotedMsg) {
    try {
      quotedMsg = await msg.getQuotedMessage();
      replyMsgId = quotedMsg?.id?._serialized;
    } catch (err) {
      console.warn('⚠️  Could not get quoted message:', err);
    }
  }

  let result;
  try {
    result = await confirmReceipt({
      reply_message_id: replyMsgId,
      chat_id: msg.from,
    });
  } catch (err) {
    console.error('❌ confirmReceipt error:', err);
    await msg.reply('❌ خطا در تایید فیش در پایگاه داده.');
    return;
  }

  if (!result.success) {
    console.warn('⚠️  Confirm failed:', result.error);
    await msg.reply(
      `⚠️ فیش در انتظار تایید یافت نشد.\n${result.error ?? ''}`
    );
    return;
  }

  console.log(`✅ Receipt ${result.receipt_id} CONFIRMED`);

  // Try to edit the quoted bot message
  let edited = false;
  if (quotedMsg && typeof (quotedMsg as Message & { edit?: (text: string) => Promise<void> }).edit === 'function') {
    try {
      await (quotedMsg as Message & { edit: (text: string) => Promise<void> }).edit(
        result.updated_text
      );
      edited = true;
      console.log('✏️  Message edited successfully.');
    } catch (editErr) {
      console.warn('⚠️  Edit failed (WhatsApp limit):', editErr);
    }
  }

  if (!edited) {
    await msg.reply('✅ اطلاعات فیش بانکی با موفقیت تایید شد.');
  }
}

// ─── Register all client events ───────────────────────────────────────────────

export function registerEvents(client: Client): void {
  client.on('qr', (qr: string) => {
    console.log('\n📲 QR Code - اسکن کنید:\n');
    qrcode.generate(qr, { small: true });
  });

  client.on('authenticated', () => {
    console.log('🔑 Authentication successful!');
  });

  client.on('loading_screen', (percent: number, message: string) => {
    console.log(`⏳ Loading: ${percent}% - ${message}`);
  });

  client.on('change_state', (state: string) => {
    console.log(`🔄 State: ${state}`);
  });

  client.on('ready', async () => {
    console.log('══════════════════════════════════════════');
    console.log('✅ WhatsApp Bot is READY!');
    console.log('══════════════════════════════════════════');

    const apiOk = await checkApiHealth();
    if (!apiOk) {
      console.warn('⚠️  FastAPI server is not reachable at 127.0.0.1:8000!');
      console.warn('   Run: python main.py (in project root terminal)');
    } else {
      console.log('✅ FastAPI server is UP and healthy.');
    }
  });

  client.on('disconnected', (reason: string) => {
    console.warn('⚠️  Disconnected:', reason);
  });

  client.on('auth_failure', (msg: string) => {
    console.error('❌ Auth failure:', msg);
  });

  // Use message_create to capture self-messages (Message Yourself)
  client.on('message_create', async (msg: Message) => {
    if (!msg?.from) return;

    // Log all incoming/created messages for debugging
    console.log(
      `📩 [Message Event] from=${msg.from} | type=${msg.type} | hasMedia=${msg.hasMedia} | fromMe=${msg.fromMe}`
    );

    // Skip WhatsApp Status updates, newsletters, and broadcast channels
    if (
      msg.from === 'status@broadcast' ||
      msg.from.endsWith('@broadcast') ||
      msg.from.endsWith('@newsletter')
    ) {
      return;
    }

    try {
      if (msg.hasMedia && msg.type === 'image') {
        console.log('📷 Image detected! Processing receipt...');
        await handleImage(client, msg);
        return;
      }

      const body = (msg.body ?? '').trim();
      const isConfirm = ['/تایید', '/confirm', 'تایید', '/تایید شده'].includes(
        body.toLowerCase()
      );
      if (isConfirm) {
        console.log('🔄 Confirmation command detected! Processing...');
        await handleConfirmation(msg);
      }
    } catch (err) {
      const detail = err instanceof Error ? err.stack ?? err.message : String(err);
      console.error('❌ Unhandled error in message_create:', detail);
    }
  });
}
