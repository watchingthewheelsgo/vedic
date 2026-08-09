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

The stated precision controls the search radius. The time source is retained as
provenance for audit and conversation context, but it does not narrow or widen
the candidate window and never shifts the reported time. A hospital record,
certificate, and family memory can all contain human recording error; VedicDust
does not impose an unvalidated reliability hierarchy between them.

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

The candidate fingerprint is narrower than the report-stability fingerprint.
It includes D1 plus D2/D4/D7/D9/D10/D12/D20/D24/D30 fields that the active
dated-event policy can test. D3/D5/D16/D27, D60, strengths, special points,
Chara Karaka ordering, and other interpretive states still mark facts unstable,
but cannot split a candidate when no current question and scoring rule can
distinguish that split.
The report-epoch `currentDasha` is likewise a report-stability field, not a
candidate-partition or question-ranking field. Historical MD/AD/PD periods are
computed separately for each submitted event interval and remain authorized
selection evidence.

An event date is an uncertainty interval unless an event time was supplied.
When the event location is unknown, the calculator expands the full civil interval
to the UTC envelope spanning UTC-12 through UTC+14 rather than assuming the birth
place. Vimshottari eligibility is checked against exact PyJHora MD/AD/PD
boundaries. Slow-transit evidence covers the complete possible UTC envelope on
a twelve-hour grid and is withheld within one degree of a sign ingress.
Diagnostic Chara Dasha is deferred during the adaptive interview and can be
requested separately for audit, but remains non-selecting. These
transparent ranking features use
`vedicdust-rectification-event-ranking/1.25.0`: correlated matches within one
Dasha level contribute that level's weight once, and overlapping reported date
intervals form one independently counted Life Episode. Varga-domain selection
uses `vedicdust-varga-domain-policy/1.0.0`, pinned to P.V.R. Narasimha Rao's
_Vedic Astrology: An Integrated Approach_ (first published 2000; author update
2010, PDF pp. 71-73). The backend-bound event subtype is part of the event
identity and selects the versioned `vedicdust-rectification-event-map/1.8.0`
mapping for every concrete user-facing subtype; `other` deliberately retains the
category rule. Free text and Agent output cannot change it. Event-house and karaka mappings and all numerical weights
remain VedicDust product hypotheses. An unmatched
activation is neutral missing evidence, not a contradiction, because the
versioned event map is not an exhaustive causal theory. Only Dasha lords whose
exact half-open period covers the user's complete reported date interval,
including the whole day when no event time was supplied, are eligible.
A period level crossed by the reported interval is withheld. A provider response
that omits a level without reporting such a boundary fails candidate scoring.
Only subtypes whose wording states an unambiguous constructive or disruptive
outcome receive direction. Value-ambiguous milestones such as marriage,
pregnancy, moves, purchases, examinations, and settlements remain neutral. For
directional events, D1 dignity of mapped house lords may add bounded
natal-promise corroboration when its direction matches. Natural-karaka dignity
is retained as interpretation context but cannot distinguish adjacent birth-time
candidates. This narrow D1 rule never vetoes an event, and one dignity condition
never becomes contradiction evidence because cancellation and wider yoga context
are outside its scope. A convergent event must include both Vimshottari
activation and event-relevant Varga activation. D1 directional capacity and
boundary-safe Jupiter/Saturn double transit remain auxiliary and cannot satisfy
the convergence gate.
The score-blind holdout does not define candidate boundaries. After candidate
construction, the backend separately verifies its Vimshottari hierarchy at every
point of the same complete minute grid, including each candidate's overlapping
transition band. The recorded one-minute audit resolution is explicit; it is not
second-level proof. Any observed change makes the holdout inconclusive and cannot
release a rectified result.
Year-only events cannot add double-transit evidence. Month- and day-level
transit support must remain active across the full UTC grid, with a conservative
sign-boundary guard, rather than appearing at one convenient instant. Each
event retains a complete observational score, including auxiliary Rahu/Ketu,
Sade Sati, and corroborated KP signals, plus a separate candidate-selection
score. Only Vimshottari Dasha and the event-relevant Varga enter the selection
score, calibration aggregate, event-discrimination test, or hidden holdout
result. D1 directional capacity, stable Jupiter/Saturn double transit, and the
other auxiliary signals remain
auditable but cannot break a tie or reverse a candidate ranking. The selection score ranks candidates;
it is not a probability or proof that an event was astrologically caused.
The candidate margin is `0.05`, aligned with the policy's smallest repeatedly
actionable pattern: two `0.08` event-relevant Varga differences across three
calibration episodes produce an aggregate lead of about `0.053`. In addition,
at least two convergent events must each favor the leader over every alternative
class by `0.05`; unrelated convergent events cannot lend authority to a separate
single-layer score difference. These are versioned product thresholds, not
classical constants or statistical confidence.

Candidate selection uses deterministic calibration-event scores only. Reader
feedback, personality testimony, appearance, preferences, and repeated wording of
an event cannot alter candidate rank, break a tie, or raise rectification confidence.
The release gate requires three calibration events across at least two mapped life
domains. D1 Vimshottari activation and activation of the same period lords in the
event-relevant Varga are complementary analysis layers, not statistically
independent votes. At least two calibration events, and the reserved holdout
event, must each receive support from both layers. The holdout must support every
interval in the selected equivalence class, not only its representative point.
Double transit remains an auxiliary cross-check. Chara Dasha
agreement remains a non-authoritative diagnostic. Agreement, disagreement,
unavailability, or a tie cannot rank, eliminate, or block a candidate until this
cross-check earns source-blind and professional validation.
The reserved holdout event remains outside calibration ranking and must pass before
a selected chart is released. When the evidence does not separate candidates, the
system requests genuinely new dated evidence or returns `underdetermined`; it does
not ask the model to map an answer back to a preferred chart.
If all remaining intervals are equivalent after the fifth independent episode,
the workflow stops questioning, preserves every interval, and permits judgement
only from facts stable across the complete reported input window.

Professionally validated `directional` interpretation remains disabled until a
professional-review fixture is auditable rather than merely labelled. Such a fixture must retain the reviewed case
IDs, protocol, reviewer and timestamp, plus the original review artifact whose
SHA-256 is verified when the rule catalog loads. The review artifact must identify
the reviewer's relevant credentials, attest subject-identity and system-authorship
blinding and implementation independence, and reference the exact Chart Record,
Claim Graph, and Consultation Dossier for every case by retained path and SHA-256.
Each case records expected versus observed publish/withhold disposition, dimension-level
assessment, reservations, disagreement, and rationale. A rejected dimension, rejected
case, disposition mismatch, missing artifact, or hash mismatch invalidates the fixture.
Engineering tests alone cannot certify a professionally directional judgement method.
VedicDust may separately expose a `traditional_tendency` when a pinned classical or
lineage source and executable contract exist. That permission is not professional
validation: it requires two distinct methods to agree, caps the released conclusion at
low certainty, and must disclose that no independent professional review has occurred.

Candidate comparison is all-or-nothing. If deterministic event scoring fails
for any candidate interval, rectification enters `calculation_failed`; successful
siblings cannot be ranked against an incompletely evaluated alternative, and no
model-generated questions are accepted until calculation is retried.

Four events are the minimum, not an automatic stopping point. If calibration,
holdout, or candidate equivalence remains inconclusive, the backend issues one
new candidate-discriminating question at a time up to five events. Only then
does it preserve an underdetermined or equivalent interval instead of forcing a
representative minute.

When a chart-changing input window has fewer than four recognized dated events,
the workflow enters `collecting_evidence` without invoking the Reader. The user
supplies four to five concise event records through structured cards; one event
is reserved score-blind as holdout, and the calculator reruns candidate event
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

City- and district-level coordinates are sampled only for geographic sensitivity.
If the declared envelope changes material chart fields, the workflow requires a
user-confirmed address or coordinate before time rectification. Life-event answers
never select or synthesize a birthplace coordinate. Geographic samples use the
complete declared `radiusKm`; the engine does not silently clip a wide municipality.
Joint time/place samples are diagnostics only and are excluded from event scoring
and candidate selection.

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
capacity-judgement rules record the VedicDust structural-bands 1.2.0 policy for SAV,
dignity, Shadbala, and combustion. Dignity and Shadbala are source-pinned
`traditional_tendency` rules. They may contribute supportive or challenging evidence
only when both methods agree, and any resulting conclusion is capped at low certainty.
SAV and combustion remain provisional `context_only` product rules, so even an extreme
numerical band is described rather than labelled favorable or unfavorable. A strict
`directional` rule additionally requires a validated derivation, validated judgement
contract, and professional-review fixture. One supportive method and one challenging
method are disagreement, not convergence, and the conclusion remains descriptive.
Every rule in the Agent-facing Judgement Context carries its explicit `context_only`,
`traditional_tendency`, or `directional` permission; the backend independently
revalidates that permission before releasing Findings and Conclusions.
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
Rectification-benchmark fixtures are a separate assurance class: they evaluate
whether source-blind output intervals retain a hidden AA-rated known birth-time
interval, whether the engine abstains instead of forcing an answer, and whether
successful answers materially narrow the reported window.
The contract can preserve accepted-with-reservations and withheld cases without
turning disagreement into approval. Only the last category can help authorize a strict
`directional` interpretation rule, and it cannot replace the pinned textual source.
Source grounding plus executable contracts may authorize only the lower-assurance
`traditional_tendency` permission described above.
Rectification maturity labels are not self-authenticating: a professionally
validated Rectification Record must retain registered professional-review fixture
IDs and registered source-blind rectification-benchmark fixture IDs. Provenance
validation rejects missing, unknown, misclassified, hash-invalid, or release-gate-
failing evidence. Expert review cannot substitute for known-time outcome testing,
and known-time coverage cannot substitute for expert method review.
The professional-review fixture must declare `rectification` or `end_to_end`
scope; a calculation/report-language review cannot certify birth-time correction.
That review requires at least five blind cases containing both publish and withhold
outcomes, the retained Rectification State, and explicit assessments of candidate
construction, event-method fidelity, holdout independence, stopping/abstention,
and uncertainty communication.

Runtime evidence confidence cannot outrun derivation maturity. A provisional
calculation rule may emit only provisional, disputed, or unavailable evidence;
it cannot label a fact corroborated or verified. Judgement permission remains a
separate axis. A corroborated dignity calculation may support only the registered
low-certainty traditional tendency until a professionally reviewed directional
interpretation rule exists; it does not become professional validation by itself.

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
