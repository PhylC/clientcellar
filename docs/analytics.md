# ClientCellar Analytics

ClientCellar uses lightweight first-party analytics for funnel tracking. The frontend sends best-effort events to `POST /api/analytics`; the backend validates event names, strips metadata to an allowlist and writes to Supabase table `analytics_events` only when the Supabase service role is configured.

Analytics must never block the user journey. If Supabase is unavailable, events are ignored.

## Events Tracked

General:
- `page_view`
- `nav_click`
- `contact_click`
- `supplier_click`

Gift flow:
- `gift_planner_started`
- `gift_free_report_generated`
- `gift_supplier_clicked`
- `gift_upgrade_clicked`
- `gift_checkout_started`
- `gift_premium_viewed`

Event flow:
- `event_planner_started`
- `event_free_report_generated`
- `event_supplier_clicked`
- `event_upgrade_clicked`
- `event_checkout_started`
- `event_premium_viewed`

Example and checkout:
- `example_gift_premium_viewed`
- `example_event_premium_viewed`
- `example_upgrade_clicked`
- `checkout_session_created`
- `checkout_success_page_viewed`
- `stripe_webhook_completed`
- `premium_access_granted`
- `premium_access_failed`

## Where Events Fire

- `static/app.js`: page views, nav/contact/supplier clicks, planner starts, free report generation, upgrade clicks, checkout starts, example and premium page views.
- `main.py`: supplier outbound redirects, Stripe checkout session creation, checkout success verification, Stripe webhook completion and premium pack access grant/failure.

## Stored Fields

The table stores:
- event name and server timestamp
- page path, referrer, device type, viewport width and user agent
- anonymous session id
- report type (`gift` or `event`) where relevant
- supplier name/link where relevant
- checkout session id where relevant
- small allowlisted metadata only

Do not store payment card details, planner personal data, email addresses or sensitive free-text content in analytics metadata.

## Admin Summary

With `ADMIN_PASSWORD` set, fetch:

```text
/api/admin/analytics-summary?password=YOUR_ADMIN_PASSWORD
```

The JSON response includes last 7 and 30 day summaries for visits by page, planner starts, free reports, upgrade clicks, checkout starts, successful payments, supplier clicks, conversion rates, gift/event comparison, mobile/desktop comparison, top clicked suppliers and the pages producing free reports, upgrade clicks, checkout starts and supplier clicks.

## Example SQL Queries

Top pages in the last 30 days:

```sql
select page_path, count(*) as views
from analytics_events
where event_name = 'page_view'
  and created_at >= now() - interval '30 days'
group by page_path
order by views desc;
```

Supplier clicks:

```sql
select supplier_name, count(*) as clicks
from analytics_events
where event_name in ('supplier_click', 'gift_supplier_clicked', 'event_supplier_clicked')
  and created_at >= now() - interval '30 days'
group by supplier_name
order by clicks desc;
```

Free report to upgrade click:

```sql
with counts as (
  select
    count(*) filter (where event_name in ('gift_free_report_generated', 'event_free_report_generated')) as free_reports,
    count(*) filter (where event_name in ('gift_upgrade_clicked', 'event_upgrade_clicked', 'example_upgrade_clicked')) as upgrade_clicks
  from analytics_events
  where created_at >= now() - interval '30 days'
)
select free_reports, upgrade_clicks,
  case when free_reports = 0 then 0 else upgrade_clicks::numeric / free_reports end as conversion_rate
from counts;
```

## Disabling Analytics

No client-side flag is required. If `SUPABASE_SERVICE_ROLE_KEY` is not configured, `/api/analytics` still returns success but does not store events.

To disable storage on a configured deployment, remove `SUPABASE_SERVICE_ROLE_KEY` or revoke service role access for `analytics_events`.
