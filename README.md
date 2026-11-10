# The Shamp House

A family organizer built in Python with Streamlit, hosted on Streamlit Community Cloud from a private GitHub repo, with data stored in your Supabase project. Use it from any phone or computer, with a separate login for each person.

**Pages**

| Page | What it does |
|---|---|
| Today | Daily dashboard. It opens with a greeting by name, today's holiday if there is one, and the weather: now, today's high and low, notes such as rain timing or heat, a 5-day forecast, and sunrise and sunset. On weekdays from 6:30 to 9:30 AM and 2:30 to 5:30 PM, the **school run** follows, with live traffic between home and school. Next come the verse of the day and **Today's extras**: trivia of the day, quote of the day, today's headlines, this day in history, the animal of the day, art of the day, NASA's space photo of the day, the recipe of the day, a dinner question and today's lessons from Learn. Then, on Sundays from 1 to 10 PM, a prompt to plan next week, then the **Countdown** (the next 4 events you've added), followed by the **Gratitude jar**: today's prompt, your note and the family's, and one earlier note from the jar. Below that: appointments and reminders for the next 7 days (up to 8, overdue reminders first), today's meals, the latest notes, drop-offs and pick-ups, chores to do, workouts, and bills due in the next 7 days. You can tick things off right here. |
| Calendar | Day, week and month views of appointments and reminders, kids' duties, meals, bills, monthly and yearly chores, workouts and holidays, with a layer toggle for each. |
| Meals | A recipe of the day, AI meal ideas from Groq or a meal you name yourself (optionally built around what's in season), produce in season in Northeast Florida this month, a week plan (including leftovers), and a saved meal library. Ingredients go to the Grocery list. |
| Notes | A shared sticky-note board. Pick a color for each note; pin, mark done, reply or delete. |
| Grocery | The shared shopping list, with big checkboxes for use in the store. Matching items are combined (1 onion + 2 onions = 3 onion). |
| Chores | The full household chore list (daily, weekly, monthly, quarterly and yearly), loaded automatically. Monthly chores have a day of the month and yearly chores a date. Tick each one off; ticks clear at the start of its next day, week, month, quarter or year. Add your own with **Add to list**. |
| Appointments & reminders | Appointments and simple reminders, either of which can repeat weekly, monthly or yearly. Tick reminders when done; a repeating reminder moves to its next date. Export one item, or all upcoming, as an `.ics` file for Apple or Google Calendar (repeats included). |
| Week ahead | One screen for a Monday–Sunday week: holidays, countdown events, dinners, drop-offs and pick-ups, appointments and reminders, workouts and bills due. It lists what's still unplanned, and you can mark the week planned. |
| Kids | Drop-off and pick-up duties by week. Assign a family member or Other (with a name), tick when done, repeat weekly, or copy a whole week. |
| Learn | Four short lessons a day (science, history, money, and health & how things work), each written from a real Wikipedia article, plus the word of the day and a daily knowledge check. Tracks a reading streak for each person. |
| Gratitude jar | One short note a day each, shared with the family, with a simple prompt of the day to follow or ignore. Shows a note from the jar each day (or shake it for another), and every note so far, searchable. |
| Photos | A family photo timeline by week. Add as many photos as you like; one each week is the photo of the week. Browse by year and month, and make a monthly collage to save or print. |
| Workouts | Generate a workout with AI or add one by hand, assign it to a person and a day, tick it when done. Shows workouts done this week and month for each person. |
| Bills | This month's checklist of every expense marked **Track & remind**. Switch who pays for any month, edit that month's amount, and tick when paid. Autopay bills are never overdue; they mark themselves paid after the due day. |
| Budget | Monthly budget, laid out like the household spreadsheet: shared expenses split 50/50, each person's own expenses, income per paycheck, surplus, % of net and gross, and guideline amounts. Charts show each person's pay split and spending by category. This is where expenses are added and edited. |
| Ask AI | A general-questions chat. Each person's chats are private, and the latest 20 are kept. |
| Contacts & info | Tap-to-call contacts, plus household info such as door codes, the Wi-Fi password and insurance numbers. **Sitter sheet** makes a one-page PDF or image from the contacts and info you tick. |
| Settings | Your name and password, family member names, kids' names, meal preferences for the AI, and the school run addresses. Admins can also add or remove logins and choose whether each one can see money and sensitive info. |

**The menu.** A bar across the top holds **Today, Calendar, Meals, Notes** and **More**. **More** opens a list in this order: Grocery, Chores, Appointments & reminders, Week ahead, Kids, Learn, Gratitude jar, Photos, Workouts, Bills, Budget, Ask AI, Contacts & info and Settings, plus Sign out. On a narrow phone screen the bar folds into a menu button at the top. **Photos 🟠** in the menu means this week has no photo yet.

---

## Folder contents

```
streamlit_app.py            Starts the app: sign-in, menu, pages
check_setup.py              Checks code, secrets and every outside service (step 9)
push_to_github.sh           Uploads the folder to your GitHub repo (step 11, and every update)
requirements.txt            Python packages (Community Cloud installs these)
.gitignore                  Keeps secrets and caches out of git
.streamlit/
  config.toml               Theme colors, upload size, static files
  secrets.toml.example      Template for your secrets (copy to secrets.toml)
sql/
  schema.sql                Creates or updates all tables and the photos bucket
  seed_budget.sql           Imports the household budget spreadsheet
static/                     Fonts, logo and home-screen icons
hub/                        App code
  config.py                 Reads secrets; time zone; shared constants
  db.py                     Database connection pool and queries
  auth.py                   Supabase sign-in, password and login management
  session.py                Sign-in page and "keep me signed in" (30 days)
  device_store/             Tiny page component that keeps the saved sign-in on each device
  ui.py                     Look and feel (cards, chips, colors) and shared helpers
  forms.py                  Appointment/reminder and expense forms
  rows.py                   Chore, duty, bill and workout rows
  quick.py                  The round + quick-add button
  data.py, dates.py         Chore, bill, duty and repeat rules; date helpers
  budget.py                 Budget calculations
  groq.py                   AI requests (meal ideas, recipes, workouts, chat)
  extras.py, trivia.py      Today's extras and the trivia game
  verses.py, gratitude.py   Verse of the day; gratitude jar
  countdown.py              Countdown events
  gratitude_prompts.txt     The 366 gratitude prompts, one per date
  learn.py                  Daily lessons (Wikipedia + AI), knowledge check, streaks
  weather.py, traffic.py    Weather and moon; school run traffic
  seasonal.py, holidays.py  In season produce; holidays and church days
  photos.py                 Photo storage, resizing and the monthly collage
  sitter.py, ics.py         Sitter sheet PDF/image; calendar export
  grocery.py, starters.py   Grocery combining; starter chore list
  week.py                   Week ahead and the Sunday banner
  pages/                    One file per page
```

---

## Setup

Allow about 45 minutes. Work through the steps in order. Step 9 checks everything before you deploy.

You need:
- a Supabase project (step 1)
- a GitHub account (free) for the private repo
- Python 3.12 on your computer to run the check and try it locally (from [python.org](https://www.python.org/downloads/))

The app uses the **same Supabase database and the same logins** as before. If your Supabase project is already set up, do step 2 (it's safe to re-run), skip steps 5–6 if they're done, and copy the same values into the secrets file in step 7.

### 1. Open your Supabase project

Open your project at [supabase.com/dashboard](https://supabase.com/dashboard), or create a new one in a US East region. Keep the database password somewhere safe. If you've lost it, reset it under **Project Settings → Database**.

> Free-tier Supabase projects pause after about a week with no activity. Daily family use keeps it awake. If it does pause, click **Restore** in the dashboard.

### 2. Create the tables

1. In Supabase, open **SQL Editor → New query**.
2. Paste the whole of `sql/schema.sql` and click **Run**.
3. On a new project only: open another new query, paste `sql/seed_budget.sql` and click **Run**. This imports the household budget spreadsheet:
   - Family members are named **Scoop** and **Kate**.
   - Each person's pay per paycheck (every 2 weeks) is loaded.
   - Every spreadsheet line becomes a budget expense with a category.
   - The fixed bills are marked **Track & remind**, due on the 1st, so they also appear on the Bills page: Mortgage (alternating payer), HOA, Fertilizer, Pest Control, Internet, Lawn Care, Daycare, Pool, Utilities, Cleaning, Netflix, and Kate's Car, Car/Home Insurance and Loan.
   - Groceries/Food, Misc, Savings, Exercise and Scoop's Car count in the budget only.

   Everything can be edited, added or removed in the app afterwards. Running the import again won't create duplicates.

The schema creates 27 tables, the private `photos` storage bucket and, on an empty database, two starter family members. It also turns on Row Level Security. With no policies defined, that blocks the public Supabase REST API from reaching your data; the app connects directly to the database instead.

`sql/schema.sql` is safe to run again at any time. On a database that already has tables, it adds whatever is missing and brings existing tables up to date without touching your data. It also removes tables the app no longer uses, with their data: `journal_entries` and `journal_prompts`.

### 3. Copy the database connection details

Click **Connect** at the top of the project and choose **Session pooler**, not Direct connection. Streamlit Community Cloud needs an IPv4 address, and the direct connection may be IPv6 only. Note these values:

| Value | Example | Secret name |
|---|---|---|
| host | `aws-0-us-east-1.pooler.supabase.com` | `PG_HOST` |
| port | `5432` | `PG_PORT` |
| database | `postgres` | `PG_DB` |
| user | `postgres.<your-project-ref>` | `PG_USER` |
| password | your database password | `PG_PASSWORD` |

### 4. Copy the API URL and keys

Under **Project Settings → API Keys**, copy:

- **Project URL**, e.g. `https://abcd1234.supabase.co` → `SUPABASE_URL`
- **Publishable key**, used for signing in. Older projects call it the `anon` key. → `SUPABASE_PUBLISHABLE_KEY`
- **Secret key**, used only on the server for photos and to add or remove logins from the app. Older projects call it the `service_role` key. → `SUPABASE_SECRET_KEY`. **Never share it or commit it to git.**

Either the new key style (`sb_publishable_…` / `sb_secret_…`) or the legacy JWT keys work.

### 5. Lock down sign-ups

Go to **Authentication → Sign In / Providers**. Keep **Email** enabled and turn **off** "Allow new users to sign up". Only logins you create can then get in.

### 6. Create logins for you and your wife

Go to **Authentication → Users → Add user → Create new user**. Enter an email and password for each of you, and tick **Auto Confirm User**.

Put both emails in `ADMIN_EMAILS` in step 7. That makes you both admins, so either of you can add more logins (grandparents, a sitter) later from **More → Settings → Logins**, with no need to return to Supabase.

### 7. Fill in the secrets file

1. In the app folder, open the hidden `.streamlit` folder. (On a Mac, press **Cmd + Shift + .** in Finder to show hidden files. On Windows, tick **View → Hidden items** in File Explorer.)
2. Copy `secrets.toml.example` to a new file named `secrets.toml` in the same folder.
3. Fill in every value from steps 3–6. Keep the quotes around each value.
4. **Groq (AI):** create a key at [console.groq.com](https://console.groq.com) under **API Keys** → `GROQ_API_KEY`. `GROQ_MODEL` defaults to `openai/gpt-oss-120b`. Groq retires models from time to time. If the configured model stops working, the app asks Groq which models are live, switches to one automatically, and writes the model it chose to the app log. Copy that name into `GROQ_MODEL` to make it permanent.
5. **School run traffic (TomTom):** sign in at [developer.tomtom.com](https://developer.tomtom.com), open **API Keys** (a default key is created with the account; it covers Routing and Search) and copy it → `TOMTOM_API_KEY`. The free tier is far more than the app needs (about 36 requests a weekday, plus one lookup when an address changes). Without a key, the rest of the app works and the school run line says the key is missing.

6. **NASA space photo (optional):** get a free key at [api.nasa.gov](https://api.nasa.gov) (name and email; the key arrives straight away) → `NASA_API_KEY`. Without one, the app uses NASA's shared demo key, which allows only a few requests a day for everyone on the same server, so the photo may sometimes be missing.

`secrets.toml` is listed in `.gitignore`, so it never goes to GitHub. Community Cloud gets the same values by pasting them into the app's **Secrets** box (step 11).

### 8. Install the Python packages

Open a terminal (Mac: **Terminal**; Windows: **PowerShell**) in the app folder and run:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Each time you open a new terminal later, run the `activate` line again before the commands below.

### 9. Check everything

```bash
python check_setup.py
```

It runs each step in turn, printing **PASS** or **FAIL** with how long it took, then a summary. Fix anything that fails and run it again. `python check_setup.py --offline` runs only the steps that don't need the internet; `--debug` adds the full error details to a failure.

What it checks:
- Python 3.11 or newer, and every package in `requirements.txt` installed
- all app code loads
- every secret in `secrets.toml` filled in
- the app's rules, against known answers:
  - dates and calendar helpers, repeating appointments and reminders, chore due dates
  - the sitter sheet draws as a PDF and an image; fonts, logo, icons and theme are present
  - gratitude jar prompts and the note from the jar, countdown labels, animal of the day (species filter, daily pick, no repeats), recipe of the day, trivia rules
  - weather notes and the moon phase
  - school run traffic rules, in season produce, word of the day parsing
  - daily learning: reading time, article trimming, knowledge-check questions and streaks
  - headlines: reading news feeds, 3 national + 2 local without repeats, and the 2-hour refresh
  - photos: weeks, photo of the week and the collage layout
  - holidays (Google feed and church days), art of the day, space photo of the day, grocery combining
  - the budget maths reproduces the household spreadsheet
  - keep me signed in (the device component and its rules)
- live, each one a real request:
  - the database connection (session pooler) and that every table exists
  - Supabase Auth is reachable and public sign-ups are off
  - the Supabase secret key works
  - bible-api.com; Wikipedia, iNaturalist, Open Trivia DB and ZenQuotes; Merriam-Webster
  - TheMealDB (recipe of the day)
  - NASA's Astronomy Picture of the Day (says whether your own key or the shared demo key was used)
  - the headline feeds (NPR, and Jacksonville Today or News4JAX)
  - daily learning: builds a day's lessons from Wikipedia with Groq (nothing is saved)
  - the Art Institute of Chicago and Google's holiday calendar
  - Open-Meteo weather
  - the `photos` storage bucket (uploads, reads and deletes a test file)
  - TomTom traffic
  - Groq: in season produce and meal ideas

### 10. Try it locally

```bash
python -m streamlit run streamlit_app.py
```

Starting it with `python -m` makes sure it uses the Python in `.venv` (where the packages were installed), not another Python on your computer. Your browser opens at `http://localhost:8501`. The tip it prints about installing Watchdog is optional: it only makes the app reload faster while you edit code. Sign in with a login from step 6. Press **Ctrl + C** in the terminal to stop it.

### 11. Put the code in a private GitHub repo

**Option A: GitHub website (no git needed)**
1. Sign in at [github.com](https://github.com) and click **+ → New repository**.
2. Name it (e.g. `family-hub`), choose **Private**, and click **Create repository**.
3. Click **uploading an existing file**. Drag in everything from the app folder **except** `.venv` and `.streamlit/secrets.toml`. Hidden folders don't always drag in, so check that `.streamlit/config.toml` and `.gitignore` are in the list; if not, use **Add file → Create new file**, type `.streamlit/config.toml` as the name and paste its contents.
4. Click **Commit changes**.

**Option B: the push script (easiest after the first time)**
Create the empty private repo on github.com first (Option A steps 1–2). If its name isn't `family-hub-py`, change the `REPO=` line near the top of `push_to_github.sh`. Then, in the app folder:
```bash
bash push_to_github.sh "First upload"
```
It works in a freshly unzipped folder (it sets up git and lines up with what's already on GitHub) or one that's already set up. It never uploads `secrets.toml` or `.venv`: it stops with a message instead. It prints each step (1/6 to 6/6) as it goes.

**Option C: git commands by hand**
```bash
git init
git add .
git status                 # secrets.toml and .venv must NOT be listed
git commit -m "Family hub"
git branch -M main
git remote add origin https://github.com/YOUR-NAME/family-hub.git
git push -u origin main
```
(Create the empty private repo on github.com first, as in Option A steps 1–2.)

Either way, open the repo on GitHub afterwards and make sure there is **no** `secrets.toml` in the `.streamlit` folder. If one was uploaded, delete it there and change the Supabase database password and secret key, since they've been exposed.

### 12. Deploy to Streamlit Community Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and **Continue with GitHub**.
2. The first time, Streamlit asks to connect GitHub. Allow access to **private repositories** (on the GitHub authorization page, grant access to your repos), or it won't see the repo.
3. Click **Create app → Deploy a public app from GitHub** (the wording may vary; you are deploying from a repo).
4. Fill in:
   - **Repository:** `YOUR-NAME/family-hub`
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
   - **App URL:** pick a name, e.g. `shamp-house` → `shamp-house.streamlit.app`
5. Open **Advanced settings**:
   - **Python version:** 3.12
   - **Secrets:** paste the whole contents of your `secrets.toml`
   - **Save**
6. Click **Deploy**. The first build takes a few minutes while it installs the packages. When it finishes, the sign-in page appears.

**Who can open it.** An app deployed from a private repo starts as **private**: only you, as the developer, can open it, and anyone else must be invited by email and sign in to Streamlit with that email before they even see your sign-in page. Change this in the app's **Share** button (top right) or **Settings → Sharing**:
- **Recommended: make the app public** ("This app is public and searchable"). The **code stays private** in your private repo; only the web address is open, and nothing loads until someone signs in with a family login. This is simplest on phones and for grandparents or a sitter.
- **Or keep it private** and invite Kate (and anyone else) by email under **Who can view this app**. Each of them then signs in twice: once to Streamlit, then to the family login.

The free plan allows one private app per account, so keeping this one private uses that slot.

### 13. Add it to both phones

Open the app's address in the phone's browser and sign in with **Keep me signed in on this device** ticked.
- **iPhone (Safari):** Share → **Add to Home Screen**.
- **Android (Chrome):** ⋮ menu → **Add to Home screen**.

It opens like an app and stays signed in (each visit renews it; 30 days without a visit signs it out).

---

## Updating the app

- **Code changes:** edit the files (or unzip a new version over the folder, keeping `.streamlit/secrets.toml`), then run `bash push_to_github.sh "what changed"`. Community Cloud notices the change and redeploys within a minute or two.
- **New packages:** add them to `requirements.txt` and push; Community Cloud installs them on the next deploy. Keep Streamlit pinned to an exact version so it doesn't change underneath you.
- **Secrets:** change them in the app's **Settings → Secrets** on share.streamlit.io. The app restarts with the new values. Update your local `secrets.toml` too so `check_setup.py` matches.
- **Database changes:** if `sql/schema.sql` changes, run it again in the Supabase SQL Editor.
- **Stuck or acting oddly:** on share.streamlit.io, open the app's ⋮ menu → **Reboot app**. **Manage app** (bottom right of the app, visible only to you) shows the log.
- **Sleeping:** an app with no visits for 12 hours goes to sleep. The next visitor sees a "This app has gone to sleep" page with a button to wake it, which takes 30–60 seconds. Daily use keeps it awake.

---

## Using it

**Chores.**
- The full chore list loads automatically the first time someone signs in. It's based on a standard cleaning schedule: daily, weekly, monthly (including optional extras), quarterly and yearly. The yearly list includes outdoor and system jobs: gutters in spring and fall, HVAC vents, outside A/C units, and pressure washing.
- **Dates:** monthly chores have a day of the month and yearly chores a date. The starter ones are spread out so they don't pile up. Each shows **Due soon** in the week before its date and **Overdue** if it's still unticked after. Change any date with the ✏️ button.
- **Ticking off:** ticks clear at the start of the next day, week, month, quarter or year. A ticked chore shows who did it.
- **Add to list** adds your own chore. Your own chores can be deleted. Starter chores can be edited or hidden (bring them back with **Show** under **Hidden chores** at the bottom).
- **Choosing what to see:** both Today and the Chores page have a dropdown: **Due now**, **Daily**, **Weekly**, **Monthly**, **Quarterly**, **Yearly** or **All**. Your choice is kept while the app is open.
  - On Today it starts on **Due now**: daily and weekly chores, plus monthly and yearly ones due within a week or overdue.
  - The Chores page starts on **Daily**.
  - Optional chores never show on Today.

**Meals.**
- **Recipe of the day** sits at the top: a main dish from [TheMealDB](https://www.themealdb.com) with its photo, cuisine and category. **Ingredients & steps** shows the full recipe, **Add to plan** puts it on a day (and can add its ingredients to the grocery list), and **Save to library** keeps it. Links go to TheMealDB's page and, when there is one, the original recipe and a video.
  - Everyone gets the same recipe each day. Desserts are skipped, and the same recipe isn't repeated within 90 days.
  - It also shows in **Today's extras**, with a link to Meals.
  - TheMealDB is free for personal projects with its public test key, so no key is needed. Measurements are as the recipe gives them, sometimes metric.
- **Generate ideas** asks Groq for meal ideas. Each new set replaces the last generated set (meals you named yourself stay), and **Clear ideas** removes them all. **Healthy options only** is on by default. **Settings → Meal preferences** is sent with every request, so put family size, dislikes, allergies and time limits there.
- To use your own dish, turn on **Add your own recipe** and type it. Choose **Get recipe with AI** for ingredients and steps, or **Add without recipe**.
- On any idea, **Ingredients & steps** shows the recipe, **Save to library** keeps it for good, and **Add to plan** puts it on a day. Adding to the plan can also put its ingredients on the grocery list.
- In **Week plan**, the **+** on a day adds a typed meal, a library meal, or **Leftovers** from a meal in the past week. The cart button on a planned meal sends its ingredients to the grocery list.

**Grocery.**
- Type items the way you'd say them ("2 lb chicken", "milk") and press Enter. **Add this week's meal ingredients** (or **Add next week's**) pulls in everything from the meal plan.
- Matching items are combined when both the item and the unit match: "1 onion" + "2 onions" becomes 3 onion, and "1 cup milk" + "½ cup milk" becomes 1 1/2 cup milk. Sizes and prep words are ignored for matching, so "1 large egg" and "12 eggs" combine, as do "2 lb boneless chicken thighs" and "1 lb chicken thighs". Different units stay separate (a can of beans and a cup of beans).
- Tick items as you shop. They move to **In the cart** at the bottom. **Clear checked** removes them.
- The list refreshes every 10 seconds, so two people can shop from it at once.

**Kids.** Add a drop-off or pick-up, choose who (a family member, or Other with a name), and optionally repeat it weekly. **Copy this week to next week** duplicates a regular routine. Change who's covering a single day from that day's dropdown.

**Budget and bills.**
- **Every expense lives in the Budget.** Each has an amount (per month, quarter or year), whose it is (Shared, split 50/50, or a person's own) and a category.
- **Track & remind** gives an expense a due day. It then appears on the **Bills** page each month and on Today when it's due within a week. For shared tracked bills you can set a payer, or alternate payers monthly (the mortgage). Personal bills are paid by their owner.
- **Autopay** bills can't be overdue. Before the due day they show as **Due soon · auto**; after it they count as paid automatically.
- On the **Bills** page, switch who pays for a single month, change that month's amount, and tick bills as paid. The bar at the top shows how much of the month is paid. **Add** there creates a tracked expense.
- In the Budget tables, type over a **Monthly** amount to change it. Tick the ✏️ box on a row to open the full form, where you can also delete an expense. Quarterly and annual expenses show as a monthly share (÷ 3 or ÷ 12); typing a new monthly share saves the matching quarterly or annual amount.
- **Charts:**
  - **By person** splits each person's monthly take-home pay into their half of shared expenses, their own expenses and what's left over.
  - **By category** ranks monthly spending, shared and personal combined.
  - Hover or tap a bar for the amounts.
- The budget is a monthly plan, not a spending log. Turn on **Show weekly / daily columns** for more detail. Pay is entered per paycheck under **Income**.
- **Calculations:**
  - Monthly pay = per-check × 26 ÷ 12.
  - Weekly = monthly × 12 ÷ 52; daily = weekly ÷ 7.
  - Guidelines are 25/36/45% of combined monthly take-home pay and 28/36% of combined monthly gross.

**Workouts.**
- **Generate** builds a workout from the type, time, intensity, equipment and any focus or limits you enter. **Edit & add** lets you adjust it, pick the day and who it's for. Ticking both people adds a copy for each.
- **Add manually** is the same form, blank.
- Tick a workout when it's done. The boxes at the top count workouts done this week and this month for each person.

**Notes.** Write a note, pick its color (yellow, pink, blue, green or purple) and tap **Stick it**.
- Each note's **⋯** button pins it to the top, marks it done, changes its color (each tap moves to the next color), adds a reply, or deletes it (or one of its replies). Done notes are hidden unless **Show done** is on.
- The latest open notes also show on Today as small stickies.

**Sitter info sheet.** On **Contacts & info**, **Sitter sheet** builds a one-page sheet for a babysitter.
- **What's on it:** a title and the home address (remembered for next time). You tick which contacts to include; Family contacts are ticked by default, so add Mom and Dad there. You also tick which household info to include; codes, Wi-Fi and passwords are pre-ticked. There's a box for tonight's notes (bedtime, allergies, where things are).
- **Formats:** **PDF** for printing, or **Image** to text straight to the sitter.
- **Fitting one page:** if there's a lot on it, the text shrinks to fit.

**Verse of the day.**
- Everyone sees the same verse each day. It is picked at random from about 100 well-known verses, without repeating within 60 days.
- Type a theme (e.g. "being kind to others") and tap **Find**, or tap **Random**, for an extra verse just for you.
- The bookmark saves any verse to the shared **Saved** list.
- Verse text comes word for word from [bible-api.com](https://bible-api.com) in the King James Version (public domain, no key needed). The AI only suggests which verse fits a theme, never the wording.
- **Translation:** set by `BIBLE_TRANSLATION` in the secrets (`kjv`). bible-api.com also offers `web` (World English Bible), `asv`, `bbe` (Basic English), `darby`, `ylt` and `oeb-us`. After a change, the next sign-in re-fetches every saved verse and today's verse in the new translation, once.

**Appointments & reminders.**
- **Appointment** has a time, place and optional end time.
- **Reminder** is just a title and date (time optional), with a box to tick when done. Overdue reminders stay at the top of the list and on Today until ticked.
- Either can repeat weekly, monthly or yearly (birthdays, filter changes, bin day). Ticking a repeating reminder done moves it to its next date.
- Monthly items on the 29th–31st land on the last day of shorter months. A yearly 29 February lands on 28 February in non-leap years.
- **Calendar sync:** each item has an **.ics** button. Tap it on your phone and Calendar offers to add it; repeating items come through as a repeating series. **Export upcoming (.ics)** downloads everything coming up at once. Each item keeps the same ID, so exporting an edited one again updates the copy already in your calendar on most apps.

**Calendar.** Switch between Day, Week and Month with the **View** buttons and move with the arrows or **Today**. The **Layers** chips turn each kind of item on or off. Tap an item to see its details.

**Week ahead and the Sunday banner.**
- **Week ahead** shows one week day by day.
- At the top it lists what's still unplanned:
  - days without a dinner
  - drop-offs or pick-ups with no one assigned
  - no workouts planned
  - weekly chores with no one assigned
- From Friday it opens on next week.
- On Sundays from 1 to 10 PM, Today shows a **Time to plan next week** banner with the gaps. **Week planned** (on the banner or the page) hides it for both of you until the following Sunday.

**In season now (Meals).**
- Lists fruit, vegetables and herbs in season in Northeast Florida this month, with a star on those at their best and a shopping tip. Groq writes the list once a month and it is saved for everyone, so it isn't a fixed list in the app. **Refresh** asks again. If nobody has loaded this month's list yet, tap **Load this month's produce**.
- **Use what's in season** (next to **Healthy options only**) builds generated ideas around this month's produce. **Meal ideas with these** on the panel ticks it and makes a new set in one tap; the ideas appear at the top of **Meal ideas**.
- It's AI-written, so treat it as a guide and check at the market.

**School run.**
- On weekdays Today shows a traffic line under the weather: **home → school** from 6:30 to 9:30 AM and **school → home** from 2:30 to 5:30 PM. It is hidden on weekends and at other times. School holidays aren't known to the app, so it shows on those weekdays too.
- It shows the drive time with live traffic, your arrival time if you leave now, and how that compares with the usual time for that hour. When it's 10 or more minutes slower than usual, the line turns orange with **Heavier than usual**.
- **Arrive at school by** (optional) adds **Leave by …** in the morning, or **Running late** once that time has passed.
- If rain is likely (50%+) during the rest of the window, it adds a rain note.
- **Maps** opens the route in Google Maps (shown to people who can see sensitive info, because it reveals the home address).
- Set it up in **Settings → School run**: the school name shown on Today, the school address (pre-filled with 8985 Annie Eliza Rd, Jacksonville, FL 32256) and the home address, which is the same one the sitter sheet uses. **Save** looks both addresses up straight away and shows what TomTom found, so a typo shows up there. Only people who can see sensitive info can view or change the home address.
- Traffic comes from TomTom, is fetched at most every 10 minutes, and the line on Today updates itself every 5 minutes while it's open. If TomTom can't be reached, the last result stays up with its time.

**Ask AI.** A general-questions chat: recipes, kids' activities, how-tos, ideas.
- Each person's chats are private. The latest 20 are kept and can be reopened from the **Chat** dropdown at the top. **New chat** starts fresh, and the bin deletes the current chat.
- Questions go to Groq with the rest of that chat for context. Nothing else from the app is sent.

**Holidays.**
- **Source:** Google's public "Holidays in the United States" calendar (free, no key). It covers federal holidays and everyday observances such as Mother's Day, Father's Day, Valentine's Day, St. Patrick's Day, Easter, Halloween and the Daylight Saving Time changes. Holidays that only apply in other states are left out. The list is saved and refreshed once a week.
- **Day off:** days Google lists as public holidays (New Year's, MLK Day, Memorial Day, July 4th, Labor Day, Veterans Day, Thanksgiving, Christmas and others) are tagged **Day off**, since offices, banks and the post office close. Schools may follow a different calendar.
- **Church days:** Ash Wednesday, Palm Sunday, Good Friday, Easter Sunday, Pentecost and the first Sunday of Advent are worked out each year from the date of Easter (the standard Gregorian calculation), so they're there even if Google's list leaves one out.
- **Where they show:** a marigold **Holidays** layer on the Calendar, a line under the date on Today ("Today is Veterans Day · Day off"), and a tag on that day in Week ahead.

**Weather.** The weather on Today comes from Open-Meteo, a free service with no key. It covers Mandarin, Jacksonville, in °F, and is fetched at most every 30 minutes. To use another spot, set `WEATHER_LAT` and `WEATHER_LON` in the secrets.
- **At a glance:** the current temperature with today's high and low, a 5-day forecast (today plus 4 days, with rain chance when it's 20% or more), sunrise and sunset, and the moon phase with the date of the next full moon. The moon phase is calculated from the date, so it needs no outside source.
- **Notes,** shown only when they matter:
  - rain likely later today or tomorrow, with the time it starts
  - a hot day (92° and up) or very high UV
  - a chilly morning (45° or below)

**Today's extras.** Each item is fetched once a day, saved, and shown to everyone. If a source is down, that line is skipped and tried again 30 minutes later.
- **Headlines:** the top 3 national stories from NPR and the top 2 local stories from Jacksonville Today (WJCT's nonprofit newsroom), each with its outlet and how long ago it was posted. Tap a headline to read it on the outlet's site. Only headlines are shown, no AI summaries. They refresh every 2 hours and everyone sees the same set. If a feed can't be reached, the app tries a backup (NPR's general news feed, or News4JAX local news) and otherwise keeps the last headlines up.
- **This day in history:** one or two events from Wikipedia's "On this day", with a link to read more.
- **Dinner question:** a conversation starter written by AI for the family. It avoids the past three weeks' questions.
- **Animal of the day (spotted near home):** a wild animal that someone photographed within about 25 miles of home in the last two weeks, from [iNaturalist](https://www.inaturalist.org) (free, no key). It shows the photo, the common and scientific names, what kind of animal it is and the day it was seen ("Bird spotted near home on Nov 5"), a short description, and a link to the sighting.
  - **Only confirmed sightings:** the iNaturalist community must have agreed on the species ("research grade"). Zoo and pet animals are left out.
  - **Photos:** only photos the photographer shared under a Creative Commons licence are used, and their credit is shown under each one, as the licence requires.
  - **Variety:** the same species isn't shown again within 60 days. If nothing new was seen in the last two weeks, it looks back 60 days.
  - **Home:** the location comes from `WEATHER_LAT` and `WEATHER_LON`. Exact spots aren't shown.
  - If the day's saved animal came from an older source (for example the R version of the app, which shares the database), it's replaced with an iNaturalist one.
- **Space photo of the day:** NASA's Astronomy Picture of the Day: the picture, its title, a few sentences of NASA's explanation, and the photographer's credit. Tap the picture to open NASA's page for it. On days when it's a video, you see its preview with a **Watch today's video** link. Just after midnight, before NASA posts the new one, it shows the latest. On the rare days it's an interactive page rather than a picture, it's left out.
- **Recipe of the day:** see **Meals** above.
- **Art of the day:** a public-domain painting from the Art Institute of Chicago (free, no key): the image, title, year, artist and a few sentences from the museum's description, with a link to the museum page. Tap the picture to see it full size there. The museum's picture server only answers requests that come from its own website, so the app downloads each day's picture itself and shows its own copy (if that fails, the painting shows without its picture). The descriptions are licensed CC BY, so the museum is credited under each one.
- **Trivia (Trivial Pursuit style):** one multiple-choice question a day from the Open Trivia Database (free, CC BY-SA 4.0). It's the same question for everyone, and each person answers once.
  - **Wedges by weekday:** Monday Geography (blue), Tuesday Entertainment (pink), Wednesday History (yellow), Thursday Arts & Literature (brown), Friday Science & Nature (green), Saturday Sports & Leisure (orange), Sunday General Knowledge (purple).
  - **Difficulty:** mostly medium, with some easy and some hard days.
  - **Scoring:** a right answer earns that day's wedge. Get all seven between Monday and Sunday to win the pie. After you answer, you see the right answer and everyone's pie for the week, plus pies won so far.
  - **Missed a day?** Yesterday's question stays open until midnight tonight. After that, the wedge is lost for the week.
- **Quote of the day:** ZenQuotes' daily inspirational quote with its author. The free service requires the "Inspirational quotes provided by ZenQuotes API" credit, which is shown with it.

**Learn.** Short lessons to read each day, under **More → Learn**.
- **Four subjects a day:** Science, History, Money, and Health & how things work. Each lesson is a 3–5 minute read ending with a takeaway. Each card shows a picture, the lesson as a question ("Why are stars different colors?"), a one-line hook and the reading time. Tap **Read** to open it and **✓ Done reading** when you're finished.
- **Where lessons come from:** each day the AI picks one topic per subject, each tied to a real Wikipedia article. The app reads the article from Wikipedia, and the AI writes the lesson using only that article's text. Every lesson links to its article, so you can check it or read more. AI can still get things wrong, so treat the article as the final word.
- **Variety:** an article isn't used again within 180 days. If a topic's article can't be found or was used recently, the AI is asked for a replacement.
- **Reading time** is worked out from the lesson's length: 200 words a minute, at least 1 minute.
- **Shared by everyone:** the first person to open Learn each day starts the writing, which takes about 20 seconds, with each step shown as it goes. After that it opens straight away for everyone. If Wikipedia or the AI can't be reached, it tries again 30 minutes later.
- **Word of the day** sits with the lessons as the **Vocabulary** card: Merriam-Webster's Word of the Day (an adult vocabulary word) from their free daily feed: the word, part of speech, definition and an example sentence. **Pronunciation and origin** opens the pronunciation and the "Did you know?" note on where the word comes from. A link goes to the full entry. The feed updates overnight, so very early in the morning the word may appear a little later.
- **Daily knowledge check:** three multiple-choice questions on the day's lessons. Each person answers once; you then see the right answer and why, and your score for the day.
- **Streak:** each person's count of days in a row with at least one lesson read or question answered. It doesn't reset until a whole day is missed.
- **On Today:** **Today's extras** lists the day's lessons with their reading times (once someone has opened Learn that day) and links to Learn. Trivia stays on Today.

**Photos.**
- **Adding:** the upload box takes as many photos as you like at once, from the camera roll or the camera. Type an optional **Caption** before tapping **Add**: it's saved on every photo in that upload, and you can change any of them later. Each one is turned the right way up, shrunk (about 1600 px), and stripped of its hidden details, including location, before it's saved.
- **Which week:** a photo goes in the week (Monday to Sunday) it was taken, using the camera's date when the file has one, otherwise the day it's added. So last weekend's photos added on Monday still land in last weekend's week. Old photos land in their own month and year.
- **Photo of the week:** the first photo in a week becomes the photo of the week. Tap **Open** under any photo to make it the photo of the week instead, add or change its caption, fix its date (which can move it to another week), or delete it.
- **Timeline:** pick the year and month at the top (months show how many photos they have). Weeks are newest first, each headed by its dates (e.g. "Nov 2 – 8, 2026"). The photo of the week is shown large and every photo shows its date with the year.
- **Reminder:** until a photo is added this week, the menu shows **Photos 🟠**. Nothing shows on Today.
- **Monthly collage:** **Make collage** builds one picture for the month shown: its month and year as the title, then one band per week with that week's dates and the photo of the week's caption. The photo of the week is large, and up to six others sit beside it (a "+N" tile if there are more). It's 8 × 10 inches at 300 dpi, ready to print or share. **Open full size to save** opens it in a new tab, where you can save or share it (on a phone, press and hold the picture). **Remake collage** updates it after you add or change photos. From the 1st of each month, the Photos page offers last month's collage until someone makes it.
- **Storage:** photos are kept in a private Supabase Storage bucket called `photos`, which `sql/schema.sql` creates. The bucket isn't public: the app shows photos through links that expire after an hour, so a copied link stops working. At about 0.5 MB each (full size plus a small copy), Supabase's free 1 GB holds roughly 2,000 photos, which is about 7 years at 5 photos a week. Delete photos you don't need to free up space, or move to a paid Supabase plan later.
- **iPhone photos:** HEIC photos are accepted and converted. If a photo ever won't upload, set **Settings → Camera → Formats → Most Compatible** on the phone. Each upload can be up to 40 MB.

**Countdown.** Days until the things you're looking forward to: a trip, a party, a due date.
- **Adding:** on Today's **Countdown** card, tap **Add**, type what it is, pick the date and an icon, and **Save**.
- **On Today:** the next 4 within a year, soonest first, showing **Today!**, **Tomorrow** or **N days**, with the date.
- **In Week ahead:** each event is tagged on its day, next to any holiday.
- **Manage** lists every countdown, past ones included, to edit (✏️) or delete. Past events drop off Today by themselves.

**Gratitude jar.** A shared jar of short notes: one a day each, seen by everyone who signs in.
- **Prompt of the day:** a simple question for each date of the year (366, themed by month: fresh starts in January, love in February, beach days in summer, thanks in November, and so on). It's the same for everyone, and each date keeps its prompt every year. Follow it or write anything. To change one, edit its line in `hub/gratitude_prompts.txt` (January 1 is first).
- **Adding:** type a few words in the card on Today (or on **More → Gratitude jar**) and tap **Put it in the jar**. Writing again the same day replaces your note; tap **Edit my note** to change it. Notes can be up to 300 characters.
- **From the jar:** Today shows one earlier note, the same for everyone that day. On the Gratitude page, **Shake the jar** pulls out another.
- **All notes:** the Gratitude page lists every note, newest first, with a search box and a filter for just your own. You can delete your own notes.

**Quick add.** The round **+** in the bottom corner adds a reminder, appointment, note, grocery item or meal from any page. It's hidden on Ask AI and the Gratitude jar so it doesn't cover the writing box. For grocery items, separate several with commas.

**Deleting.** Delete buttons ask first (notes and the grocery **Clear checked** are the exceptions): a small box opens with **Yes, delete** (or **Yes, remove**). Tap anywhere else to cancel.

**Staying signed in.** With **Keep me signed in on this device** ticked, that phone or computer stays signed in. Each visit renews it, and it's forgotten after 30 days without a visit. When you open the app it shows "Signing you in…" for a moment, then Today. If that ever hangs, tap **Sign in with email instead**.
- **How it's kept:** the sign-in is saved in the browser's own storage on that device and passed to the app through a tiny invisible part of the page. Cookies aren't used: Streamlit Community Cloud removes them before the app can read them.
- **Each sign-in works once:** every visit swaps it for a new one and saves that straight away.
- **iPhone home-screen icon:** it keeps its own sign-in, separate from Safari's, so sign in once from the icon with the box ticked.
- **Safari limit:** on iPhones and Macs, Safari may clear what a site saved if it isn't opened for about a week.
- **Signing out:** **Sign out** (at the bottom of More) forgets the device's sign-in. Untick the box on a shared computer.

**Minimizing the app on a phone.** Phones pause web apps in the background, which drops the live connection. When you come back, the app reconnects by itself (a brief "Connecting…"). If the app restarted in the meantime, it signs you back in from the 30-day sign-in and opens the page you were on. If it stays stuck, pull down to reload.

**Seeing each other's changes.** Every tap and every page switch loads fresh data. The grocery list also refreshes itself every 10 seconds and the school run every 5 minutes. To see someone else's change straight away elsewhere, tap any page in the menu or reload.

**Adding people.**
- **Family members** (Settings) are the names in every "who" dropdown, such as adding Grandma as someone who can do pick-ups.
- **Logins** (Settings, admins only) are people who can sign in. They are separate, so someone can be assignable without having a login.

**Names.** The greeting, notes and "✓ done by" use each login's display name: Scoop for `dad@shamp.com`, Kate for `mom@shamp.com` (set by `sql/seed_budget.sql`). Admins can link any login to a family member in **Settings → Logins**, which also sets its name.

**What each login can see.** Admins (the emails in `ADMIN_EMAILS`) always see everything. For every other login, two switches in **Settings → Logins** control access, and both start off:
- **Money:** the Budget and Bills pages, income, and bill amounts on Today, Calendar and Week ahead.
- **Sensitive info:** household info (codes, Wi-Fi, insurance numbers) and the sitter sheet.

What's switched off is hidden from the menus and pages, and the app also refuses those actions on the server. Changes take effect the next time that person opens the app.

---

## Notes

- **Security.** Nothing loads until someone signs in with a login you created. The code lives in a private repo, and the secrets live only in Community Cloud's Secrets box and your own `secrets.toml`, never in git. Ask AI chats are stored per login and only shown to their owner; gratitude notes are shared with the family. Public sign-ups are off (step 5), and the database is closed to the public API (step 2). The saved sign-in is kept in each device's browser storage, works only once (each visit replaces it), and is forgotten after 30 days without a visit or when you sign out.
- **Time zone.** All dates and times use `APP_TZ` (default `America/New_York`). Community Cloud servers run on UTC, so the app sets this explicitly, including for the database session.
- **Community Cloud limits.** The free plan gives each app about 1 GB of memory, which is plenty for this app. Apps sleep after 12 hours without visits (see **Updating the app**). One private app is allowed per account.
- **Backups.** Your data lives in Supabase. On the free tier, you can take an export under **Database → Backups**, or with `pg_dump` against the session pooler.
- **Troubleshooting.**
  - *"Error running app" or a blank page after deploy:* open **Manage app** to read the log. If a secret is missing, the app says which ones instead of showing the sign-in page; paste the full secrets again under **Settings → Secrets**.
  - *Database connection fails on Community Cloud:* make sure `PG_HOST` is the **Session pooler** host and `PG_USER` includes `.your-project-ref`.
  - *Sign-in isn't remembered:* private browsing forgets saved sign-ins when the tab closes, and Safari may clear them after a week without a visit. Sign in again with the box ticked.
  - *Run the checks again:* `python check_setup.py` on your computer tests the same secrets and services the app uses.
