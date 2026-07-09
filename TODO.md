# Vedic Runtime TODO

This list is based on the current repo state and focuses on making the product
better at using the vendored skills, scheduling long runs, showing progress, and
producing reliable user-facing reports.

## Landed in this pass

- Use repo-local `.claude/skills` as the default runtime source instead of a
  sibling `../vedic-astro-skills` checkout.
- Add missing vendored `agents/openai.yaml` metadata for calculator, reader,
  core, career, love, and rectifier skills.
- Make `vedic-calculator/scripts/setup_env.py` work with `uv` venvs that do not
  include a `bin/pip` executable.
- Add core job timing telemetry: job duration, wave duration, node duration, and
  a persisted `run_metrics.json` artifact.
- Show timing data in the UI while the full core report is running.

## P0: correctness and reproducibility

- Add an automated smoke test script for the real workflow:
  `create session -> run core job -> poll until complete -> verify public files`.
  It should record calculator time, each core wave time, each node time, and total
  report time.
- Add a non-LLM DAG test for `vedic-core` batches:
  verify unique IDs, valid dependencies, expected wave grouping, and expected
  public artifact composition.
- Add a local skills integrity check:
  verify each runtime skill has `SKILL.md`, required `resources/`, required
  `scripts/`, and `agents/openai.yaml` where expected.
- Decide how calculator dependencies are reproduced in fresh environments.
  Current setup uses the vendored `setup_env.py` after `uv sync`; a cleaner
  option is a first-class backend command such as `npm run backend:calculator-sync`.
- Persist job state outside process memory. A uvicorn reload or backend restart
  currently loses in-flight core job state.

## P0: chart rectification gaps

- Fix base-chart tie bias in candidate selection. The base candidate should not
  be confirmed when another candidate has comparable support; require a clear
  margin and sufficient candidate-bound evidence before allowing the full report.
- Add a strict artifact whitelist for `vedic-reader` output. The prompt says the
  reader should only write `reader_prevalidation.md`, but the backend currently
  accepts any returned artifact path.
- Enforce candidate-bound prevalidation anchors with structured validation:
  each high-risk anchor must include a machine-readable candidate ID, unstable
  field list, and user-facing claim that can actually discriminate between
  candidate charts.
- Add a real multi-round rectification loop. When the backend returns
  `needs_more_feedback` or `needs_candidate_bound_checks`, the UI/backend should
  generate the next round of narrower questions instead of leaving the session
  stalled.
- Replace fixed time sampling with adaptive narrowing inside the user's reported
  confidence window. Approximate or unknown times should progressively shrink
  the candidate range from user feedback rather than relying only on static
  samples.
- Tighten place rectification after a coordinate candidate is selected. A
  rectified coordinate should not inherit coarse city-level accuracy/radius, and
  timezone handling should be rechecked when the corrected coordinate materially
  differs from the original city center.
- Add regression tests for rectification gates: missing candidate machine lines,
  mixed candidate feedback, base-vs-non-base ties, non-base recalculation, and
  `reportAllowed` transitions.

## P0: skill execution quality

- Validate every generated public report file for non-placeholder content,
  required headings, and minimum evidence density before marking a node complete.
- Add output-specific QA rules for composed files:
  `p2a-p2d`, `p3a/p3b`, `p4a/p4b`, `p5a/p5b`, and `appendix`.
- Store the exact prompt sent to Claude Agent SDK for each node under an internal
  `.runtime/prompts/` folder for debugging and reproducibility.
- Capture LLM result metadata per node: SDK session ID, duration, cost if
  available, stop reason, model, and retry count.
- Compare vendored skills against their upstream source intentionally, with a
  documented update process instead of ad hoc copying.

## P1: scheduler and speed

- Make max concurrency configurable per environment and per skill. `10` is a
  useful local default but may be too high for provider rate limits.
- Add bounded retries for transient LLM failures, with node-level retry history
  shown in `run_metrics.json`.
- Add cancellation and pause/resume endpoints for long core jobs.
- Add ETA estimation from completed node timings and wave state.
- Skip or reuse validated node outputs when rerunning a report unless the input
  or prompt version changed.
- Consider model routing:
  smaller model for narrow audit shards, stronger model for synthesis blocks and
  appendix validation.

## P1: product interaction

- Replace raw skill names in primary controls with ordinary-user copy while
  preserving the exact skill workflow underneath.
- Render markdown as formatted report pages instead of only `<pre>` blocks.
- Add a dedicated report timeline:
  calculator, reader validation, core waves, final public files, optional
  career/love/synastry extensions.
- Add a public/private artifact filter. Users should see public report files by
  default; internal `.runtime` and diagnostics should stay hidden unless debug
  mode is enabled.
- Add a report export path: markdown bundle first, then PDF when the report
  format stabilizes.

## P1: customization and extensibility

- Introduce a skill registry instead of hard-coded skill action arrays in the
  UI and scattered prompt branches in `SkillRuntime`.
- Add typed skill descriptors:
  inputs, prerequisite artifacts, output artifacts, allowed tools, max turns,
  phase labels, and user-facing labels.
- Add user profile/context controls that write explicit, traceable context files
  instead of silently changing the astrology method.
- Support per-run intent:
  full report, focused question, relationship/synastry, career, love, rectifier.

## P2: architecture

- Split `SkillRuntime` into smaller services:
  `CorePlanBuilder`, `ArtifactComposer`, `SkillPromptBuilder`,
  `SkillResponseParser`, and `SkillRunService`.
- Move session artifacts and job metadata behind repository interfaces so the
  app can later switch from filesystem-only storage to database/object storage.
- Add OpenAPI/schema checks so frontend and backend types cannot drift.
- Add structured backend logging with request IDs, session IDs, job IDs, node IDs,
  and elapsed time.
- Add test fixtures for a tiny fake Agent SDK runtime so scheduler behavior can
  be tested without spending LLM time.

## P2: output polish

- Add a final report index page that links all public markdown files and includes
  generation time, input precision, and calculation metadata.
- Add a concise human summary generated only after all original skill files pass
  validation, clearly marked as a product layer.
- Improve Chinese copy in chat progress so ordinary users understand what is
  happening without needing to know `p2a`, `D9`, or internal skill names.
