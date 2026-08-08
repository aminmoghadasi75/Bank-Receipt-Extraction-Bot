// Test script to check what's happening during WhatsApp client initialization
const { Client, LocalAuth } = require('whatsapp-web.js');

console.log('✅ whatsapp-web.js module loaded OK');

const client = new Client({
    authStrategy: new LocalAuth({ dataPath: './.wwebjs_auth' }),
    puppeteer: {
        headless: 'new',
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--no-zygote',
            '--disable-gpu',
            '--proxy-server=http://127.0.0.1:10808',
            '--proxy-bypass-list=127.0.0.1;localhost;::1'
        ]
    }
});

console.log('⏳ Calling client.initialize()...');

// Set a 30s timeout to detect hangs
const timeout = setTimeout(() => {
    console.error('❌ TIMEOUT: client.initialize() took more than 30s. Possible causes:');
    console.error('   1. webVersionCache remote URL is unreachable (proxy issue)');
    console.error('   2. Chrome is launching but WhatsApp Web is not loading');
    process.exit(1);
}, 30000);

client.on('qr', (qr) => {
    clearTimeout(timeout);
    console.log('📲 QR received - auth required');
    process.exit(0);
});

client.on('authenticated', () => {
    console.log('🔑 Authenticated!');
});

client.on('loading_screen', (percent, message) => {
    clearTimeout(timeout);
    console.log(`⏳ Loading: ${percent}% - ${message}`);
});

client.on('change_state', (state) => {
    console.log(`🔄 State: ${state}`);
});

client.on('ready', () => {
    clearTimeout(timeout);
    console.log('✅ READY!');
    process.exit(0);
});

client.on('auth_failure', (msg) => {
    clearTimeout(timeout);
    console.error('❌ Auth failure:', msg);
    process.exit(1);
});

client.initialize().catch(err => {
    clearTimeout(timeout);
    console.error('❌ initialize() threw:', err.message);
    process.exit(1);
});
