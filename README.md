# Management System
Flask + PostgreSQL + GitHub + Render.

Features: Login, Registration, Admin Create User, Read, Update, Delete. Registration and Admin Create User are separate flows but use the same database.

Local: `pip install -r requirements.txt` then `python app.py`.
Render Build: `pip install -r requirements.txt`
Render Start: `gunicorn app:app`
Environment: `DATABASE_URL` and `SECRET_KEY`.
Demo admin: `admin` / `admin123`
