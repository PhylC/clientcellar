# Supplier Link Audit

Internal audit for public supplier and retailer links used by ClientCellar. Checked date: 2026-05-10.

ClientCellar does not claim these suppliers are partners unless separately confirmed. Links are normal public supplier links unless an affiliate or tracked relationship is explicitly configured.

| Supplier | Old URL if fixed | New URL | Page purpose | Where used | Checked date | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Majestic | No change | `https://www.majestic.co.uk/services/corporate-gifting` | Corporate gifting page | `/suppliers`, gift planner route cards, event planner route cards, guides | 2026-05-10 | Live public page for corporate gifting and larger-order conversations. |
| Laithwaites | `https://www.laithwaites.co.uk/wine-gifts` | `https://www.laithwaites.co.uk/gifts/wine-gifts` | Wine gifts page | `/suppliers`, gift planner route cards | 2026-05-10 | Old path returned 404 in link check; replaced with live UK wine gifts page. |
| The Wine Society | `https://www.thewinesociety.com/gifts` | `https://www.thewinesociety.com/buy/gifts` | Wine gifts page | `/suppliers`, gift planner premium route cards | 2026-05-10 | Public gift page; membership model may apply, so buyers should check suitability. |
| Berry Bros. & Rudd | `https://www.bbr.com/gifts` | `https://www.bbr.com/wines` | Fine wines range page | `/suppliers`, gift planner premium route cards, guides | 2026-05-10 | Old gifts path returned 404; fine wines page is a live premium merchant route. |
| Virgin Wines | `https://www.virginwines.co.uk/wine-gifts` | `https://www.virginwines.co.uk/gifts/wine-gifts` | Wine gifts page | `/suppliers`, gift planner route cards, virtual tasting pack route | 2026-05-10 | Live public wine gifts page. |
| Fortnum & Mason | No change | `https://www.fortnumandmason.com/hampers` | Hampers page | `/suppliers`, gift planner premium and hamper route cards, guides | 2026-05-10 | Live hampers page suitable for premium food and drink gifting research. |
| M&S Hampers | `https://www.marksandspencer.com/l/hampers` | `https://www.marksandspencer.com/l/gifts/food-and-drink-gifts/hampers` | Food and drink hampers page | `/suppliers`, gift planner hamper route cards, event retailer route cards | 2026-05-10 | Fixed broken M&S page that showed "Sorry, we can't find that page". New URL returned HTTP 200 and shows the hampers category. |
| Waitrose Cellar Gifts | `https://www.waitrosecellar.com/gifts` | `https://www.waitrosecellar.com/shop/gifts/wine-gifts` | Wine gifts page | `/suppliers`, gift planner mainstream route cards, event retailer route cards | 2026-05-10 | More specific wine gifts category page. |
| John Lewis Hampers | `https://www.johnlewis.com/browse/gifts/gift-food-alcohol/hampers/_/N-7d8p` | `https://www.johnlewis.com/browse/gifts/gift-food-alcohol/hampers/_/N-2q3pZ1z0vwzu` | Food hampers and gift baskets page | `/suppliers`, gift planner hamper route cards | 2026-05-10 | Replaced stale category token with current indexed hamper category URL. |
| Local independent wine merchant | No URL | No URL | Search locally | `/suppliers`, event planner route cards | 2026-05-10 | Show search suggestion instead of a button: `independent wine merchant near [location]`. |
| Noughty / Thomson & Scott | No change | `https://noughtyaf.com/` | Non-alcoholic sparkling wine | `/suppliers`, gift planner non-alcoholic route cards, event planner non-alcoholic route cards | 2026-05-10 | Live public site for alcohol-free sparkling options. |
| Dry Drinker | No change | `https://drydrinker.com/` | Alcohol-free drinks retailer | `/suppliers`, gift planner non-alcoholic route cards, event planner non-alcoholic route cards | 2026-05-10 | Live public site for alcohol-free beer, wine and spirits alternatives. |

## Display Rules

- If `supplier.isAffiliate` / `supplier.is_affiliate` is true and a real affiliate URL exists, use the affiliate URL and show the appropriate disclosure.
- If a normal supplier URL exists, use the normal URL and neutral button copy such as `Visit supplier`, `View wine gifts`, `View hampers` or `Check corporate gifting`.
- If no URL exists, show a useful search suggestion instead of a button.
- Do not add fake affiliate URLs or empty affiliate placeholders.
- Do not claim live prices, live stock, guaranteed delivery or confirmed supplier quotes.

## Known Limitations

- Supplier pages can change without notice. Recheck URLs before a major launch, paid campaign or affiliate/tracked-link migration.
- Some retailers may redirect category pages based on cookies, region or stock.
- ClientCellar remains useful without affiliate links because planners and guides show supplier routes directly.
