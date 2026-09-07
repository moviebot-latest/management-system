# Management System

Flask + PostgreSQL + GitHub + Render.

## Features
- Separate registration and admin Create User
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


## Database connection stability
For Render PostgreSQL, the app now uses SQLAlchemy connection health checks, connection recycling, TCP keepalives, and one automatic reconnect/retry when a stale SSL connection is detected.

Optional Render environment variable:
`PGSSLMODE=require`

## Dashboard
Admin dashboard now shows live:
- Total Users
- Active Users (all registered users; this version has no inactive status field)
- Today's Registrations
- Departments
- Last 7 days registration trend

The registration form validates password confirmation in the browser and the server validates it again.
