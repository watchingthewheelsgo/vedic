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

The baseline `parashari-lahiri-1.0.0` profile declares:

- sidereal zodiac using Lahiri ayanamsa;
- mean lunar nodes;
- whole-sign houses for the Rashi judgement layer;
- Parashara divisional-chart method 1;
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

## Consultation SOP

### 1. Intake qualification

Verify the Birth Assertion, evidence source, time window, place precision,
historical time-zone resolvability, subject age, audience, and consented topic.
Stop when the civil time is impossible or the location cannot be resolved.

The time source changes the minimum search radius, not the direction of a time
correction: a certificate or hospital record has a two-minute minimum radius,
clear family memory ten minutes, and approximate family memory thirty minutes.
These are VedicDust product priors, not empirical error distributions. Explicit
user precision may widen the radius; the source never moves the center by itself.

### 2. Calculation qualification

Generate the Canonical Birth Moment and Astronomy Snapshot. Run invariants,
boundary checks, and golden-reference comparisons before deriving Jyotish Facts.
No model-generated value can repair a failed calculation.

### 3. Rashi foundation

Establish Lagna, Lagnesha, Moon, Sun, house lords, occupants, conjunctions,
graha drishti, dignity, and functional role. D1 defines the primary promise;
no varga can create a promise absent from the foundation.

### 4. Capacity and confirmation

Assess strength measures and relevant vargas. Use only vargas allowed by the
Chart Record's time-confidence gate. Record confirming and contradicting facts.
Each varga carries its own whole-sign house and house-lord structure. A D1 house
lord must never be reused as the lord of the same numbered house in D9, D10, or
another varga.

### 5. Temporal activation

Apply the declared Dasha system and transits only after natal promise and
capacity are established. A forecast Claim requires promise, capacity, and
timing evidence; otherwise it is withheld or downgraded.

### 6. Rectification

Rectification is required only when plausible input variation changes a
decision-relevant fingerprint. Split the reported window at actual chart
boundaries, compare every Candidate Interval against the same calibration
events, preserve holdout events for validation, and allow an underdetermined
result. D60 is unavailable as primary evidence until the input is already
stable enough for D60 to remain meaningful.

When an event has only year or month precision, the calculator evaluates its
midpoint at local noon in the birth-place IANA time zone and converts that
instant to UTC for transit calculation. Dasha, varga-lagna, and double-transit
matches are transparent ranking features under
`transparent_product_hypothesis_v2_correlated-match-cap`: correlated matches
within one Dasha level contribute that level's weight once, and a missing match
is neutral rather than contradictory. The score ranks candidates; it is not a
probability or proof that an event was astrologically caused.

### 7. Claim synthesis

The backend first builds a Judgement Context for the active Chart Record
revision. It selects exact evidence IDs for chart foundation and the supported
domains of identity, career, finance, relationship, home, learning, children,
health, meaning, and family. Requested topics receive priority; remaining
topics are ranked by deterministic chart salience. Restricted facts and timing
periods are removed before model access.

Build Claims from exactly one backend-issued Judgement Unit and its rule
evaluations. A unit fixes the topic, permitted rules, output codes, scopes,
evidence IDs, certainty cap, and mandatory limitations before the model sees the
task. Each Claim must contain supporting facts, counter-facts, certainty, scope, source references, likely real-world
expressions, conditions, user relevance, practical implications, and explicit
limitations. Prefer a small number of decision-relevant synthesis Claims over a
planet-by-planet or house-by-house catalogue. User testimony may validate
expression but cannot retroactively manufacture a natal promise.

Domain judgement rules in rule pack `vedicdust-rules-1.2.0` are explicit
product hypotheses until edition-pinned textual research and professional
fixtures promote them. Their provisional status is a disclosure, not permission
to substitute unsupported prose.

### 8. Report rendering

Build a Consultation Dossier before prose. The fixed reader path is scope,
executive synthesis, chart foundation, current priority domains, timing,
decision support, follow-up questions, and technical evidence. Priority domains
are selected from the intersection of user concern and chart salience; they are
not a mandatory tour of all houses.

Assign every released Claim to exactly one reader section or record why it was
omitted. Write for the subject's life stage and reader relationship. Lead with
plain meaning, disclose certainty and limits, then provide technical evidence.
The backend renders the final report deterministically from the approved
Dossier and Claim Graph. Do not introduce fatalistic, medical, legal, or
financial certainty.

### 9. Consultation continuity

Build an Agent Context from the approved Dossier. Later questions retrieve
approved Claims, stable facts, Timing Windows, user-confirmed events,
uncertainties, rejected hypotheses, and open questions by topic. A later Agent
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
convenience and must not be presented as a discovered exact second.
