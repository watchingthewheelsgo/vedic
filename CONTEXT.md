# Domain Language

## Birth Assertion

The birth date, local clock time, place, and source exactly as reported by the
user. It is evidence supplied to the system, not yet a calculation input.

## Canonical Birth Moment

The resolved local and UTC moment, IANA time zone, historical offset, and WGS84
coordinates used by the calculation engine. It always retains a link to the
Birth Assertion and the evidence used to resolve it.

## Calculation Profile

A versioned declaration of every configurable astronomical and Jyotish choice
used to calculate a chart. It includes the ayanamsa, node model, house model,
divisional-chart scheme, aspect model, Dasha model, and year definition.

## Calculation Provider

Deterministic astronomical or Jyotish software used to perform a declared
calculation, such as Swiss Ephemeris or PyJHora. A provider is replaceable and
does not define VedicDust's product language.

## Calculation Adapter

The translation from a Calculation Provider's native output into VedicDust
contracts. It must preserve provider and profile provenance and cannot add an
interpretation.

## Astronomy Snapshot

Observed or computed celestial coordinates for one Canonical Birth Moment.
It contains no astrological interpretation.

## Jyotish Fact

A deterministic value derived from an Astronomy Snapshot under one Calculation
Profile, such as a graha's house, a varga placement, Shadbala, or a Dasha period.

## Calculation Assurance

The evidence grade for how a calculated value was produced and checked. It
distinguishes astronomical authority, pinned-provider regression, and an exact
independent external match. It does not describe whether the user's reported
birth input is stable.

## Input Stability

The evidence grade for whether a Jyotish Fact remains unchanged across the
user-supported time and place uncertainty. It cannot upgrade Calculation
Assurance. Effective judgement confidence is the lower of these two axes.

## Fact Catalog

The closed vocabulary of Jyotish Fact types, subject references, value shapes,
derivation rules, and evidence layers accepted by VedicDust.

## Method Rule

A versioned derivation, workflow gate, or judgement policy. Every Method Rule
identifies its applicable Calculation Profiles, evidence requirements,
lineage, source references, validation state, and limitations.

## Evidence Class

The provenance category of a fact or rule: astronomical authority, classical
text, lineage commentary, software reference, product hypothesis, or user
testimony.

## Candidate Interval

A continuous birth-time range whose decision-relevant chart fingerprint is
unchanged. Candidate Intervals, rather than arbitrary timestamp samples, are
the alternatives compared during rectification.

## Life Event

A dated user testimony used as rectification evidence. A Life Event is marked
either calibration or holdout; holdout events cannot influence candidate
selection.

## Life Episode

One independent dated evidence unit used during rectification. The first Life Event
fixes an episode's primary interval. A later event whose reported civil-date interval
overlaps that primary is retained as corroborating context and cannot move the
episode's calibration or holdout role. This prevents one real-world period from
contributing multiple votes while retaining what the user reported.

## Rectification Decision

The auditable result of comparing every Candidate Interval against the same
evidence set. It may select a bounded interval, preserve multiple candidates,
or declare the rectification underdetermined.

## Claim

A released selection of exactly one Judgement Conclusion. It copies the
backend-owned meaning, facts, rules, scope, timing evidence, user relevance,
and limitations without rewriting them, then assigns a bounded certainty and
publication status.

## Judgement Finding

One deterministic observation produced by applying a Method Rule to exact
Jyotish Facts. It records polarity, weight, parameters, provenance rule, and any
Timing Period used. A Finding is technical evidence, not reader-facing prose.

## Judgement Conclusion

A backend-owned synthesis of Judgement Findings for one topic and scope. It is
the smallest semantic result that may be published as a Claim. Its wording,
support and counter-evidence, rules, timing range, conditions, relevance, and
certainty cap are immutable downstream.

## Judgement Context

The deterministic judgement package for one Chart Record revision. It resolves
active Method Rules, requested and salient topics, allowed fact and timing IDs,
eligible vargas, restricted evidence, executable Findings, and selectable
Conclusions before the backend deterministically publishes Claims. It is not the final report.

## Timing Window

A backend-materialized historical, current, near-term, or strategic interval
backed by exactly one approved timing Claim and its exact Chart Record period.
Its expressions, conditions, confidence, and limits are copied from that Claim;
it is not a guaranteed event date.

## Consultation Dossier

The versioned consultation plan for one Chart Record revision. It selects the
few Claims relevant to the user's questions, assigns each released Claim to one
reader-facing section, records unresolved questions, and holds the release
decision. The backend projects scope, confidence, audience, and Timing Windows
onto it before release. It contains no new astrological judgement.

## Consultation Report

The deterministic readable presentation of an approved Consultation Dossier
for a specific audience and life stage. It cannot introduce facts or Claims
absent from the Claim Graph.

## Agent Context

A compact, versioned retrieval projection of an approved Consultation Dossier
for later questions. It contains approved Claims, referenced facts with separate
calculation-confidence and input-stability fields,
Timing Windows, confirmed events, rejected hypotheses, uncertainties, and open
questions. It cannot modify the Chart Record or promote a withheld Claim.
