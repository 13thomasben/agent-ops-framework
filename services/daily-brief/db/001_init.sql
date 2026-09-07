-- Daily Accountability Brief — state store (checklist item 7, built first).
-- Persistence is the product: an item gets ONE row for life, first_seen never
-- moves, and the row does not close until a real response is detected.
-- Day 4 of the same item must read "open 4 days" with no cron bumping a
-- counter — days_open is derived from first_seen at read time, never stored.
-- Target: Postgres 15+.

create table if not exists users (
  email            text primary key,
  key              text unique not null,
  full_name        text not null,
  slack_user_id    text,
  jira_account_id  text,
  mail_platform    text not null default 'm365',
  timezone         text not null default 'America/New_York',
  active           boolean not null default false,
  updated_at       timestamptz not null default now()
);

create table if not exists items (
  id                 text primary key,      -- sha256(user|source|source_id)[:16], stable for life
  user_email         text not null references users(email),
  block              char(1) not null check (block in ('A','B','C','D')),
  source             text not null check (source in ('email','slack','jira')),
  source_id          text not null,         -- email: conversationId · slack: channel:thread_ts · jira: KEY-123
  permalink          text,
  ask_summary        text not null,
  counterparty       text,
  counterparty_class text not null default 'unknown'
                     check (counterparty_class in ('customer','lender','oem','internal','vendor','unknown')),
  is_blocking        boolean not null default false,
  deadline           date,
  confidence         real,
  repeat_count       int not null default 1,          -- second/third asks on the same thread escalate hard
  last_ask_at        timestamptz,                     -- newest ask message seen — drives repeat_count
  stale_flag         boolean not null default false,  -- block C: no movement in 7+ days
  tier               text check (tier in ('blocking','overdue','today','aging')),
  score              real,
  first_seen         timestamptz not null default now(),
  last_seen          timestamptz not null default now(),
  closed_at          timestamptz,
  close_reason       text check (close_reason in ('reply','action','third_party','manual','source_gone')),
  close_evidence     text,
  unique (user_email, source, source_id)
);

create index if not exists items_open_idx on items (user_email) where closed_at is null;

create or replace view open_items as
  select i.*, (current_date - i.first_seen::date) as days_open
  from items i
  where i.closed_at is null;

-- One row per sent brief; brief_items freezes that morning's visible numbering
-- so "close 4, 7" resolves against exactly what the person read.
create table if not exists briefs (
  id          bigint generated always as identity primary key,
  user_email  text not null references users(email),
  sent_at     timestamptz not null default now(),
  subject     text not null,
  shown       int not null,
  not_shown   int not null default 0,
  waiting     int not null default 0,
  html        text
);

create table if not exists brief_items (
  brief_id  bigint not null references briefs(id) on delete cascade,
  position  int not null,
  item_id   text not null references items(id),
  primary key (brief_id, position)
);

-- Checklist item 12: every run logged with per-block counts + classifier drop
-- rate, so tuning has a baseline to move against.
create table if not exists runs (
  id           bigint generated always as identity primary key,
  kind         text not null default 'daily' check (kind in ('daily','reply_close','backfill')),
  user_email   text,
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  status       text check (status in ('ok','error','no_op')),
  counts       jsonb not null default '{}'::jsonb,
  error        text
);

-- Slack per-user OAuth tokens (Path B). M365 app creds + Jira service token
-- live in .env (Path A) and are never stored here.
create table if not exists credentials (
  user_email    text not null default '',   -- '' = workspace-level
  source        text not null check (source in ('slack','m365','jira')),
  kind          text not null default 'user_oauth',
  access_token  text not null,
  refresh_token text,
  expires_at    timestamptz,
  scopes        text,
  updated_at    timestamptz not null default now(),
  primary key (source, user_email)
);

-- Reply-to-close audit: the pressure valve, and labeled data on what the
-- classifier got wrong (every manual close = an item the system misjudged
-- or the user wanted gone).
create table if not exists reply_close_log (
  id                bigint generated always as identity primary key,
  received_at       timestamptz not null default now(),
  message_id        text unique,        -- Graph internetMessageId — dedupe without needing Mail.ReadWrite
  from_email        text,
  body_excerpt      text,
  parsed_positions  int[],
  closed_item_ids   text[],
  note              text
);
