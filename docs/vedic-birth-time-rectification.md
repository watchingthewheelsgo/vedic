# Vedic Birth-Time Rectification

This document describes the active backend-owned rectification mechanism after
reported civil time and place have been canonicalized.

## Release principle

Rectification may narrow only the user's explicit reported time window. A
city/district envelope is sampled only to detect place sensitivity; life events
cannot select a coordinate. The workflow returns a bounded interval, equivalent intervals, or an
explicit underdetermined result. It never publishes an invented exact second.

The Reader Agent does not rank candidates. Confirming an event already supplied
by the user is not independent evidence and cannot change a chart score.

## Active flow

1. Canonicalize the reported local time with IANA historical timezone rules and
   resolve the place to WGS84 coordinates.
2. Calculate the base Chart Record and scan every minute of the complete allowed
   time window. Scan the place axis only when the location remains city-level or
   otherwise uncertain. Joint time/place probes measure whether geographic
   uncertainty moves a chart boundary; they never enter candidate ranking.
3. Coalesce contiguous equal, evidence-addressable fingerprints into bounded
   candidate intervals. Only fields with an active dated-event rule can split a
   candidate; every other chart change remains in the report-stability scan.
4. If one fingerprint is stable across the full window, retain the complete
   reported interval. The state is `not_required`; an optional Reader pass may
   ask 1-5 neutral reading-quality questions using only scan-stable facts.
5. If multiple material candidates remain, stop report synthesis and collect
   4-5 independent, dated life episodes. The UI asks for one event per round; after
   each accepted answer the backend recalculates the bounded candidate state and
   issues the next deterministic question. Each round records the answered event,
   score spread across candidate classes, before/after leader margin, remaining
   blockers, and the backend-owned next action. Consultation focus is never evidence.
6. Split eligible events without looking at candidate scores. The first event fixes a
   Life Episode's primary interval; later events overlapping that primary remain
   corroborating context, so one real-world period cannot vote twice or retroactively
   move calibration and holdout roles.
   As soon as the third independent episode exists it is reserved as a stable blind
   holdout; release still requires three other calibration episodes. The interview
   prefers a third life domain when the user has one and permits a repeated domain
   only when that is the available factual evidence. Later answers cannot
   retroactively move an event from calibration into holdout. The Agent
   never receives holdout content, candidate identities, scores, or chart values.
   The backend selects the next category from its private discrimination ranking.
   The Agent may rewrite only that one selected question and cannot switch to a
   lower-ranked pool item.
7. Score each candidate from calibration events only. The current versioned
   policy records Dasha activation, relevant Varga domain activation, and stable
   Jupiter/Saturn double-transit support. Missing positive support is neutral,
   not fabricated contradiction evidence.
8. Select only when every candidate has the same calibration episode set, at least
   three calibration episodes cover at least two mapped life domains, at least two
   calibration episodes each have support from two of Dasha, relevant Varga, and
   double-transit methods, and the leader clears the declared score and margin.
   A material disagreement from the independent Chara Dasha comparison blocks selection.
   This comparison uses a Vimshottari-only calibration score against diagnostic
   Chara Dasha across distinct candidate equivalence classes; the aggregate
   varga/transit score is excluded from the independence check. Its scan-level result
   is copied to every candidate so the release gate cannot inspect a different leader.
9. Evaluate the selected candidate or equivalence class against the reserved
   event. The holdout must itself converge across at least two primary methods.
   A failed or inconclusive holdout returns `underdetermined`.
10. Every passed candidate is recalculated once at its bounded representative
    time and the user-confirmed place and enters `rectification_confirmation_required`, including when
    the selected interval contains the user's reported time. The system shows
    the remaining bounded interval first, the representative local time only as
    its calculation reference, and the submitted-evidence summary. The summary
    names the most candidate-discriminating calibration event and the separately
    checked reserved event; it is not another prediction or user vote. The system
    does not generate new retrospective events from the selected chart. The
    canonical calculation does not start
    a second uncertainty search around the representative moment: the original
    candidate scan and refined boundaries remain the selection evidence.
11. The user confirms whether the corrected time and retained interval are
    acceptable. A mismatch returns the session to `underdetermined` and requests another dated
    event instead of releasing a report. Only an explicit confirmation moves the
    recalculated revision to `corrected_chart_ready` and opens the report gate.

Every event mutation is serialized per session, checked against the chart
revision observed by the client, and recorded with an idempotency fingerprint.
A retry of an accepted answer returns the existing session instead of running
the calculator again. A stale answer is rejected and must be refreshed. The
same lock also protects the current interview while a skip or reset is being
prepared.

The current intake does not infer an event location. A reported event date is therefore
expanded to the UTC envelope covering every currently valid civil offset from UTC-12
through UTC+14. Dasha or slow-transit evidence contributes only when it remains stable
across that envelope. A boundary-sensitive level is marked unavailable instead of
silently assuming that the event happened in the birth-place timezone.

## Outcomes

- `collecting_evidence`: fewer than four independent dated episodes.
- `underdetermined`: insufficient domain breadth, no clear calibration margin,
  or failed/inconclusive holdout.
- `multiple_equivalent`: after the maximum five-event set, several bounded
  candidates remain indistinguishable. With remaining event capacity, the state
  stays `underdetermined` and asks another candidate-discriminating question.
  After capacity is exhausted, questioning stops and a scoped report may use
  only facts stable across the complete reported time window. The result retains
  every equivalent interval and never claims one corrected instant.
- `needs_recalculation`: a bounded interval passed calibration and holdout but has
  not yet been materialized as the active chart.
- `rectification_confirmation_required`: the selected bounded interval passed,
  its chart was recalculated, and the stage conclusion is waiting for the user's
  reality check.
- `corrected_chart_ready`: the selected bounded interval passed, its chart was
  recalculated at the recorded representative moment, and the user confirmed the
  stage conclusion.
- `input_resolution_required` / `calculation_failed`: civil-time/place or
  deterministic provider failure must be fixed before astrological questioning.

`corrected_chart_ready` and terminal `multiple_equivalent` states with a passed
holdout and an open scoped report gate may bypass Reader prevalidation. Stable
`not_required` charts still use the ordinary pre-reading quality check.

## Evidence contracts

- `birth_input_context.json`: immutable reported input and search constraints,
  separate reading focus and life-event ledger, plus an `activeCanonicalInput`
  that names the selected candidate interval and its representative calculation
  moment after correction.
- `sensitivity_scan.json`: full bounded scan, candidate intervals, scores,
  divisional sensitivity, provider errors, and report-readiness decision.
- `active_chart_sensitivity.json`: internal sensitivity contract produced from the
  canonical recalculation input after any selected bounded interval. Judgement uses this
  version while the original full-window scan remains the rectification audit.
- `chart_rectification_state.json`: active selection policy IDs, candidate state,
  hidden-holdout result, report gate, materialized chart revision, and the
  append-only `rectificationRounds` decision trail. The stage conclusion also
  exposes non-technical `evidenceHighlights` for the selected calibration event
  and reserved check while keeping candidate scores internal.
- `chart_record.json`: typed auditable chart, event evidence, candidates, and the
  final bounded decision consumed by judgement/report stages. Accepted event
  descriptions may also carry bounded semantic facts (`occurrence`, `agency`,
  `impact`, and `dateConfidence`) extracted by the evidence-intake Agent. These
  facts are provenance/context for downstream interpretation; they do not
  override the deterministic astrological score.
- `vedicdust-rectification-benchmark.json`: offline, source-blind known-time
  evaluation corpus. It is not a per-user runtime artifact and never enters the
  Agent context.
- `reader_prevalidation.md` / `prevalidation_result.json`: stable-chart reading
  quality checks only; they have no candidate-selection authority.

The confirmation gate does not generate chart-derived past events. Such prompts
would not be independent validation and are disabled until every visible claim can
cite a backend-released, independently validated claim record.

## Divisional sensitivity

The engine tracks `D1, D2, D3, D4, D5, D7, D9, D10, D12, D16, D20, D24,
D27, D30, D60` from the same canonical instant and calculation profile.

- D1 remains foundational.
- D2/D4/D7/D9/D10/D12/D20/D24/D30 may split candidates because the active
  event policy has an executable dated-event channel for those domains.
- D3/D5/D16/D27 are report-stability and corroboration inputs in the current
  policy. They cannot manufacture a candidate that no issued question can test.
- D60 cannot create first-pass candidates or independently select a birth time.
  It is final-confirmation-only only after the narrowed window gives it adequate
  stability; otherwise it is restricted to rectification context or omitted.

The backend uses computed transitions rather than assuming a fixed minutes-per-
division sensitivity. Optional sub-minute refinement searches only the selected
existing transition band, excludes D60-only changes, and returns an uncertainty
interval rather than an exact second.

## Current limits

- Event-house/karaka mappings and component weights are explicit versioned
  product hypotheses. The source-pinned workflow does not make those weights a
  universally accepted classical formula.
- Every `RectificationRecord` publishes its method maturity, validation status,
  policy IDs, and source IDs. Until independent professional blind-review
  fixtures exist, the contract remains `product_hypothesis` /
  `internal_regression_only`, and reports retain that limitation explicitly.
- Event records distinguish the complete observational score from the
  candidate-selection score. Rahu/Ketu transits, Sade Sati, corroborated KP, and
  diagnostic Chara Dasha stay visible as auxiliary cross-checks but cannot rank,
  eliminate, or validate a birth-time candidate. Only Vimshottari Dasha, the
  event-relevant Varga, and stable Jupiter/Saturn double transit have selection
  authority in the current policy.
- Chara Dasha agreement is retained as a diagnostic comparison only. It cannot
  rank, eliminate, or veto a candidate before independent validation establishes
  a chart- and event-specific use policy.
- Method convergence is counted by analysis layer rather than raw observations.
  D1 Vimshottari activation, use of the same MD/AD/PD lords in the event-relevant
  Varga, and stable Jupiter/Saturn double transit are distinct layers, not claims
  of statistical independence. Two layers are required for a convergent event;
  double transit is corroboration when the event interval can support it, not a
  universal prerequisite.
- The contradiction channel is intentionally unused until contrary rules have
  edition-pinned sources and professional review fixtures.
- Independent JHora desktop golden cases, source-blind rectification benchmark
  cases, and professional end-to-end review fixtures are not yet populated, so
  release certification is incomplete.
- A Rectification Record cannot promote itself by changing maturity labels. Any
  `professionally_validated` result must reference both a registered
  `professional_review` fixture and a registered `rectification_benchmark`
  fixture. The first checks method fidelity, uncertainty, and communication with
  an independent practitioner. The second checks source-blind coverage of retained
  AA known-time intervals and penalizes false exclusion, invalid outcomes, low
  decisiveness, trivial no-narrowing output, target-leaking time windows, and a
  benchmark corpus that lacks both direct-subject and deterministic-mask cases.
- One reserved event is a guard against direct fitting, not statistical proof.
  Sparse or same-domain histories correctly remain underdetermined.
- The product collects one structured dated event per interaction round. Each accepted
  answer recalculates the bounded candidates before the next question is selected.
  Adaptive follow-up should request genuinely new dated evidence or clarify date
  precision; it must never restate an existing event to manufacture another vote.
