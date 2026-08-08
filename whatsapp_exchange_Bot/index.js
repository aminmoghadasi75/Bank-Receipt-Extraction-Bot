/**
 * WhatsApp Bank Receipt Extraction Bot
 *
 * Listens for receipt images in WhatsApp (including Message Yourself / self-chats),
 * sends them to the Python FastAPI Gemini Gateway, returns formatted Persian details,
 * and handles /تایید to update status and edit the message.
 */

const fs = require('fs');
const path = require('path');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const axios = require('axios');

const API_BASE_URL = process.env.API_BASE_URL || 'http://127.0.0.1:8000';

console.log('🚀 Initializing WhatsApp Receipt Extraction Bot...');

// Automatically clean up stale Chromium Singleton lock files from previous runs
const sessionDir = path.join(__dirname, '.wwebjs_auth', 'session');
['SingletonLock', 'SingletonCookie', 'SingletonSocket'].forEach(file => {
    const lockPath = path.join(sessionDir, file);
    if (fs.existsSync(lockPath)) {
        try {
            fs.unlinkSync(lockPath);
            console.log(`🧹 Cleaned stale lock file: ${file}`);
        } catch (e) {
            // Ignore if lock removal fails
        }
    }
});

const client = new Client({
    authStrategy: new LocalAuth({
        dataPath: './.wwebjs_auth'
    }),
    webVersionCache: {
        type: 'remote',
        remotePath: 'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.3000.1018949068-alpha.html',
    },
    puppeteer: {
        headless: 'new',
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu',
            '--disable-extensions',
            // Use system proxy for WhatsApp servers, but bypass it for localhost (FastAPI)
            '--proxy-server=http://127.0.0.1:10808',
            '--proxy-bypass-list=127.0.0.1;localhost;::1'
        ]
    }
});

client.on('qr', (qr) => {
    console.log('\n📲 QR Code received! Scan with WhatsApp to log in:\n');
    qrcode.generate(qr, { small: true });
});

client.on('authenticated', () => {
    console.log('🔑 WhatsApp Authentication successful! Waiting for chat sync...');
});

client.on('loading_screen', (percent, message) => {
    console.log(`⏳ Loading WhatsApp Web: ${percent}% - ${message}`);
});

client.on('change_state', (state) => {
    console.log(`🔄 WhatsApp State changed: ${state}`);
});

client.on('ready', () => {
    console.log('====================================================');
    console.log('✅ WhatsApp Bot is READY and listening for messages!');
    console.log('====================================================');
});

client.on('disconnected', (reason) => {
    console.warn('⚠️ WhatsApp Bot Disconnected:', reason);
});

/**
 * Handle incoming/outgoing messages using message_create to support Message Yourself
 */
async function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function downloadMediaWithRetry(msg, retries = 6, delayMs = 2000) {
    await wait(1200);

    for (let attempt = 1; attempt <= retries; attempt++) {
        try {
            console.log(`⏳ Downloading media (attempt ${attempt}/${retries})...`);
            const media = await msg.downloadMedia();
            const length = media?.data?.length ?? 0;
            if (media && length > 0) {
                return media;
            }

            console.warn(
                `⚠️ Attempt ${attempt}/${retries}: Media not ready. hasMedia=${msg.hasMedia} ` +
                `type=${msg.type} dataLength=${length}`
            );
        } catch (dlErr) {
            console.warn(`⚠️ Download media attempt ${attempt}/${retries} failed:`, dlErr.message || dlErr);
        }
        if (attempt < retries) {
            await wait(delayMs * attempt);
        }
    }
    return undefined;
}

client.on('message_create', async (msg) => {
    // 1. Ignore Status broadcast messages (WhatsApp Stories)
    if (!msg || !msg.from || msg.from === 'status@broadcast' || msg.from.endsWith('@broadcast')) {
        return;
    }

    try {
        const bodyText = (msg.body || '').trim().toLowerCase();

        // 2. Process Receipt Images
        if (msg.hasMedia && msg.type === 'image') {
            console.log(`📷 Received image from ${msg.from} (fromMe: ${msg.fromMe})`);

            // Download image media from WhatsApp with retry/backoff for self-sent images
            let media = null;
            try {
                media = await downloadMediaWithRetry(msg);
            } catch (dlErr) {
                console.error('❌ Failed to download image media:', dlErr.message || dlErr);
                await msg.reply('❌ خطا در دانلود تصویر از واتساپ. لطفاً چند ثانیه صبر کنید و دوباره ارسال کنید.');
                return;
            }

            if (!media || !media.data) {
                console.error('❌ Downloaded media is empty or invalid.');
                await msg.reply('❌ فایل تصویر خالی یا نامعتبر بود. لطفاً دوباره تصویر را ارسال کنید.');
                return;
            }

            console.log(`⏳ Sending image to Gemini Extraction API (${media.data.length} chars base64)...`);

            // Call FastAPI /extract-receipt endpoint (Bypass any local system HTTP proxy)
            let response;
            try {
                response = await axios.post(`${API_BASE_URL}/extract-receipt`, {
                    image_base64: media.data,
                    mime_type: media.mimetype || 'image/jpeg',
                    whatsapp_message_id: msg.id._serialized,
                    chat_id: msg.from
                }, { proxy: false, timeout: 60000 });
            } catch (apiErr) {
                const apiErrMsg = apiErr.response && apiErr.response.data 
                    ? JSON.stringify(apiErr.response.data) 
                    : (apiErr.message || String(apiErr));
                console.error('❌ API call error:', apiErrMsg);
                
                if (apiErr.code === 'ECONNREFUSED') {
                    await msg.reply('❌ سرور پردازش (FastAPI) در حال حاضر خاموش است. لطفاً ابتدا python main.py را در یک ترمینال دیگر اجرا کنید.');
                } else {
                    await msg.reply(`❌ خطا در ارتباط با سرور پردازش فیش:\n${apiErrMsg}`);
                }
                return;
            }

            const result = response.data;
            if (result && result.success && result.formatted_text) {
                console.log(`✅ Extraction succeeded (Receipt ID: ${result.receipt_id})`);

                // Send reply message to the image in WhatsApp
                const sentMsg = await msg.reply(result.formatted_text);

                // Register reply message ID in backend database for message editing later
                if (sentMsg && sentMsg.id && sentMsg.id._serialized) {
                    await axios.post(`${API_BASE_URL}/register-reply-id`, {
                        receipt_id: result.receipt_id,
                        reply_message_id: sentMsg.id._serialized
                    }, { proxy: false }).catch(err => console.error('⚠️ Could not register reply_message_id:', err.message));
                }
            } else {
                console.warn('⚠️ Extraction returned error:', result ? result.error : 'Unknown');
                await msg.reply(`❌ خطا در استخراج اطلاعات فیش بانکی:\n${result ? result.error : 'اطلاعات قابل خواندن نبود.'}`);
            }
            return;
        }

        // 3. Process Confirmation Commands (/تایید or /confirm or تایید)
        const isConfirmCmd = bodyText === '/تایید' || bodyText === '/confirm' || bodyText === 'تایید' || bodyText === '/تایید شده';
        if (isConfirmCmd) {
            console.log(`🔄 Received confirmation command from ${msg.from}`);

            let replyMsgId = null;
            let quotedMsg = null;

            if (msg.hasQuotedMsg) {
                try {
                    quotedMsg = await msg.getQuotedMessage();
                    if (quotedMsg && quotedMsg.id) {
                        replyMsgId = quotedMsg.id._serialized;
                    }
                } catch (qErr) {
                    console.warn('⚠️ Could not fetch quoted message:', qErr.message);
                }
            }

            // Call FastAPI /confirm-receipt (Bypass any local system HTTP proxy)
            let confResponse;
            try {
                confResponse = await axios.post(`${API_BASE_URL}/confirm-receipt`, {
                    reply_message_id: replyMsgId,
                    chat_id: msg.from
                }, { proxy: false, timeout: 15000 });
            } catch (confApiErr) {
                const confErrMsg = confApiErr.response && confApiErr.response.data 
                    ? JSON.stringify(confApiErr.response.data) 
                    : (confApiErr.message || String(confApiErr));
                console.error('❌ Confirmation API error:', confErrMsg);
                await msg.reply('❌ خطا در تایید فیش در دیتابیس.');
                return;
            }

            const confResult = confResponse.data;
            if (confResult && confResult.success) {
                console.log(`✅ Receipt ID ${confResult.receipt_id} marked as CONFIRMED!`);

                let edited = false;

                // Attempt to edit the quoted message in WhatsApp
                if (quotedMsg && typeof quotedMsg.edit === 'function') {
                    try {
                        await quotedMsg.edit(confResult.updated_text);
                        edited = true;
                        console.log('✏️ Successfully edited previous WhatsApp message!');
                    } catch (editErr) {
                        console.warn('⚠️ Message edit failed (WhatsApp API limit/permission):', editErr.message);
                    }
                }

                // If editing failed or wasn't a reply, reply with confirmation message
                if (!edited) {
                    await msg.reply('✅ اطلاعات فیش بانکی با موفقیت تایید شد.');
                }
            } else {
                console.warn('⚠️ Confirmation failed:', confResult.error);
                await msg.reply(`⚠️ هیچ فیش در انتظار تاییدی یافت نشد.\n${confResult.error || ''}`);
            }
        }
    } catch (err) {
        const errorDetail = err && err.stack ? err.stack : (err && err.message ? err.message : String(err));
        console.error('❌ Unhandled error handling WhatsApp message:', errorDetail);
    }
});

client.initialize();
