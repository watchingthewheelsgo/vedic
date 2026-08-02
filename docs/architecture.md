# VedicDust Architecture

VedicDust separates deterministic Jyotish data from probabilistic language work. The
backend owns canonicalization, calculation, provenance, workflow state, deterministic
judgement publication, validation, and report rendering. Skills can ask bounded questions
or arrange approved Claims; they cannot create chart facts or bypass a release gate.

## Pipeline

```text
Birth Assertion
  -> Place Resolution + Historical Timezone
  -> Canonical Birth Moment
  -> Astronomy Snapshot + Varga Calculations
  -> Chart Record
  -> Chart Audit
  -> Rectification Record + Calibration/Holdout Decision (when required)
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
- show resolved place, coordinates, timezone, chart status, structured dated-event intake,
  optional scan-stable quality questions, and report;
- submit explicit quality feedback without turning it into calculated evidence.

Backend:

- resolve WGS84 coordinates and historical civil time;
- run Swiss Ephemeris and PyJHora through one declared Calculation Profile;
- create and validate typed VedicDust artifacts;
- keep calculation assurance separate from birth-input stability and expose the
  lower grade as effective judgement confidence;
- retain the completed input-sensitivity summary in Chart Record and bind every
  fact to canonical sensitivity dependencies, so a Lagna boundary cannot suppress
  invariant graha evidence or leave dependent strength evidence unrestricted;
- control rectification and report workflow transitions;
- publish evidence-linked Claims from immutable Judgement Conclusions;
- bind every Claim certainty to the lowest applicable rule, input, rectification,
  fact, and timing-provider confidence cap;
- materialize report identity, scope, confidence, audience, section presentation,
  omission language, unresolved questions, and timing windows from authoritative
  contracts rather than model prose;
- expose only eligible evidence to each Agent step;
- render approved reports deterministically.

Skills:

- produce neutral reading-quality questions from scan-stable facts;
- organize an approved Consultation Dossier;
- answer later questions from `agent_context.json` with Chart Record verification
  and explicit subject age, life-stage, reader-relationship, and birth-date framing.

## Runtime Entry Points

```text
POST /api/skill-sessions
  -> birth_input_context.json
  -> sensitivity_scan.json
  -> chart_record.json
  -> chart_audit.json
  -> reading_session.json

POST /api/skill-feedback
  -> Reader quality feedback for a scan-stable chart
  -> quality gate only; never candidate selection or chart revision

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
