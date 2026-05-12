# Supplier Link Audit

Internal audit for public supplier and retailer links used by ClientCellar. Checked date: 2026-05-12.

ClientCellar does not claim these suppliers are partners unless separately confirmed. Recommendations are editorially selected for now. Links are normal public supplier links unless an affiliate or tracked relationship is explicitly configured.

| Supplier | Old URL if fixed | New URL | Page purpose | Where used | Checked date | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Majestic Corporate Gifts | No change | `https://www.majestic.co.uk/services/corporate-gifting` | Corporate gifting page | Free gift planner, premium gift packs, `/suppliers`, guides | 2026-05-12 | Reliable corporate gifting landing page for client gifts, staff rewards and business wine orders. |
| Majestic Commercial / events | New route | `https://www.majestic.co.uk/information/majestic-commercial/corporate-partnerships-events` | Corporate partnerships and events page | Event planner, premium event packs, `/suppliers` event section | 2026-05-12 | Stronger event-led supplier route for larger events, office celebrations and business orders. |
| Virgin Wines Corporate Gifts | Prior fragile wine-gifts deep link | `https://www.virginwines.co.uk/corporate-gifts` | Corporate gifts page | Free gift planner alternatives, event planner, premium comparisons, `/suppliers` | 2026-05-12 | Replaced fragile deep link with corporate gifts landing page. Fallback is `https://www.virginwines.co.uk/corporate-gifting`. |
| Laithwaites Corporate Wine Gifts | `https://www.laithwaites.co.uk/gifts/wine-gifts` | `https://www.laithwaites.co.uk/gifts/corporate-wine-gifts` | Corporate wine gifts page | Free gift planner alternatives, event planner, premium comparisons, `/suppliers` | 2026-05-12 | Replaced general wine gifts route with corporate wine gifts page. Fallback is `https://www.laithwaites.co.uk/gifts/all-gifts`. |
| Waitrose Cellar Gifts | `https://www.waitrosecellar.com/shop/gifts/wine-gifts` | `https://www.waitrosecellar.com/shop/gifts` | Gifts page | Event planner, mainstream gift route, `/suppliers`, guides | 2026-05-12 | Uses broader gifts landing page as the safer category route. Fallback is wine gifts. |
| Fortnum & Mason | No change | `https://www.fortnumandmason.com/hampers` | Hampers page | Gift planner premium route, premium packs, `/suppliers`, guides | 2026-05-12 | Live UK premium hamper landing page used as a presentation-led gifting route. |
| M&S Hampers | `https://www.marksandspencer.com/l/hampers` | `https://www.marksandspencer.com/l/gifts/food-and-drink-gifts/hampers` | Food and drink hampers page | Gift planner hamper route, premium packs, `/suppliers` | 2026-05-12 | Fixed broken M&S page that showed "Sorry, we can't find that page". |
| John Lewis Hampers | No change in this pass | `https://www.johnlewis.com/browse/gifts/gift-food-alcohol/hampers/_/N-2q3pZ1z0vwzu` | Food hampers and gift baskets page | Gift planner hamper alternatives, `/suppliers` | 2026-05-12 | Retained current UK hamper category URL. |
| The Wine Society | Prior gifts deep link | No active public button | Disabled supplier link | Removed from visible supplier recommendations | 2026-05-12 | Removed from active recommendations because no verified useful landing page was supplied for this pass. |
| Berry Bros. & Rudd | Prior generic wines page | No active public button | Disabled supplier link | Removed from visible supplier recommendations | 2026-05-12 | Removed from active recommendations because the prior route was too generic/risky for this pass. |
| Noughty / Thomson & Scott | No change | `https://noughtyaf.com/` | Non-alcoholic sparkling wine | Non-alcoholic supplier routes, `/suppliers` | 2026-05-12 | UK-relevant alcohol-free option; keep as a supplier option where alcohol suitability is uncertain. |
| Dry Drinker | No change | `https://drydrinker.com/` | Alcohol-free drinks retailer | Non-alcoholic supplier routes, `/suppliers` | 2026-05-12 | UK alcohol-free drinks retailer; useful for inclusive gifting and workplace-safe alternatives. |

## Display Rules

- If `supplier.isAffiliate` / `supplier.is_affiliate` is true and a real affiliate URL exists, use the affiliate URL and show the appropriate disclosure.
- If a normal supplier URL exists, use the normal URL and clear button copy such as `View corporate gifts`, `View corporate wine gifts`, `View hampers`, `View gifts` or `Check event support`.
- If no useful URL exists, do not show a supplier button.
- Do not add fake affiliate URLs or empty affiliate placeholders.
- Do not claim live prices, live stock, guaranteed delivery or confirmed supplier quotes.

## Known Limitations

- Supplier pages can change without notice. Recheck URLs before a major launch, paid campaign or affiliate/tracked-link migration.
- Some retailers may redirect category pages based on cookies, region or stock.
- ClientCellar remains useful without affiliate links because planners and guides show supplier routes directly.
