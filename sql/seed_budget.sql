-- =============================================================================
-- One-time import of the household budget spreadsheet (budget_temp.xlsx).
-- Run in the Supabase SQL Editor AFTER sql/schema.sql.
-- Safe to re-run: nothing is added twice. Everything can be edited in the app.
--
-- Every spreadsheet line becomes a budget expense. Fixed bills are marked
-- "Track & remind" (due on the 1st), so they also appear on the Bills page.
-- =============================================================================

-- Family member names used by the budget's personal sections.
update people set name = 'Scoop' where name = 'Dad'
  and not exists (select 1 from people where name = 'Scoop');
update people set name = 'Kate'  where name = 'Mom'
  and not exists (select 1 from people where name = 'Kate');
insert into people (name, sort_order) select 'Scoop', 1 where not exists (select 1 from people where name = 'Scoop');
insert into people (name, sort_order) select 'Kate', 2  where not exists (select 1 from people where name = 'Kate');

-- Login names: the greeting and "done by" show Kate and Scoop (only if still the default).
update app_users u
   set display_name = v.name, person_id = (select id from people where name = v.name)
  from (values ('mom@shamp.com', 'Kate'), ('dad@shamp.com', 'Scoop')) as v(email, name)
 where lower(u.email) = v.email
   and (u.display_name is null or u.display_name = split_part(u.email, '@', 1));

-- Pay per paycheck (every 2 weeks = 26 paychecks a year).
insert into income (person_id, net_per_check, gross_per_check, checks_per_year)
select p.id, v.net, v.gross, 26
  from (values ('Kate', 3200.00, 4400.00), ('Scoop', 3587.87, 5396.15)) as v(name, net, gross)
  join people p on p.name = v.name
on conflict (person_id) do nothing;

-- All expenses, in spreadsheet order.
--   owner: null = shared (split 50/50); otherwise that person's own expense
--   track: true = "Track & remind" (shows on the Bills page, due on the 1st)
insert into bills (name, category, amount, frequency, budget_scope, default_payer_id, track,
                   due_day, start_month, payer_rule, alt_payer_id)
select v.name, v.category, v.amount, 'monthly',
       case when v.owner is null then 'shared' else 'personal' end,
       case when v.owner is not null then (select id from people where name = v.owner)
            when v.rule = 'alternate' then (select id from people where name = 'Scoop') end,
       v.track, 1, date_trunc('month', now())::date, v.rule,
       case when v.rule = 'alternate' then (select id from people where name = 'Kate') end
  from (values
    -- ord, name,                owner,   category,          amount,  track, payer rule
    ( 1, 'Mortgage',             null,    'Housing',         4595.00, true,  'alternate'),
    ( 2, 'HOA',                  null,    'Housing',          210.00, true,  'fixed'),
    ( 3, 'Fertilizer',           null,    'Home services',    100.00, true,  'fixed'),
    ( 4, 'Pest Control',         null,    'Home services',     15.00, true,  'fixed'),
    ( 5, 'Internet',             null,    'Utilities',         90.00, true,  'fixed'),
    ( 6, 'Lawn Care',            null,    'Home services',    220.00, true,  'fixed'),
    ( 7, 'Daycare',              null,    'Childcare',       1775.00, true,  'fixed'),
    ( 8, 'Pool',                 null,    'Home services',    140.00, true,  'fixed'),
    ( 9, 'Utilities',            null,    'Utilities',        500.00, true,  'fixed'),
    (10, 'Cleaning',             null,    'Home services',    150.00, true,  'fixed'),
    (11, 'Netflix',              null,    'Subscription',      16.00, true,  'fixed'),
    (12, 'Groceries/Food',       null,    'Food',             900.00, false, 'fixed'),
    (13, 'Misc',                 null,    'Other',            300.00, false, 'fixed'),
    (14, 'Savings',              null,    'Savings',          200.00, false, 'fixed'),
    (15, 'Car',                  'Kate',  'Transportation',   420.00, true,  'fixed'),
    (16, 'Car/Home Insurance',   'Kate',  'Insurance',        215.00, true,  'fixed'),
    (17, 'Loan',                 'Kate',  'Loan',             430.00, true,  'fixed'),
    (18, 'Exercise',             'Kate',  'Health & fitness',  90.00, false, 'fixed'),
    (19, 'Misc',                 'Kate',  'Personal',         200.00, false, 'fixed'),
    (20, 'Exercise',             'Scoop', 'Health & fitness',   0.00, false, 'fixed'),
    (21, 'Car',                  'Scoop', 'Transportation',     0.00, false, 'fixed'),
    (22, 'Misc',                 'Scoop', 'Personal',         800.00, false, 'fixed')
  ) as v(ord, name, owner, category, amount, track, rule)
 where not exists (
   select 1 from bills b
    where b.active and b.name = v.name
      and b.budget_scope = case when v.owner is null then 'shared' else 'personal' end
      and (v.owner is null or b.default_payer_id = (select id from people where name = v.owner)))
 order by v.ord;
