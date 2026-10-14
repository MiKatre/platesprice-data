# PlatesPrice data

Small, reviewed gym-plate price collector. Public data pipeline; website separate.

**25 observations across 4 retailers: 12 confirmed packs with unit prices;
13 Singular WOD variants still awaiting pack verification.**

- EU storefronts delivering to Spain: Strength Shop, 4 singles; ATLETICA, 5 pairs + 110 kg set.
- US: Get RXd, 2 single plates. Availability unconfirmed.
- These 12 additions are reviewed, dated observations—not automatically refreshed offers.
- Original Singular WOD automated pilot remains paused; do not retry its hosted access block.

Local collection succeeded. First GitHub-hosted collection received HTTP 429;
prior observations retained unchanged. **Schedule paused; manual workflow only**
until an approved runner-access/feed route is verified.

## Run

Python 3.12+, uv, macOS/Linux. Synchronous CLI; hard request deadlines use POSIX signals.

```sh
uv sync --locked --group dev
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked python -m plates.collect
uv run --locked python -m plates.collect --only singularwod-es
```

- `catalog.json`: explicitly reviewed storefronts, product URLs, variant IDs/titles, pack evidence.
- `data/latest.json`: merged validated snapshot; decimal strings, UTC timestamps.
- `reviewed/latest.json`: 12 curated factual observations, pack evidence, raw-response hashes,
  source dates and separate review dates. No merchant images/descriptions copied.
  Collector merges these without network requests or re-dating them.
- `runs/report.json`: ignored local run report; uploaded as a 14-day Actions artifact.
- `research/SOURCES.md`: source findings, exclusions, next decisions.
- No database, browser, login, proxies, API keys, checkout calls or dynamic crawler.

## Automation

GitHub Actions currently manual-only; do not repeatedly dispatch against the blocked host.
Planned cadence after access validation: 02:37, 08:37, 14:37, 20:37 UTC.
Scheduled runs can be delayed; not real-time. GitHub may disable inactive public-repo schedules.

1. Read-only job installs locked dependencies, runs offline tests, collects prices.
2. Artifact carries snapshot + report; no merchant HTML/images/descriptions published.
3. Separate minimal write-enabled job commits only `data/latest.json`.
4. Reject publishing if `master` changed during collection. Never force-push.
5. Partial failures publish good/retained observations, then mark the run failed.

Actions pinned to commit SHAs. Only the collection publisher has write permission.
No website build hook yet: there is no deployed website to rebuild.
Git tracks snapshots; no duplicate per-run JSON history in the repository.

## Collection rules

- Explicit User-Agent; check robots each run, including redirects.
- Wildcards, longest-rule precedence, normalized URLs; no off-origin redirects.
- At least two seconds between request starts; respect longer crawl delays.
- Fail closed on unrecognized robots or Request-rate directives (locked parser has a rate bug).
- Stop a source on 401/403/429. No retry or workaround for blocks.
- One retry for transient network/5xx failures; 30 requests/source maximum.
- 5 MB decoded response cap; 90-second hard source deadline; 10-minute total collection budget.
- Exact reviewed product/variant titles; new variants ignored until reviewed.
- Confirm storefront currency each run. Do not use Shopify shipping grams as plate mass.
- More than 50% price change: quarantine the source; retain approved prior observations.
- Failed refresh: retain only still-approved offers, preserving original timestamps.
- Empty/corrupt previous snapshot fails before overwrite. Missing prices never become zero.

The whole source is retained if any reviewed product fails: deliberately simpler than
a product-level merge. Removed/unreviewed variants cannot reappear through retention.
Large legitimate discounts need review; no automatic quarantine release.

## Read the data correctly

- `price`: variant's advertised price, in `currency`; not checkout/landed price.
- `available`: observed purchasability, **not verified immediate stock**;
  preorders can be true. Null means uncertain/conflicting evidence. `stock_status` stays unknown.
- `sale_unit: unknown`, empty components: pack quantity not verified.
  Total weight and both unit prices must remain null.
- Reviewed single/pair/set components use nominal plate mass.
  Price/kg = price / total included kg; 1 lb = exactly 0.45359237 kg.
- Shipping, delivered price and destination-specific tax treatment remain unknown.
- Historical unit prices remain mathematically valid when pack contents are confirmed;
  display them as recorded prices with original dates/status, not live best-buy claims.
  A current-offer recommendation would additionally require fresh successful observations
  and appropriate availability checks. This repository supplies observations, not guarantees.
- Never call a shipping-unknown offer cheapest delivered. Separate US and Spain;
  do not compare USD and EUR as though they were interchangeable.
- Current Singular evidence supports EUR and nominal variant labels, but **not pack counts**.
  Its terms describe VAT-inclusive mainland/Balearic prices unless stated otherwise;
  destination-specific tax interpretation is not implemented.

## Add a source, simply

1. Read robots and linked merchant terms. Record dated URLs and concrete restrictions.
2. Explicit collection ban, blocked request or uncertain authorization: leave in research;
   request an approved feed/export rather than bypassing.
3. Review a few product variants. Verify currency, pack quantity, nominal mass and price basis.
4. Add an allowlisted product/variant entry. Unknown pack is allowed but unranked.
   Known packs require an exact current evidence phrase in the description/product title
   or the applicable reviewed variant title—not another variant.
5. Add synthetic parser regression tests. Run tests, then one paced live collection.
6. Check GitHub-hosted execution before increasing coverage. Observe several scheduled runs.

Public access and robots permission are not a redistribution license.
Only factual observations and links are published; no merchant creative assets.
No affiliate-rate assumptions, affiliate enrollment or outreach performed.
