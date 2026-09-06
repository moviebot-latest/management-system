# Management System

Flask + PostgreSQL + GitHub + Render.

## Features
- Public self-registration from the login page
- Admin-only New User creation, editing and deletion
- Login
- User CRUD
- PostgreSQL database
- Password hashing
- Admin username/password stored only in Render Environment Variables

## Render Environment Variables
ADMIN_USERNAME=your-admin-username
ADMIN_PASSWORD=your-admin-password
SECRET_KEY=your-random-secret
DATABASE_URL=your-postgresql-connection-string

Admin credentials are read from environment variables and are not stored in the PostgreSQL users table. Normal user passwords are stored only as secure hashes.

## Render
Build Command: pip install -r requirements.txt
Start Command: gunicorn app:app
