"""Order routing and spend limits for a corporate gift brief."""

import re
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal


PENNY = Decimal("0.01")
ALCOHOL_FREE_ONLY = re.compile(
    r"\balcohol[- ]free (?:gifts? )?only\b"
    r"|\bonly alcohol[- ]free\b"
    r"|\bno alcoholic (?:gifts?|drinks?)\b"
    r"|\bno alcohol\b(?![- ]free| restrictions?| for\b)"
    r"|\balcohol (?:is )?(?:banned|prohibited)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GiftBudgetAllowance:
    per_gift: Decimal
    total: Decimal
    unknown_charges: bool


def gift_alcohol_free_count(
    recipient_count: int, count: int | None, policy_requires_alcohol_free: bool, preferences: str,
) -> int | None:
    if policy_requires_alcohol_free or (count is None and ALCOHOL_FREE_ONLY.search(preferences)):
        return recipient_count
    return count


def gift_budget_allowance(
    *,
    recipient_count: int,
    address_count: int | None,
    budget_per_recipient: float | None,
    all_in_budget: float | None,
    delivery_charge: float | None,
    delivery_basis: str,
    other_fees: float | None,
    gift_policy_cap: float | None,
) -> GiftBudgetAllowance:
    """Calculate the gift-only ceiling without treating missing charges as confirmed."""
    if all_in_budget is None:
        total = Decimal(str(budget_per_recipient)) * recipient_count
        unknown_charges = False
    else:
        delivery = None
        if delivery_charge == 0 or (delivery_basis == "order" and delivery_charge is not None):
            delivery = Decimal(str(delivery_charge))
        elif delivery_charge is not None and address_count is not None:
            delivery = Decimal(str(delivery_charge)) * address_count
        fees = Decimal(str(other_fees)) if other_fees is not None else None
        unknown_charges = delivery is None or fees is None
        total = max(Decimal(0), Decimal(str(all_in_budget)) - (delivery or 0) - (fees or 0))
    if gift_policy_cap is not None:
        total = min(total, Decimal(str(gift_policy_cap)) * recipient_count)
    return GiftBudgetAllowance(
        per_gift=(total / recipient_count).quantize(PENNY, rounding=ROUND_DOWN),
        total=total.quantize(PENNY, rounding=ROUND_DOWN),
        unknown_charges=unknown_charges,
    )


def gift_order_route(
    *,
    recipient_count: int,
    address_count: int | None,
    uk_only: bool,
    international_needed: bool,
    branding_needed: bool,
) -> dict[str, str]:
    if international_needed:
        return {
            "route": "international_quote",
            "title": "Confirm international delivery first",
            "reason": "Stock, delivery rules and fees can differ by destination.",
            "next_action": "Confirm each country and deadline with a supplier that can fulfil the order there.",
        }
    if not uk_only or address_count is None:
        return {
            "route": "confirm_delivery",
            "title": "Confirm where the gifts are going",
            "reason": "Destination and address count determine how to order and what delivery will cost.",
            "next_action": "Confirm UK coverage and add the delivery address count to narrow the supplier choices.",
        }
    if branding_needed or address_count > 1:
        return {
            "route": "bulk_quote",
            "title": "Request a bulk gifting quote",
            "reason": (
                "A custom-branded order needs supplier confirmation of minimums and proofing time."
                if branding_needed else "A bulk quote can cover the gift quantities and delivery to each address in one order."
            ),
            "next_action": "Ask for an itemised delivered total, the order cut-off and an address upload template.",
        }
    if recipient_count > 1:
        return {
            "route": "grouped_delivery",
            "title": "Group the gifts in one delivery",
            "reason": "One address lets you check a single shipment for all recipients.",
            "next_action": "Confirm the supplier can send the full quantity together and include the gift notes you need.",
        }
    return {
        "route": "online_checkout",
        "title": "Order the gift online",
        "reason": "One gift to one UK address can usually go through standard online checkout.",
        "next_action": "Check the delivered total and available date for the recipient’s postcode before ordering.",
    }
