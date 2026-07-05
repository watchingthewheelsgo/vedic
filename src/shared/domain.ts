export type BirthTimePrecision = "exact" | "approximate" | "part_of_day" | "unknown";
export type AppLocale = "zh" | "en" | "ja";

export type PlaceSearchLevel = "country" | "region" | "city";

export type PlaceOption = {
  id: string;
  label: string;
  value: string;
  meta?: string;
  country?: string;
  region?: string;
  birthPlace?: string;
};

export type PlaceSearchResponse = {
  options: PlaceOption[];
};

export type BirthInput = {
  birthDate: string;
  birthTime: string;
  birthPlace: string;
  birthTimePrecision: BirthTimePrecision;
  gender: string;
  relationship: string;
  timeSource: string;
  locale?: AppLocale;
};

export type SkillBirthInput = BirthInput;

export type SkillName =
  | "vedic-reader"
  | "vedic-core"
  | "vedic-career"
  | "vedic-love"
  | "vedic-rectifier"
  | "vedic-synastry";

export type SkillArtifact = {
  path: string;
  title: string;
  content: string;
  kind: "markdown" | "text" | "json";
  updatedAt: string;
};

export type SkillSessionStage =
  | "reader_ready"
  | "reader_validation"
  | "core_in_progress"
  | "core_complete"
  | "career_complete"
  | "love_complete"
  | "rectifier_complete"
  | "synastry_ready"
  | "synastry_complete"
  | "qa_complete"
  | "error";

export type SkillSessionResponse = {
  sessionId: string;
  stage: SkillSessionStage;
  chatMessage: string;
  artifacts: SkillArtifact[];
  activeArtifact?: string | null;
};

export type SkillRunInput = {
  sessionId: string;
  skill: SkillName;
  userMessage?: string;
  locale?: AppLocale;
};

export type CoreJobStatus = "queued" | "running" | "completed" | "failed";
export type CoreJobNodeStatus = "pending" | "running" | "completed" | "skipped" | "failed";

export type CoreJobNode = {
  id: string;
  label: string;
  files: string[];
  dependencies: string[];
  wave: number;
  status: CoreJobNodeStatus;
  startedAt?: string | null;
  finishedAt?: string | null;
  durationSeconds?: number | null;
  error?: string | null;
};

export type CoreJobProgress = {
  total: number;
  completed: number;
  running: number;
  failed: number;
  percent: number;
};

export type CoreJobWave = {
  wave: number;
  total: number;
  completed: number;
  running: number;
  failed: number;
  durationSeconds?: number | null;
};

export type CoreJobResponse = {
  jobId: string;
  sessionId: string;
  status: CoreJobStatus;
  message: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  durationSeconds?: number | null;
  progress: CoreJobProgress;
  waves: CoreJobWave[];
  nodes: CoreJobNode[];
  session?: SkillSessionResponse | null;
};

export type AdminSessionStatus =
  "draft" | "validation" | "queued" | "running" | "completed" | "failed" | "stalled";

export type AdminSessionProgress = {
  total: number;
  completed: number;
  running: number;
  failed: number;
  percent: number;
};

export type AdminArtifactSummary = {
  path: string;
  kind: "markdown" | "json" | "text" | "html" | "pdf" | "other";
  sizeBytes: number;
  updatedAt: string;
};

export type AdminExportSummary = {
  name: string;
  path: string;
  mediaType: string;
  sizeBytes: number;
  updatedAt: string;
};

export type AdminSubjectSummary = {
  birthDate?: string | null;
  birthTime?: string | null;
  birthPlace?: string | null;
  timePrecision?: string | null;
  timeSource?: string | null;
  timezone?: string | null;
  gender?: string | null;
  relationship?: string | null;
};

export type AdminSessionSummary = {
  sessionId: string;
  status: AdminSessionStatus;
  stage: string;
  createdAt?: string | null;
  updatedAt?: string | null;
  subject?: AdminSubjectSummary | null;
  progress: AdminSessionProgress;
  artifactCount: number;
  exportCount: number;
  hasPdf: boolean;
  jobId?: string | null;
  activeNode?: string | null;
  durationSeconds?: number | null;
  error?: string | null;
};

export type AdminSessionListResponse = {
  sessions: AdminSessionSummary[];
  total: number;
  running: number;
  completed: number;
  failed: number;
};

export type AdminSessionDetailResponse = {
  summary: AdminSessionSummary;
  session: SkillSessionResponse;
  artifacts: AdminArtifactSummary[];
  exports: AdminExportSummary[];
  runMetrics?: Record<string, unknown> | null;
  manifest?: Record<string, unknown> | null;
  activeJob?: CoreJobResponse | null;
};

export type SkillFeedbackInput = {
  sessionId: string;
  feedbackMarkdown: string;
};

export type SynastryBirthInput = {
  sessionId: string;
  label: string;
  relationshipType?: string;
  currentStage?: string;
  question?: string;
  birth: BirthInput;
};
