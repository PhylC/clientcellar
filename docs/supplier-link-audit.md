# Supplier Link Audit

Internal audit for public supplier and retailer links used by ClientCellar.

Updated: 2026-08-21

ClientCellar does not claim these suppliers are partners unless separately confirmed. Recommendations are editorially selected for now. Links are normal public supplier links unless an affiliate or tracked relationship is explicitly configured.

The canonical supplier URL source is `data/supplier_links.py`. Planner, guide and supplier-directory rendering should use that central config rather than hard-coded URLs.

## Current supplier configuration

| Supplier | Active | Current destination | Page purpose | Where used | Affiliate configured | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Majestic Corporate Gifts | Yes | `https://www.majestic.co.uk/services/corporate-gifting` | Corporate gifting page | Gift planner, event routes, supplier directory, premium packs, guides | No | Editorial-only for now. Awin rejected ClientCellar on 2026-08-21 because the advertiser does not work with this publisher type. |
| Majestic Commercial / events | Yes | `https://www.majestic.co.uk/information/majestic-commercial/corporate-partnerships-events` | Corporate partnerships and events page | Event planner, premium event packs, supplier directory, guides | No | Editorial-only for now. Do not use affiliate/tracked links unless a future reapplication is approved. |
| Laithwaites Corporate Wine Gifts | Yes | `https://www.laithwaites.co.uk/gifts/corporate-wine-gifts` | Corporate wine gifts page | Gift planner, event planner, premium comparisons, guides | No | High-fit affiliate/direct outreach candidate if corporate gifting tracking is available. |
| Virgin Wines Corporate Gifts | Yes | `https://www.virginwines.co.uk/corporate-gifting` | Corporate gifts page | Gift planner, event planner, premium comparisons, supplier directory, guides | No | High-fit candidate for affiliate reapplication/direct outreach. Fallback remains `https://www.virginwines.co.uk/corporate-gifts`. |
| Slurp | Yes | `https://www.slurp.co.uk/pages/gifting-services` | Gifting services page | Supplier directory and corporate gifting routes | No | Strong direct outreach candidate because the route is service-led. Contact URL uses `https://www.slurp.co.uk/pages/client-gifting`. |
| Hay Wines | Yes | `https://haywines.co.uk/pages/company-gifts` | Company gifts page | Supplier directory and independent merchant routes | No | Good direct outreach candidate for bespoke/company gift and tasting positioning. |
| Wine Direct | Yes | `https://www.winedirect.co.uk/info/corporate-wine-gifts` | Corporate wine gifts page | Supplier directory, premium comparisons and corporate gifting routes | No | High-fit supplier-direct candidate because the page is explicitly corporate. |
| Vintage Wine Gifts | Yes | `https://www.vintagewinegifts.co.uk/acatalog/corporate_gifts.html` | Corporate gifts page | Supplier directory and premium wine/Champagne gift routes | Yes when `CLIENTCELLAR_AFFILIATE_URL_VINTAGE_WINE_GIFTS` is set | Approved on Awin 2026-08-15. First accepted affiliate programme; use approved deeplink via production env var. |
| The Wine Society | Yes in directory config; inactive in legacy planner entries | `https://www.thewinesociety.com/buy/gifts/gift-cases-and-wine-hampers/` | Wine gifts page | Supplier directory where visible | No | Check membership suitability and current gift URL before using in stronger commercial copy. |
| Berry Bros. & Rudd | No | None | Disabled supplier link | Not shown as an active outbound route | No | Kept inactive because there is no verified useful destination in the central config. |
| Fortnum & Mason | Yes | `https://www.fortnumandmason.com/hampers/all-hampers/wine-hampers` | Wine hampers page | Gift planner premium route, premium packs, supplier directory, guides | No | Strong premium-hamper candidate; confirm category URL before campaign/affiliate migration. |
| M&S Hampers | Yes | `https://www.marksandspencer.com/l/gifts/food-and-drink-gifts/hampers/wine-hampers` | Wine hampers page | Gift planner hamper route, premium packs, supplier directory | No | Mainstream hamper route. Good for buyer utility, but direct partnership route may be harder. |
| Waitrose Cellar | Yes | `https://www.waitrosecellar.com/shop/gifts/wine-gifts` | Wine gifts page | Event planner, mainstream gift route, supplier directory, guides | No | Safe mainstream benchmark. Contact URL also references mixed wine case gifts. |
| John Lewis Hampers | Yes | `https://www.johnlewis.com/browse/gifts/gift-food-alcohol/hampers/_/N-2q3pZ1z0vwzu` | Hampers category | Gift planner hamper alternatives and guides | No | Useful broad hamper route. Category URL should be rechecked before major seasonal campaigns. |
| Selfridges hampers | Yes | `https://www.selfridges.com/GB/en/cat/foodhall/hampers/wine-spirits-hampers/` | Wine and spirits hampers page | Supplier directory premium hamper routes | No | Premium/luxury hamper route. Confirm category is still available before commercial use. |
| Harrods hampers | Yes in link config | `https://www.harrods.com/en-gb/shopping/hampers` | Hampers page | Available to use in guides/routes where suitable | No | Present in central config but not currently a main supplier-directory card. |
| Harvey Nichols hampers | Yes | `https://www.harveynichols.com/food-and-wine/hampers/wine-and-spirit-hampers/` | Wine and spirit hampers page | Supplier directory premium hamper routes | No | Premium/luxury route. Contact URL uses broader hampers page. |
| Great Wine Co. | Yes | `https://greatwine.co.uk/gifts-more/mixed-cases/` | Mixed cases page | Supplier directory wine/event routes | No | Useful for mixed cases and event-friendly buying, though less explicitly corporate. |
| Hotel Chocolat | Yes in link config | `https://www.hotelchocolat.com/uk/shop/gift-ideas/` | Gift ideas page | Available for staff gift/non-wine gifting where suitable | No | Non-wine gifting route. Use only where the page context fits chocolate/staff gifts. |
| Amazon | Yes in link config | `https://www.amazon.co.uk/gift-cards-vouchers/b?node=1571304031` | Gift cards/vouchers page | Available for mainstream gift-card fallback where suitable | No | Use cautiously; weaker fit for wine/editorial supplier positioning. |
| Noughty / Thomson & Scott | Yes | `https://noughtyaf.com/` | Non-alcoholic sparkling wine | Non-alcoholic supplier routes and inclusive gifting notes | No | Useful for alcohol-free alternatives and workplace-safe planning. |
| Dry Drinker | Yes | `https://drydrinker.com/` | Alcohol-free drinks retailer | Non-alcoholic supplier routes and inclusive gifting notes | No | Useful for alcohol-free gifting and events. |
| Local independent wine merchant | Search suggestion only | None | Search locally | Planner route guidance | No | Intentionally no outbound URL. |

## How to run the audit

Local configuration check:

```bash
.venv/bin/python scripts/audit_supplier_links.py
```

Optional live URL check:

```bash
.venv/bin/python scripts/audit_supplier_links.py --check-live
```

Treat live results carefully. Retailers may block bot requests, return cookie/region redirects, or reject `HEAD` requests even where the page works in a browser.

## Display rules

- If `supplier.isAffiliate` / `supplier.is_affiliate` is true and a real affiliate URL exists, use the affiliate URL and show the appropriate disclosure.
- If a normal supplier URL exists, use the normal URL and clear button copy such as `View corporate gifts`, `View corporate wine gifts`, `View hampers`, `View gifts` or `Check event support`.
- If no useful URL exists, do not show a supplier button.
- Do not add fake affiliate URLs or empty affiliate placeholders.
- Do not claim live prices, live stock, guaranteed delivery or confirmed supplier quotes.
- Do not describe a supplier as a partner unless there is a confirmed relationship.

## Monetisation notes

High-fit direct outreach or affiliate reapplication candidates:

- Virgin Wines
- Laithwaites
- Slurp
- Hay Wines
- Wine Direct
- Fortnum & Mason
- Waitrose Cellar
- premium hamper retailers where the programme accepts content-led publishers

Review-later editorial supplier:

- Majestic Corporate Gifts / Majestic Commercial: useful buyer route, but parked for affiliate purposes after Awin rejection on 2026-08-21. Revisit no earlier than 2026-11-21 with stronger profile and traffic evidence.

Lower-fit or use-cautiously routes:

- Amazon: broad but less distinctive for ClientCellar's wine and supplier-led positioning.
- Hotel Chocolat: useful for adjacent staff/client gifting, not core wine/event monetisation.
- Generic department-store pages: use where the category page is specific to hampers, wine gifts or premium food-and-drink gifting.

## Known limitations

- Supplier pages can change without notice. Recheck URLs before a major launch, paid campaign or affiliate/tracked-link migration.
- Some retailers may redirect category pages based on cookies, region or stock.
- Live HTTP checks do not replace opening high-priority supplier pages manually in a browser before outreach or campaign launch.
- ClientCellar remains useful without affiliate links because planners and guides show supplier routes directly.
