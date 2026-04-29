# ClientCellar

ClientCellar is a standalone FastAPI MVP for planning corporate wine gifts and corporate wine tasting events in a UK business context.

It helps users create practical plans for client gifts, employee wine gifts and tasting events, including budget guidance, supplier routes, ready-to-send enquiry emails and a recipient CSV template.

The app does not sell wine, scrape retailer websites, check live stock or invent supplier availability. Supplier data is manually curated in `main.py`.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`.

## Environment variables

Copy `.env.example` to `.env` if you want local environment settings.

```bash
cp .env.example .env
```

`OPENAI_API_KEY` is optional. The MVP works without OpenAI. If a key is present, ClientCellar may use it to improve the wording of rule-based plans and emails. It must not invent supplier capabilities, prices, live stock or availability.

`OPENAI_MODEL` is optional and defaults to `gpt-4o-mini`.

Never commit real secret keys.

## Render deployment notes

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Set `OPENAI_API_KEY` as a Render environment variable only if you want optional copy polishing.

## Supplier and affiliate links

The starter supplier database lives in `SUPPLIERS` inside `main.py`.

Fields include `website_url`, `affiliate_url` and `enquiry_url`. Unknown affiliate links are currently `None`. Replace these later only with confirmed supplier or affiliate URLs, and update the affiliate disclosure text before commercial launch.

## Current limitations

- Planning guidance only, not legal, tax, procurement or HR advice.
- No live pricing, stock, availability, delivery slot or licensing checks.
- Contact form submissions are stored locally in `data/contact_messages.jsonl`.
- No payment flow is implemented.
- Supplier matching is rule-based and intentionally conservative.
- International alcohol shipping rules must be confirmed directly with suppliers.

## Next build passes

- Move suppliers to SQLite with an admin editing screen.
- Add PDF export and saved plan links.
- Add supplier comparison tables and quote tracking.
- Add Stripe for the Premium Pack.
- Add proper terms, privacy and affiliate disclosure pages.
- Add email delivery for contact and supplier enquiry workflows.
- Add automated tests for API contracts and planner rules.
