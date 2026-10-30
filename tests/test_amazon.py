"""Amazon trial parsing on synthetic page extracts. No browser sessions or requests."""

from decimal import Decimal

from plates.amazon import availability, collect, offer, pack, parse_price, script
from plates.models import Offer
from tests.conftest import AT


def page(title="VirtuFit Hi-Temp Bumper Plate - Rubber Olympic Disc - 50mm", **extra):
    return {
        "captcha": False,
        "deliver": "Madrid 28001",
        "title": title,
        "price": "79,95€",
        "availability": "En stock",
        "seller": "Vendido por VirtuFit",
        "selected": ["25 kg"],
        "details": ["Marca VirtuFit", "Número de productos 1"],
        **extra,
    }


def test_prices_follow_the_storefront_format():
    assert parse_price("75,99€", "EUR") == Decimal("75.99")
    assert parse_price("1.234,50 €", "EUR") == Decimal("1234.50")
    assert parse_price("$1,234.50", "USD") == Decimal("1234.50")
    assert parse_price(None, "EUR") is None
    assert parse_price("Ver opciones", "EUR") is None
    # Amazon.com shows converted prices to visitors abroad.
    assert parse_price("EUR 68.00", "USD") is None
    assert parse_price("$68.00", "EUR") is None


def test_availability_wording():
    assert availability("En stock") is True
    assert availability("Only 3 left in stock - order soon.") is True
    assert availability("No disponible por el momento.") is False
    assert availability("Currently unavailable.") is False
    assert availability("Normalmente se envía en 1 a 2 meses") is None


def test_pack_needs_one_mass_and_an_item_count():
    assert pack("Rubber Bumper Plate", ["25 kg"], ["Número de productos 1"])[0][0].kg == 25
    pair = pack("PROIRON Discos de Goma de 5-25KG, 1/2 Pcs", ["2*5kg"], [])[0]
    assert [(c.weight, c.count) for c in pair] == [(5, 2)]
    # A family range is not the selected plate, and a missing count stays unknown.
    assert pack("Olympic Bumper Plates 5-25 kg", [], ["Number of Items 2"]) == ([], None)
    assert pack("Olympic Bumper Plate 20 kg", [], []) == ([], None)
    # The size label's explicit count wins over the listing count and over the title.
    assert [
        (c.weight, c.count) for c in pack("Disco Bumper", ["2 x 5kg"], ["Número de productos 1"])[0]
    ] == [(5, 2)]
    assert [(c.weight, c.count) for c in pack("2 Discos 15 kg", ["2x10 kg"], [])[0]] == [(10, 2)]
    assert [(c.weight, c.count) for c in pack("Micro", ["2 x 0,5 kg"], [])[0]] == [
        (Decimal("0.5"), 2)
    ]
    combo = pack("Discos Bumper", ["COMBO 70KG (2x5kg, 2x10kg, 2x15kg)"], [])[0]
    assert sum(c.kg for c in combo) == 60 and len(combo) == 3
    assert [(c.weight, c.count) for c in pack("Juego 2x5 kg y 2x10 kg", [], [])[0]] == [
        (5, 2),
        (10, 2),
    ]
    # US size labels name the pack instead of counting plates.
    assert [
        (c.weight, c.unit, c.count) for c in pack("Bumper Plate", ["45-Pound, Single"], [])[0]
    ] == [(45, "lb", 1)]
    assert [(c.weight, c.count) for c in pack("Bumper Plate", ["10lbs Pair, Black"], [])[0]] == [
        (10, 2)
    ]
    # Change-plate groups: each plate in brackets, N times; a wrong stated total stays unknown.
    group = pack("Change Weight Plates", ["17.5 LB (1.25+2.5+5) x2"], [])[0]
    assert [(c.weight, c.unit, c.count) for c in group] == [
        (Decimal("1.25"), "lb", 2),
        (Decimal("2.5"), "lb", 2),
        (5, "lb", 2),
    ]
    assert sum(c.count for c in pack("Change", ["15 LB (2.5LB+5LB)X2"], [])[0]) == 4
    assert pack("Change", ["20 LB (1.25+2.5+5) x2"], [])[0] == []
    # Several masses without an explicit composition stay unknown.
    assert pack("Set of 6 Olympic Plates 2x10kg 4x5kg", [], ["Number of Items 6"])[0] != []
    assert pack("Olympic Plates 10 kg and 5 kg", [], ["Number of Items 6"]) == ([], None)


def test_offer_records_unit_prices_and_seller():
    item = offer("ES", "B0CSGB8C87", page(), AT)
    Offer.model_validate_json(item.model_dump_json())
    assert (item.sale_unit, item.total_weight_kg, item.price_per_kg) == (
        "single",
        25,
        Decimal("3.198000"),
    )
    assert item.source_url == "https://www.amazon.es/dp/B0CSGB8C87"
    assert item.available is True and "VirtuFit" in item.price_basis
    unknown = offer("ES", "B0X", page(details=[]), AT)
    assert unknown.sale_unit == "unknown" and unknown.price_per_kg is None


def test_offer_skips_non_plates_and_missing_prices():
    assert offer("ES", "B0X", page(title="Barra olímpica 20 kg con discos"), AT) is None
    assert offer("ES", "B0X", page(title="Esterilla de yoga"), AT) is None
    assert offer("ES", "B0X", page(price=None), AT) is None


def test_collect_counts_captchas_and_errors_without_stopping():
    def run(source):
        if "/s?k=discos+bumper" in source:
            return {
                "captcha": False,
                "deliver": "Madrid 28071",
                "results": [
                    {"asin": "B1", "title": "Bumper Plate 25 kg", "sponsored": False},
                    {"asin": "B2", "title": "Bumper Plate 20 kg", "sponsored": False},
                    {"asin": "B3", "title": "Bumper Plate 15 kg", "sponsored": False},
                    {"asin": "B4", "title": "Bumper Plate 10 kg", "sponsored": True},
                    {"asin": "B5", "title": "Barbell rack", "sponsored": False},
                ],
            }
        if "/s?k=" in source:
            raise RuntimeError("Navigation timeout")
        if "/dp/B2" in source:
            return {**page(), "captcha": True}
        if "/dp/B3" in source:
            raise RuntimeError("session is dead")
        return page()

    state, stats = collect("ES", run)
    assert (stats["searches"], stats["search_ok"], stats["products"]) == (3, 1, 3)
    assert (stats["loaded"], stats["captcha"], stats["offers"], stats["per_kg"]) == (1, 1, 1, 1)
    assert len(stats["errors"]) == 3 and stats["retried"] == 1
    assert state.status == "ok" and [o.variant_id for o in state.offers] == ["B1"]


def test_product_script_sets_the_market_postcode():
    source = script("product", "https://www.amazon.es/dp/B1?psc=1", "ES")
    assert '"28001"' in source and '"https://www.amazon.es/dp/B1?psc=1"' in source
    assert "__" not in source


def test_collect_skips_prices_quoted_for_another_country():
    def run(source):
        if "/s?k=" in source:
            return {
                "captcha": False,
                "results": [
                    {"asin": "B1", "title": "Bumper Plate 25 kg", "sponsored": False},
                    {"asin": "B2", "title": "Bumper Plate 20 kg", "sponsored": False},
                ],
            }
        # The postcode change failed for B2: Amazon.es without Spanish VAT.
        return page(deliver="Estados Unidos") if "/dp/B2" in source else page()

    state, stats = collect("ES", run)
    assert stats["wrong_location"] == 1 and stats["loaded"] == 2
    assert [o.variant_id for o in state.offers] == ["B1"]


def test_run_without_offers_keeps_saved_offers(tmp_path, monkeypatch):
    import plates.amazon as amazon

    search = {
        "captcha": False,
        "results": [{"asin": "B1", "title": "Bumper Plate 25 kg", "sponsored": False}],
    }
    saved, _ = collect("ES", lambda source: search if "/s?k=" in source else page())
    monkeypatch.setattr(amazon, "OUT", tmp_path)
    (tmp_path / "latest.json").write_text(
        amazon.Snapshot(generated_at=saved.attempted_at, sources=[saved]).model_dump_json()
    )
    abroad = page(deliver="Estados Unidos")
    monkeypatch.setattr(amazon, "kitesurf", lambda source: search if "/s?k=" in source else abroad)
    monkeypatch.setattr(amazon, "collect", lambda market: collect(market, amazon.kitesurf))
    amazon.main(["--only", "ES"])
    kept = amazon.Snapshot.model_validate_json((tmp_path / "latest.json").read_text())
    assert [o.variant_id for o in kept.sources[0].offers] == ["B1"]
    assert '"wrong_location": 1' in (tmp_path / "trial.jsonl").read_text()


def test_published_snapshot_takes_the_latest_amazon_sources(tmp_path):
    from plates.amazon import with_amazon
    from plates.models import Snapshot, SourceState

    search = {
        "captcha": False,
        "results": [{"asin": "B1", "title": "Bumper Plate 25 kg", "sponsored": False}],
    }
    fresh, _ = collect("ES", lambda source: search if "/s?k=" in source else page())
    shop = SourceState(id="shop", name="Shop", status="ok", attempted_at=AT)
    stale = SourceState(id="amazon-es", name="Amazon.es", status="failed", attempted_at=AT)
    published = Snapshot(generated_at=AT, sources=[shop, stale])
    saved = tmp_path / "amazon.json"
    saved.write_text(Snapshot(generated_at=fresh.attempted_at, sources=[fresh]).model_dump_json())
    merged = with_amazon(published, saved)
    assert [s.id for s in merged.sources] == ["shop", "amazon-es"]
    assert merged.sources[1].offers and merged.generated_at == fresh.attempted_at
    assert with_amazon(published, tmp_path / "missing.json") == published
