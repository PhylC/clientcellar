"""Validated outbound supplier link configuration.

This is the single place for supplier destination URLs. Affiliate URLs can be
added here later without changing planner, guide or template rendering code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger("clientcellar.supplier_links")


@dataclass(frozen=True)
class SupplierLink:
    id: str
    name: str
    canonical_base_url: str | None
    affiliate_url: str | None
    fallback_url: str | None
    category_tags: tuple[str, ...]
    active: bool = True

    @property
    def url(self) -> str | None:
        if not self.active:
            return None
        return self.affiliate_url or self.canonical_base_url or self.fallback_url

    @property
    def is_affiliate(self) -> bool:
        return bool(self.active and self.affiliate_url)


SUPPLIER_LINK_CONFIG: dict[str, SupplierLink] = {
    "majestic": SupplierLink(
        id="majestic",
        name="Majestic Corporate Gifts",
        canonical_base_url="https://www.majestic.co.uk/services/corporate-gifting",
        affiliate_url=None,
        fallback_url="https://www.majestic.co.uk/gifting",
        category_tags=("wine", "corporate-gifting", "event-wine"),
    ),
    "majestic-commercial": SupplierLink(
        id="majestic-commercial",
        name="Majestic Commercial / events",
        canonical_base_url="https://www.majestic.co.uk/information/majestic-commercial/corporate-partnerships-events",
        affiliate_url=None,
        fallback_url="https://www.majestic.co.uk/services/corporate-gifting",
        category_tags=("wine", "corporate-gifting", "event-wine", "commercial"),
    ),
    "laithwaites": SupplierLink(
        id="laithwaites",
        name="Laithwaites Corporate Wine Gifts",
        canonical_base_url="https://www.laithwaites.co.uk/gifts/corporate-wine-gifts",
        affiliate_url=None,
        fallback_url="https://www.laithwaites.co.uk/gifts/all-gifts",
        category_tags=("wine", "wine-gifts", "corporate-gifting"),
    ),
    "virgin-wines": SupplierLink(
        id="virgin-wines",
        name="Virgin Wines Corporate Gifts",
        canonical_base_url="https://www.virginwines.co.uk/corporate-gifting",
        affiliate_url=None,
        fallback_url="https://www.virginwines.co.uk/corporate-gifts",
        category_tags=("wine", "wine-gifts", "corporate-gifting"),
    ),
    "slurp": SupplierLink(
        id="slurp",
        name="Slurp",
        canonical_base_url="https://www.slurp.co.uk/pages/gifting-services",
        affiliate_url=None,
        fallback_url="https://www.slurp.co.uk/pages/client-gifting",
        category_tags=("wine", "wine-gifts", "corporate-gifting", "event-wine"),
    ),
    "hay-wines": SupplierLink(
        id="hay-wines",
        name="Hay Wines",
        canonical_base_url="https://haywines.co.uk/pages/company-gifts",
        affiliate_url=None,
        fallback_url="https://haywines.co.uk/pages/company-gifts",
        category_tags=("wine", "independent-merchant", "corporate-gifting", "event-wine"),
    ),
    "wine-direct": SupplierLink(
        id="wine-direct",
        name="Wine Direct",
        canonical_base_url="https://www.winedirect.co.uk/info/corporate-wine-gifts",
        affiliate_url=None,
        fallback_url="https://www.winedirect.co.uk/info/corporate-wine-gifts",
        category_tags=("wine", "wine-gifts", "corporate-gifting"),
    ),
    "wine-society": SupplierLink(
        id="wine-society",
        name="The Wine Society",
        canonical_base_url="https://www.thewinesociety.com/buy/gifts/gift-cases-and-wine-hampers/",
        affiliate_url=None,
        fallback_url="https://www.thewinesociety.com/buy/gifts/",
        category_tags=("wine", "premium-gifts"),
    ),
    "berry-bros-rudd": SupplierLink(
        id="berry-bros-rudd",
        name="Berry Bros. & Rudd",
        canonical_base_url=None,
        affiliate_url=None,
        fallback_url=None,
        category_tags=("wine", "premium-gifts"),
        active=False,
    ),
    "fortnum-mason": SupplierLink(
        id="fortnum-mason",
        name="Fortnum & Mason",
        canonical_base_url="https://www.fortnumandmason.com/hampers/all-hampers/wine-hampers",
        affiliate_url=None,
        fallback_url="https://www.fortnumandmason.com/hampers",
        category_tags=("hampers", "premium-gifts"),
    ),
    "marks-spencer-corporate": SupplierLink(
        id="marks-spencer-corporate",
        name="M&S Hampers",
        canonical_base_url="https://www.marksandspencer.com/l/gifts/food-and-drink-gifts/hampers/wine-hampers",
        affiliate_url=None,
        fallback_url="https://www.marksandspencer.com/l/gifts/food-and-drink-gifts/hampers",
        category_tags=("hampers", "food-gifts"),
    ),
    "waitrose-cellar": SupplierLink(
        id="waitrose-cellar",
        name="Waitrose Cellar",
        canonical_base_url="https://www.waitrosecellar.com/shop/gifts/wine-gifts",
        affiliate_url=None,
        fallback_url="https://www.waitrosecellar.com/shop/gifts",
        category_tags=("wine", "wine-gifts"),
    ),
    "john-lewis-hampers": SupplierLink(
        id="john-lewis-hampers",
        name="John Lewis Hampers",
        canonical_base_url="https://www.johnlewis.com/browse/gifts/gift-food-alcohol/hampers/_/N-2q3pZ1z0vwzu",
        affiliate_url=None,
        fallback_url="https://www.johnlewis.com/browse/gifts/gift-food-alcohol/_/N-7d8p",
        category_tags=("hampers", "food-gifts"),
    ),
    "selfridges-hampers": SupplierLink(
        id="selfridges-hampers",
        name="Selfridges hampers",
        canonical_base_url="https://www.selfridges.com/GB/en/cat/foodhall/hampers/wine-spirits-hampers/",
        affiliate_url=None,
        fallback_url="https://www.selfridges.com/GB/en/cat/gifts/wine-food-gifts/",
        category_tags=("hampers", "premium-gifts"),
    ),
    "harrods-hampers": SupplierLink(
        id="harrods-hampers",
        name="Harrods hampers",
        canonical_base_url="https://www.harrods.com/en-gb/shopping/hampers",
        affiliate_url=None,
        fallback_url="https://www.harrods.com/en-gb/",
        category_tags=("hampers", "premium-gifts"),
    ),
    "harvey-nichols-hampers": SupplierLink(
        id="harvey-nichols-hampers",
        name="Harvey Nichols hampers",
        canonical_base_url="https://www.harveynichols.com/food-and-wine/hampers/wine-and-spirit-hampers/",
        affiliate_url=None,
        fallback_url="https://www.harveynichols.com/food-and-wine/hampers/",
        category_tags=("hampers", "premium-gifts"),
    ),
    "great-wine-co": SupplierLink(
        id="great-wine-co",
        name="Great Wine Co.",
        canonical_base_url="https://greatwine.co.uk/gifts-more/mixed-cases/",
        affiliate_url=None,
        fallback_url="https://greatwine.co.uk/",
        category_tags=("wine", "mixed-cases", "event-wine"),
    ),
    "hotel-chocolat": SupplierLink(
        id="hotel-chocolat",
        name="Hotel Chocolat",
        canonical_base_url="https://www.hotelchocolat.com/uk/shop/gift-ideas/",
        affiliate_url=None,
        fallback_url="https://www.hotelchocolat.com/uk/",
        category_tags=("chocolate", "staff-gifts"),
    ),
    "amazon": SupplierLink(
        id="amazon",
        name="Amazon",
        canonical_base_url="https://www.amazon.co.uk/gift-cards-vouchers/b?node=1571304031",
        affiliate_url=None,
        fallback_url="https://www.amazon.co.uk/",
        category_tags=("gift-cards", "mainstream-retailer"),
    ),
    "noughty-thomson-scott": SupplierLink(
        id="noughty-thomson-scott",
        name="Noughty / Thomson & Scott",
        canonical_base_url="https://noughtyaf.com/",
        affiliate_url=None,
        fallback_url="https://noughtyaf.com/",
        category_tags=("non-alcoholic",),
    ),
    "dry-drinker": SupplierLink(
        id="dry-drinker",
        name="Dry Drinker",
        canonical_base_url="https://drydrinker.com/",
        affiliate_url=None,
        fallback_url="https://drydrinker.com/",
        category_tags=("non-alcoholic",),
    ),
}


def validate_supplier_url(url: str | None, supplier_id: str) -> bool:
    if not url:
        return True
    parsed = urlparse(url)
    valid = parsed.scheme == "https" and bool(parsed.netloc)
    if not valid:
        logger.warning("Malformed supplier URL for %s: %s", supplier_id, url)
    return valid


def validate_supplier_links() -> list[str]:
    warnings: list[str] = []
    for supplier_id, link in SUPPLIER_LINK_CONFIG.items():
        for field_name in ("canonical_base_url", "affiliate_url", "fallback_url"):
            url = getattr(link, field_name)
            if not validate_supplier_url(url, supplier_id):
                warnings.append(f"{supplier_id}.{field_name}={url}")
    if warnings:
        logger.warning("Supplier link validation warnings: %s", "; ".join(warnings))
    return warnings


def get_supplier_link(supplier_id: str) -> SupplierLink | None:
    return SUPPLIER_LINK_CONFIG.get(supplier_id)


def getSupplierLink(supplier_id: str) -> SupplierLink | None:
    return get_supplier_link(supplier_id)


def supplier_url(supplier_id: str) -> str | None:
    link = get_supplier_link(supplier_id)
    return link.url if link else None


def supplier_canonical_url(supplier_id: str) -> str | None:
    link = get_supplier_link(supplier_id)
    return link.canonical_base_url if link else None


def supplier_affiliate_url(supplier_id: str) -> str | None:
    link = get_supplier_link(supplier_id)
    return link.affiliate_url if link else None


validate_supplier_links()
