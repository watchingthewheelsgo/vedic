# Workshop Flow Review

## Current Findings

The workshop should help a user understand what is happening and what they need
to do next. The previous version exposed too much implementation detail: file
names, internal batch nodes, dependencies, and timing mechanics were presented
as if they were product concepts.

The intended user-facing flow is:

1. Confirm birth details and create one chart workspace.
2. Run a short birth-time plausibility check.
3. Ask the user to mark each anchor as accurate, inaccurate, or partly accurate.
4. Generate the full report in visible stages.
5. Show the finished report and allow export.

## What The User Should See

Users should see:

- The selected stage and its plain-language purpose.
- What the stage produces for the final reading.
- What action, if any, the user needs to take.
- Whether the stage is waiting, running, complete, or failed.
- A readable generated preview when a stage has user-facing content.

Users should not see by default:

- Internal artifact file names.
- Internal shard paths.
- Backend batch ids.
- Dependency lists.
- Raw node lists.

Those details are still useful for developer debugging, but they should live in
logs, dev tools, or a later explicit debug mode rather than the normal Workshop
experience.

## Data Isolation

Current behavior:

- Each session is persisted in its own server-side folder under
  `backend/data/sessions/<session_id>/`.
- Artifact writes use safe path resolution, so generated files cannot escape the
  session folder.
- Session ids now use `secrets`-based entropy rather than `random`.

This is still not sufficient for a public multi-user product. We should not ship
URL-only session access as the long-term isolation model.

Recommended account model:

- Add authenticated users.
- Store `user_id`/owner metadata for every session.
- Scope every session read/write/job API by authenticated owner.
- Keep support/admin access as an explicit audited role, not a fallback path.
- Keep anonymous/local development sessions only for development mode.

This version intentionally does not add a temporary browser token layer. A
partial token design would add complexity but still not answer the real product
need: account-level ownership.

## Cache And Acceleration

Yes, caching should be backend-owned.

Frontend localStorage can remember UI state, but it should not be treated as the
source of truth for report reuse, privacy, or acceleration. Backend cache is
where we can enforce ownership, invalidation, and observability.

Current acceleration already present:

- Within a single session, completed core artifacts are skipped when the core
  job sees those files already exist.
- Active core jobs are de-duplicated per session while they are queued/running.

Recommended backend cache layers:

1. Calculation cache
   - Key: normalized birth input plus calculator version, ayanamsa, ephemeris
     version, and place/timezone resolver version.
   - Value: deterministic `structured_data` calculation output.
   - Safe to reuse across sessions if privacy policy allows server-side storage
     of birth data; otherwise scope by account.

2. Account-scoped session resume
   - Key: `user_id` plus normalized birth input plus selected report mode.
   - Value: previous session id and stage status.
   - Lets the same user continue a prior workshop without relying on browser
     localStorage.

3. Report artifact cache
   - Key must include `user_id`, birth input fingerprint, prompt/skill version,
     model version, and feedback/context fingerprint.
   - Do not share full report artifacts across users by default because they can
     include personal feedback, concerns, and generated interpretation.

4. Job resume cache
   - Persist job state so a backend process restart can recover or mark
     incomplete nodes clearly.

## Code Changes In This Version

- `src/client/screens/Session.tsx`
  - Removes the top overview cards.
  - Rewrites stage details into user-facing `What you get` / `What to do`
    language.
  - Removes normal UI exposure of internal files, inputs, outputs, and node
    details.

- `src/client/components/PipelineFlow.tsx`
  - Renames graph stages from implementation labels to product-language labels.

- `backend/app/utils/ids.py`
  - Uses `secrets` instead of `random` for session id entropy.

## Remaining Work

- Add real account ownership before public multi-user launch.
- Move session resume and cache lookup into backend/account state.
- Add deterministic calculation cache after deciding privacy and retention
  policy for birth data.
- Add persisted job recovery for backend restarts.
