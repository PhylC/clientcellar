# Supplier Link Audit

Internal audit for public supplier and retailer links used by ClientCellar. Checked date: 2026-05-10.

ClientCellar does not claim these suppliers are partners unless separately confirmed. Links are normal public supplier links unless an affiliate/tracked relationship is explicitly configured.

| Supplier | Category | URL | URL purpose | Checked date | Where used | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Majestic | Wine merchants / event wine | `https://www.majestic.co.uk/services/corporate-gifting` | Corporate gifting page | 2026-05-10 | `/suppliers`, gift planner route cards, event planner route cards, guides | Useful starting point for business wine gifts, case gifting and larger UK orders. |
| Laithwaites | Wine merchants | `https://www.laithwaites.co.uk/wine-gifts` | Wine gifts page | 2026-05-10 | `/suppliers`, gift planner route cards, guides | Useful for browsing wine gift cases and mixed gifts. |
| The Wine Society | Wine merchants | `https://www.thewinesociety.com/gifts` | Wine gifts page | 2026-05-10 | `/suppliers`, gift planner premium route cards | Membership model may apply; buyer should check suitability. |
| Berry Bros. & Rudd | Wine merchants | `https://www.bbr.com/gifts` | Gifts page | 2026-05-10 | `/suppliers`, gift planner premium route cards, guides | Better suited to premium client gifts, fine wine, Champagne and formal gifting. |
| Virgin Wines | Wine merchants | `https://www.virginwines.co.uk/wine-gifts` | Wine gifts page | 2026-05-10 | `/suppliers`, gift planner route cards, virtual tasting fallback route | Useful for accessible wine gifts and mixed cases. |
| Fortnum & Mason | Hampers and corporate gifting | `https://www.fortnumandmason.com/hampers` | Hampers page | 2026-05-10 | `/suppliers`, gift planner premium and hamper route cards, guides | Suitable for higher-value gifting where presentation matters. |
| M&S Hampers | Hampers and corporate gifting | `https://www.marksandspencer.com/l/hampers` | Hampers page | 2026-05-10 | `/suppliers`, gift planner hamper route cards, event retailer route cards | Useful for accessible corporate gifting and staff gifts. |
| Waitrose Cellar Gifts | Wine merchants / event wine | `https://www.waitrosecellar.com/gifts` | Wine gifts page | 2026-05-10 | `/suppliers`, gift planner mainstream route cards, event retailer route cards | Useful for straightforward wine gifting and simple self-managed events. |
| John Lewis Hampers | Hampers and corporate gifting | `https://www.johnlewis.com/browse/gifts/gift-food-alcohol/hampers/_/N-7d8p` | Hampers category | 2026-05-10 | `/suppliers`, gift planner hamper route cards | Useful for general gifting and non-specialist buyers. |
| Local independent wine merchant | Event wine and larger orders | No URL | Search locally | 2026-05-10 | `/suppliers`, event planner route cards | Search for `independent wine merchant near me` plus town/city. Useful for practical advice and local delivery support. |
| Noughty / Thomson & Scott | Non-alcoholic options | `https://noughtyaf.com/` | Non-alcoholic sparkling wine | 2026-05-10 | `/suppliers`, gift planner non-alcoholic route cards, event planner non-alcoholic route cards | Useful where alcohol may not be suitable. |
| Dry Drinker | Non-alcoholic options | `https://drydrinker.com/` | Alcohol-free drinks retailer | 2026-05-10 | `/suppliers`, gift planner non-alcoholic route cards, event planner non-alcoholic route cards | Useful for workplace-safe or inclusive gifting. |

## Display Rules

- If `supplier.isAffiliate` / `supplier.is_affiliate` is true and a real affiliate URL exists, use the affiliate URL and show the appropriate disclosure.
- If a normal supplier URL exists, use the normal URL and neutral button copy such as `Visit supplier`, `View wine gifts`, `View hampers` or `Check corporate gifting`.
- If no URL exists, show search guidance and no dead link.
- Do not add fake affiliate URLs or empty affiliate placeholders.
- Do not claim live prices, live stock, guaranteed delivery or confirmed supplier quotes.

## Known Limitations

- Supplier pages can change without notice. Recheck URLs before a major launch, paid campaign or affiliate/tracked-link migration.
- Some retailers may redirect category pages based on cookies, region or stock.
- ClientCellar remains useful without affiliate links because planners and guides now show supplier routes directly.
