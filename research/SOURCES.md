# Source review — 2026-10-14

Research, not legal advice or a claim that access grants data rights.
Stop reasons distinguish explicit collection bans, access failures and broader use restrictions.

## Added after Codex CLI research — reviewed snapshots

25 observations across four retailers; 12 have explicit pack contents and real unit prices.
The new sources are curated observations, not silently enabled scrapers. `reviewed/latest.json`
stores original capture dates, review dates, source URLs, short pack evidence and document hashes.
Native Codex search supplied discovery; exact prices/weights/currencies were checked against
saved merchant HTTP responses. Search snippets were not imported as verified prices.

- **Strength Shop**: [Deep Dish Cast Iron](https://strengthshop.eu/products/deep-dish-cast-iron-plates-singles-or-sets).
  Four individual plates: 5/10/20/25 kg at €17.99/34.99/68.99/84.99.
  Product JSON-LD explicitly says sold individually, not in pairs; EUR currency explicit.
  [Mainland Spain delivery](https://strengthshop.eu/pages/shipping-deals).
  Generic storefront prices; destination VAT may change. Inspected sales terms had no express
  scraping ban; agent-identity requirements and controlling German terms need further review
  before recurring ingestion. No .js route or Spain checkout quote claimed.
- **ATLETICA**: [Color Bumper Plates](https://atletica.de/products/color-bumper-plates-paarweise-5-25kg),
  five pairs: 2×5/10/15/20/25 kg at €58/88/128/164/198.
  [110 kg set](https://atletica.de/products/color-bumper-plates-set-110kg): €474;
  2×5 + 2×10 + 4×20 kg. HTML/JSON agree; shipping grams ignored.
  [Spain delivery table](https://atletica.de/pages/bestellablauf-zahlung-versand);
  [reviewed legal terms](https://atletica.de/pages/legal-imprints).
  German storefront VAT-inclusive prices, not verified Spanish checkout prices.
  Public product HTML/.js allowed by inspected robots; no express automation ban found
  in inspected terms. No affirmative reuse licence inferred. Best next adapter candidate.
- **Get RXd**: [45 lb cast iron single](https://getrxd.com/products/cast-iron-olympic-plate-45-lbs-piece),
  $62; [25 lb rubber-coated single](https://getrxd.com/products/rubber-coated-olympic-plate-25-lbs-piece),
  $39. Titles explicitly specify one piece; USD/price cross-checked across HTML, JSON-LD and
  embedded variant data. Orderability remains null because signals conflict.
  [Terms](https://getrxd.com/policies/terms-of-service): no express collection ban found;
  generic IP restrictions and automated-agent identification remain distinct concerns.
  No scheduled/authenticated ingestion or actual stock guarantee claimed.

EU rows belong to the Spain-delivery discovery view, not a claim of Spain-localized tax.
No shipping totals inferred from country tariffs. US and EUR prices never mixed.
Original 13 Singular rows remain unranked; no assumed single-plate quantities.

## Local pilot — hosted collection paused

**Singular WOD / Spain**
- [Robots](https://singularwod.com/robots.txt): reviewed public product HTML and .js routes allowed.
- [Sales terms](https://singularwod.com/pages/terminos-y-condiciones): no explicit price-collection ban found in inspected text. No affirmative reuse license inferred.
- Product HTML and .js both HTTP 200; EUR prices cross-checked against HTML JSON-LD.
- [Olímpico](https://singularwod.com/products/disco-olimpico): four variants, 10/15/20/25 kg labels.
- [Training Negro](https://singularwod.com/products/disco-training-negro): five variants, 5/10/15/20/25 kg labels.
- [Training Croma](https://singularwod.com/products/discos-training-croma): four variants, 10/15/20/25 kg labels.
- No explicit pack quantity found. Record prices; no unit-price ranking.
- Shipping weight differs from nominal plate weight (e.g. 10 kg option reports 10.3 kg). Do not normalize from shipping grams.
- Negro page displays reservation wording despite Shopify available=true. Purchasability is not physical stock.
- Croma vendor differs from merchandising brand; not used as manufacturer attribution.
- VAT terms: unless stated otherwise, applicable taxes included for mainland Spain/Balearics. Destination exceptions exist.
- Local collector: 13 offers succeeded at 12:34 UTC. First GitHub-hosted run at 12:37 UTC returned HTTP 429; stopped without retry. Original observations retained, status failed.
- [Runner evidence](https://github.com/MiKatre/platesprice-data/actions/runs/38565263992). Scheduled trigger removed; no proxy/IP-switch workaround.
- Next: approved runner/feed access; confirm units/pairs with merchant, permission/affiliate-feed scope, delivery regions and shipping rules.

## US — not scheduled

| Source | Evidence | Disposition |
|---|---|---|
| Fringe Sport | [Terms](https://www.fringesport.com/pages/terms-of-service), Acceptable Use: automated access and scraping expressly prohibited | Approved feed/permission needed |
| Bells of Steel US | [Terms](https://bellsofsteel.us/policies/terms-of-service), §12(i): spider/crawl/scrape prohibited | Approved feed/permission needed |
| Giant Lifting | [Terms](https://giantlifting.com/pages/terms-of-service), §12(i): spider/crawl/scrape prohibited | Approved feed/permission needed |
| REP Fitness | [Terms](https://repfitness.com/pages/terms-conditions-privacy): harvesting/collecting/gathering/assembling information or data prohibited | Approved feed/permission needed |
| Titan Fitness | [Terms](https://titan.fitness/pages/terms), §12(i): spider/crawl/scrape prohibited | Approved feed/permission needed |
| Rogue Fitness | [Terms request](https://www.roguefitness.com/terms-of-use) returned 403; robots separately disallows /media/feeds | Stopped; terms unknown, no bypass |
| Micro Gainz | [Terms](https://microgainz.com/policies/terms-of-service), §12(i): spider/crawl/scrape prohibited | Approved feed/permission needed |
| The Strength Co. | [Terms](https://www.thestrength.co/policies/terms-of-service), §12(i): spider/crawl/scrape prohibited | Approved feed/permission needed |

Some initial collection HTML exposes explicit pair/set titles and USD prices.
No US JSON product feed was verified after these restrictions were found.
Robots permission alone did not override merchant collection restrictions.
Generic copyright language alone was not treated as an explicit scraping ban.

## Spain — held for review

- **Maniak Fitness**: custom storefront, not Shopify. Public selected-variant pages expose EUR offers, units and stock; some JSON-LD malformed. [Example](https://maniakfitness.com/disco-bumper-training-v3-color-p249?s=795). [Inspected terms](https://maniakfitness.com/condiciones-de-compra) prohibit unauthorized commercial content use; private/personal-use language. Broader use restriction, not a scraping-specific clause. No scheduled adapter pending permission/scope review.
- **Ruster**: WooCommerce, not Shopify. Public product pages expose variation data; some aggregate offers are not sufficient to map exact variants. [Site](https://rusterfitness.com/). [Inspected legal notice](https://rusterfitness.com/aviso-legal-y-condiciones-generales-de-uso/) reserves reproduction/distribution/public communication of content for commercial purposes without permission. Broader IP/use restriction, not an express automation ban. Held for review.

## Claims not validated

- Affiliate rates, cookie durations, acceptance and permitted comparison/data use.
- Competitor count, inventory coverage or shipping omissions.
- Profit score, traffic, conversion rate, revenue.
- Availability of 250+ reliably normalized, permitted offers in a weekend.

## Expansion queue

1. Singular: resolve hosted-access block and pack quantities before enabling scheduled runs.
2. Request approved feeds from Giant/Bells/Fringe; no outreach sent.
3. Maniak/Ruster: clarify reuse scope, then tiny source-specific adapters.
4. Expand only reviewed variants; separately track sources, products, variants and rankable offers.
5. Shipping only when destination and conditions are evidenced. No landed-price promise.

Raw merchant captures remain local research, not committed/public fixtures.
