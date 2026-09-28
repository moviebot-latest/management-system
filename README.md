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


Database migration note: the app preserves existing PostgreSQL book data and adds missing ORM columns (including description and cover_url) when needed.

## V12 database fixes
- `user.id` is migrated to database column `user_id`; the legacy `employee_id` column is removed.
- Payment/return schema is upgraded in-place and payment foreign keys are checked.
- `audit_log` is created/upgraded and registration, login, issue, return/payment and additional-fine events are recorded.
- Existing member numeric IDs are preserved during the `id` -> `user_id` rename.
