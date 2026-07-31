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
profile, provider version, registered derivation rule, validation status, and
fact confidence. Reusing a provider does not delegate product methodology or
report semantics to that provider.

## Consultation SOP

### 1. Intake qualification

Verify the Birth Assertion, evidence source, time window, place precision,
historical time-zone resolvability, subject age, audience, and consented topic.
Stop when the civil time is impossible or the location cannot be resolved.

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

### 7. Claim synthesis

Build Claims from rule evaluations. Each Claim must contain supporting facts,
counter-facts, certainty, scope, and source references. User testimony may
validate expression but cannot retroactively manufacture a natal promise.

### 8. Report rendering

Write for the subject's life stage and reader relationship. Lead with plain
meaning, disclose certainty and limits, then provide technical evidence. Do not
introduce fatalistic, medical, legal, or financial certainty.

### 9. Quality gate

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
