# VedicDust Architecture

VedicDust separates deterministic Jyotish data from probabilistic language work. The
backend owns canonicalization, calculation, provenance, workflow state, validation, and
report rendering. Skills can ask bounded questions or formulate evidence-linked claims;
they cannot create chart facts or bypass a release gate.

## Pipeline

```text
Birth Assertion
  -> Place Resolution + Historical Timezone
  -> Canonical Birth Moment
  -> Astronomy Snapshot + Varga Calculations
  -> Chart Record
  -> Chart Audit
  -> Rectification Record and Question Rounds (when required)
  -> Judgement Context
  -> Claim Graph
  -> Consultation Dossier
  -> Consultation Report + Agent Context
```

Every artifact after the Chart Record references the active `chartRecordId` and revision.
Recalculation preserves chart identity, increments revision, and invalidates dependent
checkpoints.

## Responsibility Boundaries

Frontend:

- collect birth date, time certainty, city, optional precise place, and consultation scope;
- show resolved place, coordinates, timezone, chart status, rectification questions, and report;
- submit explicit feedback without turning it into calculated evidence.

Backend:

- resolve WGS84 coordinates and historical civil time;
- run Swiss Ephemeris and PyJHora through one declared Calculation Profile;
- create and validate typed VedicDust artifacts;
- control rectification and report workflow transitions;
- expose only eligible evidence to each Agent step;
- render approved reports deterministically.

Skills:

- produce neutral rectification language from engine-provided discriminators;
- formulate claims from the Judgement Context and registered rules;
- organize an approved Consultation Dossier;
- answer later questions from `agent_context.json` with Chart Record verification.

## Runtime Entry Points

```text
POST /api/skill-sessions
  -> birth_input_context.json
  -> sensitivity_scan.json
  -> chart_record.json
  -> chart_audit.json
  -> reading_session.json

POST /api/skill-feedback
  -> typed rectification answers
  -> candidate update or chart revision

POST /api/skill-runs (vedic-core)
  -> judgement_context.json
  -> claim_graph.json
  -> consultation_dossier.json
  -> consultation_report_manifest.json
  -> consultation_report.md
  -> agent_context.json

POST /api/skill-synastry-subject
  -> synastry_<B>_<date>/chart_record_B.json
  -> synastry_<B>_<date>/synastry_context.json
  -> synastry_<B>_<date>/reports/relationship_consultation.md
```

## Contracts

Pydantic models in `backend/app/vedicdust/models.py` are the executable contracts. Their
committed JSON Schemas live in `docs/vedicdust/schemas/`. The source registry, Calculation
Profile, Rule Catalog, and Fact Catalog are versioned inputs to validation.

The transport wrapper returned by an Agent is not a domain artifact. It only carries a
short progress message and the explicitly allowed file content back to the backend.

## Artifact Boundary

The runtime indexes, displays, and exports only artifacts declared by the current
VedicDust contract. BaZi has a separate schema and artifact namespace.
