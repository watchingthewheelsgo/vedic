# Source-Blind Rectification Benchmark

This contract measures one question that internal unit tests and practitioner
review cannot answer: when a reliable birth time is hidden, does VedicDust retain
that true interval after rectification without defaulting to the full input window?

It is an offline release-evidence protocol. Benchmark truth, source documents, and
identity-bearing event records never enter the production Agent context.

## Case protocol

Each primary case must satisfy all of the following:

1. The hidden truth is represented as an interval, not an invented exact second.
2. The source is rated `AA`: a retained civil or family record, using the
   [Astro-Databank/Rodden meaning](https://www.astro.com/astro-databank/Help%3ARR).
   A privacy-safe redacted record or public-source snapshot is retained by path and
   SHA-256. Lower-rated cases are retained for diagnostics but excluded from primary
   release metrics.
3. A salted SHA-256 commitment exists before the engine run and binds the case ID,
   truth interval, source rating, source reference, and retained source-artifact
   hash. The source artifact itself must have been retained before commitment.
4. The truth custodian and run operator are distinct, and the engine and event
   interviewer cannot see the target interval during the run.
5. The reported window uses one of two explicit origins:
   - `independent_subject_recall`: the subject supplies it without access to the
     retained record, and the custodian records that attestation;
   - `deterministic_truth_mask`: a secret committed seed places the truth at a
     reproducible pseudorandom position in a 120- or 240-minute window, with at
     least one minute retained on either side. The run
     operator receives the window but not the seed or target.
     A manually centered or hand-tuned window is target leakage, not a blind case.
6. Dated life episodes are collected without showing candidate contrasts and record
   whether they came from a subject interview or public documentary evidence. Exactly
   one independent episode is reserved as holdout and at least three others are
   used for calibration.
7. The complete source-blind input package is retained before the terminal engine
   run. It contains the reported birth input, the 4-5 dated events, the reported
   window, and evidence origins, but rejects target-bearing fields and candidate
   contrasts.
8. The complete terminal Chart Record is retained by path, timestamp, and SHA-256
   before truth reveal. It must use the exact
   scoring, event-map, and holdout policy IDs under evaluation.
9. A machine-generated run receipt binds the blind-input hash and terminal
   Chart-Record hash to one operator, one clean Git revision, one engine-source
   digest, and the exact policy IDs. A dirty or unpinned run remains diagnostic
   evidence and cannot enter primary metrics. The evaluator also compares the
   reported birth date, time, place, precision, window, and every event's ID, date,
   category, subtype, and description against the terminal Chart Record; sharing
   identifiers alone is not sufficient evidence that the retained input produced
   the retained output.
10. The truth is revealed only after the input, terminal output, and run receipt
    have all been retained.

The truth-source artifact belongs in protected benchmark evidence storage, not a
public repository or production Agent workspace. The commitment detects a changed reveal, but a self-authored timestamp is not a
trusted timestamp. Release evidence should therefore be held by an independent
custodian or stored in an externally timestamped append-only system. This is an
integrity limitation, not an astrological inference.

## Outcomes

- `hit`: the union of the terminal bounded/equivalent intervals fully contains the
  known-time interval.
- `partial`: at least one output interval overlaps the known-time interval but
  excludes part of its documented precision range.
- `miss`: the output intervals exclude the known-time interval.
- `abstained`: the engine returns `underdetermined` or keeps the whole input window.
- `invalid`: the run has no valid terminal rectification outcome, emits an interval
  outside the reported search window, or cannot produce a valid Chart Record.

`partial` is counted as false exclusion. A full input window is not counted as a
hit because a system that never narrows would otherwise score perfect coverage.

## Product release gate

`vedicdust-rectification-benchmark-release-gate/1.1.0` is a VedicDust product
acceptance policy, not a universally accepted Jyotish formula. It currently requires:

- at least 30 primary, source-blind `AA` cases;
- at least 10 independent-subject-recall cases;
- at least 10 deterministic-mask challenge cases;
- at least 10 cases whose events came from direct subject interviews;
- at least 10 end-to-end product-like cases combining independent subject recall
  with direct subject-interview events;
- at least 50% decisive outcomes;
- at least 90% full truth coverage among decisive outcomes;
- at most 10% partial-or-complete false exclusion among decisive outcomes;
- no invalid primary outcome; and
- a median retained interval no wider than 50% of the reported input window.

These composition gates prevent a public-celebrity-only corpus or a subject-recall-
only corpus from being presented as broad validation. Thresholds must be versioned
when changed. Decisive rate, full truth coverage, false exclusion, and median
narrowing must pass separately for independent-recall cases, deterministic-mask
cases, subject-interview cases, and their product-like intersection; aggregate
success cannot hide failure on the actual user interaction. Results should also be reviewed by window width, source
precision, event-date precision, geography, and age cohort; one aggregate pass does
not prove universal accuracy.

## Running the evaluator

Capture the current production-runtime output before the truth custodian reveals
the target:

```bash
uv run --project backend python scripts/capture-rectification-benchmark-run.py \
  --case-id blind-case-001 \
  --blind-input protected/blind-input.json \
  --chart-record protected/chart-record.json \
  --run-operator-id operator-02 \
  --run-started-at 2026-08-09T01:00:00Z \
  --output protected/run-receipt.json
```

The capture command validates the input/output event set and reported window,
then records the Git revision, clean-tree status, source digest, policy versions,
timestamps, and artifact hashes. The source digest and clean-tree check cover the
backend source, `pyproject.toml`, `uv.lock`, and the separately pinned
`astrology-runtime.lock` used for PyJHora and Swiss Ephemeris dependencies. It warns
when any covered input is dirty; such a receipt cannot qualify for primary metrics.

The evaluator separates protocol failures from runtime-output failures. Protocol
failures (for example target leakage or a dirty unpinned run) are excluded from
primary metrics. A terminal Chart Record that is incomplete, internally
inconsistent, or otherwise invalid remains in the primary cohort and counts as an
`invalid` engine outcome; it cannot improve the benchmark by disappearing from the
denominator. Per-case diagnostics are retained as `protocolFailures` and
`outputFailures` respectively.

After truth reveal, assemble the benchmark manifest and evaluate it:

```bash
uv run --project backend python scripts/evaluate-rectification-benchmark.py \
  path/to/benchmark.json --output path/to/report.json
```

The command exits non-zero when the release gate fails. JSON contracts are exported
as `vedicdust-rectification-benchmark.schema.json` and
`vedicdust-rectification-benchmark-report.schema.json`; the protected input and
receipt use `vedicdust-rectification-blind-input.schema.json` and
`vedicdust-rectification-run-receipt.schema.json`.

## Data acquisition boundary

Astro-Databank defines `AA` as a family- or state-recorded time, but its official
bulk export has separate license conditions. Do not scrape or bundle the database
as an implied open benchmark. Public individual pages may be retained only under
their displayed source/license terms; direct-subject cases require informed
consent and protected storage. The product-like cohort cannot be manufactured
from celebrity pages because it requires independent subject recall and direct
subject-interview events.

No benchmark corpus is currently bundled. Until a lawful source-blind corpus and
independent practitioner review both pass, the runtime must remain
`product_hypothesis` / `internal_regression_only`.
