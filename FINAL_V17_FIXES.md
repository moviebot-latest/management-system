# Final V17 Fixes

This build is based on the uploaded `Library_Management_System_FINAL_V16.zip`.

## Fixed
- Bulk PDF import no longer lets an audit-log error roll back the active SQLAlchemy transaction.
- Legacy `audit_log.username NOT NULL` schemas are supported; login/admin login now writes a real username.
- Audit logging uses its own database transaction, so audit failures cannot crash/rollback book creation, PDF import, return, payment, or registration.
- 30-book catalog import creates separate Book rows with unique `BK####` IDs.
- Bulk import creates a cropped PDF and cover image for each detected book when possible.
- Bulk import rolls back the database and removes uploaded storage objects if the whole import fails.
- Book deletion now works for books with completed issue/payment/return history. Active loans are still protected.
- Legacy `issue` table references are cleaned during book deletion when present.
- Stored book PDF/cover objects are deleted after a successful book deletion.
- A Flask 500 handler rolls back the current transaction and returns the user to the dashboard/login instead of leaving a generic error page.

## Data safety
No database reset, user reset, or book-table wipe is performed. Existing records are preserved and only required schema migrations are applied.

## Render
Keep the existing environment variables. For Neon Object Storage, the application accepts:
- `NEON_STORAGE_ENDPOINT`
- `NEON_STORAGE_ACCESS_KEY`
- `NEON_STORAGE_SECRET_KEY`
- `NEON_STORAGE_BUCKET=library-uploads`
- `NEON_STORAGE_REGION=us-east-2`

or the standard `AWS_*` equivalents already supported by the project.

After uploading this version to GitHub/Render, let the deployment complete and then test:
1. Admin login.
2. Add Book -> select the 30-book PDF -> Analyze.
3. Confirm `30 separate books detected`.
4. Press Save.
5. Confirm 30 separate Book records appear with different Book IDs.
6. Open Book List and delete a book with no active loan.
7. Check Render logs: there should be no `audit_log ... username ... null value` error.
