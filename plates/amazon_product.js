// Runs in Kitesurf's restricted engine: no setTimeout, no arguments to page.evaluate.
await page.goto(__URL__, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('#productTitle, form[action*="validateCaptcha"]', { timeout: 20000 });
return await page.evaluate(() => {
  const q = s => { const e = document.querySelector(s); return e ? e.innerText.trim().replace(/\s+/g, ' ') : null; };
  return {
    captcha: !!document.querySelector('form[action*="validateCaptcha"]'),
    title: q('#productTitle'),
    price: q('#corePrice_feature_div .a-offscreen') || q('.priceToPay .a-offscreen') || q('#apex_desktop .a-offscreen'),
    availability: q('#availability'),
    seller: q('#merchantInfoFeature_feature_div'),
    selected: [...document.querySelectorAll('[id^="inline-twister-expanded-dimension-text"], [id^="variation_"] .selection')].map(e => e.innerText.trim()),
    details: [...document.querySelectorAll('#productDetails_techSpec_section_1 tr, #productOverview_feature_div tr, #detailBullets_feature_div li')]
      .map(e => e.innerText.replace(/\s+/g, ' ').replace(/[\u200e\u200f]/g, '').trim()).filter(t => t.length < 160),
  };
});
