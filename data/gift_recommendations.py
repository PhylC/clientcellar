"""Shared supplier recommendation routes for gift planning surfaces."""

from __future__ import annotations


GIFT_SUPPLIER_RECOMMENDATIONS: list[dict] = [
    {
        "key": "corporate-wine",
        "rank": "Best overall",
        "route": "Corporate wine gifting",
        "best_when": "Client lists, repeat orders or wine-friendly recipients",
        "supplier_id": "majestic",
        "supplier": "Majestic",
        "cta_label": "View Majestic",
        "contact_label": "View Majestic",
        "why": "Best practical option for repeat business gifting and scalable wine orders.",
        "short_reason": "Best starting point for a 25-recipient client list because it balances wine choice, fulfilment practicality and business-friendly buying.",
        "alternatives": [
            {"id": "laithwaites", "label": "Laithwaites"},
            {"id": "virgin-wines", "label": "Virgin Wines"},
        ],
        "best_for": "25-250 recipient campaigns where reliable fulfilment matters more than boutique curation.",
        "best_for_tags": ["Standard clients", "Fulfilment"],
        "typical_spend": "Indicative: usually strongest around £45-£120 per recipient.",
        "ease_score": "8/10",
        "hidden_watchouts": "Substitutions can change perceived quality if the exact bottle or case is unavailable.",
        "recommendation": "Use for the standard client tier and as the first supplier to benchmark.",
        "extra_notes": "Ask whether VAT invoice, branded gift note and multi-address upload are supported before committing.",
    },
    {
        "key": "hamper-fallback",
        "rank": "Best budget-safe fallback",
        "route": "Hampers",
        "best_when": "Mixed tastes, unknown preferences or safer mainstream gifting",
        "supplier_id": "marks-spencer-corporate",
        "supplier": "M&S",
        "cta_label": "View M&S",
        "contact_label": "View hampers",
        "why": "Safest mainstream choice for mixed tastes, simple gifting and broad recipient appeal.",
        "short_reason": "Use when wine preferences are uncertain or a food-and-drink gift feels safer than one bottle.",
        "alternatives": [
            {"id": "john-lewis-hampers", "label": "John Lewis"},
            {"id": "fortnum-mason", "label": "Fortnum & Mason"},
        ],
        "best_for": "Staff, mixed-recipient groups and standard clients where food variety is safer than one bottle.",
        "best_for_tags": ["Broad appeal", "Hamper fallback"],
        "typical_spend": "Indicative: often useful around £30-£75 per recipient.",
        "ease_score": "7/10",
        "hidden_watchouts": "Low-spend options may feel more retail than premium corporate gifting.",
        "recommendation": "Use as the safest fallback when recipient preferences are unknown.",
        "extra_notes": "Check alcohol contents, dietary options, VAT invoice and delivery cut-off dates.",
    },
    {
        "key": "premium-vip",
        "rank": "Best VIP/premium",
        "route": "Premium retailer",
        "best_when": "Presentation, brand signal and perceived value matter more than price",
        "supplier_id": "fortnum-mason",
        "supplier": "Fortnum & Mason",
        "cta_label": "View Fortnum & Mason",
        "contact_label": "View hampers",
        "why": "Strongest premium signal when the gift needs to feel polished, traditional and high value.",
        "short_reason": "Reserve for senior clients or presentation-led gifts where perceived value matters more than price.",
        "alternatives": [
            {"id": "selfridges-hampers", "label": "Selfridges"},
            {"id": "harvey-nichols-hampers", "label": "Harvey Nichols"},
        ],
        "best_for": "Premium client tiers where presentation matters more than tight budget control.",
        "best_for_tags": ["VIP", "Premium hamper"],
        "typical_spend": "Indicative: usually strongest around £75-£200+ per recipient.",
        "ease_score": "6/10",
        "hidden_watchouts": "Premium packaging can push spend above policy limits once delivery and VAT are added.",
        "recommendation": "Use for VIP or senior client tiers, not necessarily the whole list.",
        "extra_notes": "Best where presentation is worth the additional admin and budget.",
    },
    {
        "key": "wine-only",
        "rank": "Best wine-only alternative",
        "route": "Wine-only comparison",
        "best_when": "You want a straightforward wine gift route to compare against Majestic",
        "supplier_id": "laithwaites",
        "supplier": "Laithwaites",
        "cta_label": "View Laithwaites",
        "contact_label": "View Laithwaites",
        "why": "Useful wine-only benchmark with accessible gift cases and straightforward browsing.",
        "short_reason": "Use as the practical wine-only comparison if hampers are too broad or Majestic is not the preferred fit.",
        "alternatives": [
            {"id": "virgin-wines", "label": "Virgin Wines"},
            {"id": "waitrose-cellar", "label": "Waitrose Cellar"},
        ],
        "best_for": "Accessible wine gift cases where range and straightforward delivery are more important than bespoke advice.",
        "best_for_tags": ["Wine gifts", "Case gifting"],
        "typical_spend": "Indicative: usually strongest around £35-£90 per recipient.",
        "ease_score": "7/10",
        "hidden_watchouts": "Mixed cases can be efficient but may feel less tailored for senior relationships.",
        "recommendation": "Use as a practical wine-only comparison against Majestic or a hamper supplier.",
        "extra_notes": "Useful benchmark against other mainstream wine gift routes.",
    },
    {
        "key": "local-advice",
        "rank": "Best local/advice-led option",
        "route": "Local wine merchant",
        "best_when": "VIP clients, smaller lists or more personal recommendations",
        "supplier_id": "local-independent-wine-merchant",
        "supplier": "Local independent wine merchant",
        "cta_label": "Find local merchant",
        "contact_label": "Find local merchant",
        "why": "Best when advice, personalisation or regional relevance matters.",
        "short_reason": "Best for advice-led VIP gifts where bottle choice or regional relevance matters.",
        "alternatives": [],
        "search_suggestion": "independent wine merchant near me",
        "best_for": "VIP clients, senior relationships and advice-led bottle choices where taste matters.",
        "best_for_tags": ["VIP", "Advice led"],
        "typical_spend": "Indicative: usually strongest around £60-£200+ per recipient.",
        "ease_score": "5/10",
        "hidden_watchouts": "The best advice-led option can become admin-heavy for large recipient lists.",
        "recommendation": "Reserve for VIP recipients or tricky briefs where a mainstream route feels too generic.",
        "extra_notes": "Search locally and ask directly about delivery radius, gift notes and invoices.",
    },
]


def gift_recommendation_routes() -> list[dict]:
    return [dict(item) for item in GIFT_SUPPLIER_RECOMMENDATIONS]


def gift_recommendation_shortlist() -> list[dict]:
    return [
        {
            "rank": item["rank"],
            "supplier": item["supplier"],
            "supplier_id": item["supplier_id"],
            "reason": item["short_reason"],
        }
        for item in GIFT_SUPPLIER_RECOMMENDATIONS
    ]


def gift_supplier_comparison_rows() -> list[dict]:
    rows = []
    for item in GIFT_SUPPLIER_RECOMMENDATIONS:
        rows.append(
            {
                "supplier_id": item["supplier_id"],
                "supplier": item["supplier"],
                "supplier_type": item["route"],
                "contact_label": item["cta_label"],
                "contactLabel": item["cta_label"],
                "product_package": item["route"],
                "unit_price": "Indicative: supplier to confirm itemised unit pricing.",
                "delivery_cost": "Indicative: ask for itemised delivery by address type.",
                "personalisation": "Ask whether gift notes, branding and proofing can be handled inside the deadline.",
                "lead_time": "Begin supplier contact 2-3 weeks before dispatch; longer in seasonal peaks.",
                "best_for": item["best_for"],
                "best_for_tags": item["best_for_tags"],
                "typical_spend": item["typical_spend"],
                "ease_score": item["ease_score"],
                "hidden_watchouts": item["hidden_watchouts"],
                "recommendation": item["recommendation"],
                "extra_notes": item["extra_notes"],
                "strengths": item["why"],
                "watchouts": item["hidden_watchouts"],
                "questions_to_ask": item["extra_notes"],
                "search_suggestion": item.get("search_suggestion"),
            }
        )
    return rows
