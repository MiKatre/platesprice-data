// Runs in Kitesurf's restricted engine: no setTimeout, no optional chaining, no page.evaluate arguments.
// __URL__, __ZIP__ and __DELIVER__ are filled in by plates/amazon.py before the script runs.
// Images, media and fonts are skipped: two full Amazon pages otherwise exceed the session memory.
await page.setRequestInterception(true);
page.on('request', r => ['image', 'media', 'font'].includes(r.resourceType()) ? r.abort() : r.continue());
await page.goto(__URL__, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('#glow-ingress-line2, form[action*="validateCaptcha"]', { timeout: 40000 });
// Amazon prices for the visitor's location (Amazon.es drops Spanish VAT abroad). Set the market's
// delivery postcode, as the "Deliver to" box does, then reload the page priced for it.
const moved = await page.evaluate(async () => {
  const label = document.querySelector('#glow-ingress-line2');
  const token = document.querySelector('#glowValidationToken');
  if (!label || !token || new RegExp(__DELIVER__).test(label.innerText)) return false;
  const response = await fetch('/gp/delivery/ajax/address-change.html', { method: 'POST', credentials: 'include',
    headers: { 'content-type': 'application/x-www-form-urlencoded;charset=UTF-8', 'anti-csrftoken-a2z': token.value,
      'x-requested-with': 'XMLHttpRequest' },
    body: 'locationType=LOCATION_INPUT&zipCode=' + __ZIP__ + '&storeContext=generic&deviceType=web&pageType=Detail&actionSource=glow' });
  return (await response.text()).indexOf('"isAddressUpdated":1') !== -1;
});
if (moved) {
  await page.goto(__URL__ + '&th=1', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForSelector('#glow-ingress-line2, form[action*="validateCaptcha"]', { timeout: 40000 });
}
await page.waitForSelector('#productTitle, form[action*="validateCaptcha"]', { timeout: 30000 });
return await page.evaluate(() => {
  const q = s => { const e = document.querySelector(s); return e ? e.innerText.trim().replace(/\s+/g, ' ') : null; };
  return {
    captcha: !!document.querySelector('form[action*="validateCaptcha"]'),
    deliver: q('#glow-ingress-line2'),
    title: q('#productTitle'),
    price: q('#corePrice_feature_div .a-offscreen') || q('.priceToPay .a-offscreen') || q('#apex_desktop .a-offscreen'),
    availability: q('#availability'),
    seller: q('#merchantInfoFeature_feature_div'),
    selected: [...document.querySelectorAll('[id^="inline-twister-expanded-dimension-text"], [id^="variation_"] .selection')].map(e => e.innerText.trim()),
    details: [...document.querySelectorAll('#productDetails_techSpec_section_1 tr, #productOverview_feature_div tr, #detailBullets_feature_div li')]
      .map(e => e.innerText.replace(/\s+/g, ' ').replace(/[‎‏]/g, '').trim()).filter(t => t.length < 160),
  };
});
