# VedicDust Runtime

This project runs a product-owned Jyotish evidence pipeline. The backend owns
canonicalization, calculation, schema validation, workflow gates, and report rendering.
Repo-local skills own only their declared interpretation or dialogue task.

Skill categories:

- `.claude/skills/vedic/*` contains Vedic/Jyotish skills.
- `.claude/skills/bazi/*` contains BaZi skills.

Rules:

- Use the VedicDust contracts and repo-local skills for Vedic workflows.
- Use `bazi-calculator` for backend-generated BaZi chart facts and prompt
  artifacts.
- Use `bazi-classics-core` for BaZi reports based on the three classical
  sources and `bazi-calculator` artifacts.
- Treat `chart_record.json` as the deterministic calculation source of truth.
- Generate and consume only artifacts declared by the current VedicDust contracts.
- Claims must reference eligible fact IDs and registered rules, pass counter-evidence and
  audience checks, and be released through the Consultation Dossier.
