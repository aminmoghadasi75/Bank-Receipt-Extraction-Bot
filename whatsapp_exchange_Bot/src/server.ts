import express, { Request, Response } from 'express';
import { buildClient, registerEvents } from './bot.js';
import { checkApiHealth } from './apiClient.js';

const PORT = parseInt(process.env.BOT_PORT ?? '3000', 10);

// ─── Express App ──────────────────────────────────────────────────────────────

const app = express();
app.use(express.json());

// Health check endpoint for the bot itself
app.get('/bot/health', async (_req: Request, res: Response) => {
  const apiOk = await checkApiHealth();
  res.json({
    bot_status: 'running',
    fastapi_healthy: apiOk,
    timestamp: new Date().toISOString(),
  });
});

// Status endpoint
app.get('/bot/status', (_req: Request, res: Response) => {
  res.json({
    name: 'WhatsApp Receipt Extraction Bot',
    version: '2.0.0',
    language: 'TypeScript',
    timestamp: new Date().toISOString(),
  });
});

// ─── WhatsApp Client ──────────────────────────────────────────────────────────

async function main(): Promise<void> {
  console.log('🚀 WhatsApp Receipt Bot (TypeScript) starting...');

  // Build and initialize WhatsApp client
  const client = buildClient();
  registerEvents(client);

  // Start Express server
  const server = app.listen(PORT, '0.0.0.0');
  server.on('listening', () => {
    console.log(`📡 Bot HTTP server listening on port ${PORT}`);
    console.log(`   → http://localhost:${PORT}/bot/health`);
    console.log(`   → http://localhost:${PORT}/bot/status`);
  });
  server.on('error', (err: NodeJS.ErrnoException) => {
    if (err.code === 'EADDRINUSE') {
      console.warn(`⚠️  Port ${PORT} already in use. Bot HTTP server disabled.`);
    } else {
      console.error('❌ Express server error:', err.message);
    }
  });

  console.log('⏳ Initializing WhatsApp client...');
  await client.initialize();
}

main().catch((err: Error) => {
  console.error('❌ Fatal error:', err.message);
  process.exit(1);
});
