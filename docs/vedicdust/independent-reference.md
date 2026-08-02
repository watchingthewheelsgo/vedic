# Independent calculation reference

VedicDust separates provider compatibility tests from independent Jyotish-software validation.
Swiss Ephemeris and direct PyJHora calls exercise the active calculation chain; neither counts as
an independent golden reference.

## Accepted snapshot

`ChartRecordBuildInput.independent_reference` accepts a normalized snapshot with:

- a supported external software name (`Jagannatha Hora` or `Parashara's Light`)
  and its exact version;
- a SHA-256 hash of the original export, screenshot bundle, or saved chart file;
- the exact VedicDust calculation profile ID used to reproduce the settings;
- D1 sign and degree for Lagna and all nine grahas;
- D2, D3, D4, D5, D7, D9, D10, D12, D16, D20, D24, D27, D30, and D60
  signs for Lagna and all nine grahas;
- all twelve Sarvashtakavarga sign totals;
- seven-graha Shadbala totals in rupas;
- one complete nine-lord Vimshottari Mahadasha cycle with timezone-aware start and end instants.

The comparator rejects Swiss Ephemeris, PyJHora, and VedicDust as reference systems. It also
rejects profile mismatches, incomplete snapshots, D1 degree differences above 0.02 degrees, and
any supported-varga sign, SAV, Shadbala, Mahadasha-lord, or Mahadasha-boundary mismatch above
120 seconds. A supplied mismatch blocks the Chart Record.
Absence of an independent snapshot remains a warning and must never be described as desktop
equivalence.

A passing snapshot upgrades the non-D1 Varga calculation-assurance axis for that exact Chart
Record from `internal_provider_regression` to `independent_external_match`. It does not upgrade
birth-input stability, does not certify a judgement rule, and does not establish corpus-wide
provider equivalence. The effective confidence exposed to judgement and future Q&A remains the
lower of calculation confidence and input stability.

Set `VEDIC_INDEPENDENT_REFERENCE_REGISTRY` to a version-controlled normalized registry. Each
entry must point to the retained original export, screenshot bundle, or saved chart file; that
artifact may live in controlled storage mounted next to the registry. The loader reads the file
and verifies its SHA-256 instead of trusting a hash-shaped string. Each entry also records the
`dual-entry-manual-v1` protocol, the normalizer, a different reviewer, and the review timestamp.
Release-certification entries additionally require a stable `caseId` and unique, non-empty
`coverageTags`.
At runtime VedicDust matches local date and
exact local time to the second (an omitted second is normalized to `00`), timezone, calculation
profile, and coordinates within the selector's explicit tolerance,
then passes the snapshot into the Chart Record quality gate. A configured missing or malformed
registry fails calculation instead of silently skipping validation.

```json
{
  "sourceSystem": "Jagannatha Hora",
  "sourceVersion": "external-version",
  "sourceArtifactSha256": "sha256:<64 lowercase hex characters>",
  "methodProfileId": "parashari-lahiri-1.1.0",
  "d1Positions": {
    "Lagna": { "sign": "Virgo", "degreeInSign": 10.8167 }
  },
  "vargaSigns": {
    "D2": { "Lagna": "Cancer" },
    "D9": { "Lagna": "Aries" },
    "D10": { "Lagna": "Leo" },
    "D60": { "Lagna": "Scorpio" }
  },
  "savBySign": { "Aries": 25 },
  "shadbalaRupas": { "Sun": 8.9 },
  "mahadashas": [
    {
      "lord": "Mars",
      "start": "1994-04-12T10:26:48-04:00",
      "end": "2001-04-12T05:30:57-04:00"
    }
  ]
}
```

The abbreviated example shows field shape only. Production snapshots must include every declared
varga and body, satisfy the complete coverage contract above, and retain the unhashed source
artifact in the configured controlled-storage path. Unit tests may synthesize a snapshot to exercise the comparator
contract, but such a fixture is not independent evidence and never satisfies release certification.

## Corpus certification

Runtime exact-user lookup answers only whether one birth assertion has a matching external
snapshot. It does not establish representative engine agreement. Release certification therefore
recalculates every registry entry and applies the same strict comparator used by the Chart Record
quality gate.

```bash
VEDIC_INDEPENDENT_REFERENCE_REGISTRY=/controlled/jhora/registry.json \
  npm run backend:certify:references
```

`npm run ci:certified` runs the ordinary CI suite and this external-corpus gate. The command exits
with `0` only when the corpus policy and every field comparison pass, `1` for a comparison or
coverage-policy failure, and `2` when the command cannot run or the registry/evidence is invalid.
It can emit a machine-readable report with `--output` using
`vedicdust-independent-reference-certification/1.0.0`.

The default release floor is twelve cases covering `ordinary`, `varga-boundary`,
`dasha-boundary`, `dst-or-offset-edge`, and `southern-hemisphere`. This is a product release floor,
not a statistical claim of universal equivalence. A release owner may raise the minimum or add
required tags, but may not lower the checked-in certified policy while describing the build as
VedicDust-certified.

No external desktop corpus is checked into this repository. Until controlled JHora or Parashara's
Light artifacts populate the registry and the certified command passes, desktop equivalence remains
unproven and affected calculation methods retain their declared provisional status.
