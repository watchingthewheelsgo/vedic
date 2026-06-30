# TODO

## Resume Point: `vedic-core` Runtime Reliability

Current status:

- `vedic-reader` has been verified end-to-end with DeepSeek Claude-compatible Agent SDK.
- `vedic-synastry` preflight has been verified: B chart generation, validation script, `synastry_data.md`, and `reports/00_signal_triage.md`.
- `vedic-core` P1 has produced `p1_overview.md` successfully.
- `vedic-core` P2A (`p2a_planets.md`) still timed out with HTTP 500 and empty `detail`.
- The current implementation now advances `vedic-core` one original file per call, but P2A still needs prompt/context reduction before it is reliable.

Next steps:

1. Reduce `vedic-core` P2A prompt/context size.
   - Only pass `structured_data.md` plus `p1_overview.md` for P2A.
   - Do not pass `reader_prevalidation.md` or `user_context.md` to P2A.
   - Consider extracting only the needed structured data sections for Sun/Moon/Yoga pre-scan.

2. Re-run P2A until it reliably creates `p2a_planets.md`.
   - Verify response stage is `core_in_progress`.
   - Verify active artifact is `p2a_planets.md`.
   - Verify markdown is not a placeholder.

3. Continue one-file validation for the rest of original `vedic-core` outputs:
   - `p2b_planets.md`
   - `p2c_planets.md`
   - `p2d_planets.md`
   - `p3a_d9.md`
   - `p3b_divisional.md`
   - `p4a_houses.md`
   - `p4b_houses.md`
   - `p5a_life.md`
   - `p5b_life.md`
   - `appendix.md`

4. Improve UI progress for repeated `vedic-core` runs.
   - Show which core artifact is next.
   - Keep the current button label as a step action, not a one-click full report promise.

5. After core is stable, smoke-test `vedic-career`, `vedic-love`, and `vedic-rectifier`.

Useful commands:

```bash
npm run check
npm run backend:check
npm run build
curl -s http://127.0.0.1:8787/api/health
```
