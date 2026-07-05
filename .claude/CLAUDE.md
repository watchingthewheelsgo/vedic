# Vedic Skills Runtime

This project runs repo-local astrology skill workflows inside a web runtime.
Version 1 must preserve the original Vedic skill behavior as closely as
possible. The repo-local `.claude/skills` directory is the runtime source of
truth; do not depend on a sibling checkout for normal app behavior.

Skill categories:

- `.claude/skills/vedic/*` contains Vedic/Jyotish skills.
- `.claude/skills/bazi/*` contains BaZi skills.

Rules:

- Use the original `vedic-reader`, `vedic-core`, `vedic-career`, `vedic-love`,
  `vedic-rectifier`, `vedic-calculator`, and `vedic-synastry` skills.
- Use `bazi-calculator` for backend-generated BaZi chart facts and prompt
  artifacts.
- Use `bazi-classics-core` for BaZi reports based on the three classical
  sources and `bazi-calculator` artifacts.
- Preserve original file names, phase order, markdown style, and chat-progress
  behavior.
- Treat `structured_data.md` as the calculation source of truth.
- Do not add app-specific claims, daily notes, checkout flows, cards, JSON
  report sections, or extra frameworks.
- The web app may wrap outputs for transport, but the user-facing artifact
  content must remain the original skill-style markdown.
