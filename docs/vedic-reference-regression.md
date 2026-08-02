# Vedic Reference Regression

This project now has a backend regression layer for the Vedic chart calculator.
It is intentionally separate from report-quality tests: these checks only answer
whether the computed chart data still matches the declared calculation profile.

## Calculation Profile

- Zodiac: sidereal
- Ayanamsa: Lahiri (`swe.SIDM_LAHIRI` and PyJHora `LAHIRI`)
- Nodes: mean Rahu/Ketu
- Rashi house mapping: whole sign from Lagna sign
- Ephemeris: Swiss Ephemeris through `pysweph`
- Planet position model: geocentric apparent positions with
  `FLG_SWIEPH | FLG_SIDEREAL | FLG_SPEED`; the same flags are installed into
  every PyJHora adapter before calculation
- Varga reference: PyJHora with the per-varga methods recorded in the
  Calculation Profile (`D2 chart_method=2`; the other supported PyJHora
  vargas use their factor-specific `chart_method=1`)
- Ashtakavarga and Vimshottari reference: pinned PyJHora adapters
- Runtime: exact distribution versions pinned by `backend/astrology-runtime.lock`;
  every Chart Record stores provider versions, IANA/tzdb version, and a SHA-256
  fingerprint of the active ephemeris files

## Test Layers

`backend/tests/test_vedic_reference_regression.py` performs four checks:

1. Swiss Ephemeris core positions
   - Compares ayanamsa, ascendant, seven classical planets, Rahu and Ketu
     directly against `swisseph`.
2. PyJHora Jyotish structures
   - Compares D1, D2, D3, D4, D5, D7, D9, D10, D12, D16, D20, D24, D27,
     D30, and D60 signs and degrees, SAV, and the first three Vimshottari
     Mahadashas against direct PyJHora calls.
   - Requires canonical Swiss and PyJHora D1 longitudes to agree within 0.5
     arcseconds for every pinned reference case, preventing a silent mix of
     apparent and true/geometric coordinates.
3. Product snapshot fixture
   - Locks selected high-signal output fields from the current backend profile
     so unexpected drift is caught in CI.
4. Runtime provenance
   - Confirms the provider versions match the runtime lock and that the active
     ephemeris directory has a non-empty SHA-256 fingerprint.

The fixture lives at:

`backend/tests/fixtures/vedic_reference/reference_cases.json`

The current cases are adapted from PyJHora's bundled
`jhora.tests.book_chart_data` samples.

## What This Does Not Prove

This is not a claim that every astrologer or every software package will produce
identical results. Vedic software differs by ayanamsa, node mode, varga method,
house/bhava settings, sunrise conventions and dasha options.

This suite demonstrates that the backend remains internally consistent with the
declared profile and with two computation providers used by that profile: Swiss
Ephemeris and PyJHora. Because the adapter and direct-reference paths still use
the same provider libraries, this is compatibility evidence, not an independent
astrologer or commercial-software gold standard.

## Future JHora Export Fixtures

For full product-grade parity, add a separate fixture set exported from
Jagannatha Hora v8.0 with the same settings:

- Lahiri ayanamsa with the exact displayed value recorded
- Mean nodes
- Matching varga preferences
- Shadbala and Ashtakavarga tables included in the export

Those exported values should be stored as normalized JSON under
`backend/tests/fixtures/vedic_reference/jhora_exports/` and tested separately.
