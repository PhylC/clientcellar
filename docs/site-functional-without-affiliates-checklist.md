# Site Functional Without Affiliates Checklist

Internal QA checklist for keeping ClientCellar useful before any supplier tracking or affiliate relationship is active.

## Checked Areas

- Free gift planner tested: generated output should include summary, recipient and occasion fit, budget estimate, suggested gift direction, supplier routes, supplier questions, risks and next steps.
- Free event planner tested: generated output should include event summary, serving assumptions, quantity estimate, budget estimate, wine mix, supplier routes, supplier questions, risks and next steps.
- Supplier directory works without affiliate links: category guidance should stand alone, and any supplier button should use a real normal URL or clear route guidance.
- Premium value does not rely on affiliates: Premium Brief Pack should be positioned as document and workflow value, not supplier access or deal access.
- Supplier form/contact route checked: `/supplier-application` should collect supplier details and provide a `partners@clientcellar.co.uk` mailto fallback if submission fails.
- All public CTAs checked: buttons should navigate, submit a working form, open mailto, or be removed.
- Contact emails checked: general enquiries use `hello@clientcellar.co.uk`; supplier and commercial enquiries use `partners@clientcellar.co.uk`.
- Sitemap checked: public sitemap should include functional public pages and exclude admin, API, test and checkout success/cancel routes.

## Known Limitations

- ClientCellar does not sell alcohol directly.
- Plans are estimates and do not verify live stock, live pricing, delivery, supplier availability or confirmed quotes.
- Supplier links may be normal, untracked links unless a real affiliate or tracked relationship is added later.
- Premium Brief Pack means supplier-ready formatting for enquiry and approval; it does not mean stock, pricing or quotes are confirmed.
- Supplier application submissions are stored by the app when the backend is available; the page also provides a mailto fallback for manual submission.
