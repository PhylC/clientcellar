# Supplier Link Audit

Internal audit for public supplier and retailer links used by ClientCellar. Checked on 2026-05-10.

| Supplier | Old URL | New URL | Purpose | Notes |
| --- | --- | --- | --- | --- |
| Majestic | `https://www.majestic.co.uk/services/corporate` | `https://www.majestic.co.uk/services/corporate-gifting` | Corporate gifting page | Replaced broken corporate page that showed a not-found style message. The new page includes client/team gifting copy and commercial enquiry details. |
| Laithwaites | `https://www.laithwaites.co.uk/` | `https://www.laithwaites.co.uk/gifts/corporate-wine-gifts` | Corporate wine gifts page | Replaced homepage with a business-gifting page containing gift products, bulk order guidance and gift FAQs. |
| Virgin Wines | `https://www.virginwines.co.uk/` | `https://www.virginwines.co.uk/corporate-gifts` | Corporate gifts and wine services page | Replaced homepage with dedicated commercial/corporate gifting page. |
| The Wine Society | `https://www.thewinesociety.com/` | `https://www.thewinesociety.com/buy/gifts` | Wine gifts page | Replaced homepage with gift page. Buyers still need to note membership requirements. |
| Berry Bros. & Rudd | `https://www.bbr.com/corporate` | `https://www.bbr.com/wines` | Fine wines range page | Replaced weak/dead corporate URL with live fine wine range page. BB&R private events are handled through support/event guidance rather than a corporate gifting claim. |
| Fortnum & Mason | `https://www.fortnumandmason.com/corporate-gifting` | `https://www.fortnumandmason.com/corporate-gifting` | Corporate gifting page | Kept. Page is relevant for premium hamper and corporate gifting enquiries. |
| Harvey Nichols hampers | `https://www.harveynichols.com/` | `https://www.harveynichols.com/info/help/services/corporate-gifts/` | Corporate gifts service page | Replaced homepage with corporate gifting/service page that references food and wine hampers and business enquiries. |
| Selfridges hampers | `https://www.selfridges.com/` | `https://www.selfridges.com/GB/en/cat/gifts/wine-food-gifts/foodhall/hampers/` | Wine and food hampers page | Replaced homepage with UK hamper category page. |
| M&S food and drink gifts | `https://www.marksandspencer.com/corporate-gifts` | `https://www.marksandspencer.com/l/gifts/food-and-drink-gifts` | Food and drink gifts page | Replaced broken/weak corporate-gifts URL and renamed the supplier entry away from a corporate-partner implication. |
| Waitrose Cellar | `https://www.waitrosecellar.com/` | `https://www.waitrosecellar.com/shop/gifts/wine-gifts` | Wine gifts page | Replaced homepage with wine gifts category page. |
| Guide merchant link: Majestic Wine | `https://www.majestic.co.uk/` | `https://www.majestic.co.uk/services/corporate-gifting` | Corporate gifting page | Updated shared guide merchant links to match audited destination. |
| Guide merchant link: Berry Bros. & Rudd | `https://www.bbr.com/` | `https://www.bbr.com/wines` | Fine wines range page | Updated shared guide merchant links to avoid generic homepage. |
| Guide merchant link: Fortnum & Mason | `https://www.fortnumandmason.com/` | `https://www.fortnumandmason.com/corporate-gifting` | Corporate gifting page | Updated shared guide merchant links to avoid generic homepage. |

## Display Rules

- Normal supplier URLs are used by default.
- Optional affiliate URLs remain supported but must only render when `is_affiliate` is true and a real affiliate URL exists.
- Empty supplier URLs should not render dead buttons.
- Link labels should describe the action honestly, such as `Check corporate gifting options`, `View wine gifts`, `View hamper options` or `Visit supplier`.

## Known Limitations

- Supplier pages can change without notice. Recheck any supplier URL before a major launch, paid campaign or affiliate/tracked-link migration.
- Some retailers may redirect or localise category pages based on cookies, region or stock. The current URLs loaded as useful public pages during this audit.
- ClientCellar does not claim any supplier listed here is a partner unless a relationship is explicitly labelled elsewhere.
