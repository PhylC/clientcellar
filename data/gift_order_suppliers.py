"""Source-backed UK supplier choices for the Gift Planner's ordering routes."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlsplit

from data.gift_recommendations import BULK_GIFT_SUPPLIERS
from data.supplier_links import (
    bottle_in_a_box_christmas_affiliate_url,
    supplier_affiliate_url,
)


SOURCES_CHECKED = "2026-11-24"
BOTTLE_IN_A_BOX = "https://bottleinabox.co.uk"
HAMPERS = "https://www.hampers.com"
VINTAGE_WINE_GIFTS = "https://www.vintagewinegifts.co.uk/"
SLURP_CORPORATE = "https://www.slurp.co.uk/pages/how-to-order"


def _card(
    supplier_id: str,
    name: str,
    *,
    fit: str,
    published: str,
    confirm: str,
    source_url: str,
    source_label: str,
    action_label: str,
    affiliate_url: str | None = None,
) -> dict:
    return {
        "supplier_id": supplier_id,
        "name": name,
        "fit": fit,
        "published": published,
        "confirm": confirm,
        "source_url": source_url,
        "source_label": source_label,
        "source_checked_date": SOURCES_CHECKED,
        "url": affiliate_url or source_url,
        "action_label": action_label,
        "is_affiliate": bool(affiliate_url),
    }


def _bottle_in_a_box_retail_link(url: str) -> str | None:
    # This merchant uses the same SliceWP referral ID on product categories.
    tracked_christmas_url = bottle_in_a_box_christmas_affiliate_url(
        supplier_affiliate_url("bottle-in-a-box"),
    )
    if not tracked_christmas_url:
        return None
    return f"{url}?{urlsplit(tracked_christmas_url).query}"


def _vintage_retail_link() -> str | None:
    configured = supplier_affiliate_url("vintage-wine-gifts")
    if not configured:
        return None
    parts = urlsplit(configured)
    if parts.scheme != "https" or parts.netloc not in {"awin1.com", "www.awin1.com"} or parts.path != "/cread.php":
        return None
    query = parse_qs(parts.query)
    advertiser = query.get("awinmid", [])
    publisher = query.get("awinaffid", [])
    if len(advertiser) != 1 or len(publisher) != 1 or not all(value.isdecimal() for value in (*advertiser, *publisher)):
        return None
    return "https://www.awin1.com/cread.php?" + urlencode({
        "awinmid": advertiser[0],
        "awinaffid": publisher[0],
        "clickref": "cc_gift_planner_online_milestone",
        "ued": VINTAGE_WINE_GIFTS,
    })


def _online_choices(
    *,
    christmas: bool,
    milestone: bool,
    alcohol_free_count: int | None,
    recipient_count: int,
    budget_per_gift: float | None,
) -> list[dict]:
    all_alcohol_free = alcohol_free_count == recipient_count
    offer_alcohol_free = alcohol_free_count != 0
    options = []
    delivery_check = "Check the current gift price, delivery charge and date for the recipient's postcode."

    if not all_alcohol_free:
        path = "/christmas-hampers" if christmas else "/wine-gifts"
        source_url = BOTTLE_IN_A_BOX + path
        options.append((29.99 if christmas else 24.99, _card(
            "bottle-in-a-box",
            "Bottle In A Box",
            fit="Gift-ready boxes for recipients who can receive alcohol.",
            published=(
                "The Christmas shop lists the Merry Christmas Wine Hamper at a regular price of £29.99."
                if christmas else
                "The wine gift shop lists the Red Wine Lover Gift Box at a regular price of £24.99."
            ),
            confirm=delivery_check,
            source_url=source_url,
            source_label="Bottle In A Box retail range",
            action_label="Shop Christmas hampers" if christmas else "Shop wine gifts",
            affiliate_url=_bottle_in_a_box_retail_link(source_url),
        )))
    if offer_alcohol_free:
        source_url = BOTTLE_IN_A_BOX + "/non-alcoholic-gifts"
        options.append((19.99, _card(
            "bottle-in-a-box",
            "Bottle In A Box",
            fit=(
                "An alcohol-free fallback when preferences are unknown."
                if alcohol_free_count is None else "Gift boxes for the recipients who need an alcohol-free option."
            ),
            published="The non-alcoholic gift shop lists the Sensational Juice & Snacks Hamper at £19.99.",
            confirm=f"Verify ingredients and any alcohol-content policy. {delivery_check}",
            source_url=source_url,
            source_label="Bottle In A Box non-alcoholic range",
            action_label="Shop alcohol-free gift boxes",
            affiliate_url=_bottle_in_a_box_retail_link(source_url),
        )))

        options.append((32, _card(
            "hampers-com",
            "Hampers.com",
            fit="Food and soft-drink gifts for recipients who prefer alcohol-free options.",
            published="The alcohol-free collection includes the £32 A Little Taste of Everything Gift Box.",
            confirm=f"Check the chosen box's ingredients and any dietary requirements. {delivery_check}",
            source_url=HAMPERS + "/collections/alcohol-free-hampers",
            source_label="Hampers.com alcohol-free range",
            action_label="Shop alcohol-free hampers",
        )))
    else:
        options.append((37, _card(
            "hampers-com",
            "Hampers.com",
            fit="A food-led gift if a single bottle would feel too narrow.",
            published="The gift-box collection includes the £37 Classic Red Wine & Cheese Gift Box.",
            confirm=f"Check dietary requirements, contents and any chilled-delivery instructions. {delivery_check}",
            source_url=HAMPERS + "/collections/gift-boxes",
            source_label="Hampers.com gift-box range",
            action_label="Shop gift boxes",
        )))
    if milestone and not all_alcohol_free:
        options.insert(1, (49.97, _card(
            "vintage-wine-gifts",
            "Vintage Wine Gifts",
            fit="A single dated bottle for an anniversary, retirement or other milestone where alcohol suits.",
            published="It accepts single-bottle orders and lists a 2021 Chablis at £49.97.",
            confirm=f"Check the available year and gift packaging for the bottle you choose. {delivery_check}",
            source_url=VINTAGE_WINE_GIFTS,
            source_label="Vintage Wine Gifts shop",
            action_label="Shop vintage wine gifts",
            affiliate_url=_vintage_retail_link(),
        )))

    return [card for example_price, card in options if budget_per_gift is None or example_price <= budget_per_gift][:3]


def _quote_choices(
    *,
    recipient_count: int,
    delivery_address_count: int | None,
    alcohol_free_count: int | None,
    branding_needed: bool,
    gift_policy_cap_per_recipient: float | None,
) -> list[dict]:
    all_alcohol_free = alcohol_free_count == recipient_count
    grouped = delivery_address_count == 1
    delivery_check = "Confirm one-office delivery, carton handover and VAT." if grouped else (
        "Confirm delivery by postcode, the order cut-off and VAT."
    )
    if branding_needed:
        delivery_check += " Ask about branding minimums and artwork lead time."
    if gift_policy_cap_per_recipient is not None:
        delivery_check += " Confirm the price of each gift is within the policy cap."

    cards = []
    bottle_in_a_box = BULK_GIFT_SUPPLIERS[0]
    minimum, maximum = bottle_in_a_box["advertised_range"]
    if minimum <= recipient_count <= maximum:
        cards.append(_card(
            bottle_in_a_box["id"],
            bottle_in_a_box["name"],
            fit=(
                "An alcohol-free gift-box quote for the whole order."
                if all_alcohol_free else "Gift-ready boxes with standard and alcohol-free options in one order."
            ),
            published=(
                f"It advertises {minimum:,}–{maximum:,} gift sets per corporate order and supports single- and multi-address delivery."
            ),
            confirm=f"Ask about available gift types and the minimum per type. {delivery_check}",
            source_url=BOTTLE_IN_A_BOX + "/corporate-gifts",
            source_label="Bottle In A Box corporate terms",
            action_label="View corporate quote options",
            affiliate_url=supplier_affiliate_url("bottle-in-a-box"),
        ))
    cards.append(_card(
        "hampers-com",
        "Hampers.com",
        fit=(
            "An alcohol-free food hamper route for the whole brief."
            if all_alcohol_free else "A food-led hamper quote that can cover different recipient preferences."
        ),
        published="Its corporate range includes alcohol-free hampers and the team supports bulk dispatch to multiple addresses.",
        confirm=f"Ask about the order minimum, food ingredients and available gift mix. {delivery_check}",
        source_url=HAMPERS + "/collections/corporate-gift-hampers",
        source_label="Hampers.com corporate ordering",
        action_label="View corporate hamper options",
    ))
    if not all_alcohol_free:
        cards.append(_card(
            "slurp",
            "Slurp",
            fit=(
                "A bottle-led comparison when the office can receive and distribute the gifts."
                if grouped else "A bottle-led comparison with a recipient spreadsheet."
            ),
            published="Its corporate order form accepts different gift products and recipient details, with delivery pricing based on the order.",
            confirm=(
                "For alcohol-free recipients, ask about 0.0% bottles and gift packaging. " if alcohol_free_count else ""
            ) + delivery_check,
            source_url=SLURP_CORPORATE,
            source_label="Slurp corporate ordering",
            action_label="View corporate order process",
        ))
    return cards


def gift_order_supplier_choices(
    *,
    route: str,
    recipient_count: int,
    delivery_address_count: int | None,
    alcohol_free_count: int | None,
    occasion: str,
    budget_per_gift: float | None = None,
    branding_needed: bool = False,
    gift_policy_cap_per_recipient: float | None = None,
    gift_style: str = "not_sure",
    tone: str = "safe",
) -> list[dict]:
    if route == "online_checkout":
        ceilings = [value for value in (budget_per_gift, gift_policy_cap_per_recipient) if value is not None]
        milestone = bool(re.search(r"\b(anniversary|milestone|retirement)\b", occasion, flags=re.I))
        return _online_choices(
            christmas=bool(re.search(r"\b(christmas|xmas)\b", occasion, flags=re.I)),
            milestone=milestone and gift_style != "wine_hamper" and tone != "low_risk",
            alcohol_free_count=alcohol_free_count,
            recipient_count=recipient_count,
            budget_per_gift=min(ceilings, default=None),
        )
    if route in {"grouped_delivery", "bulk_quote"}:
        return _quote_choices(
            recipient_count=recipient_count,
            delivery_address_count=delivery_address_count,
            alcohol_free_count=alcohol_free_count,
            branding_needed=branding_needed,
            gift_policy_cap_per_recipient=gift_policy_cap_per_recipient,
        )
    return []
