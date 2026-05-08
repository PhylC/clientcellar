# ClientCellar

ClientCellar is a standalone FastAPI MVP for UK corporate wine gifting and corporate wine tasting event planning.

It helps business users plan client gifts, staff gifts, partner thank-yous and tasting events with budget guidance, supplier routes, enquiry emails, CSV templates, Premium Brief Pack checkout and lead capture.

ClientCellar does not sell alcohol directly, scrape retailer websites, check live stock, confirm supplier pricing or invent supplier availability. Supplier data is manually curated in `main.py` and must stay conservative.

## Current positioning

ClientCellar should feel like a polished B2B planning tool, not a generic AI demo. The public experience is built around:

- UK corporate gifting and tasting event planning
- Supplier-ready enquiry emails and briefs
- Budget and recipient-count planning
- Practical checklists for delivery, policy and suitability
- Responsible gifting and alcohol-free alternative reminders
- Clear disclosure that suppliers confirm live pricing, stock and availability

## Key public routes

- `/` homepage
- `/gift-planner`
- `/event-planner`
- `/premium-pack`
- `/premium-pack/view/{pack_token}`
- `/pricing`
- `/sign-in`
- `/account`
- `/billing/success`
- `/billing/cancel`
- `/suppliers`
- `/suppliers/{tracking_slug}`
- `/suppliers/join`
- `/guides`
- `/guides/{slug}`
- `/faq`
- `/contact`
- `/terms`
- `/privacy`
- `/affiliate-disclosure`
- `/responsible-drinking`
- `/cookies`
- `/copyright`
- `/api/health`
- `/sitemap.xml`
- `/robots.txt`

Admin routes are not linked publicly:

- `/admin/leads-basic`
- `/admin/orders`
- `/admin/supplier-applications`
- `/api/leads/export.csv?password=your_password`
- `/api/admin/summary?password=your_password`

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`.

## Environment variables

Copy `.env.example` to `.env` for local configuration.

```bash
cp .env.example .env
```

Optional OpenAI wording polish:

```bash
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

The app works without OpenAI. If enabled, OpenAI may polish rule-based wording but must not invent supplier prices, stock, delivery or availability.

Account login uses Supabase Auth when configured:

```bash
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
```

The frontend may also read `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` if that naming style is used in deployment. `SUPABASE_SERVICE_ROLE_KEY` is server-side only and is used for Stripe fulfilment/profile updates. If Supabase is not configured, login pages show a clear setup message and the Free Planner remains available.

Sitemap and production URLs:

```bash
APP_BASE_URL=https://your-domain.example
```

Transactional email uses Resend for saved Premium Brief Pack links:

```bash
RESEND_API_KEY=
EMAIL_FROM="ClientCellar <hello@clientcellar.co.uk>"
```

The sending domain, for example `clientcellar.co.uk`, must be verified in the Resend dashboard before production delivery. If `RESEND_API_KEY` is missing, email delivery is skipped and logged as a server-side failure; the browser response remains generic.

## Monetisation model

The current monetisation model is a one-off Premium Brief Pack at £29.99.

Free Planner:

- Quick gift/event recommendation
- Budget estimate
- Basic supplier direction
- Draft enquiry email
- Basic CSV template

Premium Brief Pack:

- Supplier-ready buying brief
- Copy-and-send supplier enquiry email
- Budget and quantity breakdown
- Supplier shortlist guidance
- Internal approval summary
- Clear next steps checklist
- Print/save-ready document

The app must continue to work with `PAYMENTS_ENABLED=false`. In that mode, Premium Brief Pack CTAs fall back to registering interest.

ClientCellar currently sells a one-off Premium Brief Pack, not a subscription upgrade. Browser storage and query strings must never grant permanent premium status.

## Stripe setup

To enable Stripe Checkout:

```bash
PAYMENTS_ENABLED=true
STRIPE_SECRET_KEY=...
STRIPE_PRICE_ID=...
STRIPE_WEBHOOK_SECRET=...
APP_BASE_URL=https://your-domain.example
```

`STRIPE_PRICE_ID` should point to the one-off £29.99 Premium Brief Pack price in Stripe.

Stripe webhook endpoint:

```text
/stripe/webhook
```

Recommended events:

- `checkout.session.completed`
- `checkout.session.expired`
- `payment_intent.payment_failed`

The success page also performs fallback session verification when Stripe is available, but webhooks are still recommended before live launch.

Current fulfilment limitations: Stripe webhook fulfilment is MVP-level, automated PDF generation is not yet implemented, automated email delivery is not yet implemented, supplier quote comparison upload is not yet implemented, and saved account history is not yet implemented. The MVP uses the on-page Premium Brief Pack plus browser print/save.

Stripe checkout supports one-off Premium Brief Pack purchases. If a user is signed in, checkout metadata can link the payment to their Supabase profile; if not, the purchase still returns them to the Premium Brief Pack creation flow. Do not grant premium from browser storage or query strings. Webhook fulfilment can update server-side payment fields only via the service role key when user metadata exists.

## SEO and conversion strategy

ClientCellar’s public content is structured around a simple funnel:

1. High-intent guide or SEO landing page.
2. Free gift planner or event planner.
3. Premium Brief Pack, lead capture or supplier directory.
4. Supplier enquiry or tracked supplier link where appropriate.

The guide library currently includes:

- `/guides/corporate-wine-gifts-uk`
- `/guides/christmas-wine-gifts-for-clients`
- `/guides/staff-wine-gifts`
- `/guides/client-thank-you-wine-gifts`
- `/guides/corporate-wine-hampers`
- `/guides/corporate-champagne-gifts`
- `/guides/virtual-wine-tasting-for-teams`
- `/guides/corporate-wine-tasting-london`
- `/guides/wine-tasting-team-building`
- `/guides/corporate-wine-gifts-under-50`
- `/guides/corporate-wine-gifts-under-100`
- `/guides/luxury-wine-gifts-for-clients`
- `/guides/english-sparkling-corporate-gifts`
- `/guides/wine-gifts-for-sales-teams`
- `/guides/wine-gifts-for-agencies`
- `/guides/wine-gifts-for-law-firms`
- `/guides/wine-gifts-for-accountancy-firms`
- `/guides/client-gift-policy-checklist`
- `/guides/corporate-gifting-recipient-csv-template`

Internal links should point naturally from guides to planners, from planners to Premium Brief Pack and suppliers, and from supplier pages to planners and affiliate disclosure. Checkout, billing and admin routes should not be included in the sitemap and should render with `noindex` if they produce HTML.

Manual SEO QA:

1. Check each public page has a unique title, meta description and canonical URL without query strings.
2. Confirm guide pages include quick answer, budget guidance, checklist, responsible gifting note and planner CTA.
3. Confirm `/sitemap.xml` includes public SEO pages and guide pages, but not admin, checkout or billing success/cancel pages.
4. Confirm `/robots.txt` references the sitemap.
5. Keep Product schema limited to the real £29.99 Premium Brief Pack and never add fake reviews or ratings.

## Lead and supplier data

Lead enquiries, premium pack records, supplier clicks and supplier applications are stored in SQLite at `data/clientcellar.db`. The `data/` directory is gitignored and should not be committed.

To enable MVP admin views:

```bash
ADMIN_PASSWORD=your_password
```

This is MVP admin protection, not production-grade security. For production, replace query-string admin passwords with proper authentication before handling sensitive lead data at scale.

Supplier records live in `SUPPLIERS` inside `main.py`. Generic supplier categories must be labelled as supplier types, not verified suppliers. Do not add fake affiliate links, fake claims, fake availability, fake pricing or implied endorsements.

## Design and content notes

The public UI should remain:

- Premium, practical and businesslike
- Warm cream background with deep burgundy accents
- Compact and readable on mobile
- Clear about free vs premium outputs
- Honest about supplier confirmation and planning limitations
- Free of fake testimonials, invented partnerships or exaggerated claims

Reusable CSS patterns live in `static/app.css`, including page shells, sections, cards, button variants, notices, trust rows, split layouts, CTA panels and footer patterns.

## Manual design QA checklist

Check desktop around 1200px, tablet around 900px and mobile around 390px:

1. Homepage value proposition is clear above the fold.
2. Header is compact; mobile menu and account badge do not overlap.
3. Footer is compact and all legal links remain visible.
4. `/gift-planner` default form submits and results remain readable.
5. `/event-planner` default form submits and results remain readable.
6. `/premium-pack` shows the payment CTA when enabled and register-interest fallback when disabled.
7. `/pricing` clearly distinguishes Free Planner and Premium Brief Pack.
8. `/suppliers` labels generic categories as supplier types.
9. `/suppliers/join` supplier application form submits.
10. `/guides` and `/guides/{slug}` include planner CTAs and compliance notes.
11. `/faq` covers direct sales, live stock/pricing, payments, premium packs and responsible gifting.
12. `/contact` lead form submits with consent.
13. No horizontal scrolling, cramped cards, huge dead space or awkward button wrapping.
14. Stripe checkout and `/stripe/webhook` code paths are not changed during design-only work.
15. Admin routes still load when configured with `ADMIN_PASSWORD`.

## Compliance reminders

- No live price, stock, availability, delivery slot or licensing claims.
- No direct alcohol sales claims.
- No copy suggesting alcohol improves social, sexual, professional or business success.
- Do not target under-18s.
- Do not encourage excessive drinking.
- Alcohol may not be suitable for every recipient, employee, client, workplace or event.
- Always encourage alcohol-free alternatives where appropriate.
- Remind users to check gifting, anti-bribery, HR, expenses and procurement policies.
- Keep affiliate/tracked link disclosure visible and plain.

## Tests

Basic smoke tests live in `tests/test_smoke.py`.

Premium pack email smoke checklist:

- Buy Premium Brief Pack from a generated free plan.
- Receive “Your ClientCellar Premium Brief Pack is ready”.
- Open the secure pack link.
- Visit `/my-packs`.
- Request an access link with the checkout email.
- Receive “Your ClientCellar Premium Brief Packs”.
- Confirm links open saved Premium Brief Packs.

```bash
pytest
```

In this workspace, use:

```bash
.venv/bin/python -m pytest -q
```

## Troubleshooting

- Module not found: activate `.venv` and run `pip install -r requirements.txt`.
- Port already in use: run `uvicorn main:app --reload --port 8001`.
- Missing template: check the route's template name exists in `templates/`.
- Render build failed: confirm the build command is `pip install -r requirements.txt` and Python is compatible with `runtime.txt`.
- Admin disabled: set `ADMIN_PASSWORD`.
- Payments disabled: set `PAYMENTS_ENABLED=true`, `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID` and `APP_BASE_URL`.

## Current limitations

- Planning guidance only, not legal, tax, procurement, licensing or HR advice.
- No live pricing, stock, availability, delivery slot or licensing checks.
- Contact and lead enquiries are stored locally in SQLite.
- Stripe Checkout is isolated and disabled unless configured.
- Stripe webhook fulfilment is MVP-level.
- Supplier matching is rule-based and intentionally conservative.
- Supplier application and click tracking are MVP-only local database features.
- International alcohol shipping rules must be confirmed directly with suppliers.
