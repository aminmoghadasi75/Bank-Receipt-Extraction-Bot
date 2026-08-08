import express, { Request, Response } from 'express';
import path from 'path';
import fs from 'fs';
import { startBot, getBotState } from './bot.js';
import { checkApiHealth } from './apiClient.js';

const PORT = parseInt(process.env.PORT ?? process.env.BOT_PORT ?? '3000', 10);
const DOWNLOADS_DIR = path.join(__dirname, '..', 'downloaded_test_images');

// ─── Express App ──────────────────────────────────────────────────────────────

const app = express();
app.use(express.json());

// Serve static downloaded test images
app.use('/downloaded_test_images', express.static(DOWNLOADS_DIR));

// JSON API state endpoint
app.get('/api/state', async (_req: Request, res: Response) => {
  const state = getBotState();
  const apiOk = await checkApiHealth();
  res.json({
    ...state,
    fastApiHealthy: apiOk,
    timestamp: new Date().toISOString(),
  });
});

// HTML Web Dashboard
app.get('/', async (_req: Request, res: Response) => {
  const html = `
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>پنل تست و مدیریت بات واتساپ (@whiskeysockets/baileys)</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;600;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Vazirmatn', sans-serif; }
  </style>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen p-4 md:p-8">
  <div class="max-w-6xl mx-auto space-y-6">
    
    <!-- Header -->
    <header class="bg-slate-800 border border-slate-700 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <div class="flex items-center gap-3">
          <span class="text-3xl">🤖</span>
          <h1 class="text-2xl font-bold text-emerald-400">ربات استخراج فیش بانکی واتساپ</h1>
        </div>
        <p class="text-slate-400 text-sm mt-1">مهاجرت موفق به کتابخانه جدید <code class="bg-slate-900 text-amber-400 px-2 py-0.5 rounded">@whiskeysockets/baileys</code></p>
      </div>

      <!-- Status Badge -->
      <div id="status-badge" class="flex items-center gap-2 px-4 py-2 rounded-full border bg-slate-900 border-slate-700 text-slate-300 font-semibold text-sm">
        <span class="w-3 h-3 rounded-full bg-amber-500 animate-pulse"></span>
        <span id="status-text">در حال راه‌اندازی...</span>
      </div>
    </header>

    <!-- Main Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      <!-- Left Column: Connection & QR Code -->
      <div class="lg:col-span-1 bg-slate-800 border border-slate-700 rounded-2xl p-6 shadow-xl flex flex-col items-center justify-center text-center">
        <h2 class="text-lg font-bold text-slate-200 mb-2">📲 اتصال به واتساپ</h2>
        <p class="text-xs text-slate-400 mb-4">واتساپ گوشی خود را باز کرده و کد QR زیر را اسکن کنید:</p>

        <div id="qr-container" class="bg-white p-4 rounded-xl shadow-inner my-2 min-h-[220px] flex items-center justify-center w-full max-w-[240px]">
          <div class="text-slate-500 text-sm animate-pulse">در حال دریافت QR...</div>
        </div>

        <div class="mt-4 w-full bg-slate-900 border border-slate-700/60 rounded-xl p-3 text-xs text-slate-300 space-y-1 text-right">
          <p class="font-bold text-amber-400 mb-1">💡 راهنمای تست سریع:</p>
          <p>۱. کد QR بالا را با واتساپ گوشی اسکن کنید.</p>
          <p>۲. به صفحه <b>Message Yourself</b> (ارسال پیام به خود) بروید.</p>
          <p>۳. یک عکس فیش ارسال کنید.</p>
          <p>۴. عکس بلافاصله دانلود شده و در بخش تصاویر تست ذخیره می‌شود.</p>
        </div>
      </div>

      <!-- Right Column: Received Receipts & Logs -->
      <div class="lg:col-span-2 space-y-6">
        
        <!-- Saved Test Receipts Gallery -->
        <div class="bg-slate-800 border border-slate-700 rounded-2xl p-6 shadow-xl">
          <div class="flex justify-between items-center mb-4">
            <h2 class="text-lg font-bold text-emerald-400 flex items-center gap-2">
              <span>🖼️</span> تصاویر دانلود شده (تست زنده)
            </h2>
            <span id="image-count" class="text-xs bg-slate-700 text-slate-300 px-3 py-1 rounded-full font-bold">۰ تصویر</span>
          </div>

          <div id="receipts-gallery" class="grid grid-cols-1 sm:grid-cols-2 gap-4 max-h-[360px] overflow-y-auto p-1">
            <div class="col-span-full text-center py-12 text-slate-500 bg-slate-900/50 rounded-xl border border-dashed border-slate-700">
              هنوز تصویری دریافت نشده است.<br/>یک عکس در واتساپ ارسال کنید تا اینجا نمایش داده شود.
            </div>
          </div>
        </div>

        <!-- System Logs -->
        <div class="bg-slate-800 border border-slate-700 rounded-2xl p-6 shadow-xl">
          <h2 class="text-lg font-bold text-slate-200 mb-3 flex items-center gap-2">
            <span>📋</span> رویدادها و گزارش‌های زنده (Live Logs)
          </h2>
          <div id="logs-container" class="bg-slate-950 font-mono text-xs text-slate-300 p-4 rounded-xl border border-slate-800 h-44 overflow-y-auto space-y-1 text-left" dir="ltr">
            <div class="text-slate-500">[System] Initializing Baileys client...</div>
          </div>
        </div>

      </div>
    </div>

  </div>

  <script>
    async function updateDashboard() {
      try {
        const res = await fetch('/api/state');
        const data = await res.json();

        // Update Status
        const statusBadge = document.getElementById('status-badge');
        const statusText = document.getElementById('status-text');

        if (data.connectionStatus === 'connected') {
          statusBadge.className = 'flex items-center gap-2 px-4 py-2 rounded-full border bg-emerald-950 border-emerald-600 text-emerald-300 font-semibold text-sm';
          statusText.innerHTML = '✅ متصل شد (' + (data.userJid || 'حساب فعال') + ')';
        } else if (data.connectionStatus === 'qr_ready') {
          statusBadge.className = 'flex items-center gap-2 px-4 py-2 rounded-full border bg-amber-950 border-amber-600 text-amber-300 font-semibold text-sm';
          statusText.innerText = '📲 منتظر اسکن QR Code';
        } else {
          statusBadge.className = 'flex items-center gap-2 px-4 py-2 rounded-full border bg-rose-950 border-rose-600 text-rose-300 font-semibold text-sm';
          statusText.innerText = '🔴 قطع ارتباط / در حال تلاش';
        }

        // Update QR Code
        const qrContainer = document.getElementById('qr-container');
        if (data.connectionStatus === 'connected') {
          qrContainer.innerHTML = \`
            <div class="text-emerald-600 font-bold text-center py-8">
              <span class="text-4xl">🎉</span><br/>
              اتصال برقرار است!
            </div>
          \`;
        } else if (data.qrDataUrl) {
          qrContainer.innerHTML = \`<img src="\${data.qrDataUrl}" alt="QR Code" class="w-full h-auto rounded-lg"/>\`;
        } else {
          qrContainer.innerHTML = \`<div class="text-slate-400 text-xs text-center py-8">در حال تولید QR...</div>\`;
        }

        // Update Receipts Gallery
        const gallery = document.getElementById('receipts-gallery');
        const countSpan = document.getElementById('image-count');
        countSpan.innerText = (data.recentImages?.length || 0) + ' تصویر';

        if (data.recentImages && data.recentImages.length > 0) {
          gallery.innerHTML = data.recentImages.map(img => \`
            <div class="bg-slate-900 border border-slate-700/80 rounded-xl p-3 flex flex-col gap-2">
              <div class="relative aspect-video bg-slate-950 rounded-lg overflow-hidden border border-slate-800 flex items-center justify-center">
                <img src="data:\${img.mimeType};base64,\${img.imageBase64}" class="object-contain max-h-full max-w-full" alt="Receipt"/>
              </div>
              <div class="text-xs space-y-1">
                <div class="flex justify-between text-slate-300">
                  <span class="font-bold text-emerald-400">\${img.fileName}</span>
                  <span class="text-slate-400">\${img.sizeKB} KB</span>
                </div>
                <div class="text-slate-400 flex justify-between">
                  <span>فرستنده: \${img.sender}</span>
                  <span>\${img.timestamp}</span>
                </div>
                \${img.extractionResult ? \`
                  <div class="bg-slate-950 p-2 rounded text-[11px] text-amber-300 border border-slate-800 mt-1 whitespace-pre-wrap max-h-24 overflow-y-auto">
                    \${img.extractionResult.formatted_text || img.extractionResult.error || 'پردازش شد'}
                  </div>
                \` : ''}
              </div>
            </div>
          \`).join('');
        } else {
          gallery.innerHTML = \`
            <div class="col-span-full text-center py-12 text-slate-500 bg-slate-900/50 rounded-xl border border-dashed border-slate-700">
              هنوز تصویری دریافت نشده است.<br/>یک عکس در واتساپ ارسال کنید تا اینجا نمایش داده شود.
            </div>
          \`;
        }

        // Update Logs
        const logsContainer = document.getElementById('logs-container');
        if (data.logs && data.logs.length > 0) {
          logsContainer.innerHTML = data.logs.map(log => \`
            <div class="\${log.level === 'error' ? 'text-rose-400' : log.level === 'warn' ? 'text-amber-300' : 'text-slate-300'}">
              [\${log.timestamp}] \${log.text}
            </div>
          \`).join('');
        }
      } catch (err) {
        console.error('Error fetching state:', err);
      }
    }

    setInterval(updateDashboard, 2000);
    updateDashboard();
  </script>
</body>
</html>
  `;
  res.send(html);
});

// ─── Main Startup ─────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log('🚀 WhatsApp Receipt Bot (TypeScript + Baileys) starting...');

  // Start Express server
  const server = app.listen(PORT, '0.0.0.0');
  server.on('listening', () => {
    console.log(`📡 Bot Web Control Panel & Dashboard running on port ${PORT}`);
    console.log(`   → http://localhost:${PORT}/`);
  });
  server.on('error', (err: NodeJS.ErrnoException) => {
    if (err.code === 'EADDRINUSE') {
      console.warn(`⚠️ Port ${PORT} already in use.`);
    } else {
      console.error('❌ Express server error:', err.message);
    }
  });

  console.log('⏳ Initializing WhatsApp Baileys client...');
  await startBot();
}

main().catch((err: Error) => {
  console.error('❌ Fatal error:', err.message);
  process.exit(1);
});
