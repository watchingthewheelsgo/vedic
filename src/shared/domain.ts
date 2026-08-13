export type BirthTimePrecision = "exact" | "approximate" | "part_of_day" | "unknown";
export type ReportedTimeWindow = {
  minutesBefore: number;
  minutesAfter: number;
  basis: "user_certainty_choice" | "user_custom_range";
};
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
  latitude?: number;
  longitude?: number;
  timezone?: string;
  searchText?: string;
};

export type PlaceSearchResponse = {
  options: PlaceOption[];
};

export type PrecisePlaceAccuracy = "city" | "poi" | "address" | "district" | "coordinate";

export type PrecisePlaceSource = "geonames-local" | "amap" | "agent" | "manual";

export type PrecisePlaceVerificationStatus = "verified" | "city-fallback" | "unverified" | "manual";

export type PrecisePlaceOption = {
  id: string;
  label: string;
  address?: string | null;
  meta?: string | null;
  source: PrecisePlaceSource;
  accuracy: PrecisePlaceAccuracy;
  coordinateSystem: string;
  latitude: number;
  longitude: number;
  birthPlace: string;
  verificationStatus?: PrecisePlaceVerificationStatus;
  verificationReason?: string | null;
  distanceFromCityKm?: number | null;
  cityLabel?: string | null;
  sourceUrl?: string | null;
  rawEvidence?: string | null;
  locationType?: string | null;
  scopeMatchStatus?: "match" | "conflict" | "uncertain" | null;
  scopeMatchReason?: string | null;
};

export type PrecisePlaceLookupStage =
  "resolving" | "searching" | "verifying" | "matching" | "complete";

export type PrecisePlaceLookupProgress = {
  stage: PrecisePlaceLookupStage;
  query?: string | null;
  tool?: string | null;
};

export type PrecisePlaceSearchResponse = {
  options: PrecisePlaceOption[];
  localCount: number;
  fallbackSource?: string | null;
  fallbackEnabled: boolean;
  agentFallbackEnabled: boolean;
  agentAttempted: boolean;
  agentError?: string | null;
  agentSearchQueries: string[];
  verificationBase?: string | null;
  rejectedCount: number;
  attemptedSources: string[];
};

export type AccountProfileResponse = {
  userId: string;
  authMode: string;
  email?: string | null;
  role: string;
  isAdmin: boolean;
  anonymousUserId?: string | null;
};

export type BillingPlanKey = "pro_monthly" | "pro_yearly" | "single_report";

export type BillingPlanResponse = {
  key: BillingPlanKey;
  name: string;
  billingPeriod: string;
  productIdConfigured: boolean;
};

export type BillingSubscriptionResponse = {
  planKey: string;
  status: string;
  isActive: boolean;
  currentPeriodStart?: string | null;
  currentPeriodEnd?: string | null;
  cancelAtPeriodEnd: boolean;
  creemCustomerId?: string | null;
  creemSubscriptionId?: string | null;
};

export type BillingAccountResponse = {
  provider: "creem";
  configured: boolean;
  testMode: boolean;
  entitlement: "admin" | "paid" | "free";
  hasActiveEntitlement: boolean;
  canManageBilling: boolean;
  subscription?: BillingSubscriptionResponse | null;
  plans: BillingPlanResponse[];
};

export type BillingCheckoutInput = {
  planKey: BillingPlanKey;
  successUrl?: string | null;
};

export type BillingCheckoutResponse = {
  checkoutUrl: string;
  checkoutId?: string | null;
  requestId: string;
};

export type BillingPortalResponse = {
  portalUrl: string;
};

export type BirthInput = {
  displayName?: string;
  birthDate: string;
  birthTime: string;
  birthPlace: string;
  birthTimePrecision: BirthTimePrecision;
  reportedTimeWindow?: ReportedTimeWindow;
  gender: string;
  relationship: string;
  timeSource?: string;
  readingFocus?: string;
  lifeEvents?: string;
  readerRelationship?: "self" | "parent" | "partner" | "family" | "professional";
  utcOffsetSeconds?: number | null;
  locale?: AppLocale;
};

export type SkillBirthInput = BirthInput & {
  displayName: string;
  gender: string;
  relationship: string;
};

export type RectificationLifeEventCategory =
  | "education"
  | "career"
  | "relationship"
  | "relocation"
  | "child"
  | "health"
  | "family"
  | "finance"
  | "property"
  | "legal"
  | "loss"
  | "spiritual";

export type RectificationLifeEventInput = {
  questionId?: string;
  date: string;
  category: RectificationLifeEventCategory;
  eventSubtype: string;
  description: string;
};

export type RectificationLifeEventsInput = {
  sessionId: string;
  expectedChartRevision?: number;
  idempotencyKey?: string;
  events: RectificationLifeEventInput[];
};

export type RectificationLifeEventsResetInput = {
  sessionId: string;
  expectedChartRevision?: number;
};

export type RectificationInterviewInput = {
  sessionId: string;
  locale: AppLocale;
  currentQuestionId?: string;
  skippedCategory?: RectificationLifeEventCategory;
  resetSkipped?: boolean;
  availableCategories?: RectificationLifeEventCategory[];
};

export type RectificationConfirmationAnswer = "accurate" | "partly" | "inaccurate";

export type RectificationConfirmationResponse = {
  exampleId: string;
  answer: RectificationConfirmationAnswer;
  note?: string;
};

export type RectificationConfirmationInput = {
  sessionId: string;
  expectedChartRevision?: number;
  responses: RectificationConfirmationResponse[];
};

export type ConsultationQuestionInput = {
  sessionId: string;
  question: string;
};

export type ConsultationAnswerResponse = {
  answerability: "answered" | "insufficient_evidence";
  answer: string;
  supportingClaimIds: string[];
  limitations: string[];
  followUpQuestions: string[];
};

export type ConsultationExchangeResponse = ConsultationAnswerResponse & {
  askedAt: string;
  question: string;
};

export type ConsultationConversationResponse = {
  schemaVersion: "vedicdust-consultation-conversation/1.0.0";
  sessionId: string;
  exchanges: ConsultationExchangeResponse[];
};

export type BaziCalendarType = "solar" | "lunar";

export type BaziSessionInput = BirthInput & {
  calendarType: BaziCalendarType;
  currentDate: string;
  audience: string;
  topic: string;
};

export type SkillName =
  | "vedic-reader"
  | "vedic-core"
  | "vedic-rectifier"
  | "vedic-synastry"
  | "bazi-calculator"
  | "bazi-classics-core";

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
  | "rectifier_complete"
  | "synastry_ready"
  | "synastry_complete"
  | "bazi_ready"
  | "bazi_complete"
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
