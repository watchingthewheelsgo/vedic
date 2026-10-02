# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Two CLAUDE.md files — keep them separate

- `.claude/CLAUDE.md` and `.claude/skills/{vedic,bazi}/*` are **product runtime prompts**.
  The backend's `claude-agent-sdk` runtime (`backend/app/agents/claude_runtime.py`) loads
  them via `setting_sources=["project"]` with `cwd` at the repo root, both locally and in the
  production container (`/app`). Skills are product methodology: don't put dev setup,
  dependency installation, or server scripts there.
- This root `CLAUDE.md` is developer guidance only. It is listed in `.dockerignore` so it never
  reaches the production image and product agents. Keep that entry in place.

## Commands

All commands run from the repo root. The backend uses `uv` with the project at `backend/`.

```bash
npm install && npm run backend:setup   # frontend deps + uv sync + pinned astrology providers
npm run report:pdf:install             # Playwright Chromium for PDF export
npm run backend:config                 # validate .env / LLM / Clerk / claude-agent-sdk
npm run dev                            # FastAPI :8787 (reload) + Vite :5173 (proxies /api)
npm run dev:payments                   # also opens a Cloudflare quick tunnel for Creem webhooks
```

Checks (`npm run ci` runs everything, the same as `.github/workflows/ci.yml`):

```bash
npm run format:check / npm run format          # Prettier (whole repo)
npm run frontend:lint                          # ESLint
npm run frontend:test                          # node --test on src/client/lib/*.test.ts
npm run check                                  # tsc --noEmit
npm run backend:format / backend:format:check  # ruff format
npm run backend:lint                           # ruff check
npm run backend:typecheck                      # pyright
npm run backend:check                          # runtime/provider check + compileall
npm run backend:test                           # pytest backend/tests
npm run build
```

Single tests:

```bash
uv run --no-sync --project backend pytest backend/tests/test_vedicdust_contracts.py::test_generated_json_schemas_are_current
node --import tsx --test src/client/lib/workspace.test.ts
```

Other useful scripts:

- `npm run backend:calculator-sync` / `backend:calculator-check`: install or verify the exact
  calculation providers pinned in `backend/astrology-runtime.lock`. That lock is separate from
  `backend/uv.lock`, and startup fails on version drift.
- `uv run --no-sync --project backend python scripts/export-vedicdust-schemas.py`: regenerate
  `docs/vedicdust/schemas/` after changing `backend/app/vedicdust/models.py`. A test fails if
  the committed schemas are stale.
- `npm run report:export -- <session_id>`: write the HTML/PDF report under
  `backend/data/sessions/<id>/exports/`.
- `npm run workflow:test`: end-to-end report smoke test against a running backend. It needs
  `VEDIC_WORKFLOW_AUTH_TOKEN`; see the README for the event fixture env vars. Never disable
  auth to make it pass.
- `npm run ci:certified`: `ci` plus independent-reference certification.

Local modes in `.env`: `VEDIC_AI_MODE=mock` runs without an LLM token, and
`VEDIC_AUTH_MODE=disabled` skips Clerk and makes the local user admin. Use both for local
debugging only. The LLM is DeepSeek behind an Anthropic-compatible `ANTHROPIC_BASE_URL`.

## Architecture

The product is called Sign Atlas (Vedic astrology, BaZi, daily Tarot and journaling). VedicDust is
its Jyotish evidence pipeline. Stack: React 19 + Vite + Tailwind 4 + Clerk on the frontend
(`src/client`), FastAPI + SQLAlchemy async on the backend (`backend/app`), and Creem for billing.

### Core principle: deterministic backend, bounded skills

Deterministic code owns place/timezone canonicalization, astronomical calculation,
provenance, workflow gates, judgement publication, validation and report rendering. LLM skills
only ask bounded questions or arrange already-approved Claims. They must never create chart
facts or bypass a release gate. `docs/architecture.md` describes the boundaries, and
`CONTEXT.md` defines the domain vocabulary (Birth Assertion, Calculation Profile,
Jyotish Fact, Judgement Conclusion, Claim, Consultation Dossier and so on). Use those terms
exactly.

Pipeline (each artifact after the Chart Record references `chartRecordId` + revision.
Recalculation bumps the revision and invalidates dependent checkpoints):

```text
birth input -> canonical moment -> chart_record.json + chart_audit.json
  -> rectification (when required; calibration/holdout events, Candidate Intervals)
  -> judgement_context.json -> claim_graph.json -> consultation_dossier.json
  -> consultation_report.md + agent_context.json
optional: chart_record_B.json -> synastry_context.json -> relationship_consultation.md
BaZi (separate namespace): bazi-calculator -> bazi_chart_record.json -> bazi-classics-core
```

### Backend layout (`backend/app`)

- `main.py`: FastAPI routes (`/api/skill-sessions`, `/api/core-jobs`,
  `/api/skill-synastry-subject`, `/api/webhooks/creem`, admin and account routes).
- `calculator/`: Swiss Ephemeris + PyJHora adapters (dashas, vargas, shadbala, ashtakavarga,
  KP), civil time and provider provenance.
- `vedicdust/`: domain core. `models.py` holds the Pydantic executable contracts. Also here:
  fact catalog, rule engine, judgement kernel, claims, confidence caps (calculation assurance
  vs. input stability, effective = lower), sensitivity, rectification policy, synastry and
  reporting. Versioned resources live in `vedicdust/resources/*.json`.
- `services/`: workflow orchestration. `skill_runtime.py` drives the agent/skill steps;
  `core_job_runtime.py` runs core report jobs; other modules cover rectification
  interview/confirmation, place lookup, session storage (local or S3), billing, memberships,
  AI allowance, daily journal and feedback.
- `agents/claude_runtime.py`: `claude-agent-sdk` wrapper that runs repo-local skills. Agent
  output is a transport wrapper; only explicitly allowed file content is accepted back.
- `tools/`: backend tools exposed to agents (BaZi calculator, rectifier, synastry, reporting).
- `db/`: SQLAlchemy models and engine. The database stores metadata only. Artifact files live
  under `backend/data/sessions/<session_id>/` (or S3). The schema comes from `create_all` by
  default; set `DATABASE_SCHEMA_MODE=migrations` to use Alembic (`backend/alembic/versions/`).
  When you change `db/models.py`, add a migration.

The runtime indexes, displays and exports only artifacts declared by the current VedicDust
contract. Don't introduce undeclared artifact types.

### Frontend (`src/client`)

`screens/` holds the route-level pages (Landing, Intake, Session, Daily, BaziWorkshop,
Account, Admin*). `lib/` holds the pure state and domain helpers, which are the unit-tested
part. `api.ts` is the backend client, and `i18n/` holds the Chinese and English strings.

## Repo conventions

- Python: ruff line length 100, target py311. Frontend and Markdown are formatted by Prettier.
  Pre-commit hooks (`uv run --no-sync --project backend pre-commit install`) run the
  CI checks on commit.
- Don't commit `.env`, local databases, `backend/data/sessions`, exported reports or tunnel URLs.
- Deployment: `DEPLOYMENT.md`, `docs/vps-deployment.md`, `deploy.sh` and `compose.*.yml`.
