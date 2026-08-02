# Vedic Runtime TODO

This list tracks gaps in the active VedicDust pipeline. Retired chapter-based
reports and separate career/love report generators are intentionally excluded.

## Landed in this pass

- Use repo-local `.claude/skills` as the default runtime source instead of a
  sibling `../vedic-astro-skills` checkout.
- Add required `agents/openai.yaml` metadata for active runtime skills.
- Replace the retired skill-owned calculator setup with the backend-owned
  `scripts/setup-backend-runtime.py`, which bootstraps pip through the selected
  Python interpreter when a `uv` venv has no standalone `bin/pip` executable.
- Add core job timing telemetry: job duration, wave duration, node duration, and
  a persisted `run_metrics.json` artifact.
- Show timing data in the UI while the full core report is running.
- Lock Vimshottari to the declared mean-sidereal year, serialize exact MD/AD/PD
  boundaries with historical IANA offsets, and use half-open boundary semantics.
- Evaluate dated events as uncertainty intervals rather than invented midpoint
  instants; only Dasha levels stable across the interval can rank candidates.
- Sample the start, midpoint, and end of each reported event interval. Year-only
  events cannot add double-transit support, and month/day support requires the
  mapped activation to remain present at every sample.
- Localize every candidate birth moment before requesting its Vimshottari
  hierarchy, so a place hypothesis in another IANA zone cannot be scored with
  the original location's wall-clock fields.
- Treat unmatched event-map activations as neutral missing evidence rather than
  counter-evidence; deterministic contradictions now require actual contrary facts.
- Score each structured dated event once. Reader feedback is excluded from candidate
  scoring and cannot revise an event verdict.
- Fail the entire candidate comparison if any candidate calculation is incomplete,
  including coordinate timezone lookup failures.
- Preserve minute-grid transition uncertainty as overlapping Candidate Intervals
  and typed `SensitivityBoundary` records instead of reporting sampled minutes as
  exact boundaries.
- Require city/district place rectification and scan the declared geographic
  uncertainty radius without the previous 30 km clipping.
- Resolve civil time through one IANA-backed adapter. A duplicated DST wall time
  now returns the two real UTC occurrences to the UI, requires an explicit user
  choice, propagates that offset through Swiss Ephemeris/PyJHora and Chart Record,
  and scans fallback days in absolute time instead of truncating them to 24 hours.
- Split mixed provenance rules into narrow calculation contracts. Dignity and
  Panchadha Maitri now expose separate natural, temporary, and compound states;
  transit positions no longer share a rule with Sade Sati or double-transit
  interpretation; and combustion, directional strength, Vargottama, Chara Karaka,
  Arudha, lunar phase, Bhava Bala, special Lagnas, and Vargeeya Bala each have an
  independent rule ID.
- Preserve special sign dignity, Panchadha Maitri, and the downstream effective
  status as separate values instead of overwriting the compound relationship
  whenever a graha is exalted, debilitated, or in its own sign.
- Complete the narrow D1-D9 Vargottama equality surface for Lagna as well as the
  nine grahas, while keeping all strength and outcome interpretation behind a
  separate judgement permission.
- Close judgement restrictions over dependent facts: an unstable D1 Lagna now
  removes house lords, occupants, ownership, house SAV/Bhava Bala, Digbala,
  Arudha, house-target aspects, and Lagna-relative transit facts; an unstable
  varga Lagna removes that varga's complete house-dependent evidence surface.
- Carry D1 and divisional graha-structure changes from the sensitivity fingerprint
  into the LLM evidence contract. D9 structure changes now also suppress D1-D9
  Vargottama, Moon boundaries suppress Moon/Sade-Sati evidence, and unstable
  Nakshatra/Pada suppresses Vimshottari timing rather than only the Moon fact.
- Preserve sensitivity at fact granularity and Vimshottari boundary-envelope
  granularity in `vedicdust-chart-record/1.3.0`.
  Each fact now declares canonical dependency fields; the validator recomputes the
  grade, stable D1 graha facts survive Lagna-only boundaries, and interpretive-state
  changes in moon phase, combustion, Shadbala classification, Digbala, Arudha/Upapada,
  and special Lagnas split candidates and restrict only their dependent fact families.
- Carry birth-input stability into every Vimshottari period and recompute timing
  Claim confidence from the lower of Dasha-provider assurance and Moon/Dasha input
  stability. `d1Structure` is now a blocking rectification field rather than a
  guarded-report-only warning.
- Evaluate judgement and workflow rules only against the non-restricted evidence
  surface. Rule contexts and validator recomputation can no longer report a rule as
  eligible by matching a fact already removed by the sensitivity contract.
- Resolve rectification-question evidence from actual candidate signature differences.
  A `dNStructure` discriminator now cites the changed graha position facts and an
  unknown field no longer silently masquerades as D1 Lagna evidence.
- Split transit astronomy from natal-house mapping. `timing.transit.position` now
  contains only reproducible sidereal position/speed data, while the new
  `timing.transit.house` fact carries the Lagna-dependent whole-sign placement and
  is the only one suppressed by Lagna instability.
- Declare and enforce one apparent-geocentric planetary coordinate model across
  Swiss Ephemeris and every PyJHora adapter. The `parashari-lahiri-1.1.0` profile
  records the exact flags, and Chart Record quality gates now require D1 provider
  agreement within 0.5 arcseconds instead of checking zodiac signs only.
- Reject Swiss Ephemeris' silent Moshier fallback when retained `.se1` files do not
  cover the requested date, so a Chart Record cannot claim the profile's file-backed
  provider while consuming a different ephemeris implementation.
- Preserve supplied birth-time seconds through intake normalization, civil-time
  resolution, Swiss Ephemeris, every PyJHora adapter, sensitivity scans, event
  scoring, and the final Chart Record calculation. Omitted seconds remain `00`.
- When a selected rectification candidate is recalculated, preserve a UTC offset
  only for an explicitly selected DST fold. Ordinary and cross-zone corrections
  are resolved afresh by the selected IANA timezone.
- Separate derivation validation from judgement permission. Calculation rules only
  establish facts. SAV, dignity, Shadbala, and combustion now have independent
  capacity-judgement rules carried through Topic, Unit, Conclusion, and Claim
  provenance. All four remain provisional and `context_only`; directional use
  requires a separately validated judgement rule plus a validated derivation.
- Correct mean-node motion provenance: Rahu and Ketu now retain the same negative
  angular speed in both natal and transit snapshots. Transit facts also retain
  absolute longitude, degree, speed, and retrograde state instead of sign only.
- Remove unsourced 5/7/12-degree qualitative strength labels from same-sign and
  graha-drishti facts. The engine retains the exact sign contact and numerical
  degree separation without importing an undeclared orb policy.
- Include the primary 7K Chara Karaka role map in both full-chart and lightweight
  rectification fingerprints. A role change now creates an explicit unstable field
  and suppresses every dependent `karaka.chara` fact before LLM judgement.
- Withhold Chara Karaka roles that are tied at the Chart Record's six-decimal
  evidence precision, and expose the ambiguity as a calculation warning instead of
  resolving it through provider input order.
- Render sign-local positions with a shared non-overflowing degree formatter so
  near-boundary values cannot appear as the invalid coordinate `29°60'`.
- Record same-sign kendra-trikona lord associations as source-pinned Raja Yoga
  structure facts. Keep them context-only so the report cannot convert one
  structural combination into an automatic benefic promise or timed event.
- Record exact D1 house-lord exchanges as source-pinned Parivartana structure
  facts. Keep the exchange itself context-only; classification, strength,
  direction, and timing require narrower independently reviewed rules.
- Emit Gaja-Kesari only when every condition in the pinned lineage definition is
  present, evaluate Jupiter's enemy-house gate through the source-declared
  Panchadha Maitri compound relationship, route it through a dedicated context-only
  judgement rule, and prohibit automatic fame, wealth, status, magnitude, or timing
  claims.
- Use sampled Vimshottari start/end boundary ranges for consultation-horizon
  inclusion, current-period prioritization, and published timing scope; retain the
  canonical provider interval only as an auditable reference.
- Replace calculator-local varga descriptions with the source-pinned
  `vedicdust-varga-domain-policy/1.0.0`. Correct D4/D5/D30 scope drift, keep D60
  final-confirmation-only, and prevent education rectification from using D5.
- Require independent desktop snapshots to cover every supported non-D1 varga,
  not only D9/D10. Comparator contract fixtures remain explicitly non-independent;
  release certification still requires real external exports.
- Move consultation release status and quality checks out of the Agent-authored
  dossier and into deterministic backend gates for prerequisites, Claim accounting,
  and report structure.
- Validate every field of the future-Q&A Claim projection and stop treating
  report-level omissions as rejected astrological hypotheses.
- Fail candidate-event scoring when a consumed Lagna, Moon, Dasha-lord, or domain
  varga position is absent instead of silently defaulting or treating it as no match.
- Separate Moon-nakshatra timing restrictions from Moon-sign structural
  restrictions so stable house, conjunction, aspect, and Yoga facts remain usable.
- Reject malformed rectification option mappings and prevent blocked consultation
  dossiers from producing public manifests, rendered reports, or future-Q&A context.
- Enforce direction permission at the individual Finding, same-polarity method
  convergence, and final Judgement Context validation layers. Agent-facing rules now
  expose `context_only` / `directional` explicitly; opposing single methods cannot
  masquerade as convergence.
- Separate contextual chart structure from directional support throughout
  Judgement Conclusion, Claim Graph, report evidence, and future-Q&A context.
  Context-only associations and Yogas now use `contextFactIds` and cannot be
  mislabeled as affirmative support by the Agent.
- Keep rectification discriminator fields aligned with the declared varga-domain map
  and make event-score audit text describe the actual start/midpoint/end interval
  samples rather than an invented local-noon instant.
- Preserve the original full-window sensitivity scan as rectification evidence while
  writing a separate active-chart sensitivity contract after selected-interval recalculation;
  judgement now consumes the contract generated from the active canonical chart.
- Preserve intake focus and reader relationship in Chart Record, expose subject age,
  life stage, audience, and birth date in Agent Context, and render the subject frame
  plus true timing-window ages in the public report.
- Close model-authored report side channels. Dossier identity, section presentation,
  omission language, unresolved questions, visual references, and disclosure flags
  are backend projections; the Agent may only arrange approved Claims.
- Make rectification professional maturity evidence-backed. A record cannot claim
  independent professional validation without registered, hash-verified
  `professional_review` fixtures; internal records cannot carry those fixture IDs.

## P0: correctness and reproducibility

- [x] Add an authenticated smoke script for the real workflow:
      `create session -> structured event calibration/holdout when required ->
one scan-stable Reader quality check when applicable -> run core job ->
poll until complete -> verify public files`. It requires explicit fixture
      events and feedback instead of fabricating life history, records calculator,
      wave, node, and total timing, and rejects missing VedicDust or leaked
      `.runtime` artifacts.
- [x] Add a non-LLM DAG test for `vedic-core` batches that locks unique IDs,
      dependencies, wave grouping, selected skill, and the Agent-owned output contract.
- [x] Add a local skills integrity check for the active Vedic skill set. Every bundle
      now has matching `SKILL.md` frontmatter and `agents/openai.yaml` metadata; bundle
      resources/scripts remain optional unless the skill contract declares them.
- [x] Reproduce calculator dependencies through the backend-owned
      `backend/astrology-runtime.lock` and first-class
      `backend:calculator-sync` / `backend:calculator-check` commands. `uv.lock`
      remains responsible for the API environment; startup rejects calculation
      provider version drift and validates the fixed SAV runtime sample.
- [x] Persist core-job state outside process memory. Startup now restores durable
      terminal snapshots and converts interrupted `queued/running` jobs into an
      explicit retryable failure without silently reissuing paid Agent calls;
      completed artifact checkpoints remain available to the next explicit retry.

## P0: chart rectification gaps

- [x] Fix base-chart tie bias in candidate selection. The reported-time candidate
      cannot win when another candidate has comparable support; require a clear
      calibration margin and blind holdout pass before materialization.
- [x] Add a strict artifact whitelist for `vedic-reader` output. The prompt says the
      reader should only write `reader_prevalidation.md`, but the backend currently
      accepts any returned artifact path.
- [x] Retire candidate-bound Reader voting and its question/answer artifacts from the
      active runtime. New sessions select no candidate from Agent prose or a repeated
      confirmation of an already submitted event; old states can only migrate or stop.
- [x] Keep backend rectification state and bounded candidate plans auditable while
      making calibration ranking, holdout evaluation, and chart materialization
      deterministic backend responsibilities.
- [x] Narrow only within the exhaustive reported window. Candidate intervals are
      built before evidence scoring; a selected transition band may be refined,
      but Agent feedback cannot move or recreate the search space.
- [x] Add dated life-event input and backend event ledger. The initial consultation
      focus is stored separately as `readingFocus`; only the dedicated
      rectification stage can submit 3-5 dated events. The calculator writes those
      events into `birth_input_context.json.lifeEvents`, and
      `chart_rectification_state.json` exposes `lifeEventLedger` / `lifeEventFocus`
      for professional rectification anchors.
- [x] Stop fake one-candidate rectification. When the exhaustive bounded scan
      produces one stable chart fingerprint, retain the reported time interval and
      permit only scan-stable evidence instead of starting a reader round that has
      no competing chart to discriminate.
- [x] Prevent event-bound Reader anchors from masquerading as independent evidence.
      Structured life events are scored once by the backend; the reserved event is
      excluded from Agent context and evaluated only after calibration selection.
- [x] Add all-standard-varga sensitivity policy for `D1, D2, D3, D4, D5, D7,
D9, D10, D12, D16, D20, D24, D27, D30, D60`. The calculator now writes
      confidence, average lagna-slice sensitivity, changed-in-scan status, usage
      tier, and LLM primary-evidence restrictions. Candidate grouping uses
      rectification-relevant vargas without letting D60 noise explode the candidate
      set.
- [x] Stop obsolete Reader continuation loops. Reader now runs only for a
      scan-stable `not_required` chart; collecting, underdetermined, equivalent,
      failed, and corrected states follow backend-owned actions.
- [x] Add deterministic dasha/transit scoring for life events. Candidate ranking
      now records typed support and neutral missing observations for Dasha,
      relevant Varga lords, and double-transit activation. The contradiction channel
      remains reserved for a future source-pinned contrary rule; a positive-rule miss
      is not mislabeled as contrary evidence. Stable period lords can
      activate mapped D1 houses by ownership, occupancy, declared Parashari graha
      drishti, or natural-karaka role without double-counting correlated dimensions.
      Calibration events and the reserved holdout event are evaluated separately.
- [x] Scan every minute across the complete user-reported time window and coalesce
      contiguous equal fingerprints into bounded candidate intervals. Later rounds
      narrow these already-complete intervals instead of treating sparse samples as
      exhaustive.
- [x] Add optional sub-minute boundary refinement for the final surviving interval.
      After evidence selects a candidate, the runtime now narrows only its existing
      60-second chart-transition band to a bounded five-second interval. It stops on
      an intermediate fingerprint, does not refine Dasha-only transitions, excludes
      D60, and never publishes a discovered exact birth second.
- [x] Score each place candidate with its own coordinates and coordinate-derived
      timezone. A selected coordinate is recalculated as coordinate-level input and
      no longer inherits the original city radius.
- [x] Support DST-fold disambiguation end to end. Ordinary users see no offset
      field; the two earlier/later choices appear only when an IANA local time is
      duplicated, and the selected occurrence survives chart revision.
- [x] Add regression tests for deterministic rectification gates: incomplete candidate
      calculations, calibration ties and margins, holdout failure, selected-interval
      recalculation, unmaterializable selections, and `reportAllowed` transitions.

## P0: judgement and report quality

- [x] Require at least two independently eligible methods before publishing a
      supportive or challenging domain direction, with both validated derivation
      and validated interpretation permission. A lone SAV band remains descriptive
      rather than impersonating an integrated professional judgement.
- [x] Replace free-form validation fixture labels with a versioned fixture registry.
      Every referenced ID now names real pytest nodes and declares whether it is a
      contract, invariant, same-provider regression, independent external check, or
      professional review. Directional rules cannot be enabled with engineering
      tests alone; they require a registered professional-review fixture.
- [x] Remove rectification answer mapping and historical event-contrast parsing from
      the runtime. Candidate scores come exclusively from versioned calibration
      calculations and a blind holdout.
- [x] Remove circular event confirmation from candidate selection. A user answer to
      a restatement of an event they already submitted is not independent evidence.
      New sessions now rank candidates only from calibration-event calculations,
      reserve the final event for a blind backend check, and return underdetermined
      instead of using Reader prose to manufacture an extra vote.
- [x] Make professional-review fixtures auditable. A fixture label is no longer
      sufficient: directional release evidence must retain protocol, reviewer,
      timestamp, reviewed case IDs, a hash-verified source artifact, blind-review
      attestations, and hash-verified Chart Record, Claim Graph, and Dossier inputs.
      Failed assessments and publish/withhold mismatches now invalidate the fixture.
- [x] Require every active judgement rule, including provisional context-only
      domain synthesis and timing rules, to name an executable contract fixture.
      This closes the gap where a rule could reach runtime without regression
      evidence while preserving the separate professional-review requirement for
      future directional use.
- [x] Make `requiredEvidenceLayers` executable. Rule eligibility now derives the
      actually available, non-restricted fact layers and structured user testimony;
      a sensitivity gate that withholds timing also makes timing-dependent rules
      ineligible instead of leaving a misleading eligible audit record.
- [x] Close the missing-event runtime gap. Rectification collects three to five
      structured dated events, rejects duplicates, preserves explicit categories,
      reserves a score-blind holdout, requires calibration-domain breadth, and
      stops as underdetermined when deterministic evidence is insufficient.
- [x] Separate source-pinned structural method identities for house-lord placement,
      house occupancy, declared graha drishti, eligible varga confirmation, and
      same-sign/kendra-trikona association. They remain provisional and context-only;
      distinct provenance is not permission to publish direction.
- [x] Give natural-Karaka condition its own edition-pinned, context-only judgement
      method instead of attributing it to the broad domain integration rule.
- [x] Give dignity description and the anchor-lord dispositor path independent,
      edition-pinned method provenance without importing automatic good/bad labels.
- [x] Expose the Lagna-Sun-Moon D1 reference-point triad as an edition-pinned,
      fact-traceable foundation method without turning it into personality prose.
- [x] Separate calculation maturity from interpretation permission in runtime
      confidence: validated dignity facts are corroborated, provisional Bhava Bala
      stays provisional, and a validator blocks future provisional-rule overclaims.
- [x] Separate Varga calculation assurance from birth-input stability throughout
      Chart Record, deterministic judgement weighting, and Agent context. Internal
      PyJHora regression caps non-D1 calculation confidence at corroborated; exact
      external matches are recorded per chart without masking an unstable time window.
- [x] Separate report presentation policy from astrological judgement. Topic ordering,
      breadth, requested-topic timing, and coverage limits now use the versioned
      `vedicdust-presentation-selection/1.0.0` contract; every topic score exposes
      typed point contributions and supporting Fact IDs and is explicitly labelled
      presentation salience rather than strength, favourability, or life importance.
- [x] Make Claim Graph publication fail closed against the presentation policy. The
      validator now rejects non-ready Chart Records and rebuilds the complete graph
      to detect arbitrary claim insertion, deletion, renaming, reordering, omitted-topic
      drift, or quality-check drift instead of validating individual claims in isolation.
- Extend the source-pinned judgement corpus for directional dignity synthesis,
  narrower dispositor effects, and broader timing direction. These methods
  must remain context-only until each rule has a pinned source locator and professional
  fixtures.
- Add independent professional review fixtures for complete Chart Record ->
  Claim Graph -> Consultation Dossier outputs, including explicit disagreement
  cases and underdetermined outcomes. The executable artifact contract is implemented;
  real independent astrologer reviews and retained case artifacts are still absent.
- Populate a version-controlled representative JHora desktop golden corpus and run
  it as a release/CI certification gate. The loader and strict per-chart comparator
  now require D1 plus all fourteen supported non-D1 vargas, SAV, Shadbala, and
  a complete nine-lord Vimshottari Mahadasha cycle with timezone-aware boundaries.
  Registry entries must use a supported external system, retain
  an accessible source artifact whose SHA-256 is verified at load time, and record
  distinct normalizer/reviewer attestations. Exact-user lookup is only an optional
  diagnostic and cannot replace release-level coverage. Same-provider PyJHora tests
  and synthesized comparator fixtures still do not satisfy independent equivalence.
  The full-corpus command, machine-readable certification report, coverage policy,
  and strict `ci:certified` lane now exist; the real external corpus and its retained
  source artifacts are still required before that lane can pass.
- [x] Store the exact prompt sent to Claude Agent SDK for each node under an
      internal `.runtime/prompts/` folder, with a SHA-256 digest per attempt.
- [x] Capture LLM result metadata per node: SDK session ID, duration, cost if
      available, stop reason, actual configured model, and ordered retry attempts.
      These traces remain outside every public and internal artifact listing.
- Maintain VedicDust skills and rules as product-owned contracts. Upstream
  projects may inform gap analysis, but updates require an independent design,
  source review, and local validation rather than source copying.

## P1: scheduler and speed

- Make max concurrency configurable per environment and per skill. `10` is a
  useful local default but may be too high for provider rate limits.
- [x] Add bounded exponential-backoff retries for transient LLM failures. Timeout,
      connection/stream parsing, 429, overloaded, and provider 5xx failures are
      retryable; auth/config/permission and deterministic contract failures are
      not. Every provider attempt remains in the internal trace and node-level
      attempt/retry summaries are written to `run_metrics.json`.
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
  calculator, rectification, judgement, consultation dossier, final report, and
  optional synastry.
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
- Support per-run intent through requested topics in the same Claim Graph:
  full consultation, focused question, synastry, and rectification.

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
- Improve the deterministic consultation renderer with a concise executive
  synthesis after the Claim Graph and Dossier pass validation.
- Improve Chinese copy in chat progress so ordinary users understand what is
  happening without needing to know internal skill names or chart IDs.
