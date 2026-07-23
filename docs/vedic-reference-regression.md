# Vedic Reference Regression

This project now has a backend regression layer for the Vedic chart calculator.
It is intentionally separate from report-quality tests: these checks only answer
whether the computed chart data still matches the declared calculation profile.

## Calculation Profile

- Zodiac: sidereal
- Ayanamsa: `TRUE_CITRA` / True Chitrapaksha
- Nodes: mean Rahu/Ketu
- Rashi house mapping: whole sign from Lagna sign
- Ephemeris: Swiss Ephemeris through `pysweph`
- Varga, Ashtakavarga and Vimsottari reference: PyJHora, `chart_method=1`

## Test Layers

`backend/tests/test_vedic_reference_regression.py` performs three checks:

1. Swiss Ephemeris core positions
   - Compares ayanamsa, ascendant, seven classical planets, Rahu and Ketu
     directly against `swisseph`.
2. PyJHora Jyotish structures
   - Compares D4/D5/D9/D10 signs and degrees, SAV, and the first three
     Vimshottari Mahadashas against direct PyJHora calls.
3. Product snapshot fixture
   - Locks selected high-signal output fields from the current backend profile
     so unexpected drift is caught in CI.

The fixture lives at:

`backend/tests/fixtures/vedic_reference/reference_cases.json`

The current cases are adapted from PyJHora's bundled
`jhora.tests.book_chart_data` samples.

## What This Does Not Prove

This is not a claim that every astrologer or every software package will produce
identical results. Vedic software differs by ayanamsa, node mode, varga method,
house/bhava settings, sunrise conventions and dasha options.

This suite proves that the backend remains internally consistent with the
declared profile and with two external computation sources used by that profile:
Swiss Ephemeris and PyJHora.

## Future JHora Export Fixtures

For full product-grade parity, add a separate fixture set exported from
Jagannatha Hora v8.0 with the same settings:

- True Chitrapaksha / Lahiri-compatible ayanamsa
- Mean nodes
- Matching varga preferences
- Shadbala and Ashtakavarga tables included in the export

Those exported values should be stored as normalized JSON under
`backend/tests/fixtures/vedic_reference/jhora_exports/` and tested separately.
