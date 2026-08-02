# VedicDust Consultation Standard 1.0

## Scope

This is a product SOP built around a Parashari-first reading hierarchy with an
explicit Lahiri calculation profile. It is a documented product standard, not
a claim that all Jyotish lineages use identical settings or judgement rules.

Astronomical accuracy, traditional textual authority, software compatibility,
and product validation are different evidence classes. They must never be
collapsed into one generic claim of scientific proof.

## Evidence hierarchy

1. **Astronomical authority** establishes celestial and civil-time facts.
2. **Classical text** establishes a traditional rule for a pinned edition and locator.
3. **Lineage commentary** establishes a named school's interpretation.
4. **Software reference** establishes compatibility with a declared implementation.
5. **Product hypothesis** is an explicit, testable product rule without traditional authority.
6. **User testimony** supplies biographical evidence and cannot become a chart fact.

Classical and modern references with no pinned edition or locator remain
`pending-edition-pin` and cannot justify a production Method Rule by themselves.

## Calculation profile

The baseline `parashari-lahiri-1.1.0` profile declares:

- sidereal zodiac using Lahiri ayanamsa;
- apparent geocentric planetary positions using explicit Swiss Ephemeris
  `FLG_SWIEPH | FLG_SIDEREAL | FLG_SPEED` flags across both the canonical and
  PyJHora-backed calculation paths;
- mean lunar nodes;
- whole-sign houses for the Rashi judgement layer;
- a per-varga method registry: traditional Parashara Hora for D2 and each
  factor's declared traditional method for the remaining supported vargas;
- Parashari graha drishti;
- Vimshottari Dasha from the Moon's nakshatra using a 365.256364-day sidereal year;
- WGS84 coordinates, IANA historical time zones, and UTC Julian Day;
- D1 as the foundation, D9 as a general promise-confirmation chart, and other
  vargas only for their declared domains and eligible time confidence.

These choices are versioned product decisions. A future true-node, Bhava
Chalit, Jaimini, KP, Tajika, or alternate-ayanamsa method requires a separate
profile.

Swiss Ephemeris and PyJHora are Calculation Providers. Their native output is
accepted only through a VedicDust Calculation Adapter that records the active
profile, exact provider versions, time-zone database version, ephemeris-data
fingerprint, registered derivation rule, validation status, and fact confidence.
The calculation distributions are pinned in `backend/astrology-runtime.lock`.
Reusing a provider does not delegate product methodology or report semantics to
that provider.

The declared Swiss Ephemeris path is fail-fast. If the retained `.se1` files do not
cover the requested date and Swiss Ephemeris reports a Moshier fallback, the chart
calculation fails instead of publishing a Chart Record under the wrong provider model.

Calculation assurance and birth-input stability are separate dimensions. D1
positions inherit astronomical-provider assurance, while non-D1 Varga facts are
capped at `corroborated` when they have only passed the pinned PyJHora adapter and
same-provider regression suite. An exact independent external snapshot match can
raise calculation assurance for that Chart Record, but it cannot make an unstable
birth-time window stable. Every judgement and Agent projection uses the lower of
calculation confidence and input stability as its effective confidence. Neither
dimension alone authorizes an interpretation rule.

Every published Claim records the minimum effective confidence of all referenced
supporting, contextual, counter, timing, and Dasha evidence. `supportingFactIds`
is reserved for evidence that actually participates in the released direction;
`contextFactIds` carries inspectable structure such as same-sign contacts,
Parivartana, and context-only Yoga recognition. The Agent may not silently
promote context into support. Claim certainty is then bounded
by that evidence grade, the canonical birth-input grade, any rectification
decision, and the interpretation rule's maturity cap. The validator recomputes
these bounds from source artifacts, so neither a model nor a stale serialized
Claim can promote itself.

Input stability is evaluated at fact granularity under
`vedicdust-fact-sensitivity/1.0.0`. Each fact declares the scan fields on which its
interpretive value depends. D1 Lagna and house facts depend on `lagnaSign`; graha-sign
facts depend on `d1Structure`; Moon, Dasha, Varga, combustion, Shadbala classification,
Digbala, Arudha/Upapada, and special-Lagna facts add their narrower dependencies. A
changed dependency makes only that fact family provisional. Conversely, an invariant
D1 graha fact may remain corroborated when the surrounding D1 chart is low-confidence
solely because Lagna crossed a boundary. Partial or failed scans fail closed for every
fact. The validator recomputes both dependency lists and grades from the Chart Record.

Vimshottari periods use the same two-axis contract. Their provider provenance is
separate from an `inputStability` grade derived from the canonical birth-input
confidence and the `moonNakshatra`, `moonPada`, and `currentDasha` scan fields.
Claims and validation use the lower of those two grades. A stable Dasha label does
not erase the residual boundary uncertainty of an approximate birth time.

## Consultation SOP

### 1. Intake qualification

Verify the Birth Assertion, evidence source, time window, place precision,
historical time-zone resolvability, subject age, audience, and consented topic.
Stop when the civil time is impossible or the location cannot be resolved.

Civil time is resolved against the IANA zone before any astronomical provider is
called. A nonexistent wall time is rejected. If a daylight-saving rollback makes
the reported wall time occur twice, VedicDust presents the two real occurrences
to the user and requires an explicit choice; it never guesses a fold. The chosen
UTC offset is validated against the zone, persisted in the Canonical Birth Moment,
and reused by Swiss Ephemeris, PyJHora adapters, independent-reference selection,
and any later rectified chart revision.

The time source changes the minimum search radius, not the direction of a time
correction: a certificate or hospital record has a two-minute minimum radius,
clear family memory ten minutes, and approximate family memory thirty minutes.
These are VedicDust product priors, not empirical error distributions. Explicit
user precision may widen the radius; the source never moves the center by itself.

### 2. Calculation qualification

Generate the Canonical Birth Moment and Astronomy Snapshot. Run invariants,
boundary checks, and golden-reference comparisons before deriving Jyotish Facts.
No model-generated value can repair a failed calculation.

Candidate-event scoring fails closed when the rectification signature lacks a
valid D1 Lagna, Moon sign index, stable Dasha-lord position, or a required
domain-varga structure. Missing deterministic inputs never count as a negative
match against one candidate.

After any candidate interval is selected, VedicDust retains the original bounded
scan as selection evidence and writes a separate active-chart sensitivity record
from the canonical recalculation. Judgement consumes the active record so the
recalculated Chart Record and its evidence restrictions cannot refer to different
calculation windows.

### 3. Rashi foundation

Establish Lagna, Lagnesha, Moon, Sun, house lords, occupants, conjunctions,
graha drishti, dignity, and functional role. D1 defines the primary promise;
no varga can create a promise absent from the foundation.

The report exposes Lagna, Sun, and Moon as a separately traceable D1 reference-point
triad before any domain synthesis. This is chart structure, not permission to infer
personality labels or event direction. Each displayed point retains its exact
position-fact provenance.

### 4. Capacity and confirmation

Assess strength measures and relevant vargas. Use only vargas allowed by the
Chart Record's input-stability gate. Record confirming and contradicting facts.
Sign dignity and Panchadha Maitri remain distinct evidence: `special` records
exaltation, debilitation, or own-sign status; `panchadha`/`compound` records the
natural-plus-temporary relationship; `effective` is the explicit presentation
precedence and never erases either source value.
Each varga carries its own whole-sign house and house-lord structure. A D1 house
lord must never be reused as the lord of the same numbered house in D9, D10, or
another varga.
Vargottama is retained as a narrow D1-D9 same-sign equality for Lagna and the
nine grahas. It is structural confirmation only; strength or outcome requires a
separate permitted judgement rule.

The baseline 7K Chara Karaka ranking is evidence-sensitive. If adjacent grahas
are indistinguishable at the six-decimal degree precision stored in the Chart
Record, the affected roles are withheld and the quality gate records a warning;
provider input order is never treated as a tie-break rule.

A same-sign association between declared kendra and trikona lords is recorded as
a narrow Raja Yoga structure fact. The pinned lineage source supports the
structural association; VedicDust keeps it `context_only`. Cancellation,
affliction, capacity, fruition, and timing require separate evidence and may not
be inferred from this fact alone.

Gaja-Kesari is the first named Yoga whose complete published condition set is
implemented as one source-bound fact. VedicDust requires Jupiter in a quadrant
from Moon, a qualified natural benefic conjoining or aspecting Jupiter, and
Jupiter not debilitated, combust, or in an enemy's house under the source's
declared Panchadha Maitri compound relationship. The natural-benefic
classification follows the pinned P.V.R. Narasimha Rao passage literally,
including its conditional treatment of Mercury; Saturn is not silently inserted
into that passage's companion count. The resulting fact and judgement remain
`context_only`: they identify a complete structure but do not promise fame,
wealth, status, character, magnitude, fruition, or timing. Strength beyond the
published Jupiter gates still requires broader chart synthesis and professional
validation.

### 5. Temporal activation

Apply the declared Dasha system and transits only after natal promise and
capacity are established. A forecast Claim requires promise, capacity, and
timing evidence; otherwise it is withheld or downgraded.

The first production timing conclusion is intentionally narrow: it selects a
current or next Antardasha whose lord owns, occupies, or casts declared Parashari
graha drishti to a topic's anchor house. It publishes the observed outer boundary
range across the declared birth-time hypotheses, alongside the canonical provider
interval, at low certainty and does not turn that activation into an event
prediction. Horizon inclusion and current-period prioritization use that outer
range rather than pretending the canonical interval is exact. Pratyantardasha is excluded from this first gate
because its apparent precision is more sensitive to birth-time uncertainty;
transits must be recalculated for the date actually assessed.

The model may organize backend-released Claims into the consultation dossier,
but it does not own publication. The backend replaces report confidence,
timing windows, quality checks, and release status; it approves only when
deterministic prerequisites pass, every released Claim is accounted for once,
and the required report structure is complete. The future-Q&A context is a
deterministic projection of those Claims and rejects semantic field drift.
Public manifests, rendered reports, and future-Q&A context fail closed unless
the same approved Dossier and its passing quality checks are present.

The pinned lineage reference for whole-sign houses, baseline Graha Drishti,
Argala, and the worked D10 judgement order is P.V.R. Narasimha Rao,
_Lessons on Vedic Astrology_, Volume I, First Print 2005, PDF p. 27 and PDF
pp. 44-45 (book pp. 72-73). VedicDust records structural house ownership and dispositor chains as
facts; it does not turn those facts into universal benefic/malefic labels.

### 6. Rectification

Rectification is required only when plausible input variation changes a
decision-relevant fingerprint. Split the reported window at actual chart
boundaries, compare every Candidate Interval against the same calibration
events, preserve holdout events for validation, and allow an underdetermined
result. D60 is unavailable as primary evidence until the input is already
stable enough for D60 to remain meaningful.

An event date is an uncertainty interval unless an event time was supplied.
The calculator converts the interval boundaries and midpoint from the
birth-place IANA time zone to UTC. Dasha, varga-lagna, and double-transit
matches sampled across that interval are transparent ranking features under
`vedicdust-rectification-event-ranking/1.6.0`: correlated matches
within one Dasha level contribute that level's weight once. Varga-domain selection
uses `vedicdust-varga-domain-policy/1.0.0`, pinned to P.V.R. Narasimha Rao's
_Vedic Astrology: An Integrated Approach_ (first published 2000; author update
2010, PDF pp. 71-73). Event-house and karaka mappings and all numerical weights
remain VedicDust product hypotheses. An unmatched
activation is neutral missing evidence, not a contradiction, because the
versioned event map is not an exhaustive causal theory. Only Dasha lords that
remain stable across the start, midpoint, and end of the user's reported date
interval, including the whole day when no event time was supplied, are eligible.
A partial MD/AD/PD lookup fails candidate scoring. Year-only events cannot add
double-transit evidence; month- and day-level transit support must remain active
at every interval sample rather than appearing at one convenient instant. The support score ranks candidates;
it is not a probability or proof that an event was astrologically caused.

Candidate selection uses deterministic calibration-event scores only. Reader
feedback, personality testimony, appearance, preferences, and repeated wording of
an event cannot alter candidate rank, break a tie, or raise rectification confidence.
The reserved holdout event remains outside calibration ranking and must pass before
a selected chart is released. When the evidence does not separate candidates, the
system requests genuinely new dated evidence or returns `underdetermined`; it does
not ask the model to map an answer back to a preferred chart.

Directional interpretation remains disabled until a professional-review fixture is
auditable rather than merely labelled. Such a fixture must retain the reviewed case
IDs, protocol, reviewer and timestamp, plus the original review artifact whose
SHA-256 is verified when the rule catalog loads. The review artifact must identify
the reviewer's relevant credentials, attest subject-identity and system-authorship
blinding and implementation independence, and reference the exact Chart Record,
Claim Graph, and Consultation Dossier for every case by retained path and SHA-256.
Each case records expected versus observed publish/withhold disposition, dimension-level
assessment, reservations, disagreement, and rationale. A rejected dimension, rejected
case, disposition mismatch, missing artifact, or hash mismatch invalidates the fixture.
Engineering tests alone cannot certify a directional judgement method.

Candidate comparison is all-or-nothing. If deterministic event scoring fails
for any candidate interval, rectification enters `calculation_failed`; successful
siblings cannot be ranked against an incompletely evaluated alternative, and no
model-generated questions are accepted until calculation is retried.

When a chart-changing input window has fewer than three recognized dated events,
the workflow enters `collecting_evidence` without invoking the Reader. The user
supplies three to five concise event records through structured cards; one event
is selected score-blind as holdout, and the calculator reruns candidate event
scoring. Calibration ranking and the reserved-event check are backend-owned; the
Reader never receives candidate contrasts and no repeated confirmation of an
already submitted event can change the ranking. Generic traits and an initial
reading focus are never treated as substitutes for dated evidence.

The baseline scan is a complete one-minute grid over the reported time window.
A scan advances through absolute UTC instants and then renders each instant in the
birth-place zone. A DST fallback day therefore contains 1,500 sampled minutes and
both copies of the repeated hour; a spring-forward gap contributes no invented
local minutes.
A signature transition between adjacent samples is represented as a 60-second
uncertainty interval: neighboring Candidate Intervals overlap across that minute,
and the typed Chart Record publishes a `SensitivityBoundary` with its resolution.
The sampled minute is never presented as a discovered exact transition. After
dated-event evidence and the reserved holdout select one candidate, VedicDust may
recalculate only that candidate's existing transition band at sub-minute instants.
The refinement excludes D60 and Dasha-only changes, stops if a third structural
fingerprint appears, and emits a bounded interval no narrower than the configured
five-second resolution. It never converts that computational boundary into a
claimed exact birth second; independent evidence still governs the final birth-time
certainty.

City- and district-level coordinates always require place rectification or an
explicit equivalence result. Geographic envelope samples use the complete declared
`radiusKm`; the engine does not silently clip a wide municipality to 30 km.

### 7. Claim synthesis

The backend first builds a Judgement Context for the active Chart Record
revision. It selects exact evidence IDs for chart foundation and the supported
domains of identity, career, finance, relationship, home, learning, children,
health, meaning, and family. Requested topics receive priority; remaining
topics are ranked by deterministic chart salience. Restricted facts and timing
periods are removed before model access.

Topic ordering and report breadth are governed by the versioned
`vedicdust-presentation-selection/1.0.0` product policy. Its `priorityScore`
means presentation salience, not planetary strength, auspiciousness, certainty,
or predicted life importance. Every score is accompanied by typed reasons and
the exact supporting Fact IDs: a neutral baseline, explicit user request,
unusual SAV distance from the neutral reference, D1 aspect density, and the
availability of a birth-time-eligible corroborating Varga. The policy always
includes the foundation when eligible, puts requested domains first, limits the
default structural report to eight domains and the complete Claim Graph to ten
Claims, and only adds timing Claims for explicitly requested domains. These are
reader-attention and report-length decisions, not classical Jyotish rules; they
must be versioned independently from calculation and judgement methods.
The serialized policy also publishes every scoring parameter: foundation and
domain baselines, requested-topic target, SAV neutral reference and deviation
weight/cap, D1 aspect weight/cap, and eligible-Varga boost. A deployed report can
therefore be reproduced without recovering constants from source code.

Build Claims from exactly one backend-issued Judgement Unit and one of its
deterministic Conclusions. The backend judgement kernel evaluates anchor-house
lord paths, capacity, dispositors, SAV, and eligible varga confirmation into
fact-bound Findings, then resolves support and counter-evidence into a bounded
Conclusion. Varga lord placement is recorded as corroboration context rather
than automatically labelled favorable or unfavorable. Calculation rules only
establish reproducible facts; they never authorize an interpretation by
themselves. Lagna-Sun-Moon reference points, house-lord placement, house occupancy, declared Parashari graha
drishti, eligible varga confirmation, and same-sign/kendra-trikona association
plus natural-Karaka condition and dispositor path retain separate interpretation rule IDs. This
preserves method provenance and prevents several observations from masquerading
as one independently validated method. All eight are currently provisional and
`context_only`. Separate
capacity-judgement rules record the VedicDust
structural-bands 1.2.0 policy for SAV, dignity, Shadbala, and combustion. Those
rules are currently provisional and `context_only`, so even an extreme numerical
band is described rather than labelled favorable or unfavorable. Future
directional use requires both a validated derivation rule and a separately
validated judgement rule. A supportive or challenging domain direction also
requires convergence from at least two distinct validated interpretation methods
that agree on the same direction. One supportive method and one challenging method
are disagreement, not convergence, and both remain descriptive. Every rule in the
Agent-facing Judgement Context carries its explicit `context_only` or `directional`
permission; the backend independently revalidates that permission before releasing
Findings and Conclusions.
Natural Karakas use the topic's declared significators and their available D1
condition evidence under an edition-pinned method contract. Anchor-house occupants
and declared Parashari graha drishti to an anchor house or its lord also have distinct
source-pinned method identities. An anchor lord's dispositor path is retained as a
separate conditioning method instead of being attributed to the broad domain rule.
All remain context-only and receive no automatic
supportive or challenging score. Timing is released only when the Antardasha
lord itself owns, occupies, or aspects a topic anchor house. Broader sambandha,
karaka activation, and PVR's experimental D60 transit principle remain withheld
from the baseline profile.

Vimshottari dates are not treated as exact merely because PyJHora returns an
exact timestamp. The calculation stage reruns the Dasha timeline at the start,
canonical point, and end of the user's declared birth-time window. Every period
stores a start and end boundary envelope. Complete endpoint coverage can retain
the canonical input grade; partial or missing sampling downgrades timing evidence,
and a failed timing scan makes it unavailable. The envelope is an observed
endpoint range, not a proof of monotonic behavior between samples, so timing
conclusions remain low-certainty activation windows and disclose the canonical
provider interval separately.

Rectification uses a separate, provisional ranking policy. For a dated event, a
stable MD/AD/PD lord may match a mapped D1 house by ownership, occupancy, declared
Parashari graha drishti, or the event map's natural-karaka role. Multiple matches
within one Dasha level are correlated evidence and receive one level weight, not
multiple votes. Relevant varga structure and interval-stable double transit are
separate components. Missing activation is neutral rather than a contradiction.

The model must copy all semantic fields, scope, rules, timing, and backend-owned
user relevance exactly; it may select and prioritize but cannot rewrite the
Jyotish meaning. Prefer a small number of decision-relevant synthesis Claims over a
planet-by-planet or house-by-house catalogue. User testimony may validate
expression but cannot retroactively manufacture a natal promise.

Domain judgement rules in the active versioned VedicDust rule pack are explicit
product hypotheses until edition-pinned textual research and professional
fixtures promote them. Their provisional status is a disclosure, not permission
to substitute unsupported prose.

Rule validation evidence is not a free-form label. Every `validationFixtureId`
must exist in `validation_fixtures.json`, identify executable pytest nodes, and
declare its assurance kind. Contract and invariant tests establish internal
behavior; same-provider regressions detect adapter drift; independent-external
fixtures establish cross-implementation agreement; professional-review fixtures
record expert judgement review under the machine-validated blind-review contract.
The contract can preserve accepted-with-reservations and withheld cases without
turning disagreement into approval. Only the last category can help authorize a
directional interpretation rule, and it cannot replace the pinned textual source.
Rectification maturity labels are not self-authenticating: a professionally
validated Rectification Record must retain registered professional-review fixture
IDs, and provenance validation rejects unknown or non-professional fixtures.

Runtime evidence confidence cannot outrun derivation maturity. A provisional
calculation rule may emit only provisional, disputed, or unavailable evidence;
it cannot label a fact corroborated or verified. Judgement permission remains a
separate axis, so a corroborated dignity calculation is still context-only until
a professionally reviewed directional interpretation rule exists.

Structural association facts are kept method-specific. Same-sign contact,
Parashari graha drishti, kendra-trikona lord association, and exact house-lord
Parivartana are separate records. An exchange proves only mutual house placement;
it does not by itself prove benefit, harm, magnitude, or a date of fruition.

### 8. Report rendering

Build a Consultation Dossier before prose. The fixed reader path is scope,
executive synthesis, chart foundation, current priority domains, timing,
decision support, follow-up questions, and technical evidence. Priority domains
are selected from the intersection of user concern and chart salience; they are
not a mandatory tour of all houses.

Assign every released Claim to exactly one reader section or record why it was
omitted. Write for the subject's life stage and reader relationship. Lead with
plain meaning, disclose certainty and limits, then provide technical evidence.
The disclosed Claim certainty is a computed release bound, not a stylistic label;
its evidence confidence remains available to the report and follow-up Agent.
The backend replaces model-authored dossier identity, scope, confidence, locale,
audience, section title/order/purpose, omission language, unresolved questions,
visual references, confidence-disclosure flags, and timing-window content with
projections from the Chart Record, Judgement Context, and approved timing Claims.
The Agent may arrange approved Claims but cannot create a second prose judgement
channel through presentation fields. The backend then renders the final report
deterministically.
Do not introduce fatalistic, medical, legal, or financial certainty.

### 9. Consultation continuity

Build an Agent Context from the approved Dossier. Later questions retrieve
approved Claims, stable facts, Timing Windows, user-confirmed events,
uncertainties, rejected hypotheses, and open questions by topic. A later Agent
also receives the authoritative subject age, life stage, reader relationship,
consultation topics, and reported birth date so child/adult and audience framing
cannot disappear between the report and follow-up consultation. A later Agent
may append a new versioned Claim only through the judgement gate; it cannot
rewrite the Chart Record or silently reinterpret a withheld Claim.

### 10. Quality gate

A report is releasable only when calculation checks pass, required
rectification is resolved or explicitly bounded, every strong Claim is
traceable, and the report contains no unsupported statement.

## Rectification stop conditions

Rectification stops when one of the following is true:

- one Candidate Interval is supported by calibration evidence and succeeds on
  holdout evidence without a material contradiction;
- remaining candidates are equivalent for the requested consultation scope;
- additional questions have no discriminatory power;
- evidence remains contradictory or insufficient, producing `underdetermined`.

The result is a bounded interval. A representative timestamp is a calculation
convenience and must not be presented as a discovered exact second. A corrected
Chart Record preserves the original Birth Assertion and candidate scan, while
recording the representative timestamp and selected interval separately as the
active canonical calculation input.
