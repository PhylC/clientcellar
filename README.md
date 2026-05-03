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

Sitemap and production URLs:

```bash
APP_BASE_URL=https://your-domain.example
```

## Monetisation model

The current monetisation model is a one-off Premium Brief Pack at £29.99.

Free Planner:

- Quick gift/event recommendation
- Budget estimate
- Basic supplier direction
- Draft enquiry email
- Basic CSV template

Premium Brief Pack:

- Full supplier or event host brief
- Internal approval note
- Supplier comparison matrix
- Supplier questions checklist
- Message bank or event invite copy
- Risk and suitability checklist
- Timeline/action plan
- Decision scorecard
- Print/save-ready document

The app must continue to work with `PAYMENTS_ENABLED=false`. In that mode, Premium CTAs fall back to registering interest.

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
