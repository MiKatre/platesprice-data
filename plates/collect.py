"""Collect once; preserve last good offers, report failures, never invent zeros."""

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .adapters import check_currency, parse_product
from .feeds import catalog_signature, collect_feeds
from .fetch import USER_AGENT, Fetcher
from .models import Catalog, Snapshot, SourceState

ROOT = Path(__file__).resolve().parents[1]


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def retained_offers(source, previous):
    approved = {f"{source.id}:{v.id}": (p, v) for p in source.products for v in p.variants}
    retained = []
    for offer in previous.offers if previous else []:
        spec = approved.get(offer.id)
        if (
            source.feeds
            and previous.catalog_signature == catalog_signature(source)
            and offer.market == source.market
            and offer.currency == source.currency
            and offer.tax_basis == source.tax_basis
            and urlsplit(offer.source_url)[:2] == urlsplit(source.origin)[:2]
            and spec is None
        ):
            retained.append(offer)
        elif spec and (
            offer.market == source.market
            and offer.currency == source.currency
            and offer.components == spec[1].components
            and offer.sale_unit == spec[1].sale_unit
            and offer.title == spec[0].title
            and offer.variant_title == spec[1].title
            and offer.plate_type == spec[0].plate_type
            and offer.tax_basis == source.tax_basis
            and offer.source_url == f"{spec[0].url}?variant={spec[1].id}"
        ):
            retained.append(offer)
    return retained


def collect_source(source, fetcher, previous=None, *, now=None):
    at = now or datetime.now(timezone.utc)
    retained = retained_offers(source, previous)
    state = SourceState(
        id=source.id,
        name=source.name,
        status="failed",
        attempted_at=at,
        offers=retained,
        last_success_at=previous.last_success_at if previous else None,
        retained_previous=bool(retained),
        catalog_signature=catalog_signature(source) if source.feeds else None,
    )
    try:
        check_currency(fetcher.get(source.currency_evidence_url), source.currency)
        offers = []
        for product in source.products:
            body = fetcher.get(product.data_url)
            offers.extend(parse_product(source, product, body, at))
        if source.feeds:
            discovered, state.coverage, state.issues = collect_feeds(source, fetcher, at)
            reviewed_ids = {o.id for o in offers}
            offers.extend(o for o in discovered if o.id not in reviewed_ids)
        ids = [o.id for o in offers]
        if not offers or len(ids) != len(set(ids)):
            raise ValueError("empty or duplicate offers")
        old = {o.id: o for o in state.offers}
        accepted = []
        for offer in offers:
            prior = old.get(offer.id)
            if prior and (
                prior.components != offer.components
                or prior.currency != offer.currency
                or prior.market != offer.market
                or abs(offer.price / prior.price - 1) > Decimal("0.50")
            ):
                message = f"review required: weight/currency/market/price changed: {offer.id}"
                if source.feeds:
                    state.issues.append(message)
                    state.coverage["quarantined_variants"] = (
                        state.coverage.get("quarantined_variants", 0) + 1
                    )
                    continue
                state.status = "quarantined"
                raise ValueError(message)
            accepted.append(offer)
        if not accepted:
            state.status = "quarantined"
            raise ValueError("all offers require review")
        state.status = "ok"
        state.offers = accepted
        if source.feeds:
            state.coverage.update(
                priced_variants=len(accepted),
                confirmed_packs=sum(o.sale_unit != "unknown" for o in accepted),
                unconfirmed_packs=sum(o.sale_unit == "unknown" for o in accepted),
            )
        state.last_success_at = at
        state.retained_previous = False
    except Exception as exc:  # isolate malformed responses; never swallow process interrupts
        state.error = f"{type(exc).__name__}: {str(exc)[:300]}"
    state.documents = fetcher.documents
    return state


def run(catalog, previous, client, only=None):
    old = {s.id: s for s in previous.sources} if previous else {}
    states = []
    attempted = []
    deadline = time.monotonic() + 600
    for source in catalog.sources:
        if source.paused or (only and source.id not in only):
            if source.id in old:
                prior = old[source.id]
                offers = retained_offers(source, prior)
                states.append(
                    prior.model_copy(
                        update={
                            "offers": offers,
                            "retained_previous": prior.retained_previous and bool(offers),
                        }
                    )
                )
            elif source.paused:
                states.append(
                    SourceState(
                        id=source.id,
                        name=source.name,
                        status="failed",
                        attempted_at=datetime.now(timezone.utc),
                        error=f"Paused without request: {source.pause_reason}",
                    )
                )
            continue
        fetcher = Fetcher(client, source.origin)
        if hasattr(fetcher, "deadline"):
            fetcher.deadline = min(fetcher.deadline, deadline)
        state = collect_source(source, fetcher, old.get(source.id))
        states.append(state)
        attempted.append(state)
        print(
            f"{source.id}: {state.status}, {len(state.offers)} offers"
            + (f" ({state.error})" if state.error else ""),
            file=sys.stderr,
        )
    snapshot = Snapshot(generated_at=datetime.now(timezone.utc), sources=states)
    return snapshot, attempted


def merge_reviewed(snapshot, reviewed):
    """Curated facts are not re-fetched, nor re-dated by a scraper run."""
    if reviewed is None:
        return snapshot
    ids = {s.id for s in snapshot.sources}
    if ids.intersection(s.id for s in reviewed.sources):
        raise ValueError("reviewed and automated source IDs overlap")
    if any(s.collection_mode != "reviewed" for s in reviewed.sources):
        raise ValueError("reviewed file contains an automated source")
    return Snapshot(generated_at=snapshot.generated_at, sources=snapshot.sources + reviewed.sources)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "catalog.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/latest.json")
    parser.add_argument("--report", type=Path, default=ROOT / "runs/report.json")
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--reviewed", type=Path, default=ROOT / "reviewed/latest.json")
    args = parser.parse_args(argv)
    catalog = Catalog.model_validate_json(args.catalog.read_text())
    if not catalog.sources:
        parser.error("catalog is empty")
    if args.only and set(args.only) - {s.id for s in catalog.sources}:
        parser.error("--only contains unknown source IDs")
    # Validate before any network activity or writes. Never overwrite corrupt input.
    previous = (
        Snapshot.model_validate_json(args.output.read_text()) if args.output.exists() else None
    )
    reviewed = (
        Snapshot.model_validate_json(args.reviewed.read_text()) if args.reviewed.exists() else None
    )
    if reviewed and {s.id for s in reviewed.sources}.intersection(s.id for s in catalog.sources):
        parser.error("reviewed sources cannot also be automatically collected")
    with httpx.Client(
        timeout=httpx.Timeout(20),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9"},
        follow_redirects=False,
    ) as client:
        snapshot, attempted = run(catalog, previous, client, args.only)
    snapshot = merge_reviewed(snapshot, reviewed)
    payload = snapshot.model_dump(mode="json")
    atomic_json(args.output, payload)
    summary = {
        "generated_at": payload["generated_at"],
        "attempted": len(attempted),
        "ok": sum(s.status == "ok" for s in attempted),
        "offers": sum(len(s.offers) for s in attempted if s.status == "ok"),
        "failed": [s.id for s in attempted if s.status != "ok"],
        "paused": [s.id for s in catalog.sources if s.paused],
        "coverage": {
            "storefronts_with_prices": sum(bool(s.offers) for s in snapshot.sources),
            "priced_offers": sum(len(s.offers) for s in snapshot.sources),
            "confirmed_packs": sum(
                o.sale_unit != "unknown" for s in snapshot.sources for o in s.offers
            ),
        },
        "reviewed_offers": sum(
            len(s.offers) for s in snapshot.sources if s.collection_mode == "reviewed"
        ),
        "snapshot": payload,
    }
    atomic_json(args.report, summary)
    # Publish partial progress, but make degraded runs visible in Actions.
    return 0 if all(s.status == "ok" for s in attempted) else 1


if __name__ == "__main__":
    raise SystemExit(main())
