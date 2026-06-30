# Architecture

The app is a browser workspace for `vedic-astro-skills`. It does not define a
new astrology methodology in v1.

## Boundaries

Frontend responsibilities:

- collect the same birth fields requested by `vedic-calculator`
- provide country / region / city search for place selection
- show session stage, chat-box output, and markdown artifacts
- collect reader feedback into `user_context.md`
- prepare B chart input for `vedic-synastry`

Backend responsibilities:

- resolve birth place to lat/lon/time zone
- call the original calculator engine and formatter
- persist session artifacts under `backend/data/sessions/<session>`
- call original synastry scripts for `synastry_data.md`
- invoke Claude Agent SDK with the selected original skill

The original skills remain authoritative for phase order, prompts, file names,
and markdown style.

## Runtime Flow

```text
POST /api/skill-sessions
  BirthInput
  -> VedicCalculator.calculate()
  -> structured_data.md

POST /api/skill-runs
  sessionId + skill name + optional userMessage
  -> ClaudeRuntime.run_skill_prompt_task()
  -> markdown artifacts written to the session workspace

POST /api/skill-feedback
  sessionId + feedbackMarkdown
  -> user_context.md

POST /api/skill-synastry-subject
  sessionId + B BirthInput + optional intake
  -> structured_data_B.md
  -> validate_synastry_data.py
  -> build_synastry_data.py
  -> synastry_data.md
```

## Important Files

- `backend/app/services/vedic_calculator.py`
- `backend/app/services/skill_runtime.py`
- `backend/app/services/skill_workspace.py`
- `backend/app/agents/claude_runtime.py`
- `src/client/App.tsx`
- `.claude/skills/*`

## Agent Contract

The backend currently uses a transport JSON wrapper:

```json
{
  "chatMessage": "short progress or next-step message",
  "artifacts": [
    {
      "path": "original_file_name.md",
      "content": "complete markdown"
    }
  ]
}
```

The wrapper is not product output. It exists only so the backend can persist
artifacts predictably after an Agent SDK run.

## Non-Goals For V1

- no payment or checkout flow
- no app-specific report cards
- no daily recommendation product flow
- no custom claim schema
- no replacement methodology for the copied skills
