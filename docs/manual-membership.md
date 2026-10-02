# Free access and manual upgrades

Records, moods, deterministic calendar facts, basic history, saved conversations and PDF exports are free for the owner. Evidence collection uses deterministic wording and does not spend credits. New AI generation reserves credits on the server before starting:

| Operation                                             | Credits |
| ----------------------------------------------------- | ------- |
| Journal reflection (all three perspectives together)  | 1       |
| Short reading or follow-up question                   | 1       |
| Complete Vedic report, including its internal batches | 10      |

Free accounts receive 10 credits per UTC calendar month. Unused credits do not roll over. Memberships normally provide 100 credits per month; approval can set a different limit. Existing usage counts toward the new limit when upgraded mid-month. At expiry the account returns to its free limit without deleting records. Administrators are exempt.

These are product credits, not a claim that every request has equal token or dollar cost. Existing provider execution traces remain the source for available model-cost data.

Credits are reserved atomically in SQL, settled on success and returned on failure/cancellation. Background report jobs reserve once per job; duplicate starts reuse the running job. Durable terminal job records reconcile unsettled usage after restart. Orphaned synchronous reservations are returned after 24 hours when the allowance is next read. A retry after a completed request may be a new paid generation; journal request IDs replay the saved result without another charge.

The public checkout API returns 409; old Creem configuration does not activate checkout or grant AI membership. Existing provider callbacks remain available for reconciliation, but manual memberships are the only paid AI allowance source in this release.

## Upgrade request

A floating feedback button is available on the website and workspace. Users submit a message and an email or other contact directly on the site. Settings → Request an upgrade opens the same window with Upgrade selected; upgrades require login. Feedback never automatically includes journals or chart contents. Request IDs make retries idempotent, and a durable rate limit allows five submissions per sender per UTC hour.

Every accepted request is saved in the `feedback` table. No email service is used or needed. Administrators can read and resolve the latest 100 requests at `/admin/feedback` (also linked from Settings). No submission automatically grants membership.

The admin page uses the existing Clerk sign-in. Both list and update APIs independently require an authenticated Clerk administrator; ordinary accounts cannot access feedback even by calling the API directly. The `app_users.role` database field is the sole authority: new users receive `user`, and only `admin` grants administrator access. Environment allowlists and Clerk metadata do not grant this role. Each authenticated request reloads the database role, so revocation does not require signing out or restarting the server. Client-side flags and request payloads cannot grant admin access. Authentication-disabled development identities cannot access these feedback admin APIs.

- `GET /api/admin/feedback`: list feedback, contact details, account and processing status.
- `PATCH /api/admin/feedback/{id}` with `{"status":"resolved"}` or `{"status":"open"}`: mark handled or reopen.
- `POST /api/feedback`: submit feedback; membership requests require sign-in.

## Manual approval

Verify the requester owns the account and agree the plan before approving. On the server, after running migrations, use the backend environment:

```sh
python scripts/grant-membership.py --user-id user_VERIFIED_ID --days 30 --monthly-limit 100 --note "Approval reference"
```

The script requires an existing app user, replaces the membership's expiry with now + days, and records an approval note. It does not reset this month's usage, extend an existing expiry cumulatively, charge a payment method, or send mail. Do not include financial secrets or journal content in the note. Refresh Settings to verify the new limit and expiry.

## Release

Run Alembic to revision `7d931ab82c40` before starting the updated API. The migration adds `ai_allowances`, `ai_usage` `manual_memberships`, `feedback` and `feedback_rate_limits` without changing existing records. Ship backend and frontend together so costs and remaining credits are visible. Existing authenticated ownership checks remain required for every reading and export.

## Administrator role

Have the account sign in once so its `app_users` row exists. Using a trusted database connection, verify the exact `clerk_user_id`, then run:

```sql
UPDATE app_users SET role = 'admin' WHERE clerk_user_id = 'user_REPLACE_WITH_VERIFIED_ID';
```

Verify exactly one row was updated. To revoke access set `role = 'user'` instead. Existing database roles are preserved; no role is automatically promoted from an old environment allowlist. There is no public role-editing API.

## Admin membership controls

At `/admin/feedback`, query a verified Clerk user ID or select “管理此用户会员” on a signed-in user's feedback. Grant defaults to 30 days and 100 monthly credits; days (1–366), monthly limit (10–10000) and a required note are editable. Renew extends an active expiry, or starts from now for an expired account. Revoke takes effect immediately and preserves existing content and usage. Administrator quota exemptions are independent of membership status.

The API checks the database-derived administrator role. Each action and its before/after values are stored atomically in `membership_audit` with the actor and timestamp. Retried requests reuse a UUID to prevent duplicate renewals. Changes to the same account serialize in SQL. The page shows the latest 20 admin operations. The legacy CLI is a separate maintenance path and does not produce these admin-page audit entries; use the page for routine changes.
