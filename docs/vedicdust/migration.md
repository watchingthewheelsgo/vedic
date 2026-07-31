# Legacy Workflow to VedicDust Migration

## Current state

The VedicDust domain language, method SOP, Calculation Profile, source registry,
Rule Catalog, Fact Catalog, machine contracts, JSON Schemas, and four language
skills exist. The production calculator now emits a provenance-validated
`chart_record.json`, a stable `reading_session.json`, and a deterministic
`chart_audit.json` on initial calculation and every rectification recalculation.

The active adapter uses Swiss Ephemeris as the canonical D1 position provider
and PyJHora for D2-D60, Shadbala, Ashtakavarga, and Vimshottari. It records the
provider and adapter versions, rejects ambiguous or nonexistent civil times,
and blocks chart records that fail deterministic quality gates. Rectification
recalculation preserves `chartRecordId` and increments `revision`. The existing
question UI and Markdown report files remain compatibility adapters; LLM
prompts and skills treat `chart_record.json` as the deterministic source.

## Phase 1: provider-backed spacetime and astronomy

**Status: implemented in parallel production output.**

Build a VedicDust adapter over the pinned Swiss Ephemeris and PyJHora providers
behind one calculation interface:

```python
build_chart_record(birth_assertion, calculation_profile) -> ChartRecord
```

Acceptance requires strict ambiguous/nonexistent civil-time handling, pinned
ephemeris and time-zone versions, WGS84 provenance, and golden comparisons for
ascendant, ayanamsa, nine grahas, speed, and nodes.

## Phase 2: deterministic Jyotish derivation

**Status: adapter and typed Fact Catalog implemented; rule validation coverage
is incomplete.**

Implement Rashi, houses, nakshatras, vargas, aspects, dignity, strength
measures, Ashtakavarga, and timing systems as registered Method Rules or
calculation derivations. Each implementation requires:

- a rule ID and semantic version;
- a pinned source or explicit product-hypothesis classification;
- unit and boundary fixtures;
- cross-software fixtures where compatibility is claimed;
- no prose output.

## Phase 3: evidence-based rectification

**Status: identity, audit, sensitivity gates, and revision lifecycle are
implemented. Candidate-interval scoring remains on the compatibility
rectification adapter.**

Replace timestamp sampling with chart-boundary Candidate Intervals. Build the
same evidence matrix for every candidate, reserve holdout Life Events, measure
discriminatory power before asking a question, and calibrate stop thresholds on
known-time cases. Do not ship second-level claims.

## Phase 4: judgement and report runtime

**Status: Chart Record and Chart Audit are wired into production orchestration.
The approved Rule Catalog still needs enough validated judgement rules before
the legacy Markdown report renderer can be removed.**

Execute the Rule Catalog to produce a Claim Graph, invoke the four VedicDust skills by
explicit workflow step, validate every cross-artifact reference, and render the
report from the approved graph. The report runtime must not read legacy Markdown as
an authoritative data source.

## Phase 5: production cutover

Cut over only after:

- calculation fixtures cover normal, boundary, DST, high-latitude, and
  historical cases;
- rectification evaluation reports interval coverage, median error, interval
  width, abstention rate, and holdout performance;
- every production judgement rule has an accepted evidence classification;
- legal review clears source code, prompts, data, books, and runtime licenses;
- VedicDust output is compared blindly against professional consultations;
- the product can reproduce any released Claim from archived artifacts and
  exact versions.

After cutover, archive legacy compatibility artifacts and remove them from the
production dependency graph. Do not rename legacy artifacts and present them as
VedicDust artifacts.
