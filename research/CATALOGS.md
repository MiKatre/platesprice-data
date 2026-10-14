# Catalog-scale capture — 2026-10-14

1,031 priced offers; 709 confirmed packs; 16 retailers. No API credentials.

| Retailer | Market | Priced | Confirmed | Refresh |
|---|---|---:|---:|---|
| Singular WOD | ES | 13 | 0 | catalog adapter; paused/failed |
| Again Faster US | US | 75 | 43 | catalog adapter |
| American Barbell | US | 56 | 36 | catalog adapter |
| Bolt Fitness Supply | US | 40 | 39 | catalog adapter |
| Get RXd | US | 23 | 20 | catalog adapter |
| PRx Performance | US | 44 | 29 | catalog adapter |
| ATLETICA | ES | 153 | 73 | catalog adapter |
| Strength Shop EU | ES | 105 | 66 | catalog adapter |
| York Barbell | US | 72 | 62 | reviewed capture |
| Wright Equipment | US | 91 | 71 | reviewed capture |
| Hampton Fitness | US | 24 | 11 | reviewed capture; paused/failed |
| Maniak Fitness | ES | 116 | 106 | reviewed capture |
| Ruster Fitness | ES | 60 | 46 | reviewed capture |
| KingsBox | ES | 40 | 39 | reviewed capture |
| Titanium Strength | ES | 68 | 17 | reviewed capture |
| Sveltus | ES | 51 | 51 | reviewed capture |

## What changed

- Replaced tiny per-variant sampling with complete returned public catalog pages and bounded pagination.
- Seven reusable Shopify feed configurations; new variants discovered automatically.
- Eight additional retailers bulk-extracted from Woo Store API, embedded variations, product JSON and HTML tables.
  These remain reviewed snapshots until their source-specific extraction is integrated into scheduled adapters.
- New terms inspection did not equate generic copyright with an express scraping prohibition.
- All known unit prices rebuilt from Decimal nominal components; short pack evidence retained.
- Independent review removed mixed bar/rack/collar bundles, unpriced family shells and GBP-only captures.
- Ruster decimal attribute slugs corrected from displayed option labels. Sveltus 10kg ×6 correctly totals60kg.
- Accessories/merchandise excluded; shared SKU does not collapse distinct colors. Explicit B-stock identified.

## Boundaries

- 606 EUR observations /398 confirmed;425 USD /311 confirmed. Variants are offers, not distinct product families.
- Counts include historical and unavailable offers; they are not 709 immediately purchasable deals.
- Singular WOD429 and Hampton403 remain paused; original successful observations preserved.
- REP, Fringe, Bells of Steel and Giant remain unresolved named-brand gaps; inspected terms expressly restrict collection.
  See exact URLs/reasons in [coverage.json](coverage.json). No repeated requests to these held hosts.
- Again Faster Europe captured GBP, not EUR: withheld entirely. Again Faster US is USD and included.
- Unknown/unread terms are recorded as unknown, not permission. Public access is not a blanket reuse licence.
- EU shipping-to-Spain evidence recorded separately from destination VAT and delivered costs.
- New adapters have offline actual-response replay and synthetic tests; hosted runner access still needs validation.

## Still unfinished

1. Free-shipping eligibility and destination-aware landed estimates; no fake toggle backed by unknown values.
2. Integrate custom/Woo extraction into repeatable adapters; preserve pause and currency safeguards.
3. Hosted collection checks before scheduling. Resolve specific named-brand feed/access gaps.
4. Public deployment, affiliate verification and launch outreach.

## Evidence

- [coverage.json](coverage.json): factual counts, source/access notes, original capture timestamps and response hashes.
- `catalog.json`: actual feed URLs and currency evidence. `reviewed/latest.json`: custom-source observations.
- Private raw evidence/extractors archived under `.captures/2026-10-14/` (gitignored).
  Original extraction scripts use the research `/tmp` paths; archive is an audit cache, not the production runner.
- Frozen pilot fixtures preserve earlier arithmetic tests; independent coverage guards require ≥250 confirmed offers across ≥10retailers.
