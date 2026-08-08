const puppeteer = require('puppeteer');

(async () => {
    console.log('Testing Puppeteer launch...');
    try {
        const browser = await puppeteer.launch({
            headless: 'new',
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu'
            ]
        });
        console.log('✅ Puppeteer Chrome launched successfully!');
        await browser.close();
    } catch (e) {
        console.error('❌ Puppeteer launch failed:', e.message);
    }
})();
