create table if not exists public.premium_packs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  pack_type text not null check (pack_type in ('gift', 'event')),
  customer_email text not null,
  stripe_session_id text,
  stripe_payment_intent_id text,
  payment_status text not null default 'paid',
  plan_id text,
  title text,
  input_data jsonb,
  generated_content jsonb,
  access_token text unique not null,
  download_count integer not null default 0
);

alter table public.premium_packs enable row level security;

create policy "Service role can manage premium packs"
on public.premium_packs
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');

create index if not exists premium_packs_customer_email_idx
on public.premium_packs (lower(customer_email));

create index if not exists premium_packs_access_token_idx
on public.premium_packs (access_token);

-- Future auth hook:
-- Supabase magic-link login can later query packs by verified user email
-- server-side and render a dashboard without exposing rows publicly.
