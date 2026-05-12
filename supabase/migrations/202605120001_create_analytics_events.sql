create table if not exists public.analytics_events (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  event_name text not null,
  session_id text,
  page_path text,
  referrer text,
  device_type text,
  viewport_width integer,
  user_agent text,
  report_type text,
  supplier_name text,
  supplier_url text,
  checkout_session_id text,
  metadata jsonb not null default '{}'
);

alter table public.analytics_events enable row level security;

drop policy if exists "Service role can manage analytics events" on public.analytics_events;

create policy "Service role can manage analytics events"
on public.analytics_events
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

create index if not exists analytics_events_created_at_idx
on public.analytics_events (created_at desc);

create index if not exists analytics_events_event_name_idx
on public.analytics_events (event_name);

create index if not exists analytics_events_session_id_idx
on public.analytics_events (session_id);

create index if not exists analytics_events_report_type_idx
on public.analytics_events (report_type);
