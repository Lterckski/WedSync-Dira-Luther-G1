# WedSync

**All-in-one wedding planning and day-of coordination platform** for couples, coordinators and vendors.

CSIT327-G1 · Information Management 2 · Dira, Luther Derrick E.

## Stack

| Layer | Technology |
| --- | --- |
| Backend and frontend | Django 5.2 with Django templates |
| Database | PostgreSQL (local, Render or Supabase). SQLite is not used. |
| Styling | The WedSync design system: plain CSS tokens and `ws-` component classes |
| Hosting | Render |

## Run it locally

Requirements: Python 3.12+ and a PostgreSQL database.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then set SECRET_KEY and DATABASE_URL
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000.

## Project layout

```
config/       settings, URLs, WSGI
accounts/     the users table (SDD 4.4) and authentication
core/         landing page
templates/    Django templates (base layout, partials, icons)
static/       design system CSS, logo, scripts
```
