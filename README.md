# Library Management System

Flask + SQLAlchemy + PostgreSQL/SQLite library project.

## Render
Build command: `pip install -r requirements.txt`
Start command: `gunicorn app:app`

Required environment variables:
- `DATABASE_URL` = PostgreSQL connection string
- `SECRET_KEY` = long random secret
- `ADMIN_USERNAME` = admin login username
- `ADMIN_PASSWORD` = admin login password
- `ADMIN_NAME` = optional admin display name
- `PGSSLMODE` = optional, defaults to `require`

## Roles
- Member: browse books, issue/return own books, change password. No community/member list.
- Librarian: manage books and issue/return for members.
- Admin: all librarian functions + member management and promote/demote librarian.

Registration intentionally has no Department field; new accounts are created as Library Members.
