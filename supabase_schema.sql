-- ──────────────────────────────────────────────────────────────────────────
-- Mindbody Booker – Supabase schema
-- Paste into the Supabase SQL editor and run
-- ──────────────────────────────────────────────────────────────────────────

-- User Mindbody credentials (one row per user, extends auth.users)
create table if not exists user_credentials (
  id                    uuid primary key references auth.users(id) on delete cascade,
  mb_email              text,
  mb_password_encrypted text,   -- Fernet-encrypted; key lives in Railway env
  studio_id             text not null default '48016',
  created_at            timestamptz not null default now()
);

-- Bookings (one row per scheduled booking)
create table if not exists bookings (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  instructor    text not null,
  class_date    text not null,        -- DD/MM/YYYY
  class_time    text not null default '',  -- HH:MM
  location      text not null,
  run_at        timestamptz not null,
  status        text not null default 'pending',
                -- pending | running | success | failed | cancelled
  gh_run_id     bigint,               -- GitHub Actions run ID for status polling
  error_message text,
  created_at    timestamptz not null default now()
);

-- Row-level security: users can only access their own rows
alter table user_credentials enable row level security;
alter table bookings enable row level security;

create policy "own credentials"
  on user_credentials for all
  using (auth.uid() = id);

create policy "own bookings"
  on bookings for all
  using (auth.uid() = user_id);
