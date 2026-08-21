# Live affiliate link setup

Updated: 2026-08-15

ClientCellar now supports approved supplier affiliate or tracked links through environment variables. This keeps live monetised URLs out of templates and lets production fall back to normal editorial supplier URLs if a tracked URL is missing or malformed.

## How to add a live approved link

1. Confirm the supplier, network or referral programme has approved ClientCellar.
2. Confirm the tracked URL is an HTTPS URL and points to a useful buyer page.
3. Add the URL to the matching production environment variable.
4. Redeploy the app.
5. Run the supplier audit and smoke tests locally with equivalent env values.
6. Check `/affiliate-disclosure`, `/supplier-directory`, `/suppliers` and the relevant guide/planner output.

Example:

```bash
CLIENTCELLAR_AFFILIATE_URL_VINTAGE_WINE_GIFTS=https://approved-network.example/...
```

Do not commit live affiliate URLs to the repo unless a programme explicitly requires public links and the URL contains no sensitive account token. Prefer deployment environment variables.

## Supported supplier env vars

- `CLIENTCELLAR_AFFILIATE_URL_LAITHWAITES`
- `CLIENTCELLAR_AFFILIATE_URL_VIRGIN_WINES`
- `CLIENTCELLAR_AFFILIATE_URL_SLURP`
- `CLIENTCELLAR_AFFILIATE_URL_HAY_WINES`
- `CLIENTCELLAR_AFFILIATE_URL_WINE_DIRECT`
- `CLIENTCELLAR_AFFILIATE_URL_VINTAGE_WINE_GIFTS`
- `CLIENTCELLAR_AFFILIATE_URL_FORTNUM_MASON`
- `CLIENTCELLAR_AFFILIATE_URL_MARKS_SPENCER_CORPORATE`
- `CLIENTCELLAR_AFFILIATE_URL_WAITROSE_CELLAR`
- `CLIENTCELLAR_AFFILIATE_URL_JOHN_LEWIS_HAMPERS`
- `CLIENTCELLAR_AFFILIATE_URL_SELFRIDGES_HAMPERS`
- `CLIENTCELLAR_AFFILIATE_URL_HARRODS_HAMPERS`
- `CLIENTCELLAR_AFFILIATE_URL_HARVEY_NICHOLS_HAMPERS`
- `CLIENTCELLAR_AFFILIATE_URL_GREAT_WINE_CO`
- `CLIENTCELLAR_AFFILIATE_URL_HOTEL_CHOCOLAT`
- `CLIENTCELLAR_AFFILIATE_URL_AMAZON`
- `CLIENTCELLAR_AFFILIATE_URL_NOUGHTY_THOMSON_SCOTT`
- `CLIENTCELLAR_AFFILIATE_URL_DRY_DRINKER`

Do not add Majestic env vars unless a future reapplication is approved. Majestic rejected ClientCellar on Awin on 2026-08-21 because the advertiser does not work with this publisher type.

## First sensible targets

Use approved links first where they match existing search and buyer intent:

- First approved Awin target: Vintage Wine Gifts. Use `CLIENTCELLAR_AFFILIATE_URL_VINTAGE_WINE_GIFTS` with the approved Awin deeplink.
- Champagne/client gifting pages: Laithwaites, Virgin Wines, Waitrose Cellar, Fortnum & Mason and Vintage Wine Gifts where relevant.
- Supplier directory: Virgin Wines, Slurp, Wine Direct, Hay Wines, Fortnum & Mason and Vintage Wine Gifts where relevant.
- Christmas and hamper pages: Fortnum & Mason, M&S Hampers, John Lewis Hampers, Selfridges, Harvey Nichols.
- Alcohol-free gift pages: Noughty / Thomson & Scott, Dry Drinker.

## Disclosure behaviour

When at least one approved affiliate URL is active, the global footer switches from future-only wording to current affiliate-link wording. Individual supplier state is also updated through the central supplier model:

- `is_affiliate` / `isAffiliate`: true
- `commercial_relationship`: `affiliate`
- `disclosure_label`: `Affiliate link`
- `disclosure_note`: affiliate/tracked supplier disclosure
- outbound supplier destination: approved affiliate URL

Malformed affiliate URLs are ignored and the normal supplier URL remains in use.
