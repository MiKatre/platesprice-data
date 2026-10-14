# PlatesPrice data

Public factual weight-plate observations; static website separate. No API keys.

**2026-10-14 seed: 1,031 priced offers, 709 confirmed packs, 16 retailers.**

- Spain/EU: 606 offers; 398 with recorded price/kg. US: 425 offers; 311 with price/kg.
- Seven Shopify catalog collectors discover variants automatically; no per-variant allowlist.
- Eight additional retailers use reviewed WooCommerce/custom-store captures, preserving original dates.
- Singular WOD: original 13 unverified variants retained; source explicitly paused after hosted 429.
- Hampton: partial historical capture, refresh stopped after 403.
- [Coverage, exclusions and next work](research/CATALOGS.md).

## Run

Python 3.12+, uv, macOS/Linux. Hard request deadlines use POSIX signals.

```sh
uv sync --locked --group dev
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked python -m plates.collect --only atletica-eu
uv run --locked python -m plates.collect
```

`paused` sources are never requested, even with `--only`. Clear a pause only after access review.
The manual GitHub workflow remains unscheduled. New catalog adapters have been tested against
saved actual responses and synthetic regressions; hosted access is not yet validated for them.

## Files

- `catalog.json`: approved storefront scope, currency evidence, feed endpoints, pause reasons.
  Legacy exact-product entries remain supported for exceptional reviewed products.
- `plates/normalize.py`: multilingual plate qualification, explicit pack parsing, Decimal pricing.
- `plates/feeds.py`: bounded pagination, duplicate detection, coverage and recoverable issues.
- `data/latest.json`: merged observations, decimal strings, original UTC capture timestamps.
- `reviewed/latest.json`: bulk-reviewed Woo/custom observations; no requests or re-dating on merge.
- `research/coverage.json`: per-storefront counts, capture hashes, access/coverage notes.
- `runs/report.json`: ignored run report; uploaded as a 14-day Actions artifact.
- `tests/fixtures/`: frozen pilot arithmetic cases, independent of live catalog growth.
- `.captures/`: ignored local evidence cache. No merchant HTML, images or descriptions published.

## Collection rules

- Identifying User-Agent; robots checked per run and redirect. No off-origin redirects.
- At least two seconds between starts; honor longer crawl delays.
- Stop on 401/403/429; no proxies, login, cookie negotiation, impersonation or block bypass.
- Fail closed on unrecognized robots and unsupported Request-rate directives.
- One retry for transient network/5xx failures. Maximum 30 requests/source, 5 MB/response,
  90 seconds/source, ten minutes/run. Each feed capped at four pages by default.
- Confirm storefront currency. Shopify feed prices use major units; `.js` prices use cents.
- Classify actual plates; exclude storage, hardware, merchandise and mixed equipment bundles.
- Parse all variants. Explicit quantity + nominal mass required for unit-price arithmetic.
  Never use shipping grams, parent minimum prices or guessed singles.
- Ambiguous packs retain observed prices with null totals/unit prices. Bad variants become issues,
  not a reason to discard unrelated valid catalog rows. Coverage records capped/incomplete feeds.
- Dedupe identities and proven aliases within a retailer. Shared SKU alone cannot collapse
  different colors, sizes or conditions. Never dedupe equivalent offers across retailers.
- More than 50% price change or changed composition: quarantine the affected feed offer.
  Legacy exact-product collectors still quarantine at source level.
- Failed feeds retain observations only when the configured scope/parser signature matches.
  Preserve original dates. Corrupt previous snapshots fail before overwrite.

## Read correctly

- `price`: recorded selected offer price, not a delivered or guaranteed current price.
- `available`: observed purchasability; not physical stock. Null means unresolved evidence.
- `sale_unit: unknown`: empty components and null total weight / unit prices.
- Price/kg = price ÷ total nominal kg of every included plate. 1 lb = exactly 0.45359237 kg.
- `condition`: explicit used/B-stock labels only; unknown does not mean verified new.
- Historical unit-price arithmetic remains valid; age and refresh status are separate.
- EUR storefront prices are not uniformly Spain-localized VAT quotes. No FX conversion.
- Shipping and delivered totals remain unknown. Never treat unknown shipping as free.
- `collection_mode: reviewed`: saved observations, not automatically refreshed catalog data.

## Add coverage

1. Discover relevant public collection feeds or sitemaps, not two sample products.
2. Record robots/access results and exact terms URLs. Distinguish express collection restrictions
   from generic IP notices; unread terms remain unknown, not affirmative permission.
3. Confirm currency and delivery geography. Keep blocked/restricted hosts as explicit exceptions.
4. Add a bounded `feeds` entry. Check complete returned catalogs; separate priced, confirmed,
   ambiguous, duplicate and withheld counts. Preserve variant-level evidence.
5. Add synthetic regressions for new formats; validate one paced capture before enabling refresh.
6. Port reviewed custom/Woo sources to reusable adapters next. Do not silently re-date snapshots.

## GitHub Actions

Manual-only until hosted access is verified. Singular remains individually paused.

1. Read-only job installs locked dependencies, tests offline, collects configured catalogs.
2. Artifact contains snapshot/report, not raw merchant content.
3. Separate minimal write-enabled publisher commits only `data/latest.json`.
4. Refuse stale publication if `master` changed. Never force-push.
5. Publish good/retained observations before signalling partial failure.

Actions pinned to SHAs. No deployed website build hook yet. No affiliate applications or outreach.
