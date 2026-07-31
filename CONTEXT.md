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

## Fact Catalog

The closed vocabulary of Jyotish Fact types, subject references, value shapes,
derivation rules, and evidence layers accepted by VedicDust.

## Method Rule

A versioned transformation from Jyotish Facts to a structured judgement. Every
Method Rule identifies its lineage and source references.

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

## Rectification Decision

The auditable result of comparing every Candidate Interval against the same
evidence set. It may select a bounded interval, preserve multiple candidates,
or declare the rectification underdetermined.

## Claim

A user-facing conclusion supported by explicit Jyotish Facts, Method Rules,
counter-evidence, conditions, user relevance, and a certainty grade. A Claim is
not free-form model output and cannot silently absorb a new chart fact.

## Judgement Context

The deterministic evidence menu for one Chart Record revision. It resolves the
active Method Rules, requested and salient topics, allowed fact and timing IDs,
eligible vargas, and restricted evidence before an Agent forms Claims. It is
not a judgement and contains no report prose.

## Timing Window

A bounded historical, current, near-term, or strategic interval backed by one
or more approved timing Claims and exact Chart Record timing periods. It
describes possible constructive and pressure expressions plus their conditions;
it is not a guaranteed event date.

## Consultation Dossier

The versioned consultation plan for one Chart Record revision. It selects the
few Claims relevant to the user's questions, assigns each released Claim to one
reader-facing section, records Timing Windows and unresolved questions, and
holds the release decision. It contains no new astrological judgement.

## Consultation Report

The deterministic readable presentation of an approved Consultation Dossier
for a specific audience and life stage. It cannot introduce facts or Claims
absent from the Claim Graph.

## Agent Context

A compact, versioned retrieval projection of an approved Consultation Dossier
for later questions. It contains approved Claims, referenced stable facts,
Timing Windows, confirmed events, rejected hypotheses, uncertainties, and open
questions. It cannot modify the Chart Record or promote a withheld Claim.
