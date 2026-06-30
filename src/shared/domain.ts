export type BirthTimePrecision = "exact" | "approximate" | "part_of_day" | "unknown";

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
