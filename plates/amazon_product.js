// Runs in Kitesurf's restricted engine: no setTimeout, no optional chaining, no page.evaluate arguments.
// __URL__, __ZIP__ and __DELIVER__ are filled in by plates/amazon.py before the script runs.
// Images, media and fonts are skipped to stay within the session memory.
await page.setRequestInterception(true);
page.on('request', r => ['image', 'media', 'font'].includes(r.resourceType()) ? r.abort() : r.continue());
await page.goto(__URL__, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('#productTitle, form[action*="validateCaptcha"]', { timeout: 40000 });
return await page.evaluate(async () => {
  // Amazon prices for the visitor's location (Amazon.es drops Spanish VAT abroad). Set the market's
  // delivery postcode, as the "Deliver to" box does. Amazon sometimes answers with an empty 200.
  const setPostcode = async () => {
    const token = document.querySelector('#glowValidationToken');
    if (!token) return 'no postcode token';
    let answer = '';
    for (let attempt = 0; attempt < 3; attempt++) {
      const response = await fetch('/gp/delivery/ajax/address-change.html', { method: 'POST', credentials: 'include',
        headers: { 'content-type': 'application/x-www-form-urlencoded;charset=UTF-8', 'anti-csrftoken-a2z': token.value,
          'x-requested-with': 'XMLHttpRequest' },
        body: 'locationType=LOCATION_INPUT&zipCode=' + __ZIP__ + '&storeContext=generic&deviceType=web&pageType=Detail&actionSource=glow' });
      const text = await response.text();
      if (text.indexOf('"isAddressUpdated":1') !== -1) return 'moved';
      answer = 'postcode request: HTTP ' + response.status + ', ' + text.length + ' bytes';
    }
    return answer;
  };
  const label = document.querySelector('#glow-ingress-line2');
  const move = label && !new RegExp(__DELIVER__).test(label.textContent) ? await setPostcode() : null;
  let doc = document;
  if (move === 'moved') {
    // Parsed, not rendered: a second rendered page exceeds the session memory and kills it.
    const html = await (await fetch(__URL__ + '&th=1', { credentials: 'include' })).text();
    doc = new DOMParser().parseFromString(html, 'text/html');
    doc.querySelectorAll('script, style').forEach(e => e.remove());
  }
  const clean = e => e.textContent.replace(/\s+/g, ' ').trim();
  const q = s => { const e = doc.querySelector(s); return e ? clean(e) : null; };
  return {
    captcha: !!doc.querySelector('form[action*="validateCaptcha"]'),
    move,
    deliver: q('#glow-ingress-line2'),
    title: q('#productTitle'),
    price: q('#corePrice_feature_div .a-offscreen') || q('.priceToPay .a-offscreen') || q('#apex_desktop .a-offscreen'),
    availability: q('#availability'),
    seller: q('#merchantInfoFeature_feature_div'),
    selected: [...doc.querySelectorAll('[id^="inline-twister-expanded-dimension-text"], [id^="variation_"] .selection')].map(clean),
    details: [...doc.querySelectorAll('#productDetails_techSpec_section_1 tr, #productOverview_feature_div tr, #detailBullets_feature_div li')]
      .map(e => clean(e).replace(/[‎‏]/g, '')).filter(t => t.length < 160),
  };
});
