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
adminpanel/   WedSync's own user management (replaces Django admin)
core/         landing page, error pages, shared template tags and fields
templates/    Django templates (layouts, partials, icons, pages)
static/       design system CSS, logo, scripts
```

## Git workflow

The first commit is on `main`. Each feature is built on its own branch, opened as a pull request and merged into `main`.
