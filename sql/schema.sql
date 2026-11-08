-- =============================================================================
-- Family Hub database schema (Supabase / PostgreSQL)
-- Run once in the Supabase SQL Editor. Safe to re-run: every statement uses
-- "if not exists" or "on conflict do nothing".
-- =============================================================================

-- People who can be assigned chores, duties and bills (not the same as logins).
create table if not exists people (
  id          bigint generated always as identity primary key,
  name        text    not null unique,
  is_active   boolean not null default true,
  sort_order  int     not null default 0
);

-- App profile for each Supabase Auth login.
create table if not exists app_users (
  user_id       uuid primary key,              -- matches auth.users.id
  email         text not null unique,
  display_name  text,
  person_id     bigint references people(id) on delete set null,
  is_admin      boolean not null default false,   -- admins always see everything
  can_see_money boolean not null default false,   -- Budget, Bills, income, bill amounts
  can_see_sensitive boolean not null default false, -- codes, Wi-Fi, insurance numbers, sitter sheet
  created_at    timestamptz not null default now()
);

-- Free-form household settings (e.g. meal preferences sent to the AI).
create table if not exists household_settings (
  key    text primary key,
  value  text
);

-- ---------------------------------------------------------------- Chores ----
create table if not exists chores (
  id           bigint generated always as identity primary key,
  title        text not null,
  frequency    text not null check (frequency in ('daily','weekly','monthly','quarterly','yearly')),
  due_day      int  check (due_day between 1 and 31),     -- monthly and yearly chores
  due_month    int  check (due_month between 1 and 12),   -- yearly chores
  optional     boolean not null default false,
  starter_key  text unique,                               -- set for chores from the starter list
  notes        text,
  active       boolean not null default true,              -- false = hidden
  created_at   timestamptz not null default now()
);

-- One row per chore per period (day / week / month / quarter).
create table if not exists chore_log (
  id            bigint generated always as identity primary key,
  chore_id      bigint not null references chores(id) on delete cascade,
  period_start  date   not null,
  done          boolean not null default false,
  done_at       timestamptz,
  done_by       text,
  unique (chore_id, period_start)
);

-- ----------------------------------------------------------------- Meals ----
create table if not exists meals_library (
  id            bigint generated always as identity primary key,
  name          text not null,
  description   text,
  ingredients   text,            -- one ingredient per line
  instructions  text,
  prep_minutes  int,
  healthy       boolean not null default true,
  source        text not null default 'manual' check (source in ('manual','ai')),
  created_at    timestamptz not null default now()
);

create table if not exists meal_plan (
  id                bigint generated always as identity primary key,
  plan_date         date not null,
  slot              text not null default 'Dinner',
  meal_name         text not null,
  library_id        bigint references meals_library(id) on delete set null,
  ingredients       text,          -- copied from library / AI so grocery adds work
  instructions      text,
  is_leftovers      boolean not null default false,
  leftover_of_id    bigint references meal_plan(id) on delete set null,
  notes             text,
  created_at        timestamptz not null default now()
);

create table if not exists grocery_items (
  id          bigint generated always as identity primary key,
  item        text not null,               -- display name, e.g. 'onions'
  quantity    text,                        -- display amount, e.g. '3' or '1 1/2 cup'
  qty_num     numeric,                     -- parsed amount, used to merge duplicates
  unit        text,                        -- parsed unit ('' when none)
  name_key    text,                        -- normalised name used to merge duplicates
  for_meal    text,
  checked     boolean not null default false,
  created_at  timestamptz not null default now()
);

-- ------------------------------------------------------------- Childcare ----
create table if not exists childcare_duties (
  id          bigint generated always as identity primary key,
  duty_date   date not null,
  duty_type   text not null default 'Drop-off',
  duty_time   text,                      -- 'HH:MM', optional
  child       text,
  location    text,
  person_id   bigint references people(id) on delete set null,
  other_name  text,                      -- used when an "Other" person covers it
  done        boolean not null default false,
  notes       text,
  created_at  timestamptz not null default now()
);

-- ------------------------------------------------------ Budget expenses ----
-- Every budget expense lives here. Items with track = true also appear on the
-- Bills page each month (due day, who pays, paid) and in reminders.
create table if not exists bills (
  id                 bigint generated always as identity primary key,
  name               text not null,
  category           text not null default 'Other',
  amount             numeric(12,2),                 -- per period (see frequency)
  frequency          text not null default 'monthly' check (frequency in ('monthly','quarterly','annual')),
  budget_scope       text not null default 'shared' check (budget_scope in ('shared','personal')),
  default_payer_id   bigint references people(id) on delete set null,  -- owner if personal; payer if tracked
  track              boolean not null default true,  -- "Track & remind"
  due_day            int  not null default 1 check (due_day between 1 and 31),
  start_month        date not null default date_trunc('month', now())::date,
  payer_rule         text not null default 'fixed' check (payer_rule in ('fixed','alternate')),
  alt_payer_id       bigint references people(id) on delete set null,
  autopay            boolean not null default false,
  notes              text,
  active             boolean not null default true,
  created_at         timestamptz not null default now()
);

-- One row per tracked expense per month: who pays this month, and whether it is paid.
create table if not exists bill_payments (
  id         bigint generated always as identity primary key,
  bill_id    bigint not null references bills(id) on delete cascade,
  month      date   not null,                 -- first day of the month
  payer_id   bigint references people(id) on delete set null,
  amount     numeric(12,2),
  paid       boolean not null default false,
  paid_on    date,
  unique (bill_id, month)
);

-- ------------------------------------------------ Appointments & reminders ----
-- A repeating item is one row; its start_at is the first (or, for reminders,
-- the next) occurrence. Ticking a repeating reminder done moves it forward.
create table if not exists appointments (
  id          bigint generated always as identity primary key,
  kind        text not null default 'appointment' check (kind in ('appointment','reminder')),
  title       text not null,
  who         text,
  all_day     boolean not null default false,
  start_at    timestamptz not null,
  end_at      timestamptz,
  recurrence  text not null default 'none' check (recurrence in ('none','weekly','monthly','yearly')),
  location    text,
  notes       text,
  done        boolean not null default false,       -- reminders only
  done_at     timestamptz,
  created_by  text,
  created_at  timestamptz not null default now()
);

-- ------------------------------------------------- Contacts and info hub ----
create table if not exists contacts (
  id          bigint generated always as identity primary key,
  name        text not null,
  category    text not null default 'Other',
  phone       text,
  email       text,
  address     text,
  notes       text,
  created_at  timestamptz not null default now()
);

create table if not exists household_info (
  id          bigint generated always as identity primary key,
  label       text not null,
  value       text,
  category    text not null default 'Other',
  notes       text,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------- Budget ----
-- Take-home (net) and gross pay per paycheck, per person.
create table if not exists income (
  person_id        bigint primary key references people(id) on delete cascade,
  net_per_check    numeric(12,2) not null default 0,
  gross_per_check  numeric(12,2) not null default 0,
  checks_per_year  int not null default 26        -- paid every 2 weeks
);


-- -------------------------------------------------------------- Workouts ----
create table if not exists workouts (
  id             bigint generated always as identity primary key,
  workout_date   date not null,
  person_id      bigint references people(id) on delete set null,
  title          text not null,
  workout_type   text not null default 'Other',
  duration_min   int,
  intensity      text,
  details        text,
  done           boolean not null default false,
  done_at        timestamptz,
  source         text not null default 'manual' check (source in ('manual','ai')),
  created_at     timestamptz not null default now()
);

-- ----------------------------------------------------------------- Notes ----
create table if not exists notes (
  id          bigint generated always as identity primary key,
  parent_id   bigint references notes(id) on delete cascade,   -- set for replies
  author      text,
  body        text not null,
  color       text not null default 'yellow',
  pinned      boolean not null default false,
  done        boolean not null default false,
  created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------- Verses ----
create table if not exists daily_verse (
  verse_date   date primary key,
  reference    text not null,
  verse_text   text,
  translation  text
);

create table if not exists saved_verses (
  id           bigint generated always as identity primary key,
  reference    text not null,
  verse_text   text,
  translation  text,
  theme        text,
  saved_by     text,
  saved_at     timestamptz not null default now()
);

-- ------------------------------------------------------------- Ask AI ----
-- Private per login (filtered by user_id in the app).
create table if not exists chat_threads (
  id          bigint generated always as identity primary key,
  user_id     uuid not null,
  title       text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists chat_messages (
  id          bigint generated always as identity primary key,
  thread_id   bigint not null references chat_threads(id) on delete cascade,
  role        text not null check (role in ('user','assistant')),
  content     text not null,
  created_at  timestamptz not null default now()
);

-- -------------------------------------------------- Today's extras ----
-- One saved item per day and kind (history, joke, dinner, animal, recipe, lessons...), shared by everyone.
create table if not exists daily_extras (
  extra_date  date not null,
  kind        text not null,
  content     text not null,      -- JSON
  fetched_at  timestamptz not null default now(),
  primary key (extra_date, kind)
);

-- Trivia answers: one per person per day; a correct answer earns that day's wedge.
create table if not exists trivia_answers (
  user_id      uuid not null,
  answer_date  date not null,
  wedge        text not null,
  choice       text,
  correct      boolean not null default false,
  answered_at  timestamptz not null default now(),
  primary key (user_id, answer_date)
);

-- Daily learning: what each login has read (item = subject key) and knowledge-check answers (item = q0, q1, ...).
-- The lessons themselves are saved in daily_extras (kinds learn_adult and learn_kids).
create table if not exists learn_log (
  learn_date  date not null,
  track       text not null check (track in ('adult','kids')),
  item        text not null,
  user_id     uuid not null,
  answer      int,
  correct     boolean,
  done_at     timestamptz not null default now(),
  primary key (learn_date, track, item, user_id)
);

-- ------------------------------------------------------------- Photos ----
-- Photo files live in the private Storage bucket "photos" (created at the end of this
-- file); this table holds what the app needs to list them. week_start is the Monday of
-- the week the photo belongs to. One photo per week is the photo of the week.
create table if not exists photos (
  id           bigserial primary key,
  week_start   date not null,
  taken_on     date,
  path         text not null unique,      -- full-size file (about 1600 px) in the bucket
  thumb_path   text not null,             -- small copy for the timeline
  width        integer,
  height       integer,
  caption      text,
  is_featured  boolean not null default false,
  added_by     uuid,
  added_by_name text,
  created_at   timestamptz not null default now()
);
create index if not exists photos_week_idx on photos (week_start);
create unique index if not exists photos_one_featured on photos (week_start) where is_featured;

-- ------------------------------------------------- Journal/reflection ----
-- Private to each login (filtered by user_id in the app). One entry per person per day.
create table if not exists journal_entries (
  id          bigint generated always as identity primary key,
  user_id     uuid not null,
  entry_date  date not null,
  prompt      text,
  body        text not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (user_id, entry_date)
);

-- The day's AI-written prompt for each person (so it stays put until "New prompt").
create table if not exists journal_prompts (
  user_id      uuid not null,
  prompt_date  date not null,
  prompt       text not null,
  primary key (user_id, prompt_date)
);

-- --------------------------------------------- Upgrades to earlier tables ----
-- (No effect on a fresh install; brings an existing database up to date.)
alter table chores    add column if not exists optional boolean not null default false;
alter table chores    add column if not exists due_day int check (due_day between 1 and 31);
alter table chores    add column if not exists due_month int check (due_month between 1 and 12);
alter table chores    add column if not exists starter_key text unique;
alter table chores    drop column if exists default_person_id;
alter table chore_log drop column if exists person_id;
alter table notes     add column if not exists color text not null default 'yellow';
alter table app_users add column if not exists can_see_money boolean not null default false;
alter table app_users add column if not exists can_see_sensitive boolean not null default false;

-- Home upkeep was folded into Chores; remove its tables if they hold nothing.
do $$
declare n bigint;
begin
  if to_regclass('public.home_task_log') is not null then
    execute 'select count(*) from home_task_log' into n;
    if n = 0 then execute 'drop table home_task_log'; end if;
  end if;
  if to_regclass('public.home_tasks') is not null and to_regclass('public.home_task_log') is null then
    execute 'select count(*) from home_tasks' into n;
    if n = 0 then execute 'drop table home_tasks'; end if;
  end if;
end $$;
alter table chores    drop constraint if exists chores_frequency_check;
alter table chores    add constraint chores_frequency_check
  check (frequency in ('daily','weekly','monthly','quarterly','yearly'));
alter table meal_plan add column if not exists instructions text;
alter table bills     add column if not exists budget_scope text not null default 'shared';
alter table bills     add column if not exists track boolean not null default true;
alter table bills     drop constraint if exists bills_budget_scope_check;
-- Items previously marked "not in budget" are retired.
update bills set active = false, budget_scope = 'shared' where budget_scope not in ('shared','personal');
alter table bills     add constraint bills_budget_scope_check check (budget_scope in ('shared','personal'));

-- Budget-only items used to live in a separate table; fold them in as untracked expenses.
do $$
begin
  if to_regclass('public.budget_lines') is not null then
    insert into bills (name, category, amount, frequency, budget_scope, default_payer_id, track)
    select l.name,
           case l.name when 'Groceries/Food' then 'Food' when 'Savings' then 'Savings'
                       when 'Exercise' then 'Health & fitness' when 'Car' then 'Transportation'
                       when 'Misc' then case when l.scope = 'personal' then 'Personal' else 'Other' end
                       else 'Other' end,
           l.monthly_amount, 'monthly', l.scope, l.person_id, false
      from budget_lines l
     order by l.scope desc, l.person_id nulls first, l.sort_order, l.id;
    drop table budget_lines;
  end if;
end $$;

alter table appointments  add column if not exists kind text not null default 'appointment'
  check (kind in ('appointment','reminder'));
alter table appointments  add column if not exists recurrence text not null default 'none'
  check (recurrence in ('none','weekly','monthly','yearly'));
alter table appointments  add column if not exists done boolean not null default false;
alter table appointments  add column if not exists done_at timestamptz;
alter table grocery_items add column if not exists qty_num numeric;
alter table grocery_items add column if not exists unit text;
alter table grocery_items add column if not exists name_key text;

-- ----------------------------------------------------------------- Indexes --
create index if not exists idx_chore_log_period   on chore_log (period_start);
create index if not exists idx_meal_plan_date     on meal_plan (plan_date);
create index if not exists idx_childcare_date     on childcare_duties (duty_date);
create index if not exists idx_bill_payments_mon  on bill_payments (month);
create index if not exists idx_appointments_start on appointments (start_at);
create index if not exists idx_workouts_date      on workouts (workout_date);
create index if not exists idx_notes_parent       on notes (parent_id);
create index if not exists idx_chat_threads_user  on chat_threads (user_id, updated_at desc);
create index if not exists idx_chat_messages      on chat_messages (thread_id, id);
create index if not exists idx_journal_user_date  on journal_entries (user_id, entry_date desc);

-- ------------------------------------------------------------- Seed data ----
-- Starter family members, only on a brand-new database (rename them in Settings).
insert into people (name, sort_order)
  select v.name, v.sort_order from (values ('Dad', 1), ('Mom', 2)) as v(name, sort_order)
  where not exists (select 1 from people);

insert into household_settings (key, value)
  values ('meal_preferences', 'Family with young kids. Prefer quick weeknight dinners (under 40 minutes).'),
         ('kids_names', 'Alan, Betty')
  on conflict (key) do nothing;

-- ---------------------------------------------------- Row Level Security ----
-- The app connects as the database owner through the session pooler, which
-- bypasses RLS. Turning RLS on with no policies blocks the public REST API
-- (the publishable/anon key) from reading or writing any of these tables.
alter table people             enable row level security;
alter table app_users          enable row level security;
alter table household_settings enable row level security;
alter table chores             enable row level security;
alter table chore_log          enable row level security;
alter table meals_library      enable row level security;
alter table meal_plan          enable row level security;
alter table grocery_items      enable row level security;
alter table childcare_duties   enable row level security;
alter table bills              enable row level security;
alter table bill_payments      enable row level security;
alter table appointments       enable row level security;
alter table contacts           enable row level security;
alter table household_info     enable row level security;
alter table income             enable row level security;
alter table workouts           enable row level security;
alter table notes              enable row level security;
alter table daily_verse        enable row level security;
alter table saved_verses       enable row level security;
alter table chat_threads       enable row level security;
alter table chat_messages      enable row level security;
alter table journal_entries    enable row level security;
alter table daily_extras       enable row level security;
alter table journal_prompts    enable row level security;
alter table trivia_answers     enable row level security;
alter table learn_log          enable row level security;
alter table photos             enable row level security;

-- ------------------------------------------------------ Photo storage ----
-- A private bucket: files are only reachable through short-lived links the app makes.
-- Skipped automatically outside Supabase (where there is no storage schema).
do $$
begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    values ('photos', 'photos', false, 10485760, array['image/jpeg', 'image/png'])
    on conflict (id) do nothing;
  end if;
end $$;
