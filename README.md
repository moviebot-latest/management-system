# Library Management System

Flask + PostgreSQL/SQLite Library Management System.

## Roles
- Admin: full control, users, books, issue/return, role promotion/demotion.
- Librarian: book management and issue/return.
- Member: view/search books and own issue history.

## Features
- Member registration (Department removed)
- User/Member CRUD
- Admin promotion/demotion: Member <-> Librarian
- Book CRUD
- Book search
- Issue/Return
- Due dates and late fine calculation (₹5/day)
- Dashboard statistics
- Password hashing, CSRF, secure cookies and security headers
- Existing PostgreSQL database compatibility: old `role` column is added automatically.

## Environment Variables
SECRET_KEY=your-random-secret
DATABASE_URL=your-postgresql-connection-string
ADMIN_USERNAME=your-admin-username
ADMIN_PASSWORD=your-admin-password
ADMIN_NAME=Admin
PGSSLMODE=require

## Render
Build Command: pip install -r requirements.txt
Start Command: gunicorn app:app

## Vercel
The Flask app can be deployed with a Vercel Python/Flask configuration if your Vercel project is configured for Flask. For persistent production data, use PostgreSQL rather than the default SQLite database.
