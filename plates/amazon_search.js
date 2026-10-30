// Runs in Kitesurf's restricted engine: no setTimeout, no arguments to page.evaluate.
await page.goto(__URL__, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('[data-component-type="s-search-result"], form[action*="validateCaptcha"]', { timeout: 20000 });
return await page.evaluate(() => ({
  captcha: !!document.querySelector('form[action*="validateCaptcha"]'),
  deliver: document.querySelector('#glow-ingress-line2') ? document.querySelector('#glow-ingress-line2').innerText.trim() : null,
  results: [...document.querySelectorAll('[data-component-type="s-search-result"]')].map(n => ({
    asin: n.dataset.asin, title: n.querySelector('h2') ? n.querySelector('h2').innerText.trim() : '',
    sponsored: !!n.querySelector('.puis-sponsored-label-text') })),
}));
