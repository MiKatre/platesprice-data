# PlatesPrice data

Small, reviewed gym-plate price collector. Public data pipeline; website separate.

**Pilot: Singular WOD Spain; 3 products, 13 variants. Pack quantities unverified.
All 13 are unranked observations, not €/kg comparisons. No active US sources yet.**

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
- `data/latest.json`: validated current snapshot; decimal strings, UTC timestamps.
- `runs/report.json`: ignored local run report; uploaded as a 14-day Actions artifact.
- `research/SOURCES.md`: source findings, exclusions, next decisions.
- No database, browser, login, proxies, API keys, checkout calls or dynamic crawler.

## Automation

GitHub Actions: 02:37, 08:37, 14:37, 20:37 UTC; manual dispatch also available.
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
- `available`: Shopify says purchasable. **Not verified immediate stock**;
  preorders can be true. `stock_status` stays unknown.
- `sale_unit: unknown`, empty components: pack quantity not verified.
  Total weight and both unit prices must remain null.
- Reviewed single/pair/set components use nominal plate mass.
  Price/kg = price / total included kg; 1 lb = exactly 0.45359237 kg.
- Shipping, delivered price and destination-specific tax treatment remain unknown.
- Rank only fresh (<24 hours), successful-source offers with verified pack contents
  and non-null unit prices. Show purchaser availability/preorder uncertainty separately.
  This repository provides data, not a public ranking UI.
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
