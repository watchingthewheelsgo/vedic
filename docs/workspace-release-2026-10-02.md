# Sign Atlas workspace release

## Product shape

Visitors enter the public website; authenticated users enter `/app`. `/welcome` always shows the public website. A validated `returnTo` preserves a protected deep link through sign-in. Existing `/daily`, `/new`, `/bazi`, `/account`, and `/session/:id` links redirect to their new workspace destinations. Signing out returns to the website.

The shared desktop sidebar / mobile bottom navigation contains Today, Journal, Explore, and My charts. Account and billing are settings, not a competing dashboard. Vedic intake, BaZi preview, and report reading live inside the same shell. Public website copy introduces the journal → reflection → revisit loop.

| Before                                           | After                                                                                   | Why                                                        |
| ------------------------------------------------ | --------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Independent Daily, account and report pages      | Shared app shell and contextual navigation                                              | Keep orientation across features                           |
| All capabilities on a long Daily page            | Today for capture; Journal for history and statistics; Explore for contextual questions | Each view has one primary task                             |
| Re-enter context when asking questions           | A dated record opens Explore with its saved content, answers and chart association      | Preserve the connection to real life                       |
| Advice ends at generated text                    | Persist planned/done action states per reflection and perspective                       | Allow follow-through and later review                      |
| Each page repeats its own top navigation         | One header; report keeps only its own reading controls                                  | Reduce duplicated controls                                 |
| Anonymous reading and invalid-token fallback     | Verified users required on all product APIs, including place lookup                     | Private content has a stable owner                         |
| Legacy anonymous IDs automatically claim reports | No client-header ownership transfer; existing data retained                             | Avoid reintroducing guest ownership through legacy clients |

## Scope and release review

This release includes the previously deployed personal-journal module, associated migration, branding/UI improvements, and VPS deployment support, which had not yet been committed. Existing uncommitted changes to `core_job_runtime.py`, `skill_runtime.py`, `test_core_job_runtime.py`, and `test_consultation_runtime.py` are excluded and retained locally. Two existing local commits preceding this release contain consultation-context corrections; their boundary/contract tests are included in validation.

The release crosses authentication, persisted JSON state and UI routes. It is a large change under review-and-ship defaults. The user explicitly requested this reviewed workspace design be implemented, pushed and deployed; delivery follows that authorization with focused auth/data tests, build checks, clean-source validation, a database backup and post-deployment verification. No payment prices or account entitlements change.

## Data and privacy

The existing `journal_entries` table persists records. `reflections[].actionStates` is an optional backward-compatible JSON field; older entries require no rewrite. Owner checks and a row lock guard action updates. No journal content is placed into browser local storage. Leaving via workspace links or account menu prompts when a record is unsaved; browser unload also warns. The app does not promise recovery after a browser crash.

Existing anonymous reports are retained on disk/database. Their automated client-side claim is intentionally disabled; any future recovery must verify ownership separately. Production Clerk authentication remains enabled. Local explicitly disabled-auth development behavior is unchanged.

Daily BaZi is a civil-date calendar association, not a natal favorable-element calculation. Tarot uses 22 upright major arcana. A selected owned Vedic chart provides evidence; absent a chart, the UI says the reflection is general. Actions are optional reflective suggestions.

## Validation boundaries

Relevant auth HTTP tests cover anonymous and expired bearer rejection, daily record ownership, old-header non-claim, redirect validation, reflection persistence and action-state ownership. Clean release-source tests include the existing consultation-context commits. Production build and browser desktop/mobile checks are required before considering the release complete. Full paid report generation, payment and every chart algorithm are separate acceptance paths.

Use `bash scripts/production/update-vps.sh` in the clean VPS checkout for subsequent pull/build/backup/migrate/health-checked updates. The release records image tag and previous tag under `.deploy`. Migration rollback is not destructive; application rollback retains journal data.

## Pre-release results

Clean selected release source: 278 backend tests passed (auth, journal/action ownership, migrations, workspace boundaries, chart input sensitivity, evidence contracts and core job runtime). Frontend: 9 tests passed, TypeScript + production build passed, ESLint 0 errors / 8 pre-existing Fast Refresh warnings. Deployment script bash syntax and git diff whitespace checks passed.

The full commit hook also exposed a pre-existing billing test with a hardcoded subscription end date that has expired. Its already-reviewed test-only fix uses relative dates and covers both active and expired subscriptions; it is included without changing billing behavior. Untracked consultation-runtime tests belong to the excluded runtime changes, so they are preserved separately while the commit hook validates the actual release source.
