# ClientCellar launch and monetisation backlog

Updated: 2026-08-18

This is the working backlog for launching ClientCellar properly and monetising the site now that it has started to rank and attract search clicks.

## Completed

- Premium Brief Pack payment funnel is live and working.
- Pricing page conversion first pass: clearer Free vs Premium positioning, paid-pack proof points and planner-first CTAs.
- Supplier-direct monetisation first pass: public partnership options and internal media kit/outreach copy.
- Affiliate reapplication first pass: publisher profile strengthened and internal reapplication pack/tracker created.
- Analytics/GSC prioritisation first pass: admin summary now includes page-level funnel views and a weekly prioritisation workflow has been added.
- Supplier link audit refresh: current central supplier config documented and offline audit script added.
- High-intent lead capture first pass: pricing and supplier-directory pages now include compact buyer enquiry forms using the existing lead system.
- Fulfilment polish first pass: My Packs recovery copy improved, access/download counters now work with recovery tokens, and admin orders show download counts.
- Legal/trust commercial disclosure first pass: affiliate/editorial disclosure wording is ready for normal, affiliate/tracked and sponsored link states, with a go-live checklist added.
- SEO query-growth tooling first pass: Search Console CSV analyser added and documented for query/page prioritisation.
- Search Console export application first pass: 2026-08-15 export analysed and query-led updates applied to Champagne, best client gifts, Christmas client gifts and supplier-directory pages.

## Active priorities

1. Monitor the updated GSC pages after the next crawl window and prioritise the next round from fresh impressions/clicks.
2. Maintain twice-weekly LinkedIn/Facebook posting for ClientCellar using `docs/social-content-tracker.md`.

## SEO growth next checks

- Real Search Console export data from 2026-08-15 is now available locally and the first page updates have been applied.
- Export fresh Search Console query or page CSV data after the next meaningful crawl window.
- Run `.venv/bin/python scripts/analyse_gsc_export.py path/to/search-console-export.csv`.
- For priority 1 rows, rewrite title/meta, intro and first-screen CTA.
- For priority 2 rows, strengthen the existing page or add a better-matched section before creating a new page.
- For priority 3 rows, improve planner, Premium Brief Pack, supplier-directory and lead-capture CTAs.
- Only create new SEO pages where the real query cannot be served by an existing page.

## Legal/trust next checks

- Use `docs/commercial-disclosure-go-live-checklist.md` before adding the first live affiliate, tracked, referral or sponsored placement.
- When a real affiliate URL is added, confirm the relevant supplier/page disclosure still matches the live state.
- When a sponsored placement is added, confirm it is labelled clearly on the page and recorded in the supplier monetisation notes.

## Fulfilment next checks

- Run a live purchase and confirm the pack-ready email arrives from the verified sending domain.
- Use `/my-packs` with the checkout email and confirm the recovery email opens the saved pack.
- Confirm admin orders show access and download counts after viewing, printing or downloading a pack.
- Consider a dedicated server-generated PDF later if browser print/save proves too inconsistent for customers.

## Lead capture next checks

- Watch `/admin/leads-basic` and the lead CSV export for enquiries from `/pricing` and `/supplier-directory`.
- Compare lead capture rate against page views in `/api/admin/analytics-summary`.
- If pricing-page enquiries convert, consider adding similar compact forms to the highest-intent guide pages.

## Supplier link audit next checks

- Run `.venv/bin/python scripts/audit_supplier_links.py` before supplier or affiliate updates.
- Run `.venv/bin/python scripts/audit_supplier_links.py --check-live` before major campaigns, affiliate migrations or supplier outreach.
- Open high-priority supplier pages manually in a browser before promising placement or sending supplier-specific outreach.

## Analytics/GSC next checks

- Export the latest 28-day Search Console pages and queries.
- Fetch `/api/admin/analytics-summary?password=YOUR_ADMIN_PASSWORD` on production.
- Fill the weekly review template in `docs/analytics-gsc-prioritisation.md`.
- Use supplier-click pages and top clicked suppliers in affiliate reapplications and supplier outreach.

## Affiliate reapplication next checks

- Pull current Google Search Console clicks, impressions, top pages and top queries.
- Pull first-party analytics for supplier clicks, planner starts, completed free plans and upgrade clicks.
- Fill the target tracker in `docs/affiliate-reapplication-pack.md`.
- Add approved supplier affiliate URLs through `CLIENTCELLAR_AFFILIATE_URL_*` production environment variables rather than hardcoding network URLs in templates.
- Record rejection reasons rather than repeatedly reapplying with the same evidence.

## Supplier-direct monetisation next checks

- Pull a current media snapshot from Google Search Console and first-party analytics before outreach.
- Build a small supplier target list from current directory categories.
- Send test outreach to a few relevant suppliers before publishing any fixed rate card.
- Keep sponsored placement wording clearly labelled and separate from editorial selection.

## Social content next checks

- Check `docs/social-content-tracker.md` before recommending next actions.
- If fewer than two posts are planned or published for the current week, add a twice-weekly social posting task to the next action list.
- Prioritise posts that support current affiliate evidence, supplier outreach, Premium Brief Pack credibility or high-intent guide pages.

## Notes

- Keep ClientCellar useful without affiliate links.
- Do not imply a supplier partnership unless it has been agreed.
- Clearly label sponsored placements and affiliate relationships.
- Keep the core Premium Brief Pack flow planner-first, not direct checkout-first.
