# ClientCellar affiliate and supplier outreach tracker

Updated: 2026-08-15

Purpose: maintain the working list of affiliate networks, direct supplier targets and sponsored-placement prospects for ClientCellar. Keep this as the source of truth for outreach status, rejections, approvals and follow-ups.

## Current status summary

- Live affiliate infrastructure is ready via `CLIENTCELLAR_AFFILIATE_URL_*` environment variables.
- No real approved affiliate URLs are currently configured in the repo.
- The repo does not contain exact historic rejection emails or rejection wording. If recovered from email/network dashboards, paste the date and reason into the tracker below.
- Strong review evidence is now available: indexed public site, supplier directory, editorial policy, affiliate disclosure, pricing page, Premium Brief Pack example and early GSC visibility.
- Awin publisher profile copy is prepared in `docs/awin-publisher-profile.md`.

## Evidence pack to use

Use these URLs in network applications and supplier emails:

- Homepage: `https://clientcellar.co.uk/`
- Gift planner: `https://clientcellar.co.uk/gift-planner`
- Event planner: `https://clientcellar.co.uk/event-planner`
- Supplier directory: `https://clientcellar.co.uk/supplier-directory`
- Supplier comparison: `https://clientcellar.co.uk/uk-wine-gift-supplier-comparison`
- Guides: `https://clientcellar.co.uk/guides`
- Champagne guide: `https://clientcellar.co.uk/guides/champagne-gifts-for-clients`
- Christmas corporate wine gifts: `https://clientcellar.co.uk/guides/christmas-corporate-wine-gifts`
- Example Premium Brief Pack: `https://clientcellar.co.uk/example-premium-brief-pack`
- Pricing: `https://clientcellar.co.uk/pricing`
- Publisher profile: `https://clientcellar.co.uk/network-readiness`
- Editorial policy: `https://clientcellar.co.uk/editorial-policy`
- Affiliate disclosure: `https://clientcellar.co.uk/affiliate-disclosure`
- Supplier partnerships: `https://clientcellar.co.uk/supplier-partnerships`

Use current GSC evidence from `docs/gsc-action-log-2026-08-15.md`:

- `/guides/corporate-wine-gifts-uk`: 826 impressions, 1 click.
- `/guides/best-client-wine-gifts`: 316 impressions, 0 clicks.
- `/guides/champagne-gifts-for-clients`: 232 impressions, 0 clicks, average position 7.56.
- `/guides/christmas-corporate-wine-gifts`: 145 impressions, 0 clicks.
- `/supplier-directory`: 97 impressions, 1 click.

## Outreach stages

- `Research`: target identified, programme/contact not yet confirmed.
- `Ready to apply`: programme/contact route exists and evidence pack is ready.
- `Applied`: application submitted; record date and proof.
- `Rejected`: record exact reason and date. Do not reapply without changing evidence or positioning.
- `Follow-up`: waiting after application/email.
- `Approved`: approved; add tracked URL through env var and run `docs/live-affiliate-link-setup.md`.
- `Live`: affiliate/tracked/sponsored link is active and disclosed.
- `Parked`: not worth pursuing now.

## Priority target tracker

| Priority | Target | Type | Route / network | Current status | Previous rejection/status | Why it fits ClientCellar | Next action | Link env var if approved | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1 | Majestic Wine | Affiliate + direct supplier | Awin merchant profile found; direct commercial page exists | Applied | Applied 2026-08-15; awaiting response | Strong corporate gifting and event relevance; existing supplier-directory and planner fit | Check Awin status in 3-5 working days; if rejected, record exact reason and consider direct Majestic Commercial outreach | `CLIENTCELLAR_AFFILIATE_URL_MAJESTIC`, `CLIENTCELLAR_AFFILIATE_URL_MAJESTIC_COMMERCIAL` | Public Awin profile lists Majestic Wine programme and content-friendly assets. |
| P1 | Laithwaites | Affiliate + direct supplier | UK affiliate page; corporate/business page exists | Ready to apply | Unknown, exact old status not found locally | High-fit corporate wine gifts and business gifting content | Apply/reapply through stated affiliate/network route; emphasise business gift guides and supplier-ready planning | `CLIENTCELLAR_AFFILIATE_URL_LAITHWAITES` | UK affiliate page references LinkShare/Rakuten-style route; confirm current dashboard route before applying. |
| P1 | Virgin Wines | Affiliate/direct supplier | Research needed | Research | Unknown, exact old status not found locally | Corporate gifts, staff rewards and branded gifting already appear in directory | Confirm current affiliate/network route or direct corporate contact, then apply/email | `CLIENTCELLAR_AFFILIATE_URL_VIRGIN_WINES` | Good fit but public programme route still needs confirmation. |
| P1 | Slurp | Direct supplier / tracked link | Direct corporate email/page found | Ready to email | Unknown | Corporate gifting services, client gifting, employee gifting and event support match ClientCellar closely | Send direct supplier visibility email asking about tracked/affiliate route or sponsored test | `CLIENTCELLAR_AFFILIATE_URL_SLURP` | Direct corporate route may be stronger than network application. |
| P1 | Wine Direct | Direct supplier / tracked link | Direct corporate gift page found | Ready to email | Unknown | Explicit corporate wine gifts and spreadsheet/order process fits Premium Brief Pack audience | Send direct supplier visibility email asking about referral/tracked link or sponsored directory test | `CLIENTCELLAR_AFFILIATE_URL_WINE_DIRECT` | Strong direct outreach candidate. |
| P1 | Hay Wines | Direct supplier / sponsored placement | Direct company gifts page exists | Ready to email | Unknown | Independent merchant angle; company gifts/tastings fit event and premium briefs | Send direct supplier visibility email; ask for corporate ordering details and tracked-link possibility | `CLIENTCELLAR_AFFILIATE_URL_HAY_WINES` | Likely more personal direct relationship than network affiliate. |
| P1 | Fortnum & Mason | Affiliate / premium hamper | Research current programme route | Research | Unknown | Premium hampers and senior client gifts; strong Champagne/Christmas fit | Confirm affiliate network route and apply only to hamper/wine-hamper content | `CLIENTCELLAR_AFFILIATE_URL_FORTNUM_MASON` | Use carefully; premium but may be selective. |
| P2 | Waitrose Cellar | Affiliate / retailer | Research current programme route | Research | Unknown | Useful mainstream wine gift benchmark | Confirm affiliate route and apply if content publishers accepted | `CLIENTCELLAR_AFFILIATE_URL_WAITROSE_CELLAR` | Good buyer utility; may be harder if programme is broader Waitrose/John Lewis. |
| P2 | John Lewis Hampers | Affiliate / retailer | Research current programme route | Research | Unknown | Broad hamper pages fit Christmas and mixed-recipient gifting | Confirm programme route and whether food/alcohol hamper pages are allowed | `CLIENTCELLAR_AFFILIATE_URL_JOHN_LEWIS_HAMPERS` | Use mainly for hamper/client gift content. |
| P2 | M&S Hampers | Affiliate / retailer | Research current programme route | Research | Unknown | Mainstream food and drink hampers; accessible staff/client route | Confirm programme route and category permission | `CLIENTCELLAR_AFFILIATE_URL_MARKS_SPENCER_CORPORATE` | Good user fit, likely more generic affiliate route. |
| P2 | Harvey Nichols Hampers | Affiliate / premium hamper | Research current programme route | Research | Unknown | Premium wine/spirit hampers for senior gifting | Confirm affiliate route; apply with premium gift pages | `CLIENTCELLAR_AFFILIATE_URL_HARVEY_NICHOLS_HAMPERS` | Premium fit but not core corporate ordering. |
| P2 | Selfridges Hampers | Affiliate / premium hamper | Research current programme route | Research | Unknown | Premium/luxury hamper route | Confirm affiliate route; apply with luxury hamper/champagne pages | `CLIENTCELLAR_AFFILIATE_URL_SELFRIDGES_HAMPERS` | Use where page context is premium. |
| P2 | Regency Hampers | Affiliate / hamper supplier | Awin programme terms found | Applied | Applied 2026-08-15; awaiting response | Strong hamper/corporate gift fit and content publishers appear permitted | Check Awin status in 3-5 working days; if approved, add supplier mapping and env-var support | Add supplier mapping first if approved | Not currently in supplier config; add only after approval/editorial review. |
| P2 | Hay Hampers / Hampers.co.uk | Affiliate / hamper supplier | Awin profile found publicly, but direct profile showed inactive in Awin UI | Blocked | Not previously tracked | Corporate and multiple-address orders mentioned; good Christmas/client fit | Skip for now unless it appears in authenticated Awin search later | Add supplier mapping first if approved | Direct profile returned "The account you are trying to view is not active" on 2026-08-15. |
| P2 | Prestige Hampers | Affiliate / hamper supplier | Awin profile found and visible in Awin UI | Applied | Applied 2026-08-15; awaiting response | Hampers and gifts across UK; useful for Christmas pages | Check Awin status in 3-5 working days; if approved, add supplier mapping and env-var support | Add supplier mapping first if approved | Not currently in supplier config. |
| P2 | Vintage Wine Gifts | Affiliate / wine and Champagne gifts | Awin profile found | Approved; ready for production env var | Accepted on Awin 2026-08-15 | Vintage wine, Champagne and corporate gift fit for premium/milestone pages | Set `CLIENTCELLAR_AFFILIATE_URL_VINTAGE_WINE_GIFTS` in production, then run live-link QA | `CLIENTCELLAR_AFFILIATE_URL_VINTAGE_WINE_GIFTS` | First accepted Awin wine-gift programme. Approved deeplink generated for corporate gifts page. |
| P3 | Bottle in a Box | Affiliate / alcohol gift hampers | Affiliate page found | Ready to apply | Not previously tracked | Alcohol gift hampers and corporate gifting sites explicitly mentioned | Apply if alcohol/corporate gifting terms fit; review product quality and B2B usefulness | Add supplier mapping first if approved | Good for niche hamper/gift guide pages. |
| P3 | Noughty / Thomson & Scott | Direct/affiliate alcohol-free | Research current programme route | Research | Unknown | Alcohol-free sparkling gifts and inclusive workplace gifting | Research affiliate route or email direct about tracked links | `CLIENTCELLAR_AFFILIATE_URL_NOUGHTY_THOMSON_SCOTT` | Useful compliance-friendly category. |
| P3 | Dry Drinker | Direct/affiliate alcohol-free | Research current programme route | Research | Unknown | Alcohol-free drinks retailer for inclusive gifting/events | Research affiliate route or email direct about tracked links | `CLIENTCELLAR_AFFILIATE_URL_DRY_DRINKER` | Good supporting category, not first revenue priority. |
| P3 | Amazon Associates | Broad affiliate | Known broad network, exact ClientCellar status unknown | Research | Unknown | Can monetise gift-card fallback, but weaker editorial fit | Only apply/use if direct supplier routes stall; keep low prominence | `CLIENTCELLAR_AFFILIATE_URL_AMAZON` | Avoid making ClientCellar feel generic. |
| P3 | Skimlinks or similar content monetisation platform | Subnetwork/content monetisation | Research current eligibility | Research | User recalls big affiliate sites previously refused; exact platform/status unknown | Could unlock broad retailer monetisation without individual approvals | Reapply only with stronger evidence pack and exact rejection reason if available | N/A | Useful fallback, but direct high-fit suppliers should come first. |

## First outreach batch

Start with Awin-accessible targets first:

1. Majestic Wine: Awin application/reapplication.
2. Hay Hampers / Hampers.co.uk: Awin application.
3. Regency Hampers: Awin application.
4. Prestige Hampers: Awin application.
5. The British Hamper Company: Awin application.
6. Vintage Wine Gifts: Awin application.
7. Cartwright & Butler: Awin application.

Keep direct supplier emails to Slurp, Wine Direct and Hay Wines as the next batch after the Awin applications.

## Awin-first shortlist

| Batch | Target | Awin ID | Fit | Why apply now | Status |
| --- | --- | ---: | --- | --- | --- |
| 1 | Majestic Wine | 1546 | Wine merchant / corporate gifting / event wine | Already in ClientCellar supplier flow; strong corporate wine gifting relevance | Applied 2026-08-15 |
| 1 | Hay Hampers / Hampers.co.uk | 29169 | Luxury hampers / food, wine and beer gifts / corporate orders | Strong Christmas/client hamper fit; Awin profile mentions corporate and multiple-address orders | Blocked: direct Awin profile showed inactive |
| 1 | Regency Hampers | 119899 | Luxury food and drink hampers / corporate buyers | Awin profile explicitly references corporate buyers, Q4 gifting and deeplinking | Applied 2026-08-15 |
| 1 | Prestige Hampers | 32959 | Hampers and gifts | Strong hamper/Christmas fit, active Awin profile, 70-day cookie and product feed | Applied 2026-08-15 |
| 2 | The British Hamper Company | 35023 | Premium British hampers | High AOV, UK/international gifting, deeplinks and content-friendly fit | Ready to apply |
| 2 | Vintage Wine Gifts | 806 | Vintage wine, Champagne and spirits gifts | Direct wine/Champagne gift fit; useful for premium and milestone gift pages | Approved 2026-08-15 |
| 2 | Cartwright & Butler | 21047 | Luxury food and drink hampers | Premium food gifting fit; useful for alcohol-free/mixed-recipient routes | Ready to apply |
| 3 | Virginia Hayward Hampers | 2500 | Hampers, gifts and corporate customers | Good corporate hamper fit; lower commission than some alternatives | Research/application later |
| 3 | Blossoming Gifts | 5836 | Flowers, hampers, wines and personalised gifts | Broader gifting fit; less focused on corporate wine but useful for alternatives | Research/application later |
| 3 | 8wines UK | 106707 | Wine retailer | Wine fit, but less obviously UK corporate gifting-led | Research/application later |
| 3 | Wine52 | 110978 | Wine subscription club | Wine fit but subscription/free-case angle is less aligned with business gifting | Park unless needed |

## Application/reapplication notes

For previously rejected targets, use this angle:

> ClientCellar was newer when first reviewed. Since then it has more indexed public content, a supplier directory, editorial policy, affiliate disclosure, public publisher profile, Premium Brief Pack example and Search Console evidence for relevant corporate wine gift and supplier queries.

Do not overstate traffic. Use “early search visibility” and quote the GSC page/query examples above where useful.

## Direct supplier email draft

Subject: ClientCellar supplier visibility for corporate wine gifts

Hi [Name],

I run ClientCellar, a UK-focused planning site that helps business buyers choose corporate wine gifts, client hampers and event drinks suppliers.

I’m reviewing a small number of suppliers for our business-buyer pages and thought [Supplier] looked relevant because [specific reason].

Useful review links:

- Supplier directory: https://clientcellar.co.uk/supplier-directory
- Gift planner: https://clientcellar.co.uk/gift-planner
- Publisher profile: https://clientcellar.co.uk/network-readiness
- Editorial policy: https://clientcellar.co.uk/editorial-policy

There are a few possible routes:

- editorial review for directory inclusion where useful for buyers
- tracked or affiliate links if you already support them
- a small clearly labelled sponsored placement test on relevant pages
- supplier profile updates with corporate ordering details, delivery regions and trade contact routes

ClientCellar does not publish fake reviews, hide paid placements or imply official partnerships unless agreed. Supplier availability, pricing and delivery still need to be confirmed directly by buyers.

If this is relevant, who is the best person to speak to about corporate gifting / partnerships?

Best,
Phyl
ClientCellar
partners@clientcellar.co.uk

## Affiliate network application note

Use this short publisher description:

> ClientCellar helps UK business buyers plan corporate wine gifts, client hampers, staff rewards and wine tasting/event drinks suppliers. The site publishes practical buying guides, free planners, supplier-directory content and supplier-ready Premium Brief Packs. Recommendations are editorially selected based on buyer usefulness, corporate ordering support, budget fit, presentation, delivery practicality and suitability for professional relationships. Commercial links are disclosed clearly and ClientCellar does not claim live prices, stock or supplier availability unless verified directly.

Review URLs:

- `https://clientcellar.co.uk/network-readiness`
- `https://clientcellar.co.uk/supplier-directory`
- `https://clientcellar.co.uk/gift-planner`
- `https://clientcellar.co.uk/guides/champagne-gifts-for-clients`
- `https://clientcellar.co.uk/affiliate-disclosure`
- `https://clientcellar.co.uk/editorial-policy`

## Rejection log

| Date | Target | Channel | Outcome | Exact reason | Evidence submitted | Next move |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-08-15 | Majestic Wine | Awin | Applied | Pending | Awin publisher profile plus ClientCellar site/evidence URLs | Check status in 3-5 working days. |
| 2026-08-15 | Regency Hampers | Awin | Applied | Pending | ClientCellar site/evidence URLs and corporate hamper/gifting positioning | Check status in 3-5 working days. |
| 2026-08-15 | Prestige Hampers | Awin | Applied | Pending | ClientCellar site/evidence URLs and Christmas/client hamper positioning | Check status in 3-5 working days. |
| 2026-08-15 | Vintage Wine Gifts | Awin | Approved | Accepted | ClientCellar site/evidence URLs and premium wine/Champagne gift positioning | Production env var ready: `CLIENTCELLAR_AFFILIATE_URL_VINTAGE_WINE_GIFTS`. |
| Unknown | Big affiliate site(s) | Unknown | Rejected/refused | Exact rejection not found locally | Unknown | Recover exact rejection from email/dashboard before reapplying. |
