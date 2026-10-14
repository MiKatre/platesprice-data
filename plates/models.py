"""Small JSON contracts; money/weight are decimals, unknown costs are null."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

LB_KG = Decimal("0.45359237")
Positive = Decimal


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Component(Model):
    weight: Positive = Field(gt=0, le=500, allow_inf_nan=False)
    unit: Literal["kg", "lb"]
    count: int = Field(gt=0, le=100)

    @property
    def kg(self):
        return self.weight * self.count * (LB_KG if self.unit == "lb" else Decimal(1))


def validate_pack(sale_unit, components):
    count = sum(c.count for c in components)
    if sale_unit == "unknown" and components:
        raise ValueError("unknown pack must not invent components")
    if sale_unit == "single" and count != 1:
        raise ValueError("single must contain one plate")
    if sale_unit == "pair" and (count != 2 or len(components) != 1):
        raise ValueError("pair must contain two identical plates")
    if sale_unit == "set" and count < 2:
        raise ValueError("set must contain multiple plates")


class Variant(Model):
    id: str = Field(pattern=r"^[0-9]+$")
    title: str
    components: list[Component] = Field(default_factory=list)
    sale_unit: Literal["single", "pair", "set", "unknown"]

    @model_validator(mode="after")
    def coherent(self):
        validate_pack(self.sale_unit, self.components)
        return self


class Product(Model):
    url: str
    data_url: str
    adapter: Literal["shopify_json", "shopify_js"]
    title: str
    plate_type: Literal["bumper", "iron", "rubber_coated", "urethane", "change"]
    variants: list[Variant] = Field(min_length=1)
    evidence: str
    pack_evidence: str | None = Field(default=None, min_length=3)
    reviewed_on: str

    @model_validator(mode="after")
    def unique(self):
        if any(v.sale_unit != "unknown" for v in self.variants) and not self.pack_evidence:
            raise ValueError("known packs require current pack evidence")
        ids = [v.id for v in self.variants]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate variant IDs")
        return self


class Feed(Model):
    """Approved catalog endpoint; discover variants without enumerating their IDs."""

    url: str
    adapter: Literal["shopify_feed"] = "shopify_feed"
    max_pages: int = Field(default=4, ge=1, le=8)

    @model_validator(mode="after")
    def endpoint(self):
        parts = urlsplit(self.url)
        if not parts.path.endswith("/products.json") or parts.query or parts.fragment:
            raise ValueError("feed must be a products.json endpoint without query or fragment")
        return self


class Source(Model):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str
    origin: str
    market: Literal["US", "ES"]
    currency: Literal["USD", "EUR"]
    currency_evidence_url: str
    # Markets are separate storefronts, not FX-converted versions of one catalog.
    tax_basis: Literal["excluded", "included", "unknown"] = "unknown"
    terms_url: str | None = None
    notes: list[str] = Field(default_factory=list)
    paused: bool = False
    pause_reason: str | None = None
    products: list[Product] = Field(default_factory=list)
    feeds: list[Feed] = Field(default_factory=list)

    @model_validator(mode="after")
    def safe_urls(self):
        origin = urlsplit(self.origin)
        if origin.scheme != "https" or not origin.hostname or origin.username:
            raise ValueError("source requires an HTTPS origin")
        if origin.path not in ("", "/") or origin.query or origin.fragment:
            raise ValueError("origin cannot contain a path/query/fragment")
        if not self.products and not self.feeds:
            raise ValueError("source requires products or catalog feeds")
        if self.paused and not self.pause_reason:
            raise ValueError("paused source requires a reason")
        for url in (
            [u for u in (self.currency_evidence_url, self.terms_url) if u]
            + [u for p in self.products for u in (p.url, p.data_url)]
            + [f.url for f in self.feeds]
        ):
            parts = urlsplit(url)
            if (parts.scheme, parts.netloc) != (origin.scheme, origin.netloc):
                raise ValueError("all source URLs must share the approved HTTPS origin")
        urls = [p.data_url for p in self.products] + [f.url for f in self.feeds]
        if len(urls) != len(set(urls)):
            raise ValueError("duplicate product URL")
        return self


class Catalog(Model):
    schema_version: Literal[1] = 1
    sources: list[Source]

    @model_validator(mode="after")
    def unique(self):
        ids = [s.id for s in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate source IDs")
        return self


class Offer(Model):
    id: str
    sku: str | None = None
    condition: Literal["new", "used", "b_stock", "unknown"] = "unknown"
    source_id: str
    market: Literal["US", "ES"]
    currency: Literal["USD", "EUR"]
    title: str
    variant_title: str
    variant_id: str
    source_url: str
    plate_type: str
    sale_unit: Literal["single", "pair", "set", "unknown"]
    components: list[Component]
    total_weight_kg: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    price_per_kg: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    price_per_lb: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    available: bool | None = Field(default=None, strict=True)  # Purchasability, not physical stock.
    stock_status: Literal["unknown"] = "unknown"
    tax_basis: Literal["excluded", "included", "unknown"]
    shipping_status: Literal["unknown"] = "unknown"
    shipping_price: None = None
    delivered_price: None = None
    observed_at: datetime
    pack_evidence: str | None = None
    price_basis: str | None = None

    @model_validator(mode="after")
    def coherent(self):
        if self.observed_at.utcoffset() is None:
            raise ValueError("timestamp must be timezone aware")
        if self.sale_unit == "unknown":
            if self.components or any(
                v is not None for v in (self.total_weight_kg, self.price_per_kg, self.price_per_lb)
            ):
                raise ValueError("unknown pack cannot have total weight or unit prices")
            return self
        validate_pack(self.sale_unit, self.components)
        if self.total_weight_kg != sum(c.kg for c in self.components):
            raise ValueError("inconsistent total weight")
        kg = (self.price / self.total_weight_kg).quantize(Decimal("0.000001"))
        lb = (self.price / self.total_weight_kg * LB_KG).quantize(Decimal("0.000001"))
        if self.price_per_kg != kg or self.price_per_lb != lb:
            raise ValueError("inconsistent unit prices")
        return self


class SourceState(Model):
    id: str
    name: str
    status: Literal["ok", "failed", "quarantined"]
    attempted_at: datetime
    last_success_at: datetime | None = None
    retained_previous: bool = False
    error: str | None = None
    collection_mode: Literal["automated", "reviewed"] = "automated"
    reviewed_at: datetime | None = None
    offers: list[Offer] = Field(default_factory=list)
    documents: list[dict] = Field(default_factory=list)
    coverage: dict[str, int] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    catalog_signature: str | None = None


class Snapshot(Model):
    schema_version: Literal[1] = 1
    generated_at: datetime
    sources: list[SourceState]

    @model_validator(mode="after")
    def coherent(self):
        source_ids = [s.id for s in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate source IDs")
        ids = []
        for source in self.sources:
            if source.collection_mode == "reviewed" and source.reviewed_at is None:
                raise ValueError("reviewed sources require a review date")
            for offer in source.offers:
                if (
                    source.collection_mode == "reviewed"
                    and offer.sale_unit != "unknown"
                    and not offer.pack_evidence
                ):
                    raise ValueError("reviewed offers require pack evidence")
                if offer.source_id != source.id or offer.observed_at > self.generated_at:
                    raise ValueError("invalid source or future timestamp")
                ids.append(offer.id)
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate offers")
        return self
