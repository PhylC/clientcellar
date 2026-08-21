# Majestic Wine Awin application

Updated: 2026-08-21

Target: Majestic Wine  
Network: Awin  
Programme ID: `1546`  
Public profile: `https://ui.awin.com/merchant-profile/1546`  
Application priority: Parked until reapplication review  
Tracker: `docs/affiliate-supplier-outreach-tracker.md`

## Current outcome

Majestic Wine rejected ClientCellar's Awin application on 2026-08-21.

Exact reason supplied by Awin:

> Advertiser doesn't work with this publisher type

Action now:

- Keep Majestic as a normal editorial supplier reference only.
- Do not use Majestic affiliate or tracked links.
- Do not describe Majestic as a partner, approved supplier, affiliate supplier or sponsored placement.
- Review for possible reapplication no earlier than 2026-11-21, after updating the Awin publisher profile and gathering stronger evidence of relevant corporate gifting / supplier-directory traffic.
- Consider direct Majestic Commercial outreach separately only if the message is clearly about editorial listing or direct business relationship, not an implied affiliate approval.

## Programme fit notes

Majestic is a strong fit for ClientCellar because:

- It is a UK specialist wine retailer with corporate gifting, event and commercial routes.
- ClientCellar already references Majestic in supplier-directory and planner flows as a useful buyer route.
- ClientCellar has active content around corporate wine gifts, client gifts, Champagne gifts, Christmas gifts and event wine.
- Majestic's public Awin information states content publishers are allowed.
- Majestic supports deeplinking to products or categories through Awin's deeplinking tool.

Public programme details to reference carefully:

- 30-day cookie.
- 4% commission for new customers and 1% for existing customers.
- Content publishers permitted.
- Affiliates are manually approved.
- Child-related sites may be rejected because Majestic sells age-restricted products.
- Brand/social restrictions apply; do not register social handles, usernames or domains containing the Majestic brand.

## Recommended application form fields

### Website

`https://clientcellar.co.uk/`

### Website / company description

ClientCellar is a UK-focused business gifting and event drinks planning website. It helps professionals choose suitable corporate wine gifts, client hampers, staff rewards and wine tasting/event drinks suppliers using practical guides, free planning tools, supplier-directory content and paid supplier-ready Premium Brief Packs.

The site is not a voucher-code or discount site. It is a planning and supplier-discovery resource for buyers who are deciding what type of supplier fits their brief.

### Promotional methods

Content / SEO / editorial guides / planning tools / supplier directory.

No PPC brand bidding, no coupon scraping, no fake reviews, no direct alcohol sales, no under-18 targeting.

### Primary audience

UK business buyers and professionals planning:

- client wine gifts
- staff rewards
- corporate Christmas gifts
- Champagne or sparkling gifts
- client hampers
- event wine and tasting supplier routes

### Why ClientCellar is a good fit for Majestic

ClientCellar is a strong fit for the Majestic Wine programme because the site helps UK business buyers plan corporate wine gifts and event drinks before choosing a supplier.

Majestic is already a useful editorial route in ClientCellar's supplier directory and planner flow because of its broad UK wine range, corporate gifting page, event/commercial relevance and recognisable buyer proposition.

ClientCellar visitors are not looking for generic discount codes. They are usually shaping a buying brief: budget, recipient count, occasion, delivery needs, gift suitability, supplier questions and internal approval notes. That makes Majestic relevant for content-led supplier discovery, corporate gifting and event-drinks decisions.

### Application message

Hi Majestic / Awin team,

I would like to apply to the Majestic Wine affiliate programme with ClientCellar.

ClientCellar is a UK-focused business gifting and event drinks planning site. It helps professionals plan corporate wine gifts, client hampers, staff rewards and event drinks suppliers through practical guides, free planning tools, a supplier directory and supplier-ready Premium Brief Packs.

Majestic is a strong fit for the site because ClientCellar visitors are often comparing corporate wine gift and event wine routes before contacting suppliers or ordering. Majestic is already referenced editorially as a useful UK route for corporate gifting, broader wine gifts and event-friendly buying.

Useful review pages:

- Homepage: https://clientcellar.co.uk/
- Supplier directory: https://clientcellar.co.uk/supplier-directory
- Gift planner: https://clientcellar.co.uk/gift-planner
- Event planner: https://clientcellar.co.uk/event-planner
- Publisher profile: https://clientcellar.co.uk/network-readiness
- Champagne/client gift guide: https://clientcellar.co.uk/guides/champagne-gifts-for-clients
- Corporate wine gifts guide: https://clientcellar.co.uk/guides/corporate-wine-gifts-uk
- Affiliate disclosure: https://clientcellar.co.uk/affiliate-disclosure
- Editorial policy: https://clientcellar.co.uk/editorial-policy

ClientCellar is editorial and planning-led rather than voucher-code-led. Supplier references are based on buyer usefulness, corporate gifting/event fit, presentation, delivery practicality and suitability for professional relationships. Commercial links are disclosed clearly, and ClientCellar does not claim live prices, stock or supplier availability unless verified directly.

The site has early relevant Search Console visibility for corporate wine gifts, client gift and Champagne gift queries, including visibility for:

- corporate wine gifts / corporate wine gifts UK
- Champagne gifts for clients
- Christmas corporate wine gifts
- supplier-directory style searches

If approved, I would use Majestic links only in relevant buyer contexts such as the supplier directory, corporate wine gift guides, event wine planning pages and planner supplier-route outputs. I would also use Awin deeplinking where appropriate so users land on useful Majestic pages rather than a generic homepage.

Best,
Phyl  
ClientCellar  
partners@clientcellar.co.uk

## Short version if the Awin field is limited

ClientCellar is a UK-focused business gifting and event drinks planning site. It helps professionals choose corporate wine gifts, client hampers, staff rewards and event drinks suppliers through practical guides, free planners, a supplier directory and paid supplier-ready Premium Brief Packs.

Majestic is a strong editorial fit because ClientCellar visitors are actively planning corporate wine gifts, Champagne/client gifts and event wine before choosing suppliers. The site is content/planning-led, not voucher-code-led, and includes clear affiliate disclosure and editorial policy pages.

Review URLs:

- https://clientcellar.co.uk/network-readiness
- https://clientcellar.co.uk/supplier-directory
- https://clientcellar.co.uk/gift-planner
- https://clientcellar.co.uk/guides/champagne-gifts-for-clients
- https://clientcellar.co.uk/affiliate-disclosure
- https://clientcellar.co.uk/editorial-policy

If approved, Majestic links would be used only in relevant buyer contexts and deeplinked to useful supplier/product/category pages where appropriate.

## Compliance notes for application

Confirm in application/terms acceptance:

- No PPC brand bidding.
- No unauthorised coupon/promo-code presentation.
- No use of Majestic brand in domain names or social handles.
- No use of Majestic logo as avatar/profile image.
- No child/under-18 targeting.
- Any social affiliate links must be clearly disclosed or route via ClientCellar first.
- If prices are shown in future, use approved/current feed data only.

## If approved

Do not use this section unless a future reapplication is approved.

1. Create Awin deeplink(s) to:
   - Majestic corporate gifting page.
   - Majestic Commercial / events page if allowed.
   - Relevant gift/case/category pages where appropriate.
2. Add approved links to production env vars:
   - `CLIENTCELLAR_AFFILIATE_URL_MAJESTIC`
   - `CLIENTCELLAR_AFFILIATE_URL_MAJESTIC_COMMERCIAL`
3. Re-enable the Majestic affiliate URL lookups in `data/supplier_links.py`. They are intentionally disabled while the programme is rejected.
4. Run:

```bash
.venv/bin/python scripts/audit_supplier_links.py
.venv/bin/python -m pytest -q
```

5. Check:
   - `/supplier-directory`
   - `/suppliers`
   - `/gift-planner`
   - `/event-planner`
   - relevant guide pages
   - `/affiliate-disclosure`

## If rejected

Record exact rejection in `docs/affiliate-supplier-outreach-tracker.md`:

- rejection date
- exact wording
- whether reason was traffic, content, alcohol category, site age, publisher model, policy or missing evidence
- evidence submitted
- whether direct Majestic Commercial outreach is a better next route

Current recorded rejection:

- Date: 2026-08-21.
- Outcome: rejected.
- Exact reason: "Advertiser doesn't work with this publisher type".
- Next move: keep editorial-only and reapply no earlier than 2026-11-21 if the publisher profile and evidence pack are stronger.
