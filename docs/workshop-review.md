# Workshop Flow Review

## Current Findings

The workshop is useful for debugging, but the previous UI exposed too much of the
internal execution model to a normal user. File names such as
`structured_data.md`, internal shard paths, node dependencies, and batch timing
are valid implementation details, but they should not be the main explanation of
the product flow.

The user-facing flow should be:

1. Confirm birth details and create one private chart workspace.
2. Run a short birth-time plausibility check.
3. Ask the user to mark the anchors as accurate, inaccurate, or partly accurate.
4. Generate the full report in visible stages.
5. Show the finished report and allow export.

## What The User Should See

Users should always see:

- Current step and whether user input is required.
- Plain-language purpose for the selected stage.
- What result this stage produces for the report.
- Whether the system is waiting, running, complete, or failed.
- The final report preview/export when complete.

Users should see only on demand:

- Internal artifact names.
- Core batch node names.
- Dependency and timing details.
- Raw generated markdown excerpts.

These details are still useful for support and debugging, so the first version
keeps them behind a `Technical details` disclosure.

## Data Isolation

Before this change, sessions were already stored in separate directories:

```text
backend/data/sessions/<session_id>/
```

Artifact writes also use safe path resolution, so generated files cannot escape
their own session folder. However, the URL session id effectively acted as the
only bearer secret.

This version adds a lightweight session access token:

- New sessions get a token stored in `.meta/session.json`.
- The browser stores that token in `localStorage`.
- Session reads, skill runs, core job starts, core job polling, synastry subject
  creation, and feedback submission send `x-session-token`.
- Token-protected sessions reject requests without the matching token.
- Older sessions without metadata remain readable for local backward
  compatibility.

This is not a replacement for real accounts. For production multi-user use, the
next step should be authenticated users and server-side ownership checks.

## Cache And Acceleration

The safest cache is local resume, not shared report reuse. Full generated
reports may include user feedback and personal concerns, so cross-user reuse is
not safe by default.

This version adds:

- Same-browser resume by birth-input fingerprint.
- A cached workshop prompt on the intake page.
- `Start fresh` for users who want a new run.
- Reuse of the backend's existing same-session artifact skip behavior.

The backend already skips completed core artifacts inside the same session. This
means a resumed session can avoid regenerating stages that are already present.

## Code Changes

- `src/client/screens/Session.tsx`
  - Adds a top workshop overview with current action, data isolation, and speed
    behavior.
  - Rewrites stage copy into user-facing language.
  - Moves internal files and node lists into `Technical details`.

- `src/client/components/PipelineFlow.tsx`
  - Renames graph stages from implementation labels to product-language labels.

- `src/client/lib/sessionAccess.ts`
  - Adds local resume cache and session token storage.

- `src/client/screens/Intake.tsx`
  - Reuses matching same-browser sessions by default.
  - Provides a `Start fresh` option.

- `src/client/api.ts`
  - Sends `x-session-token` for session-scoped requests.

- `backend/app/services/skill_workspace.py`
  - Creates and validates per-session access tokens.

- `backend/app/main.py`
  - Enforces token validation on session-scoped API routes.

- `backend/app/utils/ids.py`
  - Uses `secrets` instead of `random` for session id entropy.

## Remaining Production Gaps

- Add real user accounts and ownership checks before public multi-tenant launch.
- Move local resume cache into account-scoped server persistence after login.
- Add a deterministic calculation cache for `structured_data` only; do not share
  complete report artifacts unless the cache key includes user feedback scope
  and explicit privacy policy decisions.
- Add a server-side job resume endpoint for completed or failed jobs after
  backend process restart.
