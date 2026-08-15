# ClientCellar analytics and Search Console prioritisation

Updated: 2026-08-15

Use this workflow to decide what to improve next. The goal is to prioritise pages and funnels that can produce Premium Brief Pack purchases, supplier clicks, affiliate approvals or supplier-direct conversations.

## Data to pull weekly

### Google Search Console

Export the last 28 days and, where useful, the last 3 months:

- top pages by clicks
- top pages by impressions
- top queries by clicks
- top queries by impressions
- average position for high-impression queries
- country split
- device split

You can turn a Search Console CSV export into an action list with:

```bash
.venv/bin/python scripts/analyse_gsc_export.py path/to/search-console-export.csv
```

The script accepts query or page exports where columns include common Search Console labels such as `Query`, `Page`, `Clicks`, `Impressions`, `CTR` and `Position`.

If you need a quick format reference, use `docs/search-console-export-template.csv`. Replace the example rows with the real export from Search Console.

### ClientCellar first-party analytics

Fetch:

```text
/api/admin/analytics-summary?password=YOUR_ADMIN_PASSWORD
```

Use both `last_7_days` and `last_30_days`.

Key fields:

- `visits_by_page`
- `planner_starts`
- `free_reports_generated`
- `upgrade_clicks`
- `checkout_starts`
- `successful_payments`
- `supplier_clicks`
- `top_free_report_pages`
- `top_upgrade_click_pages`
- `top_checkout_start_pages`
- `top_supplier_click_pages`
- `top_clicked_suppliers`
- `free_report_to_upgrade_click_rate`
- `checkout_start_to_payment_success_rate`

## Prioritisation matrix

| Signal | Meaning | Action |
| --- | --- | --- |
| High impressions, low clicks | Google is testing the page but snippet/title may be weak | Rewrite title/meta intro, improve first-screen relevance |
| Clicks but low planner starts | Page attracts visitors but does not route them into a planner | Add stronger planner CTA and internal links |
| Planner starts but low free reports | Form may be too much friction or unclear | Improve form copy, defaults, mobile layout or required-field clarity |
| Free reports but low upgrade clicks | Premium value is not obvious at the decision moment | Add clearer Premium example, stronger CTA, outcome copy |
| Upgrade clicks but low checkout starts | Checkout trigger or email requirement may be causing friction | Review upgrade UI and error states |
| Checkout starts but low paid conversions | Payment/price/trust friction | Review checkout success/failure events, trust copy and pack value |
| Supplier clicks but no affiliate/direct monetisation | Commercial opportunity | Prioritise affiliate applications or direct supplier outreach |
| Supplier page gets organic clicks | Potential sponsored profile or supplier partnership route | Add to supplier outreach list |

## Weekly review template

Date:

### Search opportunities

- Highest-impression page/query:
- Page with best click growth:
- Page with weak CTR:
- Query that suggests buyer intent:

### Funnel opportunities

- Top planner-start page:
- Top free-report page:
- Top upgrade-click page:
- Top checkout-start page:
- Biggest drop-off:

### Supplier opportunities

- Most-clicked supplier:
- Supplier category with strongest interest:
- Supplier pages worth affiliate/direct outreach:

### This week's actions

1.
2.
3.

## Decision rules

- Prioritise pages that already have impressions or clicks before creating lots of new pages.
- Prioritise pages that produce planner starts, upgrade clicks or supplier clicks over pages that only get passive visits.
- Use supplier-click evidence in affiliate reapplications and direct supplier outreach.
- Do not claim traffic publicly unless the latest data supports it.
- Keep the Premium flow planner-first: price pages and guides should usually push users into gift or event planning before checkout.

## Query-led content actions

Use the GSC analyser priority labels this way:

- `Improve title/meta and first-screen relevance`: keep the page, but rewrite the title, meta description, intro and first CTA so they match the query more directly.
- `Strengthen existing page or create a better-matched section`: add a section, comparison table, checklist or internal link before creating a whole new page.
- `Add monetisation and planner CTAs`: the page already earns clicks, so make sure it routes visitors into gift planner, event planner, Premium Brief Pack, supplier directory or supplier enquiries.
- `Map query to an existing page or content gap`: decide whether the query belongs to an existing page. Create a new page only where no current page can satisfy the intent.
- `Monitor`: leave alone unless it supports a supplier, Premium or affiliate application priority.
