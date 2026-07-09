# Vedic Skills Runtime

Web runtime for repo-local astrology skill workflows, with methodology skills
vendored into this repo under `.claude/skills`.

Version 1 intentionally does not add product-specific readings, daily notes,
claims, payment flows, or custom methodology. The goal is to expose the original
skills through a browser workspace while preserving their input/output contract:

```text
birth information
  -> vedic-calculator
  -> birth_input_context.json + sensitivity_scan.json + structured_data.md/json
  -> vedic-reader / vedic-core / vedic-career / vedic-love / vedic-rectifier
  -> original markdown artifacts

optional second chart
  -> structured_data_B.md
  -> synastry_data.md
  -> vedic-synastry reports/*

BaZi birth information
  -> bazi-calculator
  -> bazi_structured_data.md/json + bazi_report_context.md
  -> bazi-classics-core
  -> classical BaZi markdown artifacts
```

## Stack

- React + Vite frontend
- Python FastAPI backend
- Python `claude-agent-sdk` runtime pointed at a Claude-compatible DeepSeek API
- Repo-local `.claude/skills` as the source of truth for prompts, resources,
  workflow order, concepts, and output contracts
- Backend-owned Python calculator and workflow tools under `backend/app`
- Skill directories are grouped by top-level system category:
  `.claude/skills/vedic/*` for Vedic/Jyotish and `.claude/skills/bazi/*`
  for BaZi.

## Requirements

- Node.js 20+
- `uv`
- Python 3.11+ for this backend
- DeepSeek/Anthropic-compatible token in `.env`
- Clerk publishable key for the React app and a Clerk secret key for the backend
  token verifier
- `cloudflared` when testing Creem webhooks against the local backend

Example `.env`:

```env
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
VEDIC_AUTH_MODE=clerk
DEEPSEEK_API_KEY=...
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_MODEL=deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash
DATABASE_URL=sqlite+aiosqlite:///./backend/data/vedic.db
SUPABASE_PROJECT_REF=pkjtffyirhjpfpbyrfmu
SUPABASE_DB_PASSWORD=
```

`DATABASE_URL` defaults to local SQLite. Production can use a normal
Postgres/Supabase connection string; the backend normalizes it to
`postgresql+asyncpg://` at startup and stores only metadata in the database.
For the vedic Supabase project, set `SUPABASE_PROJECT_REF=pkjtffyirhjpfpbyrfmu`
and `SUPABASE_DB_PASSWORD`; when `DATABASE_URL` is not customized, the backend
will connect to `db.pkjtffyirhjpfpbyrfmu.supabase.co`.
Markdown, HTML, and PDF artifacts remain local files under
`backend/data/sessions/<session_id>/` with their paths indexed in the database.

## Contribution

This section is written for new contributors and coding agents starting from a
fresh checkout. It separates what can be automated by commands from the external
dashboard actions that still need a human.

### Safety Rules

- Do not commit `.env`, local databases, generated sessions, exported reports,
  or webhook tunnel URLs.
- Keep secrets in `.env` or the deployment platform's secret manager.
- Use local SQLite unless you intentionally need to test shared Supabase state.
- Use Creem test mode until checkout and webhook delivery are verified end to
  end.
- The repo-local `.claude/skills` directory is product methodology. Do not move
  environment setup, dependency installation, or server scripts into skills.

### Fresh Checkout

From the repo root:

```bash
npm install
cp .env.example .env
npm run report:pdf:install
npm run backend:setup
npm run backend:config
npm run dev
```

Before `npm run backend:config`, edit `.env` with real values for the mode you
want to test. A populated `.env` from another developer is also acceptable.

Effect:

- Installs frontend dependencies from `package-lock.json`.
- Creates/syncs the backend uv environment.
- Installs backend-owned astrology runtime dependencies into `backend/.venv`.
- Installs Playwright Chromium for PDF export.
- Validates `.env`, LLM config, Clerk config, and `claude-agent-sdk`.
- Starts FastAPI on `http://127.0.0.1:8787`.
- Starts Vite on `http://127.0.0.1:5173`.
- Creates a local SQLite database automatically on first backend startup.

If you only need UI-level work and do not have third-party keys yet, set
`VEDIC_AI_MODE=mock` and `VEDIC_AUTH_MODE=disabled` in `.env` before running the
backend config check.

### One-Command Local Product Run

After dependencies and `.env` are ready:

```bash
npm run dev
```

Use this for normal UI/backend work. It does not open a public webhook tunnel.

Open:

- App: `http://127.0.0.1:5173/`
- Account: `http://127.0.0.1:5173/account`
- Admin sessions: `http://127.0.0.1:5173/admin/sessions`
- Backend health: `http://127.0.0.1:8787/api/health`

### Environment Modes

Full AI mode:

```env
VEDIC_AI_MODE=
DEEPSEEK_API_KEY=...
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
ANTHROPIC_MODEL=deepseek-v4-pro[1m]
```

Effect: Vedic/BaZi report generation calls the Claude-compatible DeepSeek API
through `claude-agent-sdk`.

UI-only mode:

```env
VEDIC_AI_MODE=mock
```

Effect: the app can start without an LLM token, but full report quality and
agent-backed workflows are not representative.

No-login local mode:

```env
VEDIC_AUTH_MODE=disabled
```

Effect: backend user filtering is disabled and the local user acts as admin.
Use only for local debugging. Do not use this for payment, account isolation, or
production testing.

### Database Setup

Default local database:

```env
DATABASE_URL=sqlite+aiosqlite:///./backend/data/vedic.db
SUPABASE_DB_PASSWORD=
```

Effect:

- No external database is required.
- `backend/data/vedic.db` is created automatically.
- Tables are created on backend startup.
- Generated markdown, HTML, and PDF files are written under
  `backend/data/sessions/<session_id>/`.

Supabase/Postgres database:

```env
SUPABASE_PROJECT_REF=pkjtffyirhjpfpbyrfmu
SUPABASE_DB_PASSWORD=...
```

or:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require
```

Effect:

- The backend stores users, sessions, artifacts, exports, jobs, and billing
  metadata in Postgres.
- Artifact file contents still stay on the local filesystem for now.
- The database user must be allowed to create tables.

Current schema note: fresh databases are initialized by SQLAlchemy
`create_all()` during backend startup. This is acceptable for early development,
but production schema changes should move to explicit migrations before the
database becomes durable shared infrastructure.

### Clerk Authentication Setup

Required `.env` values:

```env
VEDIC_AUTH_MODE=clerk
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
VEDIC_ADMIN_USER_IDS=
VEDIC_ADMIN_EMAILS=
```

Effect:

- The React app initializes Clerk from `VITE_CLERK_PUBLISHABLE_KEY`.
- The backend validates decoded Clerk session subjects through Clerk Backend API
  using `CLERK_SECRET_KEY`.
- Sessions, jobs, exports, and billing records are isolated by Clerk user id.

Human actions:

1. Confirm the Clerk application allows local origins and redirects for
   `http://127.0.0.1:5173` and `http://localhost:5173`.
2. Start the app with `npm run dev`.
3. Sign up or sign in from the app UI.
4. For admin testing, copy the signed-in Clerk user id into
   `VEDIC_ADMIN_USER_IDS`, or set the email in `VEDIC_ADMIN_EMAILS`, then
   restart the backend.

Optional Clerk CLI project link:

```bash
clerk auth login
clerk init --app app_3G2qnI6QRzmAOMo7y6RqdOlWUIE
clerk doctor
```

Use the CLI when setting up or inspecting the Clerk project. The runtime itself
does not require every contributor to run `clerk init` if `.env` and the Clerk
Dashboard are already correct.

### Creem Payment Testing

Required local tool:

```bash
brew install cloudflared
```

Required `.env` values:

```env
CREEM_API_KEY=...
CREEM_WEBHOOK_SECRET=...
CREEM_TEST_MODE=true
CREEM_SUCCESS_URL=http://localhost:5173/account?billing=success
CREEM_PRODUCT_PRO_MONTHLY=prod_...
CREEM_PRODUCT_PRO_YEARLY=
CREEM_PRODUCT_SINGLE_REPORT=
```

Start payment testing:

```bash
npm run dev:payments
```

Effect:

- Starts the backend.
- Starts the frontend.
- Starts a Cloudflare quick tunnel to the local backend.
- Prints and saves the Creem webhook URL to:

```text
tmp/creem-webhook-url.txt
```

Human actions:

1. Copy the saved webhook URL.
2. In Creem Dashboard, create or update the test webhook endpoint.
3. Select these events:

```text
checkout.completed
subscription.active
subscription.paid
subscription.trialing
subscription.expired
subscription.paused
subscription.canceled
subscription.scheduled_cancel
subscription.past_due
refund.created
dispute.created
```

4. Copy the webhook secret from Creem Dashboard into `CREEM_WEBHOOK_SECRET`.
5. Restart or reload the backend.
6. Sign in to the app.
7. Open `/account`.
8. Click Upgrade and complete a Creem test checkout.
9. Return to `/account` and confirm paid access changed after webhook delivery.

Important: Cloudflare quick tunnel URLs are temporary. If
`npm run dev:payments` is restarted and the `trycloudflare.com` URL changes,
update the Creem Dashboard webhook URL again. The webhook secret must match the
configured Creem webhook endpoint.

### Report And PDF Testing

Install the browser used for PDF rendering once:

```bash
npm run report:pdf:install
```

Export a completed session:

```bash
npm run report:export -- <session_id>
```

Output:

```text
backend/data/sessions/<session_id>/exports/report.html
backend/data/sessions/<session_id>/exports/report.pdf
```

If PDF export fails on a fresh machine, rerun `npm run report:pdf:install` and
confirm Playwright Chromium is available.

### Workflow Testing

Fast local checks:

```bash
npm run check
npm run backend:config
npm run backend:check
npm run backend:test
npm run build
```

Full CI-equivalent check:

```bash
npm run ci
```

Effect:

- Prettier format check.
- Frontend ESLint.
- Python format and lint checks.
- TypeScript typecheck.
- Backend uv sync and runtime setup.
- Backend runtime check.
- Pyright typecheck.
- Backend tests.
- Frontend production build.

Full report-generation smoke test:

```bash
npm run workflow:test
```

Current limitation: this script talks directly to the backend API and does not
currently acquire a Clerk session token. For a real authenticated full-report
smoke test, either run through the browser UI while signed in, or temporarily set
`VEDIC_AUTH_MODE=disabled` in local `.env` and restart the backend. Do not use
disabled auth for production or payment validation.

### Commit Hooks

Install once per checkout:

```bash
uv run --no-sync --project backend pre-commit install
```

Effect: staged commits run whitespace checks, Prettier format checks, ESLint,
Python format/lint/type checks, TypeScript type checks, and backend tests.

### Port Conflicts

Default ports:

- Frontend: `5173`
- Backend: `8787`

If `8787` is already in use, stop the old uvicorn process before running
`npm run dev`. The current npm script starts uvicorn on `8787`, and the Vite
proxy also points `/api` to `8787`.

### Production Deployment Checklist

Minimum production shape:

1. Serve the Vite build from a stable HTTPS app host.
2. Run FastAPI as a long-lived service behind HTTPS.
3. Set production environment variables in the server or platform secret
   manager, not in git.
4. Use Postgres/Supabase instead of local SQLite.
5. Store `backend/data/sessions` on durable storage, or move artifacts to S3.
6. Set `CREEM_SUCCESS_URL=https://<app-host>/account?billing=success`.
7. Point Creem webhook to
   `https://<backend-host>/api/webhooks/creem`.
8. Use live Creem keys and live product IDs only after test checkout and webhook
   delivery are verified.
9. Use `VEDIC_AUTH_MODE=clerk`; never deploy with auth disabled.

For VPS deployments, use Caddy or Nginx to terminate TLS and proxy `/api` to
FastAPI on `127.0.0.1:8787`. If using Cloudflare Tunnel in production, use a
named tunnel with your own domain, not a quick `trycloudflare.com` tunnel.

## Authentication

The frontend uses `@clerk/clerk-react`. Set `VITE_CLERK_PUBLISHABLE_KEY` in the
project `.env`; it is safe for the browser. The backend verifies Clerk session
tokens without JWKS: it decodes Clerk JWT claims locally, requires a valid
non-expired `exp`, and confirms the decoded `sub` exists via Clerk Backend API
using `CLERK_SECRET_KEY`. The Clerk user id is stored as `owner_user_id` on
session, artifact, export, and job metadata.

For the Clerk CLI project link, run this from the repo root in a normal
terminal:

```bash
clerk auth login
clerk init --app app_3G2qnI6QRzmAOMo7y6RqdOlWUIE
clerk doctor
```

For local UI/backend testing without login, set `VEDIC_AUTH_MODE=disabled`.
That mode disables user-level filtering and should not be used for production.

## Billing And Webhooks

Creem checkout creation only needs `CREEM_API_KEY` and the relevant product ID.
Automatic paid access requires webhooks, so `CREEM_WEBHOOK_SECRET` must be set
before a completed payment can update local subscription state.

Local payment test flow:

1. Run `npm run dev:payments`.
2. Copy the URL printed by the `creem:webhook:tunnel` process.
3. In Creem Dashboard > Developers/Webhooks, create or update the webhook URL.
4. Copy the webhook secret into `.env` as `CREEM_WEBHOOK_SECRET`.
5. Restart or reload the backend.
6. Complete a Creem test checkout from the account page.

Recommended local webhook events:

```text
checkout.completed
subscription.active
subscription.paid
subscription.trialing
subscription.expired
subscription.paused
subscription.canceled
subscription.scheduled_cancel
subscription.past_due
refund.created
dispute.created
```

You do not need a domain for local testing. The `trycloudflare.com` URL is good
enough for short-lived test sessions. Do not use quick tunnels for production.

Production billing setup:

- Host the backend on a stable public HTTPS URL.
- Point the Creem webhook to
  `https://<backend-host>/api/webhooks/creem`.
- Set `CREEM_SUCCESS_URL` to the production frontend account page, for example
  `https://<app-host>/account?billing=success`.
- Keep `CREEM_API_KEY`, `CREEM_WEBHOOK_SECRET`, Clerk keys, LLM keys, and
  database credentials in server environment variables, not in git.
- Use live Creem keys and live product IDs only after test checkout and webhook
  delivery are verified end to end.

If deploying on a VPS, use Caddy or Nginx to terminate TLS and proxy `/api` to
the FastAPI service on `127.0.0.1:8787`, while serving the Vite build from
`dist/client`. If you prefer Cloudflare Tunnel in production, use a named tunnel
with your own domain, not an accountless quick tunnel:

```bash
cloudflared tunnel login
cloudflared tunnel create vedic-prod
cloudflared tunnel route dns vedic-prod api.example.com
cloudflared tunnel run vedic-prod
```

## Run

```bash
npm install
npm run report:pdf:install
npm run backend:setup
npm run backend:config
npm run dev
```

Frontend: `http://127.0.0.1:5173/`

Backend: `http://127.0.0.1:8787/`

Admin sessions console: `http://127.0.0.1:5173/admin/sessions`

For local Creem payment testing, run:

```bash
npm run dev:payments
```

This starts the backend, frontend, and a Cloudflare quick tunnel to the backend.
The tunnel command prints and saves the Creem webhook URL to:

```text
tmp/creem-webhook-url.txt
```

Use that URL in the Creem Dashboard webhook settings. Quick tunnel URLs are
temporary; if you restart the tunnel, update the Dashboard webhook URL.

If port `8787` is already in use, stop the old uvicorn process before running
`npm run dev`. The current npm script starts uvicorn on `8787`, and the Vite
proxy also points `/api` to `8787`.

`npm run backend:config` checks startup-only requirements before uvicorn starts:
`.env`, LLM auth, Claude-compatible base URL, model name, and
`claude-agent-sdk`. If it fails, copy `.env.example` to `.env`, set
`DEEPSEEK_API_KEY=...`, then run `npm run dev` again. For UI-only local testing
without an LLM, set `VEDIC_AI_MODE=mock`.

## Checks

```bash
npm run ci
npm run format
npm run format:check
npm run frontend:lint
npm run backend:sync
npm run backend:setup
npm run backend:format
npm run backend:format:check
npm run backend:lint
npm run backend:typecheck
npm run check
npm run backend:config
npm run backend:check
npm run backend:test
npm run build
```

Install local commit hooks once per checkout:

```bash
uv run --no-sync --project backend pre-commit install
```

The configured hook runs staged whitespace checks, Prettier format checks,
ESLint, Python format/lint/type checks, TypeScript type checks, and backend
tests before commits. Pull requests run the same core checks in GitHub Actions.

`npm run backend:dev` runs `backend:ensure` before starting uvicorn. The backend
startup preflight fails fast if calculator dependencies, PyJHora data, bundled
ephemeris files, `.env`, or LLM settings are not ready. Run
`npm run backend:setup` after a fresh clone or whenever `backend/.venv` is
rebuilt.

## Report Export

Export a completed session's public markdown artifacts into a themed HTML report
and a Playwright-rendered PDF:

```bash
npm run report:export -- <session_id>
```

Output defaults to:

```text
backend/data/sessions/<session_id>/exports/report.html
backend/data/sessions/<session_id>/exports/report.pdf
```

PDF rendering uses Chromium through Playwright, so fresh machines must run:

```bash
npm run report:pdf:install
```

## API Surface

- `GET /api/health`
- `GET /api/places`
- `GET /api/precise-places`
- `POST /api/skill-sessions`
- `GET /api/skill-sessions/{session_id}`
- `GET /api/skill-sessions/{session_id}/report.pdf`
- `GET /api/admin/sessions`
- `GET /api/admin/sessions/{session_id}`
- `POST /api/core-jobs`
- `GET /api/core-jobs/{job_id}`
- `POST /api/skill-synastry-subject`
- `POST /api/skill-runs`
- `POST /api/skill-feedback`

`GET /api/precise-places` searches the local GeoNames city index first. Pass the
selected city as `city=...` when searching for a hospital, district, landmark, or
address. The backend treats that city as the verification base: AMap, agent,
and web-search candidates are only returned when their coordinates stay within
the city's accepted distance band; otherwise the response falls back to the
city center and marks the result as `city-fallback`. If
`AMAP_PLACE_FALLBACK_ENABLED=true` with `AMAP_WEB_SERVICE_KEY` set, AMap POI
results are normalized from GCJ-02 to WGS84. When the LLM agent runtime is
configured, unresolved POI queries call an agent WebSearch/WebFetch task before
the deterministic web fallback. `WEB_PLACE_SEARCH_ENABLED=true` adds a final
best-effort web search fallback that extracts coordinate evidence from
search-result text and still requires city-distance verification before use.

## Alignment Rules

- `.claude/skills/<category>/*` is committed with this app and is the
  prompt/resource source for the skill workflows. Current first-level
  categories include `vedic` and `bazi`.
- Skills only contain workflow, prompts, concepts, definitions, and output
  rules. They must not install dependencies, create venvs, or own service
  runtime scripts.
- Backend owns calculator code, dependency setup, startup preflight, and tool
  scripts. Runtime defaults point at the repo-local `.claude/skills`;
  `VEDIC_ASTRO_SKILLS_ROOT` is only an advanced prompt/resource override.
- Claude Agent SDK receives backend tools through the in-process
  `vedic_backend_tools` MCP server; it is not allowed to run arbitrary Bash.
- `structured_data.md` is generated by the backend calculator using the original
  formatter contract and remains the skill/LLM prompt artifact.
- `structured_data.json` is generated alongside it as the canonical
  machine-readable chart fact schema (`vedic-chart-facts/v1`) for validators,
  backend tools, and future deterministic rule engines.
- `birth_input_context.json` records the original birth-time/place facts,
  resolved coordinates, timezone, coordinate source, place accuracy, radius, and
  rectification guardrails.
- `sensitivity_scan.json` records small-sample time/place perturbation checks.
  Reader/core workflows use it to decide whether prevalidation should validate a
  single chart or first shrink uncertain time/place candidates. It also exposes
  `candidateGroups`, `stability`, `reportReadiness`, and an `llmContract` so
  downstream LLM steps know which chart factors may be used as primary evidence
  and which factors must be downgraded or omitted.
- Aspect facts use Vedic whole-sign contact + Graha Drishti. Western
  degree-angle aspects are not part of the calculation fact source.
- Skill outputs stay as markdown artifacts with the original file names.
- `vedic-core` is advanced in original phase batches; click/run it repeatedly
  until `core_complete`.
- The JSON wrapper used between backend and Claude Agent SDK is transport only;
  users see the original-style markdown files.
- `user_context.md` is created only from explicit feedback or user additions.
