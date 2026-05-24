-- RoadLime initial schema.
-- Applied via Supabase MCP `apply_migration` once a project is provisioned.
-- The /lib/db.ts file-based store is the dev fallback; swapping in Supabase
-- means reimplementing that module against these tables (same TS interface).

create extension if not exists "pgcrypto";

-- ============================================================================
-- vendors
-- ============================================================================
create table if not exists public.vendors (
  id              uuid primary key default gen_random_uuid(),
  email           text not null unique,
  phone           text not null,
  password_hash   text,                       -- null when Supabase Auth owns the user
  auth_user_id    uuid unique,                -- references auth.users(id) when wired
  business_name   text not null,
  slug            text not null unique,
  description     text not null default '',
  category        text not null default '',
  logo_url        text,
  banner_url      text,
  status          text not null default 'draft'
                  check (status in ('draft','pending_review','live','suspended')),
  onboarding_step text not null default 'kyc'
                  check (onboarding_step in
                    ('signup','kyc','bank','category','location','products','go-live','done')),
  lat             double precision,
  lng             double precision,
  address         text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists vendors_status_idx     on public.vendors (status);
create index if not exists vendors_category_idx   on public.vendors (category);
create index if not exists vendors_geo_idx        on public.vendors (lat, lng);

-- ============================================================================
-- vendor_kyc — separated for stricter RLS on PII
-- ============================================================================
create table if not exists public.vendor_kyc (
  vendor_id     uuid primary key references public.vendors(id) on delete cascade,
  id_type       text check (id_type in ('passport','drivers_license','national_id')),
  id_number     text,
  document_url  text,
  submitted_at  timestamptz,
  reviewed_at   timestamptz,
  reviewer_id   uuid,
  review_notes  text
);

-- ============================================================================
-- vendor_bank — separated for stricter RLS on payout details
-- ============================================================================
create table if not exists public.vendor_bank (
  vendor_id       uuid primary key references public.vendors(id) on delete cascade,
  account_holder  text,
  bank_name       text,
  account_number  text,
  routing_number  text,
  country         text
);

-- ============================================================================
-- products
-- ============================================================================
create table if not exists public.products (
  id           uuid primary key default gen_random_uuid(),
  vendor_id    uuid not null references public.vendors(id) on delete cascade,
  name         text not null,
  description  text not null default '',
  price_cents  integer not null check (price_cents >= 0),
  currency     text not null default 'TTD',
  image_url    text,
  is_active    boolean not null default true,
  created_at   timestamptz not null default now()
);
create index if not exists products_vendor_idx on public.products (vendor_id, created_at desc);

-- ============================================================================
-- payments
-- ============================================================================
create table if not exists public.payments (
  id                  uuid primary key default gen_random_uuid(),
  vendor_id           uuid not null references public.vendors(id) on delete cascade,
  customer_email      text,
  processor           text not null check (processor in ('wipay','powertranz','stripe')),
  processor_txn_id    text,
  amount_cents        integer not null,
  fee_cents           integer not null default 0,
  currency            text not null default 'TTD',
  status              text not null
                      check (status in ('pending','succeeded','failed','refunded')),
  created_at          timestamptz not null default now()
);
create index if not exists payments_vendor_idx  on public.payments (vendor_id, created_at desc);
create index if not exists payments_status_idx  on public.payments (status);

-- ============================================================================
-- payouts
-- ============================================================================
create table if not exists public.payouts (
  id                   uuid primary key default gen_random_uuid(),
  vendor_id            uuid not null references public.vendors(id) on delete cascade,
  amount_cents         integer not null,
  currency             text not null default 'TTD',
  status               text not null
                       check (status in ('queued','sent','failed','cancelled')),
  processor_reference  text,
  created_at           timestamptz not null default now()
);
create index if not exists payouts_vendor_idx on public.payouts (vendor_id, created_at desc);

-- ============================================================================
-- reviews
-- ============================================================================
create table if not exists public.reviews (
  id          uuid primary key default gen_random_uuid(),
  vendor_id   uuid not null references public.vendors(id) on delete cascade,
  user_id     uuid,
  rating      smallint not null check (rating between 1 and 5),
  comment     text,
  created_at  timestamptz not null default now()
);
create index if not exists reviews_vendor_idx on public.reviews (vendor_id, created_at desc);

-- ============================================================================
-- categories — denormalized lookup for filters / pin colors
-- ============================================================================
create table if not exists public.categories (
  id     text primary key,
  name   text not null,
  icon   text not null,
  color  text not null
);

insert into public.categories (id, name, icon, color) values
  ('doubles',     'Doubles',          '🫓', '#F4C233'),
  ('corn_soup',   'Corn Soup',        '🌽', '#0FB892'),
  ('shark_bake',  'Shark & Bake',     '🦈', '#4A1E7A'),
  ('bbq',         'BBQ & Grill',      '🔥', '#F76B1C'),
  ('drinks',      'Drinks & Coconut', '🥥', '#0FB892'),
  ('costumes',    'Costumes',         '🪶', '#F4C233'),
  ('makeup',      'Makeup & Glam',    '💄', '#F76B1C'),
  ('taxi',        'Taxi & Rides',     '🚖', '#4A1E7A'),
  ('parking',     'Parking',          '🅿️', '#5A5A6A'),
  ('event',       'Event Services',   '🎉', '#F4C233')
on conflict (id) do nothing;

-- ============================================================================
-- updated_at trigger
-- ============================================================================
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists vendors_touch_updated_at on public.vendors;
create trigger vendors_touch_updated_at
  before update on public.vendors
  for each row execute function public.touch_updated_at();

-- ============================================================================
-- RLS — locked down by default. App reads live vendors via anon, writes via
-- service role for now. Tighten with auth.uid() checks once Supabase Auth is
-- wired to vendors.auth_user_id.
-- ============================================================================
alter table public.vendors     enable row level security;
alter table public.vendor_kyc  enable row level security;
alter table public.vendor_bank enable row level security;
alter table public.products    enable row level security;
alter table public.payments    enable row level security;
alter table public.payouts     enable row level security;
alter table public.reviews     enable row level security;

drop policy if exists vendors_public_read on public.vendors;
create policy vendors_public_read on public.vendors
  for select using (status = 'live');

drop policy if exists products_public_read on public.products;
create policy products_public_read on public.products
  for select using (
    is_active and exists (
      select 1 from public.vendors v
      where v.id = products.vendor_id and v.status = 'live'
    )
  );

drop policy if exists reviews_public_read on public.reviews;
create policy reviews_public_read on public.reviews
  for select using (true);
