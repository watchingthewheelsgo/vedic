# Vedic Skills Runtime

This project runs the original `vedic-astro-skills` workflow inside a web
runtime. Version 1 must preserve the original skill behavior as closely as
possible. The repo-local `.claude/skills` directory is the runtime source of
truth; do not depend on a sibling checkout for normal app behavior.

Rules:

- Use the original `vedic-reader`, `vedic-core`, `vedic-career`, `vedic-love`,
  `vedic-rectifier`, `vedic-calculator`, and `vedic-synastry` skills.
- Preserve original file names, phase order, markdown style, and chat-progress
  behavior.
- Treat `structured_data.md` as the calculation source of truth.
- Do not add app-specific claims, daily notes, checkout flows, cards, JSON
  report sections, or extra frameworks.
- The web app may wrap outputs for transport, but the user-facing artifact
  content must remain the original skill-style markdown.
