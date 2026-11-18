# WedSync

**All-in-one wedding planning and day-of coordination platform** for couples, coordinators and vendors.

CSIT327-G1 · Information Management 2 · Dira, Luther Derrick E.

## Stack

| Layer | Technology |
| --- | --- |
| Backend and frontend | Django 5.2 with Django templates (full-stack Django) |
| Database | PostgreSQL (local, Render or Supabase). SQLite is not supported. |
| Styling | The WedSync design system: CSS tokens and `ws-` component classes, a little vanilla JavaScript |
| Hosting | Render |

## Phase 1 — Account Feature

| Requirement | How WedSync does it |
| --- | --- |
| Registration | `/accounts/register/` — full name, email, contact number (optional), role, password and confirmation. Required fields, email format, unique email (case-insensitive), matching passwords and Django's password rules are all checked, with an error under each field and a message at the top. |
| Hashed passwords | Django's built-in authentication stores a salted PBKDF2 hash in `users.password_hash`. Plain-text passwords are never stored. |
| Login / logout | `/accounts/login/` uses the email as the username. Wrong credentials show an error; deactivated accounts get their own message. Logout is a POST button that ends the session. |
| Protected pages | Every dashboard, profile and admin page requires login; logged-out visitors are sent to the login page and returned afterwards. Pages are marked no-store so the Back button can't show them after logout. |
| Role-based dashboards | Roles: **Couple**, **Coordinator**, **Vendor**, plus **Administrator** for user management. After login each user lands on their own dashboard with its own content and navigation. Opening another role's dashboard URL returns a 403 page. |
| User profile | `/accounts/profile/` shows the signed-in user's own details; `/accounts/profile/edit/` updates name, email and contact number; `/accounts/profile/password/` changes the password. There's no user id in these URLs, so nobody can open someone else's profile. |
| Own admin panel | Django's built-in admin is **not installed**. Administrators use `/manage/`: account counts by role, a searchable and filterable user list, create accounts with any role, edit details and roles, deactivate or reactivate, and set a new password. Administrators can't deactivate or demote themselves. |

### Database

The `users` table matches the SDD data dictionary (section 4.4) column for column:
`user_id`, `email` (UNIQUE), `password_hash`, `full_name`, `phone` (NULL), `role` (CHECK), `is_active` (DEFAULT TRUE), `created_at` (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP).

One addition to the SDD: the `role` CHECK also allows `'ADMIN'`, for the user-management panel the project requires.
Django's own framework tables (sessions, content types, auth permissions) sit alongside it.

## Phase 2 — Wedding Workspace and Budget & Expense Tracker

The core feature is **F-03, the Budget & Expense Tracker**. It works per wedding, so it is built on **F-02, the Wedding Workspace**.

### Wedding workspace (F-02)

| Requirement | How WedSync does it |
| --- | --- |
| Create a wedding | Couples use `/weddings/new/`: title, date, venue (optional) and the budget currency. The creator becomes the wedding's first **Couple** member. A couple account belongs to one wedding only. |
| Event code | Every wedding gets an 8-character code of uppercase letters and digits, without the look-alikes 0, O, 1 and I. The couple sees it on the wedding page and dashboard with a **Copy code** button, and can make a new one; the old code stops working at once. |
| Join a wedding | The partner (Couple) and coordinators type the code on their dashboard or at `/weddings/join/`. Any case and spaces are accepted. Joining twice, or a couple joining a second wedding, is refused with a clear message. Vendors and administrators can't join by code (vendors join through contracts in a later phase). |
| Manage the wedding | The couple edits the title, date, venue and status (Planning, Completed, Cancelled). The currency is fixed once the wedding exists (BR-04). Deleting asks for confirmation and is blocked while the wedding has budget categories; the message suggests status Cancelled instead. |
| Members | Every member sees the member list. The couple can remove a coordinator; a coordinator can leave. Both ask for confirmation first. |
| Privacy | A wedding page for a wedding you don't belong to returns 404, so wedding ids reveal nothing. |
| Dashboards | Couple: "Create your wedding" and "Join with an event code", or the wedding card with its event code. Coordinator: a join form and the list of their weddings (title, date, couple names, status) to switch between them. Vendor: unchanged. |

### Budget & Expense Tracker (F-03)

| Requirement | How WedSync does it |
| --- | --- |
| Budget overview | `/weddings/<id>/budget/` shows Total allocated, Total spent and Remaining, then a table of categories with allocated, spent, remaining, % used and a progress bar. Categories where spent is more than allocated are marked **Over budget**. Inactive categories are listed separately and still count in the totals. Amounts use the wedding's currency, e.g. "PHP 12,500.00". |
| Categories | Name (unique per wedding, ignoring letter case) and allocated amount (0 or more, BR-05). Couples and coordinators add categories; only the couple edits, deactivates, reactivates or deletes them. A category with expenses can't be deleted — it can be deactivated instead (BR-07). |
| Expenses | Description, category, amount (more than 0, BR-06) and date (defaults to today, never in the future). Only active categories of the same wedding can be chosen; an expense being edited keeps its category even if that category was deactivated. The list is newest first, filterable by category and paginated at 20. |
| Over-budget warning | An expense that takes a category past its allocation is still saved, with a warning such as "Catering is now PHP 2,500.00 over budget." |
| Validation | Every form shows an error under the field and a message at the top. Amounts allow up to 2 decimal places and at most 9,999,999,999.99, and may be typed with thousands separators. |
| Totals | Calculated by PostgreSQL with `SUM` and subqueries, never row by row. The overview uses the same number of queries however many categories there are. |
| Dashboards | Couple: a budget card (allocated, spent, remaining, categories over budget) with Open budget, Add expense and Add category. Coordinator: the same figures for each wedding in their list. Vendors and administrators see no budget links. |

### Who can do what

The wedding role is the member's `wedding_members.member_role` for the wedding being viewed. Every rule is checked on the server for both GET and POST; hidden buttons are only a convenience.

| Action | Couple | Coordinator | Vendor / Admin |
| --- | --- | --- | --- |
| View budget overview and expenses | Yes | Yes | No (403) |
| Create a category | Yes | Yes | No (403) |
| Edit, deactivate, reactivate or delete a category | Yes | No (403) | No (403) |
| Create an expense | Yes | Yes | No (403) |
| Edit or delete an expense | All expenses | Only ones they recorded | No (403) |
| Edit or delete the wedding, change its event code | Yes | No (403) | — |
| Remove a coordinator / leave the wedding | Remove | Leave | — |

Logged-out visitors are sent to the login page. Anyone who isn't a member of the wedding gets a 404. Every delete goes through a confirmation page and is POST-only, and every form has CSRF protection.

### Database

The four new tables follow the SDD data dictionary (section 4.4). CHECK and UNIQUE constraints are named, so they exist in PostgreSQL itself. Money is `NUMERIC(12,2)`, never a float.

| Table | Columns |
| --- | --- |
| `weddings` | `wedding_id`, `title` VARCHAR(150), `event_code` VARCHAR(8) UNIQUE, `wedding_date` DATE, `venue` VARCHAR(255) NULL, `base_currency` CHAR(3) DEFAULT 'PHP', `status` CHECK (PLANNING, COMPLETED, CANCELLED) DEFAULT 'PLANNING', `created_at` |
| `wedding_members` | `wedding_member_id`, `wedding_id` → weddings ON DELETE CASCADE, `user_id` → users ON DELETE CASCADE, `member_role` CHECK (COUPLE, COORDINATOR, VENDOR), `joined_at`, UNIQUE (`wedding_id`, `user_id`) (BR-03) |
| `budget_categories` | `category_id`, `wedding_id` → weddings ON DELETE RESTRICT, `name` VARCHAR(100), `allocated_amount` NUMERIC(12,2) CHECK ≥ 0, `is_active` DEFAULT TRUE, `created_at`, UNIQUE (`wedding_id`, `name`) |
| `expenses` | `expense_id`, `category_id` → budget_categories ON DELETE RESTRICT, `recorded_by` → users ON DELETE RESTRICT, `description` VARCHAR(255), `amount` NUMERIC(12,2) CHECK > 0, `expense_date` DATE DEFAULT CURRENT_DATE, `created_at` |

Django's `on_delete` only runs in Python, so a migration in each app (`0002_…_on_delete_rules`) sets every foreign key's ON DELETE rule in PostgreSQL too. A delete run outside the app (psql, the Supabase dashboard) is refused or cascaded exactly as the app would.

Additions to SDD 4.4, made on purpose:

- **`weddings.event_code`** is a new column. It is how a partner or coordinator joins a wedding; the SDD will be updated to include it.
- `weddings_event_code_check` keeps codes to the 8-character format.
- A partial unique index (`wedding_members_one_couple_wedding`) enforces "a couple account belongs to one wedding" in the database.
- A unique index on (`wedding_id`, `LOWER(name)`) makes "Catering" and "catering" the same category at the database level.

### How to use it

1. **Couple:** register, then choose **Create your wedding** on the dashboard. Copy the event code from the wedding card and send it to your partner and coordinator.
2. **Partner and coordinator:** register, type the event code in **Join** on the dashboard.
3. Open **Budget** in the navigation bar. Add categories (Venue, Catering, Photography…) with the amount set aside for each.
4. Record each payment with **Add expense**. The overview shows what's left per category and in total, and flags anything over budget.
5. When a category is no longer needed, **Deactivate** it. Its expenses stay in the totals; reactivate it any time.

## Run it locally

Requirements: Python 3.12+ and PostgreSQL.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then set SECRET_KEY and DATABASE_URL
python manage.py migrate
python manage.py ensure_admin      # creates the first administrator (asks for email and password)
python manage.py runserver
```

Open http://127.0.0.1:8000. Register as a couple, coordinator or vendor, or log in as the administrator.

### Tests

```bash
python manage.py test
```

The suite runs against PostgreSQL and covers the schema, registration validation, login and logout, role-based access for every role, the profile pages and the admin panel.
Phase 2 adds tests for the wedding and budget tables (CHECK, UNIQUE and ON DELETE rules checked in the database), every validation rule, every view as a logged-out visitor, non-member, couple, coordinator, vendor and administrator, and a full create → read → update → delete flow.

Tests use a separate `test_<database name>` database that Django creates and drops; the real data is never touched. With Supabase's Session pooler, `core/test_runner.py` drops that test database with `DROP DATABASE … WITH (FORCE)`, because the pooler keeps a connection to it open. Run one test command at a time: two runs at once share the same test database.

## Deploy to Render

The repository includes `render.yaml` (a Render Blueprint) and `build.sh`.

1. In Render, choose **New → Blueprint** and select this repository. Render creates the PostgreSQL database and the web service.
2. When asked, fill in `ADMIN_EMAIL`, `ADMIN_PASSWORD` and `ADMIN_FULL_NAME`. The build step creates that administrator once; later deploys leave it alone.
3. Deploy. `build.sh` installs requirements, collects static files, runs migrations and creates the administrator.

**Using Supabase instead of Render's database:** set `DATABASE_URL` to Supabase's *Session pooler* connection string (it works over IPv4) and set `DATABASE_SSL_REQUIRE=True`. Render's free PostgreSQL databases expire after a limited time, so Supabase is the longer-lived option.

## Project layout

```
config/       settings, URLs, WSGI
accounts/     users table (SDD 4.4), registration, login/logout, profile, role checks
dashboards/   couple, coordinator and vendor dashboards
weddings/     weddings and wedding_members tables, event codes, membership checks (F-02)
budget/       budget_categories and expenses tables, budget overview and expense log (F-03)
adminpanel/   WedSync's own user management (replaces Django admin)
core/         landing page, error pages, shared template tags, fields, money formatting, test runner
templates/    Django templates (layouts, partials, icons, pages)
static/       design system CSS, logo, scripts
```

## Git workflow

- `main` holds stable releases only; nothing is committed to it directly.
- `develop` is the integration branch, created from `main`.
- Each feature gets its own `feature/<name>` branch from an up-to-date `develop` (Phase 2: `feature/wedding-workspace`, then `feature/budget-tracker`; documentation in `docs/phase2-readme`).
- A finished branch is merged into `develop` through a pull request. At the end of a phase, a pull request merges `develop` into `main`.
- Merged branches are kept, and `.env` is never committed.

Phase 1 was merged into `main` directly through feature pull requests, before `develop` existed.
