# Commercial disclosure go-live checklist

Updated: 2026-08-15

Use this before adding the first live affiliate, tracked, referral or sponsored supplier placement.

## Before adding commercial links

- Confirm the supplier programme or sponsored agreement is genuinely approved.
- Save the supplier/programme name, network, approval date and allowed landing pages.
- Confirm whether the programme permits alcohol, corporate gifting, hampers, event pages and content-led publisher traffic.
- Confirm whether direct linking, deep linking and email/social promotion are allowed.
- Confirm any required wording from the supplier or network.
- Run `.venv/bin/python scripts/audit_supplier_links.py`.
- Open the supplier destination manually in a browser.

## When adding an affiliate or tracked URL

- Add the real approved URL to the matching `CLIENTCELLAR_AFFILIATE_URL_*` deployment environment variable documented in `docs/live-affiliate-link-setup.md`.
- Change `data/supplier_links.py` only when adding a new supplier or new supported env-var mapping.
- Do not add placeholders, guessed tracking URLs or network links that have not been approved.
- Confirm `supplier.isAffiliate` / `supplier.is_affiliate` becomes true only where the real affiliate URL exists.
- Confirm the public supplier button still points to a useful buyer page, not a generic homepage unless that is the only approved route.
- Confirm the affiliate disclosure is linked from the relevant page footer or local disclosure copy.
- Run the supplier audit script and smoke tests.

## When adding a sponsored placement

- Label the placement clearly as `Sponsored` or `Sponsored supplier`.
- Keep sponsored placement copy factual and buyer-useful.
- Do not imply editorial ranking, testing, official partnership or guaranteed suitability unless true.
- Do not promise live pricing, live stock, delivery slots or supplier quote availability.
- Keep a normal editorial alternative visible where practical.
- Update the supplier/media-kit notes with the placement date and agreed terms.

## Public wording standards

Use:

- `Affiliate link`
- `Tracked supplier link`
- `Sponsored supplier`
- `Normal supplier link`
- `Editorially listed`

Avoid:

- `Partner` unless a partnership is agreed.
- `Recommended by ClientCellar` where the placement is paid and not editorial.
- `Best` if the claim is paid, untested or not supported by page context.
- `Live price`, `in stock`, `guaranteed delivery` or `confirmed quote` unless verified directly.

## Pages to check after launch

- `/affiliate-disclosure`
- `/editorial-policy`
- `/supplier-directory`
- `/suppliers`
- relevant guide pages
- relevant planner result supplier cards
- `/supplier-partnerships`
- footer disclosure copy
- sitemap/robots unchanged

## Admin and evidence checks

- Confirm supplier clicks are tracked in first-party analytics.
- Confirm `/api/admin/analytics-summary` shows supplier-click pages.
- Record the change in `docs/supplier-link-audit.md`.
- Update the affiliate target tracker in `docs/affiliate-reapplication-pack.md`.
- Keep screenshots or notes from the first live placement for future network reviews.
