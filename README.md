# ClientCellar

ClientCellar is a standalone FastAPI MVP for UK corporate wine gifting and corporate wine tasting planning.

It helps business users plan client gifts, staff gifts, partner thank-yous and tasting events with budget guidance, supplier routes, enquiry emails, CSV templates, premium pack previews and lead capture.

ClientCellar does not sell alcohol directly, scrape retailer websites, check live stock or invent supplier availability. Supplier data is manually curated in `main.py`.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`.

## Key routes

- `/` homepage
- `/gift-planner`
- `/event-planner`
- `/premium-pack`
- `/pricing`
- `/guides`
- `/contact`
- `/api/health`
- `/sitemap.xml`
- `/robots.txt`

Admin routes are not linked publicly:

- `/admin/leads-basic`
- `/api/leads/export.csv?password=your_password`

## Render deployment

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

`runtime.txt` pins Python to `python-3.11.9`, which is compatible with the app.

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

## Lead admin setup

Lead enquiries are stored in SQLite at `data/clientcellar.db`. The `data/` directory is gitignored and should not be committed.

To enable the basic MVP lead admin view:

```bash
ADMIN_PASSWORD=your_password
```

Admin URL:

```text
/admin/leads-basic
```

CSV export:

```text
/api/leads/export.csv?password=your_password
```

This is MVP admin protection, not production-grade security. For production, replace the query-string admin password with proper authentication before handling sensitive lead data at scale.

## Payment setup placeholder

The Premium Pack architecture works without Stripe by default. If payments are disabled, users see a register-interest fallback.

To enable Stripe Checkout later:

```bash
PAYMENTS_ENABLED=true
STRIPE_SECRET_KEY=...
STRIPE_PRICE_ID=...
APP_BASE_URL=https://your-domain.example
```

`STRIPE_PRICE_ID` should point to the one-off £29.99 Premium Pack price in Stripe.

Stripe webhook fulfilment is not yet implemented. Automated PDF and email delivery are not yet implemented. The MVP uses the on-page premium preview plus browser print/save.

## Supplier and affiliate links

The starter supplier database lives in `SUPPLIERS` inside `main.py`.

Supplier records are normalised at app startup with fields such as `supplier_id`, `tracking_slug`, `description`, `website_url`, `affiliate_url`, `enquiry_url`, `commercial_relationship`, `disclosure_note` and `active`.

Commercial relationships default to `none`. Unknown affiliate links are currently `None`. Replace these later only with confirmed supplier or affiliate URLs, and keep the affiliate disclosure clear.

Tracked supplier links use:

```text
/out/supplier/{tracking_slug}
```

The redirect stores a minimal click event in `supplier_clicks` with supplier id, tracking slug, destination URL, source page, referrer and user agent. It redirects to `affiliate_url` first, then `enquiry_url`, then `website_url`.

Do not add fake affiliate links, fake claims, fake availability, fake pricing or implied endorsements. Generic supplier categories are planning guidance, not supplier endorsements.

Supplier applications are submitted through:

```text
/suppliers/join
```

Admin view:

```text
/admin/supplier-applications?password=your_password
```

Admin summary:

```text
/api/admin/summary?password=your_password
```

Before using real affiliate links or sponsored placements, review platform rules and disclosure obligations.

## Legal caveat

The legal and trust pages are practical MVP templates, not lawyer-approved documents. They should be reviewed by a qualified professional before commercial launch.

## Manual smoke test checklist

1. Open `/`.
2. Open `/gift-planner`, submit the default form and copy the enquiry email.
3. Open `/event-planner`, submit the default form and copy the enquiry email.
4. Preview the Premium Pack from a planner result.
5. Submit a lead form with consent checked.
6. Open `/premium-pack`, `/pricing`, `/guides`, `/terms`, `/privacy`.
7. Check `/api/health`.
8. Check `/sitemap.xml` and `/robots.txt`.
9. Confirm `/admin/leads-basic` is disabled when `ADMIN_PASSWORD` is missing.
10. Open `/suppliers` and one supplier detail page.
11. Submit a test supplier application from `/suppliers/join`.

## Tests

Basic smoke tests live in `tests/test_smoke.py`.

```bash
pytest
```

## Troubleshooting

- Module not found: activate `.venv` and run `pip install -r requirements.txt`.
- Port already in use: run `uvicorn main:app --reload --port 8001`.
- Missing template: check the route's template name exists in `templates/`.
- Render build failed: confirm the build command is `pip install -r requirements.txt` and Python is compatible with `runtime.txt`.
- Admin disabled: set `ADMIN_PASSWORD`.
- Payments disabled: set `PAYMENTS_ENABLED=true`, `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID` and `APP_BASE_URL`.

## Current limitations

- Planning guidance only, not legal, tax, procurement or HR advice.
- No live pricing, stock, availability, delivery slot or licensing checks.
- Contact and lead enquiries are stored locally in `data/clientcellar.db`.
- Stripe Checkout is isolated and disabled unless configured.
- No Stripe webhook fulfilment, automated PDF export or automated email delivery yet.
- Supplier matching is rule-based and intentionally conservative.
- Supplier application and click tracking are MVP-only local database features.
- International alcohol shipping rules must be confirmed directly with suppliers.

## Roadmap

1. Real supplier affiliate links.
2. Stripe payment completion.
3. PDF/email delivery.
4. Proper admin authentication.
5. Supplier onboarding form.
6. Analytics and SEO tracking.
7. Domain and Google Search Console.
