import { SignedIn, SignedOut, SignInButton, SignUpButton, useAuth } from "@clerk/clerk-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ComponentProps, FormEvent, ReactNode } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  Baby,
  BookOpen,
  Briefcase,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  Download,
  Eye,
  FileText,
  GraduationCap,
  Heart,
  HeartCrack,
  Home,
  Info,
  ListChecks,
  LoaderCircle,
  MapPinned,
  RefreshCw,
  Scale,
  Sparkles,
  Stethoscope,
  Target,
  Users,
  Wallet,
  Workflow,
  type LucideIcon
} from "lucide-react";
import { ApiError, api } from "../api";
import { AccountCenter } from "../components/AccountCenter";
import { ChartRevealProgress } from "../components/ChartRevealProgress";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import {
  aggregateWorkshopStages,
  WORKSHOP_STAGES,
  type StageDef,
  type StageStatus
} from "../components/PipelineFlow";
import { MarkdownReport } from "../components/MarkdownReport";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { Textarea } from "../components/ui/textarea";
import {
  formatDuration,
  getPipelineData,
  parseRunMetrics,
  type PipelineData,
  type PipelineNode
} from "../lib/pipeline";
import {
  chartRevealCoordinatesFromRecord,
  deriveChartRevealState
} from "../lib/chartRevealMapping";
import { getReportSections, titleForArtifact } from "../lib/report";
import { cn } from "../lib/cn";
import { useI18n } from "../i18n/provider";
import type {
  BirthInput,
  ConsultationExchangeResponse,
  CoreJobResponse,
  RectificationConfirmationAnswer,
  RectificationConfirmationResponse,
  RectificationLifeEventCategory,
  RectificationLifeEventInput,
  SkillArtifact,
  SkillSessionResponse
} from "../../shared/domain";

type NavState = { name?: string; birth?: BirthInput; concern?: string } | null;

const CHART_RECORD_JSON = "chart_record.json";

type BirthInfo = {
  name: string;
  date: string;
  time: string;
  place: string;
  latitude: string;
  longitude: string;
  gender: string;
  relationship: string;
  timePrecision: string;
  effectivePrecision: string;
  concern: string;
};

type StageCopy = {
  purpose: string;
  userResult: string;
  userAction: string;
  expected: string;
};

type ValidationAnswer = "accurate" | "partly" | "inaccurate";

type ValidationAnchor = {
  id: string;
  index: number;
  statement: string;
  rationale: string;
};

type ValidationFeedbackSummary = {
  answer: ValidationAnswer | "recorded";
  answerLabel: string;
  note: string;
  anchorText: string;
};

type ResultPreviewSection = {
  id: string;
  title: string;
  body: string;
};

type RectificationState = {
  status?: string;
  riskLevel?: string;
  reportReadinessMode?: string;
  equivalentCandidateCount?: number;
  availableRectificationCategories?: RectificationLifeEventCategory[];
  selectionConfidence?: string;
  evidenceInvalidation?: {
    status?: "reset_required" | string;
    reason?: string;
    eventIds?: string[];
    requiresReset?: boolean;
  };
  selectionEvidence?: {
    calibrationEventCount?: number;
    calibrationEpisodeCount?: number;
    calibrationCategoryCount?: number;
    holdoutEventCount?: number;
    holdoutEpisodeCount?: number;
    submittedEventCount?: number;
    correlatedEventCount?: number;
  };
  reportGate?: {
    fullReportAllowed?: boolean;
    reason?: string;
    reportScope?: string;
    nextStep?: string;
  };
  rectificationPlan?: {
    action?: string;
    eventCollectionRequired?: boolean;
  };
  lifeEventLedger?: {
    independentEpisodeCount?: number;
    events?: Array<{
      date?: string;
      category?: RectificationLifeEventCategory;
      eventSubtype?: string;
      description?: string;
    }>;
  };
  rectificationRounds?: Array<{
    round?: number;
    decision?: {
      outcome?:
        | "bounded_candidate_selected"
        | "holdout_failed"
        | "holdout_inconclusive"
        | "candidate_scores_separated"
        | "correlated_episode_recorded"
        | "evidence_recorded_without_required_margin";
    };
  }>;
  activeChartRevision?: {
    revision?: number;
    source?: string;
  };
  rectificationConclusion?: {
    schemaVersion?: string;
    status?: string;
    chartRevision?: number;
    confidence?: string;
    correctedBirthTime?: {
      localDate?: string;
      localTime?: string;
      timezoneId?: string | null;
      utcOffsetSeconds?: number | null;
      displayPrecision?: string;
    };
    selectedInterval?: {
      start?: string;
      end?: string;
      boundarySemantics?: "start_inclusive_end_exclusive";
    };
    methodAssurance?: {
      methodMaturity?: string;
      validationStatus?: string;
      independentProfessionalReviewCompleted?: boolean;
    };
    evidenceSummary?: {
      calibrationEventCount?: number;
      calibrationEpisodeCount?: number;
      calibrationCategoryCount?: number;
      holdoutEventCount?: number;
      holdoutEpisodeCount?: number;
      correlatedEventCount?: number;
      holdoutResult?: string;
      method?: string;
    };
    evidenceHighlights?: Array<{
      eventId?: string;
      date?: string;
      datePrecision?: "day" | "month" | "year" | "range";
      category?: RectificationLifeEventCategory | string;
      eventSubtype?: string;
      description?: string;
      role?: "calibration" | "holdout";
      result?: "used_for_candidate_comparison" | "passed_reserved_cross_check";
      usedForSelection?: boolean;
    }>;
    examples?: Array<{
      exampleId?: string;
      eventId?: string;
      startDate?: string;
      endDate?: string;
      category?: RectificationLifeEventCategory | string;
      prompt?: string;
      description?: string;
      source?: "deterministic_input_review" | "submitted_evidence" | string;
      usedForSelection?: boolean;
    }>;
    generation?: {
      source?: string;
      postSelectionOnly?: boolean;
      usedForSelection?: boolean;
      disclaimer?: string;
    };
    confirmation?: {
      status?: string;
      responses?: Array<{
        exampleId?: string;
        answer?: RectificationConfirmationAnswer;
        note?: string;
      }>;
    };
  };
};

type Translate = (key: string, vars?: Record<string, string | number>) => string;
type ReadingProductPhaseStatus = "done" | "active" | "pending";
type ReadingProductPhase = {
  id: "input" | "calibration" | "chart" | "reveal" | "report";
  label: string;
  detail: string;
  status: ReadingProductPhaseStatus;
};

const STAGE_COPY: Record<string, StageCopy> = {
  src: {
    purpose: "Keeps your birth details fixed for the rest of the reading.",
    userResult: "The reading uses one clear set of date, time, place, and time certainty details.",
    userAction: "Review the details. If something is wrong, start a fresh reading.",
    expected: "Usually seconds. If the city cannot be found, choose it again from search."
  },
  chart: {
    purpose: "Calculates and saves the chart facts before any LLM interpretation begins.",
    userResult: "You can inspect the exact structured-data sections used by later stages.",
    userAction: "Review the chart facts. Birth-time verification uses these facts as its source.",
    expected: "Generated immediately after the birth details are accepted."
  },
  reader: {
    purpose: "Narrows an uncertain birth-time window using dated events from your life.",
    userResult:
      "You receive a bounded time range, or a clear explanation that the evidence is not yet decisive.",
    userAction:
      "Choose one event that really happened, then add the date as precisely as you remember it.",
    expected:
      "Usually three events, with up to five only when the remaining chart ranges are still difficult to separate."
  },
  judgement: {
    purpose: "Turns qualified chart facts into a small set of traceable conclusions.",
    userResult:
      "Each conclusion is checked against natal promise, capacity, eligible supporting charts, timing, and counter-evidence.",
    userAction: "No action required. The system is evaluating the evidence relevant to you.",
    expected: "Usually one focused analysis step after the birth-time check."
  },
  consultation: {
    purpose: "Organizes the approved conclusions into a readable professional consultation.",
    userResult:
      "You receive an executive synthesis, priority life themes, bounded timing guidance, practical implications, and a technical evidence appendix.",
    userAction: "Open the Report tab when this completes.",
    expected: "The final rendering follows immediately after evidence synthesis."
  },
  bazi_chart: {
    purpose:
      "Calculates the four pillars, ten gods, hidden stems, solar-term boundaries, and luck cycles.",
    userResult: "A structured BaZi chart workspace is saved before any interpretation begins.",
    userAction: "Review the chart facts, then generate the classical report when ready.",
    expected: "Usually seconds."
  },
  bazi_report: {
    purpose: "Turns the chart facts into a classical BaZi report using the repo-local skill.",
    userResult: "The Report tab becomes available with BaZi sections and timing notes.",
    userAction: "Sign in if needed, then generate the report.",
    expected: "Usually several minutes."
  }
};

function localizedStageCopy(stageId: string, t: Translate): StageCopy {
  const fallback = STAGE_COPY[stageId] ?? STAGE_COPY.consultation;
  const fieldKeys: Record<keyof StageCopy, string> = {
    purpose: "purpose",
    userResult: "result",
    userAction: "action",
    expected: "expected"
  };
  const fromKey = (field: keyof StageCopy) => {
    const key = `stage.copy.${stageId}.${fieldKeys[field]}`;
    const text = t(key);
    return text === key ? fallback[field] : text;
  };
  return {
    purpose: fromKey("purpose"),
    userResult: fromKey("userResult"),
    userAction: fromKey("userAction"),
    expected: fromKey("expected")
  };
}

const STAGE_ARTIFACT_CANDIDATES: Record<string, string[]> = {
  src: [CHART_RECORD_JSON, "birth_input_context.json", "sensitivity_scan.json", "run_metrics.json"],
  chart: [
    CHART_RECORD_JSON,
    "birth_input_context.json",
    "sensitivity_scan.json",
    "chart_rectification_state.json"
  ],
  reader: [
    "reader_prevalidation.md",
    "prevalidation_result.json",
    "chart_rectification_state.json",
    "user_context.md"
  ],
  judgement: ["claim_graph.json", "judgement_context.json"],
  consultation: ["consultation_report.md"],
  bazi_chart: ["bazi_chart_foundation.md", "bazi_report_context.md", "bazi_chart_record.json"],
  bazi_report: [
    "bazi_life_report.md",
    "bazi_overview.md",
    "bazi_classics_audit.md",
    "bazi_timing_report.md",
    "bazi_data_audit.md",
    "bazi_appendix.md"
  ]
};

const BAZI_WORKSHOP_STAGES: StageDef[] = [
  {
    id: "src",
    label: "Birth Details",
    sub: "intake",
    seed: true,
    match: () => false
  },
  {
    id: "bazi_chart",
    label: "BaZi Chart Facts",
    sub: "four pillars",
    match: (id) => id === "bazi_chart"
  },
  {
    id: "bazi_report",
    label: "Classical Report",
    sub: "three classics",
    match: (id) => id === "bazi_report"
  }
];

const PRECISION_LABELS: Record<string, string> = {
  exact: "Official record",
  approximate: "Close memory",
  part_of_day: "Known hour",
  unknown: "Unknown time",
  精确到分钟: "Official record",
  约略时间: "Close memory",
  仅知道时段: "Known hour",
  未知出生时间: "Unknown"
};

const GENDER_LABELS: Record<string, string> = {
  女: "Female",
  男: "Male",
  未提供: "Prefer not to say"
};

const RELATIONSHIP_LABELS: Record<string, string> = {
  单身: "Single",
  恋爱中: "Dating / in a relationship",
  已婚: "Married",
  分居或离异: "Separated / divorced",
  丧偶: "Widowed",
  未提供: "Prefer not to say"
};

const VALIDATION_CHOICES: Array<{
  value: ValidationAnswer;
  labelKey: string;
  storedLabel: string;
  descriptionKey: string;
}> = [
  {
    value: "accurate",
    labelKey: "validation.accurate.label",
    storedLabel: "准",
    descriptionKey: "validation.accurate.description"
  },
  {
    value: "partly",
    labelKey: "validation.partly.label",
    storedLabel: "部分准",
    descriptionKey: "validation.partly.description"
  },
  {
    value: "inaccurate",
    labelKey: "validation.inaccurate.label",
    storedLabel: "不准",
    descriptionKey: "validation.inaccurate.description"
  }
];

type LifeEventDraft = Omit<RectificationLifeEventInput, "eventSubtype"> & {
  eventSubtype?: string;
  category: RectificationLifeEventCategory | "";
  datePrecision: "day" | "month" | "year";
  choiceId: string;
  note: string;
};

type LifeEventChoice = {
  id: string;
  label: { en: string; zh: string; ja: string };
  requiresNote?: boolean;
};

const LIFE_EVENT_CHOICES: Record<RectificationLifeEventCategory, LifeEventChoice[]> = {
  education: [
    {
      id: "admission",
      label: {
        en: "Started a new school or was admitted",
        zh: "升学 / 被学校录取",
        ja: "進学・入学が決まった"
      }
    },
    {
      id: "graduation",
      label: { en: "Graduated or received a degree", zh: "毕业 / 获得学位", ja: "卒業・学位取得" }
    },
    {
      id: "exam",
      label: {
        en: "Took an important exam",
        zh: "参加重要考试或资格考试",
        ja: "重要な試験を受けた"
      }
    },
    {
      id: "study_abroad",
      label: {
        en: "Transferred, studied abroad, or left school long-term",
        zh: "转学、留学或长期离开学校",
        ja: "転校・留学・長期の休学や離学"
      }
    },
    {
      id: "other",
      label: {
        en: "Another major education change",
        zh: "其他明显的教育变化",
        ja: "その他の大きな学業の変化"
      },
      requiresNote: true
    }
  ],
  career: [
    {
      id: "first_job",
      label: {
        en: "Started my first regular job",
        zh: "开始第一份正式工作",
        ja: "初めての本格的な仕事を始めた"
      }
    },
    {
      id: "promotion",
      label: {
        en: "Got a major promotion or responsibility change",
        zh: "明显升职或职责发生重大变化",
        ja: "大きな昇進や責任の変化があった"
      }
    },
    {
      id: "job_change",
      label: {
        en: "Changed industries, moved for work, or started a business",
        zh: "换行业、因工作迁居或开始创业",
        ja: "転職・転業・仕事のための転居・起業"
      }
    },
    {
      id: "job_loss",
      label: {
        en: "Lost a job or had a long work interruption",
        zh: "失业、停工或被迫离开工作",
        ja: "失職・長期の仕事中断があった"
      }
    },
    {
      id: "other",
      label: {
        en: "Another major work change",
        zh: "其他明显的工作变化",
        ja: "その他の大きな仕事の変化"
      },
      requiresNote: true
    }
  ],
  relationship: [
    {
      id: "started_relationship",
      label: {
        en: "Started an important relationship",
        zh: "开始一段重要关系",
        ja: "大切な関係が始まった"
      }
    },
    {
      id: "marriage",
      label: {
        en: "Married, registered, or began living together",
        zh: "结婚、登记或开始长期同居",
        ja: "結婚・入籍・同居を始めた"
      }
    },
    {
      id: "separation",
      label: {
        en: "Separated, divorced, or ended a major relationship",
        zh: "分手、分居或离婚",
        ja: "別居・離婚・大きな関係の終了"
      }
    },
    {
      id: "other",
      label: {
        en: "Another major relationship change",
        zh: "其他明显的关系变化",
        ja: "その他の大きな関係の変化"
      },
      requiresNote: true
    }
  ],
  relocation: [
    {
      id: "moved_city",
      label: { en: "Moved to another city", zh: "搬到另一座城市", ja: "別の都市へ引っ越した" }
    },
    {
      id: "moved_country",
      label: {
        en: "Moved abroad or relocated long-term",
        zh: "出国或长期迁居",
        ja: "海外移住・長期の転居"
      }
    },
    {
      id: "first_home",
      label: {
        en: "Started living independently for the first time",
        zh: "第一次独立居住",
        ja: "初めて一人暮らし・独立生活を始めた"
      }
    },
    {
      id: "other",
      label: { en: "Another major move", zh: "其他明显的搬迁变化", ja: "その他の大きな転居" },
      requiresNote: true
    }
  ],
  child: [
    {
      id: "pregnancy",
      label: { en: "Pregnancy became part of my life", zh: "经历怀孕", ja: "妊娠を経験した" }
    },
    {
      id: "birth",
      label: {
        en: "A child was born or joined the family",
        zh: "生育或迎来孩子",
        ja: "出産・子どもを家族に迎えた"
      }
    },
    {
      id: "child_major",
      label: {
        en: "A major event happened in a child's life",
        zh: "孩子经历了重要变化",
        ja: "子どもの人生に大きな出来事があった"
      }
    },
    {
      id: "other",
      label: {
        en: "Another major child-related change",
        zh: "其他明显的子女相关变化",
        ja: "その他の大きな子どもに関する変化"
      },
      requiresNote: true
    }
  ],
  health: [
    {
      id: "surgery",
      label: {
        en: "Had surgery or a significant hospital stay",
        zh: "做过手术或经历较长住院",
        ja: "手術・大きな入院を経験した"
      }
    },
    {
      id: "diagnosis",
      label: {
        en: "Received a clear diagnosis or began long-term treatment",
        zh: "明确诊断或开始长期治疗",
        ja: "診断を受けた・長期治療を始めた"
      }
    },
    {
      id: "accident",
      label: {
        en: "Had a serious accident or physical injury",
        zh: "经历重大事故或身体损伤",
        ja: "大きな事故・けがを経験した"
      }
    },
    {
      id: "other",
      label: {
        en: "Another major health change",
        zh: "其他明显的健康变化",
        ja: "その他の大きな健康上の変化"
      },
      requiresNote: true
    }
  ],
  family: [
    {
      id: "family_structure",
      label: {
        en: "A family member joined or left the household",
        zh: "家庭成员增加或离开家庭",
        ja: "家族が増えた・家を離れた"
      }
    },
    {
      id: "parent_change",
      label: {
        en: "A parent's marriage, work, or home changed significantly",
        zh: "父母的婚姻、工作或居住发生重大变化",
        ja: "親の結婚・仕事・住居に大きな変化があった"
      }
    },
    {
      id: "caregiving",
      label: {
        en: "I began caring for a family member long-term",
        zh: "开始长期照护家人",
        ja: "家族の長期的な介護や世話を始めた"
      }
    },
    {
      id: "other",
      label: {
        en: "Another major family change",
        zh: "其他明显的家庭变化",
        ja: "その他の大きな家族の変化"
      },
      requiresNote: true
    }
  ],
  finance: [
    {
      id: "major_gain",
      label: {
        en: "Had a first major income rise or financial gain",
        zh: "第一次明显增收或获得较大利益",
        ja: "初めて大きな収入増・利益があった"
      }
    },
    {
      id: "major_loss",
      label: {
        en: "Had a major loss, debt, or financial interruption",
        zh: "经历重大亏损、负债或财务中断",
        ja: "大きな損失・負債・財務中断があった"
      }
    },
    {
      id: "financial_independence",
      label: { en: "Became financially independent", zh: "开始经济独立", ja: "経済的に自立した" }
    },
    {
      id: "other",
      label: {
        en: "Another major financial change",
        zh: "其他明显的财务变化",
        ja: "その他の大きな金銭上の変化"
      },
      requiresNote: true
    }
  ],
  property: [
    {
      id: "purchase",
      label: {
        en: "Bought a home or important property",
        zh: "买房或购置重要资产",
        ja: "家・重要な不動産を購入した"
      }
    },
    {
      id: "sale",
      label: {
        en: "Sold property or lost a home",
        zh: "卖房、失去住处或重要资产",
        ja: "不動産を売却・住居を失った"
      }
    },
    {
      id: "move_home",
      label: { en: "Moved into a new home", zh: "入住新家", ja: "新しい住居に入った" }
    },
    {
      id: "other",
      label: {
        en: "Another major property change",
        zh: "其他明显的房产变化",
        ja: "その他の大きな住居・不動産の変化"
      },
      requiresNote: true
    }
  ],
  legal: [
    {
      id: "lawsuit",
      label: {
        en: "Entered a lawsuit or formal legal process",
        zh: "进入诉讼或正式法律程序",
        ja: "訴訟・正式な法的手続きに入った"
      }
    },
    {
      id: "settlement",
      label: {
        en: "Reached a major legal result or settlement",
        zh: "得到重大法律结果或达成和解",
        ja: "大きな法的決着・和解があった"
      }
    },
    {
      id: "documents",
      label: {
        en: "Had a major change in status or official documents",
        zh: "身份、移民或重要证件发生重大变化",
        ja: "身分・移民・重要書類に大きな変化があった"
      }
    },
    {
      id: "other",
      label: {
        en: "Another major legal change",
        zh: "其他明显的法律变化",
        ja: "その他の大きな法的変化"
      },
      requiresNote: true
    }
  ],
  loss: [
    {
      id: "bereavement",
      label: {
        en: "A close person or important relationship ended through death",
        zh: "亲人或重要关系中的人离世",
        ja: "身近な人・大切な関係者との死別"
      }
    },
    {
      id: "sudden_loss",
      label: {
        en: "A major loss changed my home or daily life",
        zh: "重大失去改变了居住或日常生活",
        ja: "大きな喪失で住居や日常が変わった"
      }
    },
    {
      id: "other",
      label: { en: "Another major loss", zh: "其他重大失去或告别", ja: "その他の大きな喪失" },
      requiresNote: true
    }
  ],
  spiritual: [
    {
      id: "practice",
      label: {
        en: "Started a sustained spiritual or religious practice",
        zh: "开始持续的宗教、冥想或修行",
        ja: "継続的な宗教・瞑想・精神的実践を始めた"
      }
    },
    {
      id: "belief_change",
      label: {
        en: "My beliefs or worldview changed significantly",
        zh: "信仰或世界观发生明显改变",
        ja: "信念・世界観が大きく変わった"
      }
    },
    {
      id: "community",
      label: {
        en: "Joined or left a spiritual community",
        zh: "加入或离开一个宗教 / 修行团体",
        ja: "宗教・精神的なコミュニティに参加・離脱した"
      }
    },
    {
      id: "other",
      label: {
        en: "Another major values change",
        zh: "其他明显的价值观变化",
        ja: "その他の大きな価値観の変化"
      },
      requiresNote: true
    }
  ]
};

const LIFE_EVENT_CATEGORY_ICONS: Record<RectificationLifeEventCategory, LucideIcon> = {
  education: GraduationCap,
  career: Briefcase,
  relationship: Heart,
  relocation: MapPinned,
  child: Baby,
  health: Stethoscope,
  family: Users,
  finance: Wallet,
  property: Home,
  legal: Scale,
  loss: HeartCrack,
  spiritual: Sparkles
};

const PRIMARY_RECTIFICATION_CATEGORIES: RectificationLifeEventCategory[] = [
  "relationship",
  "child",
  "health",
  "relocation",
  "career",
  "education"
];

const SECONDARY_RECTIFICATION_CATEGORIES: RectificationLifeEventCategory[] = [
  "property",
  "loss",
  "family",
  "finance",
  "legal",
  "spiritual"
];

const YOUNG_PERSON_RECTIFICATION_CATEGORIES: RectificationLifeEventCategory[] = [
  "education",
  "relocation",
  "family",
  "health"
];

type RectificationInterviewAction = {
  currentQuestionId?: string;
  skippedCategory?: RectificationLifeEventCategory;
  resetSkipped?: boolean;
  availableCategories?: RectificationLifeEventCategory[];
};

type RectificationClarification = {
  questionId: string;
  reasonCode: string;
  message: string;
};

type RectificationInterviewQuestion = {
  questionId: string;
  category: RectificationLifeEventCategory;
  title: string;
  prompt: string;
  whyWeAsk: string;
  dateLabel: string;
  detailsLabel: string;
  detailsPlaceholder: string;
  allowedSubtypes?: string[];
};

type RectificationInterview = {
  schemaVersion: `vedicdust-rectification-interview/1.${number}.0`;
  title: string;
  intro: string;
  source: string;
  progress: { answered: number; target: number; maximumAccepted: number; label: string };
  questions: RectificationInterviewQuestion[];
  availableCategories?: RectificationLifeEventCategory[];
  stopReason?: string | null;
};

function statusBadgeVariant(status: StageStatus): ComponentProps<typeof Badge>["variant"] {
  if (status === "done") return "done";
  if (status === "running" || status === "waiting") return "gold";
  if (status === "failed") return "error";
  return "neutral";
}

const READING_INTERRUPTED_MESSAGE =
  "The reading was interrupted. Completed parts are saved, and resume will continue from the unfinished part.";

const TECHNICAL_ERROR_PATTERN =
  /(reader_prevalidation|user_context|run_metrics|\.md|artifact|agent output|traceback|vedic-core|batch|node|pipeline|skill|expected artifact|AGENT_TIMEOUT_MS|JSON)/i;

function userFacingError(caught: unknown, fallback: string) {
  return sanitizeUserMessage(caught instanceof Error ? caught.message : "", fallback);
}

function sanitizeUserMessage(message: string | null | undefined, fallback: string) {
  const trimmed = (message ?? "").trim();
  if (!trimmed || TECHNICAL_ERROR_PATTERN.test(trimmed)) return fallback;
  return trimmed;
}

function rectificationClarificationFromError(caught: unknown): RectificationClarification | null {
  if (!(caught instanceof ApiError) || caught.status !== 409) return null;
  const detail = caught.detail;
  if (!detail || typeof detail !== "object") return null;
  const record = detail as Record<string, unknown>;
  if (record.code !== "rectification_evidence_clarification_required") return null;
  const message = String(record.message || caught.message || "").trim();
  if (!message) return null;
  return {
    questionId: String(record.questionId || ""),
    reasonCode: String(record.reasonCode || "event_not_confirmed"),
    message
  };
}

export function Session() {
  const { id = "" } = useParams();
  const { isLoaded: authLoaded, isSignedIn } = useAuth();
  const navigate = useNavigate();
  const { locale, t } = useI18n();
  const location = useLocation();
  const navState = location.state as NavState;
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "report" ? "report" : "reading";

  const [session, setSession] = useState<SkillSessionResponse | null>(null);
  const [coreJob, setCoreJob] = useState<CoreJobResponse | null>(null);
  const [error, setError] = useState("");
  const [rectificationClarification, setRectificationClarification] =
    useState<RectificationClarification | null>(null);
  const [activeSection, setActiveSection] = useState(0);
  const [selectedStageId, setSelectedStageId] = useState("src");
  const [readerRunning, setReaderRunning] = useState(false);
  const [readerStartedAt, setReaderStartedAt] = useState<number | null>(null);
  const [validationFeedback, setValidationFeedback] = useState("");
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [submittingLifeEvents, setSubmittingLifeEvents] = useState(false);
  const [submittingRectificationConfirmation, setSubmittingRectificationConfirmation] =
    useState(false);
  const [preparingRectificationInterview, setPreparingRectificationInterview] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [baziRunning, setBaziRunning] = useState(false);
  const [now, setNow] = useState(Date.now());
  const sessionRef = useRef<SkillSessionResponse | null>(null);
  const coreStartedRef = useRef(false);
  const readerStartedRef = useRef(false);
  const baziStartedRef = useRef(false);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  const baziMode = useMemo(() => isBaziSession(session), [session]);
  const reportSections = useMemo(() => getReportSections(session), [session]);
  const runMetrics = useMemo(() => parseRunMetrics(session), [session]);
  const baziPipelineData = useMemo(
    () => getBaziPipelineData(session, baziRunning),
    [baziRunning, session]
  );
  const pipelineData = useMemo(
    () =>
      baziMode
        ? baziPipelineData
        : getPipelineData(coreJob, runMetrics, { session, readerRunning }),
    [baziMode, baziPipelineData, coreJob, runMetrics, session, readerRunning]
  );
  const pipelineStages = baziMode ? BAZI_WORKSHOP_STAGES : WORKSHOP_STAGES;
  const jobActive = !baziMode && (coreJob?.status === "queued" || coreJob?.status === "running");
  const complete = baziMode
    ? session?.stage === "bazi_complete"
    : session?.stage === "core_complete" || coreJob?.status === "completed";
  const coreInterrupted =
    !baziMode && (coreJob?.status === "failed" || (!coreJob && runMetrics?.status === "failed"));
  const birthInfo = useMemo(() => resolveBirthInfo(navState, session), [navState, session]);
  const readerPrevalidation = findArtifact(session, "reader_prevalidation.md");
  const feedbackArtifact = findArtifact(session, "user_context.md");
  const awaitingValidationFeedback = Boolean(
    readerPrevalidation &&
    !hasCurrentValidationFeedback(readerPrevalidation, feedbackArtifact) &&
    !complete
  );
  const calibrationDone = baziMode || canStartFullReading(session);
  const calibrationFocus = Boolean(session) && !baziMode && !calibrationDone && !complete;
  const productPhases = useMemo(
    () =>
      deriveReadingProductPhases({
        baziMode,
        session,
        pipelineData,
        readerRunning,
        awaitingValidationFeedback,
        jobActive,
        complete,
        calibrationDone,
        reportReady: complete && reportSections.length > 0,
        baziRunning,
        t
      }),
    [
      awaitingValidationFeedback,
      baziMode,
      baziRunning,
      complete,
      calibrationDone,
      jobActive,
      pipelineData,
      readerRunning,
      reportSections.length,
      session,
      t
    ]
  );

  const setTab = useCallback(
    (next: "reading" | "report") => {
      const params = new URLSearchParams(searchParams);
      params.set("tab", next);
      setSearchParams(params, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const startCoreReport = useCallback(
    async (options: { resume?: boolean; sessionOverride?: SkillSessionResponse } = {}) => {
      if (!id || (coreStartedRef.current && !options.resume)) return;
      if (!authLoaded) {
        setError("Account status is still loading. Please try again in a moment.");
        return;
      }
      if (!isSignedIn) {
        setError("Sign in or create an account to start the full reading.");
        return;
      }
      if (
        readingContinuationAction(options.sessionOverride ?? sessionRef.current) ===
        "confirm_rectification"
      ) {
        setSelectedStageId("reader");
        setError(t("session.rectification.conclusion.mustConfirm"));
        return;
      }
      coreStartedRef.current = true;
      setError("");
      try {
        const job = await api.startCoreJob({
          sessionId: id,
          skill: "vedic-core",
          userMessage: "",
          locale
        });
        setCoreJob(job);
        if (job.session) setSession(job.session);
      } catch (caught) {
        coreStartedRef.current = false;
        setError(userFacingError(caught, t("session.error.startReading")));
      }
    },
    [authLoaded, id, isSignedIn, locale, t]
  );

  const resumeCoreReport = useCallback(async () => {
    coreStartedRef.current = false;
    setCoreJob(null);
    await startCoreReport({ resume: true });
  }, [startCoreReport]);

  const startReaderValidation = useCallback(
    async (options?: { force?: boolean }) => {
      if (!id || (readerStartedRef.current && !options?.force)) return;
      readerStartedRef.current = true;
      setError("");
      setReaderRunning(true);
      setReaderStartedAt(Date.now());
      setSelectedStageId("reader");
      try {
        const response = await api.runSkill({
          sessionId: id,
          skill: "vedic-reader",
          userMessage: "",
          locale
        });
        setSession(response);
      } catch (caught) {
        readerStartedRef.current = false;
        setError(userFacingError(caught, t("session.error.firstCheck")));
      } finally {
        setReaderRunning(false);
      }
    },
    [id, locale, t]
  );

  const startBaziReport = useCallback(async () => {
    if (!id || baziStartedRef.current) return;
    if (!authLoaded) {
      setError("Account status is still loading. Please try again in a moment.");
      return;
    }
    if (!isSignedIn) {
      setError("Sign in or create an account to generate the BaZi classical report.");
      return;
    }
    baziStartedRef.current = true;
    setError("");
    setBaziRunning(true);
    setSelectedStageId("bazi_report");
    try {
      const response = await api.runSkill({
        sessionId: id,
        skill: "bazi-classics-core",
        userMessage: "生成八字经典报告",
        locale
      });
      setSession(response);
      setTab("report");
    } catch (caught) {
      baziStartedRef.current = false;
      setError(userFacingError(caught, "Could not generate the BaZi report. Please try again."));
    } finally {
      setBaziRunning(false);
    }
  }, [authLoaded, id, isSignedIn, locale, setTab]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const loaded = await api.getSkillSession(id);
        if (cancelled) return;
        setSession(loaded);
        if (isBaziSession(loaded)) {
          setSelectedStageId(loaded.stage === "bazi_complete" ? "bazi_report" : "bazi_chart");
          return;
        }
        if (loaded.stage === "core_complete") return;

        const loadedReader = findArtifact(loaded, "reader_prevalidation.md");
        const loadedFeedback = findArtifact(loaded, "user_context.md");
        const hasFeedback = hasCurrentValidationFeedback(loadedReader, loadedFeedback);
        const hasReader = Boolean(loadedReader);
        if (hasFeedback) {
          const nextStep = readingContinuationAction(loaded);
          if (nextStep === "full_report") void startCoreReport({ sessionOverride: loaded });
          else if (nextStep === "reader") void startReaderValidation({ force: true });
          else if (nextStep === "collect_events") setSelectedStageId("reader");
          else if (nextStep === "confirm_rectification") setSelectedStageId("reader");
          else if (nextStep === "reset_events") setSelectedStageId("reader");
          else setSelectedStageId("chart");
        } else if (hasReader) {
          setSelectedStageId("reader");
        } else {
          const nextStep = readingContinuationAction(loaded);
          if (nextStep === "reader") void startReaderValidation();
          else if (nextStep === "collect_events") setSelectedStageId("reader");
          else if (nextStep === "confirm_rectification") setSelectedStageId("reader");
          else if (nextStep === "reset_events") setSelectedStageId("reader");
          else setSelectedStageId("chart");
        }
      } catch (caught) {
        if (!cancelled) setError(userFacingError(caught, "Could not load this reading."));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, startCoreReport, startReaderValidation]);

  useEffect(() => {
    if (readerPrevalidation && !feedbackArtifact) setSelectedStageId("reader");
  }, [readerPrevalidation, feedbackArtifact]);

  useEffect(() => {
    if (!readerRunning && !jobActive) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [readerRunning, jobActive]);

  useEffect(() => {
    const jobId = coreJob?.jobId;
    if (!jobId || (coreJob?.status !== "queued" && coreJob?.status !== "running")) return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      api
        .getCoreJob(jobId)
        .then((response) => {
          if (cancelled) return;
          setCoreJob(response);
          if (response.session) setSession(response.session);
          if (response.status === "failed") {
            coreStartedRef.current = false;
            setError(sanitizeUserMessage(response.message, READING_INTERRUPTED_MESSAGE));
          }
        })
        .catch((caught) => {
          if (!cancelled) setError(userFacingError(caught, "Could not refresh reading progress."));
        });
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [coreJob?.jobId, coreJob?.status]);

  function scrollToSection(index: number) {
    setActiveSection(index);
    document
      .getElementById(`section-${index}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function onExport() {
    if (!id || exportingPdf) return;
    setError("");
    setExportingPdf(true);
    try {
      await api.downloadReportPdf(id);
    } catch (caught) {
      setError(userFacingError(caught, "Could not prepare the PDF. Please try again."));
    } finally {
      setExportingPdf(false);
    }
  }

  async function onSubmitFeedback(event: FormEvent) {
    event.preventDefault();
    if (!authLoaded) {
      setError("Account status is still loading. Please try again in a moment.");
      return;
    }
    if (!isSignedIn) {
      setError("Sign in or create an account to save your replies and continue.");
      return;
    }
    const feedback = validationFeedback.trim();
    if (!feedback) {
      setError("Please answer the current check before starting the full reading.");
      return;
    }

    const concern = birthInfo.concern.trim();
    const feedbackMarkdown = concern
      ? `### 初始关心事项\n\n${concern}\n\n### 验前事逐条反馈\n\n${feedback}`
      : feedback;

    setError("");
    setSubmittingFeedback(true);
    try {
      const updated = await api.recordSkillFeedback({
        sessionId: id,
        feedbackMarkdown
      });
      setSession(updated);
      const nextStep = readingContinuationAction(updated);
      if (nextStep === "full_report") await startCoreReport({ sessionOverride: updated });
      else if (nextStep === "reader") await startReaderValidation({ force: true });
      else if (nextStep === "collect_events") setSelectedStageId("reader");
      else if (nextStep === "confirm_rectification") setSelectedStageId("reader");
      else if (nextStep === "reset_events") setSelectedStageId("reader");
      else setSelectedStageId("chart");
    } catch (caught) {
      setError(userFacingError(caught, "Could not save your replies. Please try again."));
    } finally {
      setSubmittingFeedback(false);
    }
  }

  async function onSubmitLifeEvents(events: RectificationLifeEventInput[]) {
    if (!authLoaded) {
      setError("正在确认会话，请稍后再试。");
      return;
    }
    if (!isSignedIn) {
      setError("请先登录，再继续出生时间校准。");
      return;
    }
    setError("");
    setRectificationClarification(null);
    setSubmittingLifeEvents(true);
    try {
      const chartRecord = parseJsonArtifact(session, CHART_RECORD_JSON);
      const expectedChartRevision = numberLike(chartRecord?.revision);
      if (expectedChartRevision == null) {
        throw new Error(
          "The active chart revision is missing. Refresh the session before continuing."
        );
      }
      const updated = await api.recordRectificationLifeEvents({
        sessionId: id,
        events,
        expectedChartRevision
      });
      setSession(updated);
      readerStartedRef.current = false;
      const nextStep = readingContinuationAction(updated);
      if (nextStep === "full_report") await startCoreReport({ sessionOverride: updated });
      else if (nextStep === "reader") await startReaderValidation({ force: true });
      else if (nextStep === "collect_events") setSelectedStageId("reader");
      else if (nextStep === "confirm_rectification") setSelectedStageId("reader");
      else if (nextStep === "reset_events") setSelectedStageId("reader");
      else setSelectedStageId("chart");
    } catch (caught) {
      const clarification = rectificationClarificationFromError(caught);
      if (clarification) {
        setRectificationClarification(clarification);
        setError("");
      } else {
        setError(userFacingError(caught, "Could not save these life events. Please try again."));
      }
    } finally {
      setSubmittingLifeEvents(false);
    }
  }

  async function onResetLifeEvents() {
    if (!authLoaded) {
      setError("正在确认会话，请稍后再试。");
      return;
    }
    if (!isSignedIn) {
      setError("请先登录，再重新开始出生时间校准。");
      return;
    }
    setError("");
    setRectificationClarification(null);
    setSubmittingLifeEvents(true);
    try {
      const chartRecord = parseJsonArtifact(session, CHART_RECORD_JSON);
      const expectedChartRevision = numberLike(chartRecord?.revision);
      if (expectedChartRevision == null) {
        throw new Error(
          "The active chart revision is missing. Refresh the session before restarting."
        );
      }
      const updated = await api.resetRectificationLifeEvents({
        sessionId: id,
        expectedChartRevision
      });
      setSession(updated);
      readerStartedRef.current = false;
      setSelectedStageId("reader");
    } catch (caught) {
      setError(
        userFacingError(caught, "Could not restart the birth-time check. Please try again.")
      );
    } finally {
      setSubmittingLifeEvents(false);
    }
  }

  async function onSubmitRectificationConfirmation(responses: RectificationConfirmationResponse[]) {
    if (!authLoaded) {
      setError("正在确认会话，请稍后再试。");
      return;
    }
    if (!isSignedIn) {
      setError("请先登录，再确认生时校正结果。");
      return;
    }
    setError("");
    setRectificationClarification(null);
    setSubmittingRectificationConfirmation(true);
    try {
      const chartRecord = parseJsonArtifact(session, CHART_RECORD_JSON);
      const expectedChartRevision = numberLike(chartRecord?.revision);
      if (expectedChartRevision == null) {
        throw new Error(
          "The active chart revision is missing. Refresh the session before confirming."
        );
      }
      const updated = await api.confirmRectification({
        sessionId: id,
        responses,
        expectedChartRevision
      });
      setSession(updated);
      readerStartedRef.current = false;
      const nextStep = readingContinuationAction(updated);
      if (nextStep === "full_report") await startCoreReport({ sessionOverride: updated });
      else if (nextStep === "collect_events") setSelectedStageId("reader");
      else if (nextStep === "confirm_rectification") setSelectedStageId("reader");
      else if (nextStep === "reset_events") setSelectedStageId("reader");
      else setSelectedStageId("chart");
    } catch (caught) {
      setError(
        userFacingError(caught, "Could not save the rectification check. Please try again.")
      );
    } finally {
      setSubmittingRectificationConfirmation(false);
    }
  }

  const prepareRectificationInterview = useCallback(
    async (action: RectificationInterviewAction = {}) => {
      if (!authLoaded || preparingRectificationInterview) return;
      if (!isSignedIn) {
        setError("请先登录，再继续出生时间校准。");
        return;
      }
      setError("");
      setPreparingRectificationInterview(true);
      try {
        const updated = await api.prepareRectificationInterview({
          sessionId: id,
          locale,
          ...action
        });
        setSession(updated);
      } catch (caught) {
        setError(userFacingError(caught, "Could not prepare the next verification question."));
      } finally {
        setPreparingRectificationInterview(false);
      }
    },
    [authLoaded, id, isSignedIn, locale, preparingRectificationInterview]
  );

  return (
    <div className="app-shell flex h-screen flex-col overflow-hidden bg-cream-2">
      <div className="app-tabs z-10 flex shrink-0 items-center gap-2 border-b border-gold/25 bg-cream/95 px-3 py-3 backdrop-blur-lg sm:px-8">
        <button
          className="brand-logo mr-1 border-0 bg-transparent sm:mr-3"
          onClick={() => navigate("/")}
        >
          Vedic<span>Dust</span>
        </button>
        <Button
          variant="tab"
          size="sm"
          data-active={tab === "reading"}
          aria-label={t("session.tab.reading")}
          onClick={() => setTab("reading")}
        >
          <Workflow size={14} />
          <span className="hidden sm:inline">{t("session.tab.reading")}</span>
        </Button>
        <Button
          variant="tab"
          size="sm"
          data-active={tab === "report"}
          aria-label={t("session.tab.report")}
          onClick={() => setTab("report")}
        >
          <BookOpen size={14} />
          <span className="hidden sm:inline">{t("session.tab.report")}</span>
        </Button>
        <div className="flex-1" />
        <SessionAuthControls />
      </div>

      {error && (
        <div
          className="screen-error mx-5 mt-3 shrink-0 rounded-md border border-red/30 bg-red/10 px-4 py-3 text-[13px] text-red sm:mx-8"
          role="alert"
        >
          {error}
        </div>
      )}

      {!calibrationFocus && <ReadingJourneyBar phases={productPhases} />}

      {tab === "reading" ? (
        <div
          className={cn(
            "min-h-0 flex-1 bg-night",
            calibrationFocus
              ? "relative isolate overflow-y-auto px-4 py-5 sm:px-6 sm:py-6"
              : "grid grid-cols-1 overflow-y-auto lg:grid-cols-[minmax(0,1fr)_minmax(360px,430px)] lg:overflow-hidden"
          )}
        >
          {calibrationFocus && (
            <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden>
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_8%,rgba(201,169,110,0.17),transparent_34%),radial-gradient(circle_at_82%_36%,rgba(105,72,142,0.16),transparent_34%),linear-gradient(180deg,#08070d_0%,#120d17_58%,#08070d_100%)]" />
              <div className="absolute left-1/2 top-24 size-[680px] -translate-x-1/2 rounded-full border border-gold/8 shadow-[0_0_120px_rgba(201,169,110,0.08)]" />
              <div className="absolute left-[14%] top-[22%] size-1 rounded-full bg-gold/45 shadow-[180px_110px_0_rgba(237,217,163,0.22),620px_70px_0_rgba(201,169,110,0.2),850px_260px_0_rgba(237,217,163,0.16)]" />
            </div>
          )}
          {!calibrationFocus && (
            <ReadingRevealPanel
              session={session}
              pipelineData={pipelineData}
              selectedStageId={selectedStageId}
              stages={pipelineStages}
              baziMode={baziMode}
              reportReady={complete && reportSections.length > 0}
              reportSectionCount={reportSections.length}
              onOpenReport={() => setTab("report")}
              onSelectStage={setSelectedStageId}
            />
          )}
          <WorkshopDetailPanel
            selectedStageId={selectedStageId}
            stages={pipelineStages}
            baziMode={baziMode}
            session={session}
            pipelineData={pipelineData}
            birthInfo={birthInfo}
            readerRunning={readerRunning}
            readerStartedAt={readerStartedAt}
            now={now}
            validationFeedback={validationFeedback}
            submittingFeedback={submittingFeedback}
            submittingLifeEvents={submittingLifeEvents}
            rectificationClarification={rectificationClarification}
            submittingRectificationConfirmation={submittingRectificationConfirmation}
            preparingRectificationInterview={preparingRectificationInterview}
            onValidationFeedbackChange={setValidationFeedback}
            onSubmitFeedback={onSubmitFeedback}
            onSubmitLifeEvents={onSubmitLifeEvents}
            onResetLifeEvents={onResetLifeEvents}
            onSubmitRectificationConfirmation={onSubmitRectificationConfirmation}
            onPrepareRectificationInterview={prepareRectificationInterview}
            onResumeCoreReport={resumeCoreReport}
            onStartBaziReport={startBaziReport}
            coreInterrupted={coreInterrupted}
            baziRunning={baziRunning}
            authLoaded={authLoaded}
            isSignedIn={Boolean(isSignedIn)}
            focused={calibrationFocus}
            secondary={!calibrationFocus}
          />
        </div>
      ) : complete && reportSections.length > 0 ? (
        <div className="report-doc grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[1fr_260px]">
          <main className="report-main overflow-y-auto bg-cream px-6 py-9 pb-20 sm:px-11">
            <div className="report-doc-head mb-7 flex flex-wrap items-center justify-between gap-4">
              <h1 className="text-[28px] font-light tracking-normal">
                {baziMode ? "Your BaZi Report" : t("session.report.heading")}
              </h1>
              <Button onClick={() => void onExport()} disabled={exportingPdf}>
                {exportingPdf ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <Download size={15} />
                )}
                {exportingPdf ? t("session.report.pdfPreparing") : t("session.report.downloadPdf")}
              </Button>
            </div>
            <ReportOverview
              session={session}
              reportSections={reportSections}
              baziMode={baziMode}
              onJump={scrollToSection}
            />
            {reportSections.map((artifact, index) => (
              <section
                className="report-section mb-12 scroll-mt-20 border-b border-gold/25 pb-12 last:border-0"
                id={`section-${index}`}
                key={artifact.path}
              >
                <div className="mb-2 text-[10px] uppercase tracking-[3px] text-gold">
                  {t("session.report.section", { number: String(index + 1).padStart(2, "0") })}
                </div>
                <div className="mb-4 text-[22px] font-medium tracking-normal text-ink">
                  {titleForArtifact(artifact, locale)}
                </div>
                <MarkdownReport content={artifact.content} />
              </section>
            ))}
            {!baziMode && (
              <ConsultationQuestionPanel sessionId={id} isSignedIn={Boolean(isSignedIn)} />
            )}
          </main>
          <nav className="report-toc hidden overflow-y-auto border-l border-gold/25 bg-cream-2 px-4 py-6 lg:block">
            <h4 className="mb-3.5 text-[11px] uppercase tracking-[2px] text-muted">
              {t("session.report.contents")}
            </h4>
            {reportSections.map((artifact, index) => (
              <button
                key={artifact.path}
                className={cn(
                  "flex w-full items-baseline gap-2 rounded-md px-2.5 py-2 text-left text-[13px] text-body transition hover:bg-gold/10 hover:text-ink",
                  activeSection === index && "bg-gold text-white hover:bg-gold hover:text-white"
                )}
                onClick={() => scrollToSection(index)}
              >
                <span
                  className={cn(
                    "shrink-0 text-[11px] font-bold text-gold",
                    activeSection === index && "text-white"
                  )}
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                {titleForArtifact(artifact, locale)}
              </button>
            ))}
          </nav>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 place-items-center px-6 py-10 text-center">
          <div>
            <div className="mx-auto mb-5 size-11 animate-spin rounded-full border-[3px] border-gold/25 border-t-gold" />
            <h2 className="mb-2 text-2xl font-light">
              {baziMode
                ? baziRunning
                  ? "Generating BaZi report"
                  : "BaZi chart facts are ready"
                : coreInterrupted
                  ? t("session.empty.paused")
                  : awaitingValidationFeedback
                    ? t("session.empty.firstCheckReady")
                    : readerRunning
                      ? t("session.empty.preparingCheck")
                      : t("session.empty.preparing")}
            </h2>
            <p className="mx-auto mb-6 max-w-[420px] text-sm text-body">
              {baziMode
                ? "Review the chart workspace in the Reading tab, then generate the classical report when ready."
                : coreInterrupted
                  ? sanitizeUserMessage(coreJob?.message, t("session.interrupted"))
                  : awaitingValidationFeedback
                    ? t("session.empty.answerChecks")
                    : t("session.empty.progress", {
                        progress: pipelineData
                          ? t("session.empty.partsReady", {
                              completed: pipelineData.completed,
                              total: pipelineData.total
                            })
                          : ""
                      })}
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {baziMode && !complete && (
                <Button
                  disabled={baziRunning || !authLoaded || !isSignedIn}
                  onClick={() => void startBaziReport()}
                >
                  {baziRunning ? (
                    <LoaderCircle className="size-4 animate-spin" />
                  ) : (
                    <BookOpen size={15} />
                  )}
                  {baziRunning ? "Generating..." : "Generate Classical Report"}
                </Button>
              )}
              {coreInterrupted && (
                <Button onClick={() => void resumeCoreReport()}>
                  <RefreshCw size={15} /> {t("session.empty.resume")}
                </Button>
              )}
              <Button
                variant={coreInterrupted ? "outline" : "gold"}
                onClick={() => setTab("reading")}
              >
                <Workflow size={15} /> {t("session.empty.viewProgress")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ReportOverview({
  session,
  reportSections,
  baziMode,
  onJump
}: {
  session: SkillSessionResponse | null;
  reportSections: SkillArtifact[];
  baziMode: boolean;
  onJump: (index: number) => void;
}) {
  const { locale, t } = useI18n();
  const milestones = baziMode
    ? [
        {
          label: t("session.report.journey.chart"),
          done: Boolean(findArtifact(session, "bazi_chart_foundation.md"))
        },
        { label: t("session.report.journey.report"), done: reportSections.length > 0 }
      ]
    : [
        {
          label: t("session.report.journey.chart"),
          done: Boolean(findArtifact(session, CHART_RECORD_JSON))
        },
        {
          label: t("session.report.journey.calibration"),
          done: Boolean(findArtifact(session, "chart_rectification_state.json"))
        },
        {
          label: t("session.report.journey.synthesis"),
          done: Boolean(findArtifact(session, "consultation_dossier.json"))
        },
        { label: t("session.report.journey.report"), done: reportSections.length > 0 }
      ];
  const updatedAt = reportSections.reduce<string | null>(
    (latest, artifact) => (!latest || artifact.updatedAt > latest ? artifact.updatedAt : latest),
    null
  );

  return (
    <section className="mb-10 border-b border-gold/25 pb-7" aria-labelledby="report-overview-title">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <div className="mb-2 text-[10px] uppercase tracking-[3px] text-gold">
            {t("session.report.kicker")}
          </div>
          <h2 id="report-overview-title" className="mb-2 text-xl font-medium text-ink">
            {t("session.report.overviewTitle")}
          </h2>
          <p className="m-0 text-[13px] leading-7 text-body">{t("session.report.overviewBody")}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2 text-[11px] text-muted">
          <span className="rounded-full border border-gold/25 px-3 py-1.5">
            {t("session.report.sectionCount", { count: String(reportSections.length) })}
          </span>
          {updatedAt ? (
            <span className="rounded-full border border-gold/25 px-3 py-1.5">
              {t("session.report.updated", {
                time: new Date(updatedAt).toLocaleDateString(locale)
              })}
            </span>
          ) : null}
        </div>
      </div>

      <div className="mb-6">
        <div className="mb-3 text-[10px] uppercase tracking-[2px] text-muted">
          {t("session.report.journey")}
        </div>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
          {milestones.map((milestone, index) => (
            <div key={milestone.label} className="flex items-center gap-2 text-[12px] text-body">
              <CheckCircle2
                className={cn("size-4", milestone.done ? "text-gold" : "text-muted/40")}
              />
              <span>{milestone.label}</span>
              {index < milestones.length - 1 ? <span className="text-muted/50">/</span> : null}
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1" aria-label={t("session.report.contents")}>
        {reportSections.map((artifact, index) => (
          <button
            key={artifact.path}
            type="button"
            className="shrink-0 rounded-md border border-gold/25 px-3 py-2 text-left text-[12px] text-body transition hover:border-gold hover:text-ink"
            onClick={() => onJump(index)}
          >
            <span className="mr-2 text-[10px] font-bold text-gold">
              {String(index + 1).padStart(2, "0")}
            </span>
            {titleForArtifact(artifact, locale)}
          </button>
        ))}
      </div>
    </section>
  );
}

function deriveReadingProductPhases({
  baziMode,
  session,
  pipelineData,
  readerRunning,
  awaitingValidationFeedback,
  jobActive,
  complete,
  calibrationDone,
  reportReady,
  baziRunning,
  t
}: {
  baziMode: boolean;
  session: SkillSessionResponse | null;
  pipelineData: PipelineData | null;
  readerRunning: boolean;
  awaitingValidationFeedback: boolean;
  jobActive: boolean;
  complete: boolean;
  calibrationDone: boolean;
  reportReady: boolean;
  baziRunning: boolean;
  t: Translate;
}): ReadingProductPhase[] {
  const hasSession = Boolean(session);
  const hasVedicChart = Boolean(findArtifact(session, CHART_RECORD_JSON));
  const hasBaziChart = Boolean(findArtifact(session, "bazi_chart_foundation.md"));
  const hasChart = baziMode ? hasBaziChart : hasVedicChart;
  const revealStarted = Boolean(
    complete ||
    jobActive ||
    baziRunning ||
    (pipelineData && pipelineData.completed > (baziMode ? 1 : 2))
  );

  const calibrationActive = !baziMode && (readerRunning || awaitingValidationFeedback);
  return [
    {
      id: "input",
      label: t("session.phase.input"),
      detail: hasSession ? t("session.phase.input.done") : t("session.phase.input.waiting"),
      status: hasSession ? "done" : "active"
    },
    {
      id: "calibration",
      label: baziMode ? t("session.phase.calibration.bazi") : t("session.phase.calibration"),
      detail: baziMode
        ? t("session.phase.calibration.baziDone")
        : calibrationDone
          ? t("session.phase.calibration.done")
          : calibrationActive
            ? t("session.phase.calibration.active")
            : t("session.phase.calibration.preparing"),
      status: calibrationDone ? "done" : calibrationActive || hasSession ? "active" : "pending"
    },
    {
      id: "chart",
      label: t("session.phase.chart"),
      detail: hasChart
        ? calibrationDone
          ? t("session.phase.chart.ready")
          : t("session.phase.chart.computed")
        : t("session.phase.chart.calculating"),
      status: hasChart && calibrationDone ? "done" : calibrationDone ? "active" : "pending"
    },
    {
      id: "reveal",
      label: t("session.phase.reveal"),
      detail: complete
        ? t("session.phase.reveal.complete")
        : revealStarted
          ? t("session.phase.reveal.running")
          : t("session.phase.reveal.next"),
      status: complete ? "done" : revealStarted ? "active" : "pending"
    },
    {
      id: "report",
      label: t("session.phase.report"),
      detail: reportReady ? t("session.phase.report.ready") : t("session.phase.report.final"),
      status: reportReady ? "done" : complete ? "active" : "pending"
    }
  ];
}

function ReadingJourneyBar({ phases }: { phases: ReadingProductPhase[] }) {
  const activeIndex = Math.max(
    0,
    phases.findIndex((phase) => phase.status === "active")
  );
  const activePhase = phases[activeIndex] ?? phases[0];

  return (
    <nav
      className="relative z-10 shrink-0 border-b border-gold/18 bg-night/88 px-4 py-3 text-cream shadow-[0_14px_44px_rgba(0,0,0,0.22)] backdrop-blur-xl sm:px-8"
      aria-label="Reading progress"
    >
      <div className="mx-auto max-w-[1120px]">
        <div className="flex items-center justify-between gap-4 md:hidden">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[1.8px] text-gold/70">
              {activeIndex + 1} / {phases.length}
            </div>
            <div className="truncate text-sm font-semibold text-cream">{activePhase.label}</div>
          </div>
          <div className="truncate text-right text-[12px] text-cream/48">{activePhase.detail}</div>
        </div>
        <div className="hidden grid-cols-5 gap-5 md:grid">
          {phases.map((phase, index) => (
            <div
              key={phase.id}
              className={cn("min-w-0", phase.status === "pending" && "opacity-45")}
              aria-current={phase.status === "active" ? "step" : undefined}
            >
              <div className="mb-1 flex items-center gap-2">
                <span
                  className={cn(
                    "grid size-5 shrink-0 place-items-center rounded-full border text-[10px] font-semibold",
                    phase.status === "done"
                      ? "border-gold bg-gold text-night"
                      : phase.status === "active"
                        ? "border-gold bg-gold/14 text-gold-light"
                        : "border-gold/25 text-cream/40"
                  )}
                >
                  {phase.status === "done" ? "✓" : index + 1}
                </span>
                <span className="truncate text-[12.5px] font-semibold text-cream">
                  {phase.label}
                </span>
              </div>
              <div className="truncate pl-7 text-[11px] text-cream/42">{phase.detail}</div>
            </div>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-5 gap-1.5">
          {phases.map((phase) => (
            <span
              key={phase.id}
              className={cn(
                "h-0.5 rounded-full",
                phase.status === "done"
                  ? "bg-gold"
                  : phase.status === "active"
                    ? "bg-gold/65"
                    : "bg-white/10"
              )}
            />
          ))}
        </div>
      </div>
    </nav>
  );
}

function SessionAuthControls() {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-2">
      <LanguageSwitcher />
      <SignedOut>
        <span className="hidden rounded-full border border-gold/25 bg-gold/10 px-2.5 py-1 text-[11px] font-medium text-gold-dim sm:inline-flex">
          {t("common.trialMode")}
        </span>
        <SignInButton mode="modal">
          <Button variant="ghost" size="sm" className="hidden sm:inline-flex">
            {t("common.signIn")}
          </Button>
        </SignInButton>
        <SignUpButton mode="modal">
          <Button size="sm">{t("common.createAccount")}</Button>
        </SignUpButton>
      </SignedOut>
      <SignedIn>
        <AccountCenter compact />
      </SignedIn>
    </div>
  );
}

function ReadingRevealPanel({
  session,
  pipelineData,
  selectedStageId,
  stages,
  baziMode,
  reportReady,
  reportSectionCount,
  onOpenReport,
  onSelectStage
}: {
  session: SkillSessionResponse | null;
  pipelineData: PipelineData | null;
  selectedStageId: string;
  stages: StageDef[];
  baziMode: boolean;
  reportReady: boolean;
  reportSectionCount: number;
  onOpenReport: () => void;
  onSelectStage: (stageId: string) => void;
}) {
  const { t } = useI18n();
  const stageAgg = useMemo(
    () => (pipelineData ? aggregateWorkshopStages(pipelineData.nodes, stages) : null),
    [pipelineData, stages]
  );
  const activeStage = useMemo(
    () => (stageAgg ? activeStageFromAggregation(stages, stageAgg) : stages[0]),
    [stageAgg, stages]
  );
  const revealState = useMemo(
    () => (baziMode ? null : deriveChartRevealState(pipelineData)),
    [baziMode, pipelineData]
  );
  const revealCoordinates = useMemo(
    () =>
      baziMode
        ? null
        : chartRevealCoordinatesFromRecord(parseJsonArtifact(session, CHART_RECORD_JSON)),
    [baziMode, session]
  );
  const baziReveal = useMemo(
    () => (baziMode ? deriveBaziRevealCopy(pipelineData) : null),
    [baziMode, pipelineData]
  );
  const title = revealState?.title ?? baziReveal?.title ?? t("session.map.loading");
  const caption = revealState?.caption ?? baziReveal?.caption ?? "";
  const progressLabel = revealState?.progressLabel ?? baziReveal?.progressLabel ?? "0/0";
  const percent = pipelineData?.percent ?? 0;
  const readyCopy = {
    eyebrow: t("session.reveal.readyEyebrow"),
    title: t("session.reveal.readyTitle"),
    body: t("session.reveal.readyBody", { count: reportSectionCount }),
    cta: t("session.reveal.readyCta"),
    detail: t("session.reveal.readyDetail")
  };

  return (
    <section
      className={cn(
        "relative min-w-0 overflow-hidden bg-night text-cream max-lg:min-h-[720px] lg:order-1 lg:min-h-0",
        reportReady ? "order-1" : "order-2"
      )}
    >
      <div className="pointer-events-none absolute inset-0 opacity-90">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_28%,rgba(201,169,110,0.16),transparent_32%),radial-gradient(circle_at_82%_18%,rgba(237,217,163,0.08),transparent_28%),linear-gradient(180deg,rgba(15,12,9,0.78),rgba(28,22,16,0.96))]" />
        <div className="absolute left-1/2 top-[48%] h-[720px] w-[720px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-gold/10 shadow-[0_0_120px_rgba(201,169,110,0.08)]" />
        <div className="absolute left-1/2 top-[48%] h-[520px] w-[520px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-gold/10" />
      </div>

      <div className="relative z-[1] mx-auto flex min-h-full max-w-[760px] flex-col justify-center gap-6 px-5 py-8 sm:px-8 lg:h-full lg:overflow-y-auto">
        <div className="text-center">
          <div className="mb-2 text-[10px] uppercase tracking-[3px] text-gold/72">
            {reportReady ? readyCopy.eyebrow : t("session.reveal.eyebrow")}
          </div>
          <h2 className="mx-auto max-w-[620px] text-[25px] font-light leading-tight tracking-normal text-cream sm:text-[32px]">
            {reportReady
              ? readyCopy.title
              : baziMode
                ? t("session.reveal.baziTitle")
                : t("session.reveal.title")}
          </h2>
          <p className="mx-auto mt-3 max-w-[520px] text-[13.5px] leading-[1.8] text-cream/62">
            {reportReady
              ? readyCopy.body
              : baziMode
                ? t("session.reveal.baziBody")
                : t("session.reveal.body")}
          </p>
        </div>

        <div className="flex justify-center">
          {pipelineData ? (
            baziMode ? (
              <BaziRevealProgress data={pipelineData} />
            ) : (
              <ChartRevealProgress
                state={revealState ?? undefined}
                coordinates={revealCoordinates}
              />
            )
          ) : (
            <div className="grid min-h-[360px] place-items-center text-center text-cream/58">
              <div>
                <LoaderCircle className="mx-auto size-8 animate-spin text-gold" />
                <p className="mt-3 text-sm">{t("session.map.loading")}</p>
              </div>
            </div>
          )}
        </div>

        <div className="rounded-[18px] border border-gold/25 bg-[rgba(16,12,22,0.68)] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.35),inset_0_1px_0_rgba(255,255,255,0.05)] backdrop-blur-xl">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="mb-1 text-[10px] uppercase tracking-[2px] text-gold/75">
                {t("session.reveal.currentFocus")}
              </div>
              <h3 className="m-0 text-base font-semibold tracking-normal text-cream">{title}</h3>
            </div>
            <Badge variant={statusBadgeVariant(stageAgg?.[activeStage.id]?.status ?? "pending")}>
              {t(`status.${stageAgg?.[activeStage.id]?.status ?? "pending"}`)}
            </Badge>
          </div>
          <p className="m-0 text-[13px] leading-[1.75] text-cream/66">{caption}</p>
          <div className="mt-4">
            <div className="mb-2 flex items-center justify-between text-[11px] uppercase tracking-[1.4px] text-cream/45">
              <span>{progressLabel}</span>
              <span>{percent}%</span>
            </div>
            <div
              className="h-[7px] overflow-hidden rounded-full bg-white/8"
              role="progressbar"
              aria-valuenow={percent}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <span
                className="block h-full rounded-full bg-linear-to-r from-gold-dim via-gold to-gold-light transition-[width] duration-500"
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>
        </div>

        {reportReady && (
          <div className="rounded-[18px] border border-gold/40 bg-gold/12 p-5 text-center shadow-[0_24px_80px_rgba(201,169,110,0.12)] backdrop-blur-xl">
            <div className="mx-auto grid size-10 place-items-center rounded-full border border-gold/45 bg-gold text-night">
              <CheckCircle2 className="size-5" aria-hidden="true" />
            </div>
            <p className="mx-auto mb-4 mt-3 max-w-[520px] text-[13px] leading-6 text-cream/62">
              {readyCopy.detail}
            </p>
            <Button size="lg" onClick={onOpenReport}>
              <BookOpen className="size-4" aria-hidden="true" />
              {readyCopy.cta}
            </Button>
          </div>
        )}

        {pipelineData && stageAgg && (
          <details className="rounded-[18px] border border-gold/18 bg-[rgba(16,12,22,0.46)] p-4 backdrop-blur-xl">
            <summary className="cursor-pointer select-none text-[11px] uppercase tracking-[2px] text-gold/72 outline-none">
              {t("session.reveal.details")}
            </summary>
            <div className="mt-4 grid gap-2">
              {stages.map((stage, index) => {
                const stat = stageAgg[stage.id] ?? { status: "pending", done: 0, total: 0 };
                const selected = selectedStageId === stage.id;
                const active = activeStage.id === stage.id;
                return (
                  <button
                    type="button"
                    key={stage.id}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-xl border px-3.5 py-3 text-left transition",
                      selected
                        ? "border-gold bg-gold/15 text-cream shadow-[0_0_0_1px_rgba(201,169,110,0.24)]"
                        : "border-gold/16 bg-white/[0.035] text-cream/68 hover:border-gold/40 hover:bg-gold/8"
                    )}
                    onClick={() => onSelectStage(stage.id)}
                  >
                    <span
                      className={cn(
                        "grid size-7 shrink-0 place-items-center rounded-full border text-[11px] font-semibold tabular-nums",
                        active
                          ? "border-gold bg-gold text-night"
                          : selected
                            ? "border-gold/70 bg-gold/20 text-gold-light"
                            : "border-gold/25 bg-night-3 text-cream/48"
                      )}
                    >
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-cream">
                        {stageLabelFor(stage, t)}
                      </span>
                      <span className="mt-0.5 block text-[12px] text-cream/45">
                        {stageSubFor(stage, t)}
                      </span>
                    </span>
                    <span className="shrink-0 text-right text-[11px] uppercase tracking-[1px] text-cream/45">
                      {stageProgressLabel(stat, t)}
                    </span>
                  </button>
                );
              })}
            </div>
          </details>
        )}
      </div>
    </section>
  );
}

function BaziRevealProgress({ data }: { data: PipelineData }) {
  const hasChart = data.nodes.some(
    (node) => node.id === "bazi_chart" && node.status === "completed"
  );
  const hasReport = data.nodes.some(
    (node) => node.id === "bazi_report" && node.status === "completed"
  );
  const pillars = ["Year", "Month", "Day", "Hour"];
  return (
    <div className="w-full max-w-[460px] rounded-[22px] border border-gold/18 bg-[rgba(16,12,22,0.36)] p-6 shadow-[0_28px_90px_rgba(0,0,0,0.35)] backdrop-blur-xl">
      <div className="grid grid-cols-4 gap-3">
        {pillars.map((pillar, index) => (
          <div
            key={pillar}
            className={cn(
              "relative min-h-[150px] overflow-hidden rounded-xl border px-3 py-4 text-center transition",
              hasChart
                ? "border-gold/35 bg-gold/10 text-gold-light"
                : "border-gold/16 bg-white/[0.035] text-cream/38"
            )}
          >
            <div className="absolute inset-x-3 top-3 h-px bg-gold/25" />
            <div className="mt-5 text-[10px] uppercase tracking-[1.7px] text-current/70">
              {pillar}
            </div>
            <div className="mt-5 text-2xl font-light">{hasChart ? "柱" : "·"}</div>
            <div className="mt-4 text-[11px] text-current/58">{index + 1}/4</div>
          </div>
        ))}
      </div>
      <div className="mt-5 rounded-xl border border-gold/20 bg-night/55 px-4 py-3 text-center">
        <div className="text-[10px] uppercase tracking-[2px] text-gold/70">BaZi reveal</div>
        <div className="mt-1 text-sm font-semibold text-cream">
          {hasReport
            ? "Classical report ready"
            : hasChart
              ? "Four pillars verified"
              : "Calculating pillars"}
        </div>
      </div>
    </div>
  );
}

function activeStageFromAggregation(
  stages: StageDef[],
  stageAgg: Record<string, { status: StageStatus; done: number; total: number }>
): StageDef {
  const active = stages.find(
    (stage) => stageAgg[stage.id]?.status === "running" || stageAgg[stage.id]?.status === "waiting"
  );
  if (active) return active;
  return [...stages].reverse().find((stage) => stageAgg[stage.id]?.status === "done") ?? stages[0];
}

function deriveBaziRevealCopy(data: PipelineData | null) {
  if (!data) {
    return {
      title: "Preparing BaZi workspace",
      caption: "Waiting for the chart calculation to start.",
      progressLabel: "0/0"
    };
  }
  const chart = data.nodes.find((node) => node.id === "bazi_chart");
  const report = data.nodes.find((node) => node.id === "bazi_report");
  if (report?.status === "completed") {
    return {
      title: "Classical report ready",
      caption: "The verified four-pillar chart has been converted into the classical report.",
      progressLabel: `${data.completed}/${data.total}`
    };
  }
  if (report?.status === "running" || report?.status === "waiting") {
    return {
      title: "Generating classical interpretation",
      caption: "The chart facts are ready. The system is applying the BaZi classics to the report.",
      progressLabel: `${data.completed}/${data.total}`
    };
  }
  if (chart?.status === "completed") {
    return {
      title: "Four pillars verified",
      caption: "The deterministic BaZi chart workspace is ready for the classical reading.",
      progressLabel: `${data.completed}/${data.total}`
    };
  }
  return {
    title: "Calculating four pillars",
    caption:
      "The system is turning the birth date, time, calendar type, and place into the BaZi chart facts.",
    progressLabel: `${data.completed}/${data.total}`
  };
}

function stageSubFor(stage: StageDef, t: Translate) {
  const key = `stage.${stage.id}.sub`;
  const text = t(key);
  return text === key ? stage.sub : text;
}

function stageProgressLabel(
  stat: { status: StageStatus; done: number; total: number },
  t: Translate
) {
  if (stat.status === "waiting") return t("status.waiting");
  if (stat.total > 1) return `${stat.done}/${stat.total}`;
  return t(`status.${stat.status}`);
}

function WorkshopDetailPanel({
  selectedStageId,
  stages,
  baziMode,
  session,
  pipelineData,
  birthInfo,
  readerRunning,
  readerStartedAt,
  now,
  validationFeedback,
  submittingFeedback,
  submittingLifeEvents,
  rectificationClarification,
  submittingRectificationConfirmation,
  preparingRectificationInterview,
  onValidationFeedbackChange,
  onSubmitFeedback,
  onSubmitLifeEvents,
  onResetLifeEvents,
  onSubmitRectificationConfirmation,
  onPrepareRectificationInterview,
  onResumeCoreReport,
  onStartBaziReport,
  coreInterrupted,
  baziRunning,
  authLoaded,
  isSignedIn,
  focused = false,
  secondary = false
}: {
  selectedStageId: string;
  stages: StageDef[];
  baziMode: boolean;
  session: SkillSessionResponse | null;
  pipelineData: PipelineData | null;
  birthInfo: BirthInfo;
  readerRunning: boolean;
  readerStartedAt: number | null;
  now: number;
  validationFeedback: string;
  submittingFeedback: boolean;
  submittingLifeEvents: boolean;
  rectificationClarification: RectificationClarification | null;
  submittingRectificationConfirmation: boolean;
  preparingRectificationInterview: boolean;
  onValidationFeedbackChange: (value: string) => void;
  onSubmitFeedback: (event: FormEvent) => void;
  onSubmitLifeEvents: (events: RectificationLifeEventInput[]) => Promise<void>;
  onResetLifeEvents: () => Promise<void>;
  onSubmitRectificationConfirmation: (
    responses: RectificationConfirmationResponse[]
  ) => Promise<void>;
  onPrepareRectificationInterview: (action?: RectificationInterviewAction) => Promise<void>;
  onResumeCoreReport: () => Promise<void>;
  onStartBaziReport: () => Promise<void>;
  coreInterrupted: boolean;
  baziRunning: boolean;
  authLoaded: boolean;
  isSignedIn: boolean;
  focused?: boolean;
  secondary?: boolean;
}) {
  const { t } = useI18n();
  const stage = stages.find((item) => item.id === selectedStageId) ?? stages[0];
  const stageLabel = stageLabelFor(stage, t);
  const copy = localizedStageCopy(stage.id, t);
  const nodes = pipelineData?.nodes.filter((node) => stage.match(node.id)) ?? [];
  const stageAgg = pipelineData
    ? aggregateWorkshopStages(pipelineData.nodes, stages)[stage.id]
    : null;
  const status = stage.seed ? "done" : (stageAgg?.status ?? "pending");
  const focusedCalibration = focused && stage.id === "reader";
  const rectificationState = focusedCalibration
    ? parseRectificationState(
        findArtifact(session, "chart_rectification_state.json")?.content ?? ""
      )
    : null;

  return (
    <aside
      className={cn(
        "relative px-6 py-7",
        focused
          ? focusedCalibration
            ? "mx-auto w-full max-w-[780px] bg-transparent sm:px-8 sm:py-5"
            : "mx-auto w-full max-w-[780px] rounded-[22px] border border-gold/24 bg-cream shadow-[0_32px_100px_rgba(0,0,0,0.42)] sm:px-8 sm:py-7"
          : secondary
            ? "order-1 border-t border-gold/20 bg-cream max-lg:border-t lg:order-2 lg:min-h-0 lg:overflow-y-auto lg:border-l lg:border-t-0"
            : "border-r border-gold/25 bg-cream max-lg:border-b max-lg:border-r-0 lg:min-h-0 lg:overflow-y-auto"
      )}
    >
      {focusedCalibration && (
        <RectificationFocusHeader
          state={rectificationState}
          birthInfo={birthInfo}
          readerRunning={readerRunning || preparingRectificationInterview}
        />
      )}
      {!focused && !focusedCalibration && (
        <StageInfoPopover stageLabel={stageLabel} copy={copy} className="absolute right-6 top-7" />
      )}
      {!focusedCalibration && (
        <>
          <div className="mb-2 pr-9 text-[10px] uppercase tracking-[2.4px] text-gold">
            {focused ? t("session.phase.calibration") : t("session.detail.eyebrow")}
          </div>
          <div className={cn("mb-5 flex items-start justify-between gap-3", !focused && "pr-9")}>
            <h3 className="min-w-0 text-lg font-semibold tracking-normal text-ink">{stageLabel}</h3>
            <Badge variant={statusBadgeVariant(status)}>{t(`status.${status}`)}</Badge>
          </div>
        </>
      )}

      <div
        className={cn(
          focusedCalibration &&
            "rounded-[22px] border border-gold/24 bg-cream px-5 py-5 shadow-[0_32px_100px_rgba(0,0,0,0.42),inset_0_1px_0_rgba(255,255,255,0.55)] sm:px-7"
        )}
      >
        {stage.id === "src" ? (
          <BirthDetail birthInfo={birthInfo} />
        ) : stage.id === "chart" ? (
          <ChartFactsDetail session={session} status={status} birthInfo={birthInfo} />
        ) : baziMode ? (
          <BaziStageDetail
            stageId={stage.id}
            session={session}
            nodes={nodes}
            status={status}
            baziRunning={baziRunning}
            onStartBaziReport={onStartBaziReport}
            authLoaded={authLoaded}
            isSignedIn={isSignedIn}
          />
        ) : stage.id === "reader" ? (
          <ReaderDetail
            session={session}
            readerRunning={readerRunning}
            readerStartedAt={readerStartedAt}
            now={now}
            validationFeedback={validationFeedback}
            submittingFeedback={submittingFeedback}
            submittingLifeEvents={submittingLifeEvents}
            rectificationClarification={rectificationClarification}
            submittingRectificationConfirmation={submittingRectificationConfirmation}
            preparingRectificationInterview={preparingRectificationInterview}
            onValidationFeedbackChange={onValidationFeedbackChange}
            onSubmitFeedback={onSubmitFeedback}
            onSubmitLifeEvents={onSubmitLifeEvents}
            onResetLifeEvents={onResetLifeEvents}
            onSubmitRectificationConfirmation={onSubmitRectificationConfirmation}
            onPrepareRectificationInterview={onPrepareRectificationInterview}
            authLoaded={authLoaded}
            isSignedIn={isSignedIn}
          />
        ) : (
          <CoreStageDetail
            stageId={stage.id}
            session={session}
            nodes={nodes}
            status={status}
            onResumeCoreReport={onResumeCoreReport}
            coreInterrupted={coreInterrupted}
          />
        )}
      </div>
    </aside>
  );
}

function compactBirthTimeRangeParts(
  start?: string,
  end?: string
): { start: string; end?: string } | null {
  if (!start) return null;

  const parseLocalDateTime = (value: string) => {
    const match = value.trim().match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)$/);
    return match ? { date: match[1], time: match[2] } : null;
  };
  const startParts = parseLocalDateTime(start);

  if (!end || end === start) return { start: startParts?.time ?? start };

  const endParts = parseLocalDateTime(end);
  if (startParts && endParts && startParts.date === endParts.date) {
    return { start: startParts.time, end: endParts.time };
  }
  return { start, end };
}

function RectificationFocusHeader({
  state,
  birthInfo,
  readerRunning
}: {
  state: RectificationState | null;
  birthInfo: BirthInfo;
  readerRunning: boolean;
}) {
  const { t } = useI18n();
  const conclusion =
    state?.status === "rectification_confirmation_required" &&
    state.rectificationConclusion?.confirmation?.status !== "rejected"
      ? state.rectificationConclusion
      : undefined;
  const corrected = conclusion?.correctedBirthTime;
  const interval = conclusion?.selectedInterval;
  const evidenceCount =
    state?.selectionEvidence?.calibrationEpisodeCount ??
    state?.selectionEvidence?.calibrationEventCount ??
    state?.lifeEventLedger?.independentEpisodeCount ??
    state?.lifeEventLedger?.events?.length ??
    0;
  const resolved = Boolean(conclusion);
  const comparing =
    readerRunning || state?.status === "collecting_evidence" || state?.status === "underdetermined";
  const displayTime = corrected?.localTime || birthInfo.time || "—";
  const compactInterval = compactBirthTimeRangeParts(interval?.start, interval?.end);
  const displayRange = compactInterval
    ? compactInterval.end
      ? interval?.boundarySemantics === "start_inclusive_end_exclusive"
        ? t("session.rectification.conclusion.rangeExclusive", compactInterval)
        : `${compactInterval.start} – ${compactInterval.end}`
      : compactInterval.start
    : displayTime;
  const copy = {
    eyebrow: t("session.rectification.focus.eyebrow"),
    title: t(
      resolved
        ? "session.rectification.focus.titleReady"
        : "session.rectification.focus.titleCollecting"
    ),
    body: t(
      resolved
        ? "session.rectification.focus.bodyReady"
        : "session.rectification.focus.bodyCollecting"
    ),
    dial: t(
      resolved
        ? "session.rectification.focus.dialReady"
        : comparing
          ? "session.rectification.focus.dialComparing"
          : "session.rectification.focus.dialReported"
    ),
    evidence: t("session.rectification.focus.evidence", { count: evidenceCount }),
    action: t(
      resolved
        ? "session.rectification.focus.actionReady"
        : "session.rectification.focus.actionCollecting"
    )
  };

  return (
    <header className="mb-4 text-center text-cream" aria-live="polite">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-normal text-gold-light/70">
        {copy.eyebrow}
      </div>
      <h1 className="mx-auto max-w-[620px] text-[26px] font-light leading-tight tracking-normal text-cream sm:text-[32px]">
        {copy.title}
      </h1>
      <p className="mx-auto mt-2 max-w-[600px] text-[12.5px] leading-5 text-cream/58">
        {copy.body}
      </p>

      <div className="relative mx-auto mt-2 h-[112px] w-full max-w-[380px] overflow-hidden">
        <svg viewBox="0 0 420 180" className="absolute inset-0 size-full" aria-hidden>
          <defs>
            <linearGradient id="rectification-focus-gradient" x1="0" x2="1">
              <stop offset="0" stopColor="rgba(201,169,110,0.18)" />
              <stop offset="0.5" stopColor="rgba(237,217,163,0.95)" />
              <stop offset="1" stopColor="rgba(201,169,110,0.18)" />
            </linearGradient>
          </defs>
          <path
            d="M 38 154 A 172 132 0 0 1 382 154"
            fill="none"
            stroke="rgba(201,169,110,0.16)"
            strokeWidth="9"
            strokeLinecap="round"
            pathLength="100"
          />
          <path
            d="M 38 154 A 172 132 0 0 1 382 154"
            fill="none"
            stroke="url(#rectification-focus-gradient)"
            strokeWidth="9"
            strokeLinecap="round"
            pathLength="100"
            className={cn(
              "transition-opacity duration-700",
              resolved ? "opacity-100" : "opacity-45",
              comparing && !resolved && "animate-pulse"
            )}
          />
          {Array.from({ length: 13 }, (_, index) => {
            const angle = Math.PI - (Math.PI * index) / 12;
            const x1 = 210 + Math.cos(angle) * 156;
            const y1 = 154 - Math.sin(angle) * 120;
            const x2 = 210 + Math.cos(angle) * 166;
            const y2 = 154 - Math.sin(angle) * 128;
            return (
              <line
                key={index}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke="rgba(237,217,163,0.34)"
                strokeWidth={index % 3 === 0 ? 2 : 1}
              />
            );
          })}
        </svg>
        <div className="absolute inset-x-8 bottom-0 text-center">
          <div className="text-[10px] uppercase tracking-normal text-gold-light/55">
            {copy.dial}
          </div>
          <div className="mx-auto mt-0.5 max-w-[320px] break-words text-[15px] font-semibold leading-5 tabular-nums text-cream sm:text-base">
            {displayRange}
          </div>
          <div className="mt-0.5 flex items-center justify-center gap-2 text-[10.5px] text-cream/42">
            <span>{copy.evidence}</span>
            <span aria-hidden>·</span>
            <span>{copy.action}</span>
          </div>
        </div>
      </div>
    </header>
  );
}

function BaziStageDetail({
  stageId,
  session,
  nodes,
  status,
  baziRunning,
  onStartBaziReport,
  authLoaded,
  isSignedIn
}: {
  stageId: string;
  session: SkillSessionResponse | null;
  nodes: PipelineNode[];
  status: StageStatus;
  baziRunning: boolean;
  onStartBaziReport: () => Promise<void>;
  authLoaded: boolean;
  isSignedIn: boolean;
}) {
  const { t } = useI18n();
  const copy = localizedStageCopy(stageId, t);
  const completedNodes = nodes.filter((node) => node.status === "completed");
  const runningNodes = nodes.filter((node) => node.status === "running");
  const artifact = findStageArtifact(session, stageId, nodes);
  const canGenerate = stageId === "bazi_report" && status !== "done";

  return (
    <>
      <StageStatusSummary
        status={status}
        copy={copy}
        completed={completedNodes.length}
        total={nodes.length}
        running={runningNodes.length}
        durationSeconds={completedNodes.reduce((sum, node) => sum + (node.durationSeconds ?? 0), 0)}
        coreInterrupted={false}
      />

      {canGenerate && (
        <div className="my-5 rounded-xl border border-gold/30 bg-gold/10 px-4 py-3">
          <DetailSubtitle>Classical report</DetailSubtitle>
          <p className="m-0 mb-3 text-[13px] leading-[1.7] text-body">
            Generate the BaZi report from the chart facts using the repo-local three-classics skill.
          </p>
          <Button
            className="w-full"
            disabled={baziRunning || !authLoaded || !isSignedIn}
            onClick={() => void onStartBaziReport()}
          >
            {baziRunning ? (
              <>
                <LoaderCircle className="size-4 animate-spin" /> Generating...
              </>
            ) : (
              <>
                <BookOpen size={15} /> Generate Classical Report
              </>
            )}
          </Button>
          {authLoaded && !isSignedIn && (
            <p className="m-0 mt-2 text-[12.5px] leading-relaxed text-muted">
              Sign in from the top-right account controls to run the report generator.
            </p>
          )}
        </div>
      )}

      {artifact ? (
        <ResultPreview artifact={artifact} status={status} />
      ) : (
        <EmptyResultState status={status} copy={copy} progress="" />
      )}
    </>
  );
}

function StageInfoPopover({
  stageLabel,
  copy,
  className
}: {
  stageLabel: string;
  copy?: StageCopy;
  className?: string;
}) {
  const { t } = useI18n();
  if (!copy) return null;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "grid size-5 shrink-0 place-items-center rounded-full border border-gold/25 bg-cream-2 text-gold-dim transition hover:border-gold hover:bg-gold/10 hover:text-gold focus:outline-none focus:ring-4 focus:ring-gold/15",
            className
          )}
          aria-label={t("session.guide.aria", { stage: stageLabel })}
        >
          <Info className="size-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(92vw,380px)] p-4" align="end" side="bottom">
        <div className="mb-3">
          <div className="mb-1 text-[10px] uppercase tracking-[1.8px] text-gold">
            {t("session.guide.title")}
          </div>
          <h4 className="m-0 text-base font-semibold text-ink">{stageLabel}</h4>
        </div>
        <div className="grid gap-3 text-[13px] leading-[1.65] text-body">
          <StageInfoBlock title={t("session.guide.purpose")}>{copy.purpose}</StageInfoBlock>
          <StageInfoBlock title={t("session.guide.result")}>{copy.userResult}</StageInfoBlock>
          <StageInfoBlock title={t("session.guide.action")}>{copy.userAction}</StageInfoBlock>
          <div className="border-t border-gold/20 pt-3">
            <StageInfoBlock title={t("session.guide.timing")}>{copy.expected}</StageInfoBlock>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function StageInfoBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-0.5 text-[10px] uppercase tracking-[1.4px] text-muted">{title}</div>
      <p className="m-0">{children}</p>
    </div>
  );
}

function BirthDetail({ birthInfo }: { birthInfo: BirthInfo }) {
  const { t } = useI18n();
  return (
    <>
      <div className="my-4">
        <InfoRow label={t("session.birth.name")} value={birthInfo.name} />
        <InfoRow label={t("session.birth.date")} value={birthInfo.date} />
        <InfoRow label={t("session.birth.time")} value={birthInfo.time} />
        <InfoRow label={t("session.birth.place")} value={birthInfo.place} />
        <InfoRow label={t("session.birth.latitude")} value={birthInfo.latitude} />
        <InfoRow label={t("session.birth.longitude")} value={birthInfo.longitude} />
        <InfoRow label={t("session.birth.precision")} value={birthInfo.timePrecision} />
        <InfoRow label={t("session.birth.effective")} value={birthInfo.effectivePrecision} />
        {birthInfo.gender && <InfoRow label={t("session.birth.gender")} value={birthInfo.gender} />}
        {birthInfo.relationship && (
          <InfoRow label={t("session.birth.relationship")} value={birthInfo.relationship} />
        )}
      </div>
      {birthInfo.concern && (
        <div className="my-4">
          <DetailSubtitle>{t("session.birth.concern")}</DetailSubtitle>
          <p className="m-0 text-[13px] leading-[1.7] text-body">{birthInfo.concern}</p>
        </div>
      )}
    </>
  );
}

function ChartFactsDetail({
  session,
  status,
  birthInfo
}: {
  session: SkillSessionResponse | null;
  status: StageStatus;
  birthInfo: BirthInfo;
}) {
  const { t } = useI18n();
  const copy = localizedStageCopy("chart", t);
  const chartRecordArtifact = findArtifact(session, CHART_RECORD_JSON);
  const chartRecord = useMemo(() => parseJsonArtifact(session, CHART_RECORD_JSON), [session]);
  const inputContext = findArtifact(session, "birth_input_context.json");
  const sensitivityScan = findArtifact(session, "sensitivity_scan.json");
  const activeSensitivityScan = findArtifact(session, "active_chart_sensitivity.json");
  const rectificationArtifact = findArtifact(session, "chart_rectification_state.json");
  const rectificationState = useMemo(
    () => parseRectificationState(rectificationArtifact?.content ?? ""),
    [rectificationArtifact?.content]
  );
  const sections = useMemo(() => chartRecordSections(chartRecord), [chartRecord]);
  const publicationMode = chartDetailPublicationMode(rectificationState);
  const showReferenceNotice =
    publicationMode === "representative" && rectificationState?.status === "corrected_chart_ready";

  return (
    <>
      <StageStatusSummary
        status={status}
        copy={copy}
        completed={chartRecordArtifact ? 1 : 0}
        total={1}
        running={0}
        durationSeconds={0}
        coreInterrupted={false}
      />

      <ChartConfirmationCard
        birthInfo={birthInfo}
        hasChartFacts={Boolean(chartRecordArtifact)}
        rectificationState={rectificationState}
      />

      <details className="my-5 rounded-xl border border-gold/18 bg-cream-2 px-4 py-3">
        <summary className="cursor-pointer select-none text-[11px] uppercase tracking-[1.4px] text-muted outline-none">
          {t("session.chart.sourceFiles")}
        </summary>
        <div className="mt-3 flex flex-wrap gap-2">
          {[
            chartRecordArtifact?.path,
            inputContext?.path,
            sensitivityScan?.path,
            activeSensitivityScan?.path,
            rectificationArtifact?.path
          ]
            .filter((path): path is string => Boolean(path))
            .map((path) => (
              <span
                className="rounded-full border border-gold/25 bg-cream px-2.5 py-1 text-[11px] font-medium text-muted"
                key={path}
              >
                {path}
              </span>
            ))}
        </div>
      </details>

      {rectificationState && <ChartRectificationSummary state={rectificationState} />}

      {publicationMode === "representative" && sections.length > 0 ? (
        <section className="my-5 border-t border-gold/25 pt-4">
          <DetailSubtitle>{t("session.chart.sections")}</DetailSubtitle>
          {showReferenceNotice && (
            <p className="mb-3 mt-0 rounded-xl border border-gold/20 bg-gold/8 px-3.5 py-3 text-[12.5px] leading-[1.65] text-body">
              {t("session.chart.details.reference")}
            </p>
          )}
          <div className="grid gap-3">
            {sections.map((section, index) => (
              <article
                className="rounded-xl border border-gold/25 bg-cream-2 px-4 py-3"
                key={section.id}
              >
                <div className="mb-1.5 flex items-baseline gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-[1.4px] text-gold">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <h4 className="m-0 text-sm font-semibold leading-snug text-ink">
                    {section.title}
                  </h4>
                </div>
                <p className="m-0 whitespace-pre-wrap text-[12.5px] leading-[1.7] text-body">
                  {excerpt(stripMarkdownForPreview(section.body), 520)}
                </p>
              </article>
            ))}
          </div>
        </section>
      ) : publicationMode === "stable_intersection" ? (
        <ChartDetailNotice
          title={t("session.chart.details.stableTitle")}
          body={t("session.chart.details.stableBody")}
        />
      ) : publicationMode === "withheld" ? (
        <ChartDetailNotice
          title={t("session.chart.details.withheldTitle")}
          body={t("session.chart.details.withheldBody")}
        />
      ) : (
        <EmptyResultState status={status} copy={copy} progress="" />
      )}
    </>
  );
}

type ChartDetailPublicationMode = "representative" | "stable_intersection" | "withheld";

function chartDetailPublicationMode(state: RectificationState | null): ChartDetailPublicationMode {
  if (!state) return "representative";
  if (state.status === "multiple_equivalent" && state.reportGate?.fullReportAllowed === true) {
    return "stable_intersection";
  }
  if (
    state.reportGate?.fullReportAllowed === true &&
    (state.status === "not_required" || state.status === "corrected_chart_ready")
  ) {
    return "representative";
  }
  return "withheld";
}

function ChartDetailNotice({ title, body }: { title: string; body: string }) {
  return (
    <section className="my-5 border-t border-gold/25 pt-4">
      <div className="rounded-xl border border-gold/25 bg-cream-2 px-4 py-3">
        <h4 className="m-0 text-sm font-semibold leading-snug text-ink">{title}</h4>
        <p className="mb-0 mt-1.5 text-[12.5px] leading-[1.7] text-body">{body}</p>
      </div>
    </section>
  );
}

function ChartConfirmationCard({
  birthInfo,
  hasChartFacts,
  rectificationState
}: {
  birthInfo: BirthInfo;
  hasChartFacts: boolean;
  rectificationState: RectificationState | null;
}) {
  const { t } = useI18n();
  const latitude = Number(birthInfo.latitude);
  const longitude = Number(birthInfo.longitude);
  const hasCoordinates =
    birthInfo.latitude.trim() !== "" &&
    birthInfo.longitude.trim() !== "" &&
    Number.isFinite(latitude) &&
    Number.isFinite(longitude);
  const locationMode = hasCoordinates
    ? t("session.chart.location.coordinatesReady")
    : t("session.chart.location.placeRecorded");
  const timeMode = birthInfo.timePrecision || t("session.chart.time.recorded");
  const gateAllowed = rectificationState?.reportGate?.fullReportAllowed === true;
  const chartReady =
    hasChartFacts &&
    (!rectificationState ||
      (gateAllowed &&
        ["not_required", "corrected_chart_ready", "multiple_equivalent"].includes(
          rectificationState.status ?? ""
        )));
  const representativeTime =
    rectificationState?.status === "corrected_chart_ready"
      ? rectificationState.rectificationConclusion?.correctedBirthTime?.localTime
      : undefined;
  const statusLabel = chartReady
    ? t("session.chart.readiness.ready")
    : hasChartFacts
      ? t("session.chart.readiness.checks")
      : t("session.chart.readiness.preparing");
  const nextStepLabel = rectificationNextStepLabel(rectificationState, t);

  return (
    <section className="my-5 overflow-hidden rounded-[16px] border border-gold/30 bg-[linear-gradient(135deg,rgba(201,169,110,0.14),rgba(255,255,255,0.035))] shadow-[0_18px_48px_rgba(44,31,15,0.08)]">
      <div className="border-b border-gold/18 px-4 py-3">
        <div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[1.7px] text-gold">
          <MapPinned className="size-4" />{" "}
          {t(chartReady ? "session.chart.confirmed.title" : "session.chart.review.title")}
        </div>
        <p className="m-0 text-[13px] leading-[1.65] text-body">
          {t(chartReady ? "session.chart.confirmed.body" : "session.chart.review.body")}
        </p>
      </div>
      <div className="grid gap-2 p-4">
        <ChartConfirmationRow
          label={t("session.chart.confirmed.time")}
          value={representativeTime || birthInfo.time || "—"}
          detail={timeMode}
        />
        <ChartConfirmationRow
          label={t("session.chart.confirmed.place")}
          value={birthInfo.place || "—"}
          detail={locationMode}
        />
        <ChartConfirmationRow
          label={t("session.chart.confirmed.coordinates")}
          value={hasCoordinates ? `${birthInfo.longitude}, ${birthInfo.latitude}` : "—"}
          detail={t("session.chart.confirmed.coordinatesDetail")}
        />
        <ChartConfirmationRow
          label={t("session.chart.confirmed.readiness")}
          value={statusLabel}
          detail={nextStepLabel || t("session.chart.confirmed.next")}
        />
      </div>
    </section>
  );
}

function rectificationNextStepLabel(state: RectificationState | null, t: Translate): string {
  if (!state) return "";
  if (state.status === "rectification_confirmation_required") {
    return t("session.rectification.conclusion.title");
  }
  if (state.status === "corrected_chart_ready") {
    return t("session.chart.readiness.ready");
  }
  if (state.status === "multiple_equivalent" && state.reportGate?.fullReportAllowed === true) {
    return t("session.rectification.stableReport");
  }
  if (state.status === "collecting_evidence") {
    return t("session.rectification.continueCheck");
  }
  if (state.status === "underdetermined") {
    if (state.rectificationPlan?.action === "reset_rectification_evidence") {
      return t("session.rectification.evidenceReset.title");
    }
    return state.rectificationPlan?.eventCollectionRequired === true
      ? t("session.rectification.continueCheck")
      : t("session.rectification.reviewBirthWindow");
  }
  if (state.status === "input_resolution_required") {
    return t("session.rectification.inputResolution");
  }
  if (state.status === "calculation_failed") {
    return t("session.rectification.calculationFailed");
  }
  return t("session.rectification.continue");
}

function ChartConfirmationRow({
  label,
  value,
  detail
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-xl border border-gold/18 bg-cream/60 px-3 py-2.5">
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-[1.25px] text-muted">{label}</div>
        <div className="mt-0.5 truncate text-sm font-semibold text-ink">{value}</div>
      </div>
      <div className="max-w-[44%] text-right text-[12px] leading-[1.45] text-muted">{detail}</div>
    </div>
  );
}

function ChartRectificationSummary({ state }: { state: RectificationState }) {
  const revision = state.activeChartRevision?.revision ?? 0;
  const gateAllowed = state.reportGate?.fullReportAllowed === true;
  const hasEquivalentCandidates = state.status === "multiple_equivalent";
  const isUnderdetermined = state.status === "underdetermined";
  const needsConfirmation = state.status === "rectification_confirmation_required";
  const needsInputResolution = state.status === "input_resolution_required";
  const calculationFailed = state.status === "calculation_failed";
  const { t } = useI18n();
  const confidenceLabel = gateAllowed
    ? state.status === "multiple_equivalent"
      ? t("session.rectification.stableIntersection")
      : state.status === "corrected_chart_ready"
        ? t("session.rectification.corrected")
        : t("session.rectification.accepted")
    : needsConfirmation
      ? t("session.rectification.conclusion.title")
      : calculationFailed
        ? t("session.rectification.calculationFailed")
        : needsInputResolution
          ? t("session.rectification.inputResolution")
          : hasEquivalentCandidates
            ? t("session.rectification.equivalent")
            : isUnderdetermined
              ? t("session.rectification.underdetermined")
              : t("session.rectification.waiting");
  const confidenceBody = gateAllowed
    ? state.status === "multiple_equivalent"
      ? t("session.rectification.body.stableIntersection", {
          count: state.equivalentCandidateCount ?? 0
        })
      : t("session.rectification.body.ready")
    : needsConfirmation
      ? t("session.rectification.conclusion.body")
      : calculationFailed
        ? t("session.rectification.body.calculationFailed")
        : needsInputResolution
          ? t("session.rectification.body.inputResolution")
          : hasEquivalentCandidates
            ? t("session.rectification.body.equivalent", {
                count: state.equivalentCandidateCount ?? 0
              })
            : isUnderdetermined
              ? t("session.rectification.body.underdetermined")
              : t("session.rectification.body.more");
  const nextStepLabel = rectificationNextStepLabel(state, t);
  const latestRound = state.rectificationRounds?.[state.rectificationRounds.length - 1];
  const latestRoundFeedback = latestRound?.decision?.outcome
    ? t(`session.rectification.round.${latestRound.decision.outcome}`)
    : "";

  return (
    <section className="my-5 border-t border-gold/25 pt-4">
      <DetailSubtitle>{t("session.rectification.title")}</DetailSubtitle>
      <div className="rounded-xl border border-gold/25 bg-cream-2 px-4 py-3">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Badge variant={gateAllowed ? "done" : "neutral"}>{confidenceLabel}</Badge>
          <span className="text-[12px] text-muted">
            {t("session.rectification.reviewMeta", {
              risk: state.riskLevel || "standard",
              revision
            })}
          </span>
        </div>
        <p className="m-0 text-[13px] leading-[1.7] text-body">{confidenceBody}</p>

        <div className="mt-3 grid gap-2 text-[12.5px] leading-[1.6] text-body">
          <InfoRow
            label={t("session.rectification.anchors")}
            value={String(
              state.selectionEvidence?.calibrationEpisodeCount ??
                state.selectionEvidence?.calibrationEventCount ??
                0
            )}
          />
          <InfoRow
            label={t("session.rectification.nextStep")}
            value={nextStepLabel || t("session.rectification.continue")}
          />
          {latestRoundFeedback && (
            <InfoRow label={t("session.rectification.latestAnswer")} value={latestRoundFeedback} />
          )}
        </div>
      </div>
    </section>
  );
}

function RectificationWorkingState({
  mode,
  recordedCount
}: {
  mode: "question" | "comparison";
  recordedCount: number;
}) {
  const { locale } = useI18n();
  const copy =
    locale === "zh"
      ? mode === "comparison"
        ? {
            eyebrow: "正在重新计算",
            title: "正在比较候选出生时间",
            body: `第 ${recordedCount} 件经历已保存。系统正在重算候选盘，再决定下一步。`,
            steps: ["保存这条经历", "重新比较候选时间", "选择下一道问题"]
          }
        : {
            eyebrow: "正在准备下一题",
            title: "正在寻找最有区分度的问题",
            body: "系统只会从你选过的经历中提问，并优先选择能区分当前候选时间的一项。",
            steps: ["读取当前候选", "比较可回答领域", "生成一张问题卡"]
          }
      : locale === "ja"
        ? mode === "comparison"
          ? {
              eyebrow: "再計算中",
              title: "出生時刻の候補を比較しています",
              body: `${recordedCount} 件目の出来事を保存しました。候補を再計算して次の手順を決めます。`,
              steps: ["出来事を保存", "候補時刻を再比較", "次の質問を選択"]
            }
          : {
              eyebrow: "次の質問を準備中",
              title: "最も区別しやすい質問を探しています",
              body: "選択した出来事の範囲だけから、現在の候補を区別できる質問を一つ選びます。",
              steps: ["候補を確認", "回答可能な領域を比較", "質問カードを作成"]
            }
        : mode === "comparison"
          ? {
              eyebrow: "Recalculating",
              title: "Comparing the remaining birth times",
              body: `Event ${recordedCount} is saved. The system is recalculating the candidates before deciding what comes next.`,
              steps: ["Save this event", "Recompare candidate times", "Choose the next question"]
            }
          : {
              eyebrow: "Preparing the next question",
              title: "Finding the most useful question",
              body: "The system asks only about the event areas you selected, prioritizing the one that can separate the current candidates.",
              steps: [
                "Read current candidates",
                "Compare answerable areas",
                "Build one question card"
              ]
            };

  return (
    <section
      className="mt-5 flex min-h-[390px] flex-col items-center justify-center px-4 text-center"
      aria-live="polite"
    >
      <div className="relative mb-7 grid size-24 place-items-center">
        <span className="absolute inset-0 rounded-full border border-gold/20" />
        <span className="absolute inset-2 animate-spin rounded-full border border-transparent border-t-gold/80 [animation-duration:2.2s]" />
        <span className="absolute inset-5 animate-spin rounded-full border border-transparent border-b-gold-light/60 [animation-direction:reverse] [animation-duration:3s]" />
        <Sparkles className="size-5 text-gold" />
      </div>
      <div className="text-[10px] font-semibold uppercase tracking-[2.4px] text-gold-dim">
        {copy.eyebrow}
      </div>
      <h3 className="mb-0 mt-2 text-xl font-semibold tracking-normal text-ink">{copy.title}</h3>
      <p className="mb-0 mt-3 max-w-[480px] text-[13px] leading-6 text-body">{copy.body}</p>
      <div className="mt-7 grid w-full max-w-[520px] gap-2.5 sm:grid-cols-3">
        {copy.steps.map((step, index) => (
          <div
            key={step}
            className="flex min-h-12 items-center gap-2 rounded-lg border border-gold/18 bg-cream-2 px-3 text-left text-[11px] leading-4 text-muted"
          >
            {index === 0 && mode === "comparison" ? (
              <CheckCircle2 className="size-3.5 shrink-0 text-gold" />
            ) : (
              <span className="grid size-4 shrink-0 place-items-center rounded-full border border-gold/35 text-[9px] text-gold-dim">
                {index + 1}
              </span>
            )}
            {step}
          </div>
        ))}
      </div>
    </section>
  );
}

function EventAvailabilityStep({
  lifeStage,
  initialCategories = [],
  disabled = false,
  onContinue
}: {
  lifeStage: string;
  initialCategories?: RectificationLifeEventCategory[];
  disabled?: boolean;
  onContinue: (categories: RectificationLifeEventCategory[]) => void;
}) {
  const { locale, t } = useI18n();
  const [selected, setSelected] = useState<RectificationLifeEventCategory[]>(initialCategories);
  const youngPerson = lifeStage === "child" || lifeStage === "teen";
  const primary = youngPerson
    ? YOUNG_PERSON_RECTIFICATION_CATEGORIES
    : PRIMARY_RECTIFICATION_CATEGORIES;
  const secondary = youngPerson ? [] : SECONDARY_RECTIFICATION_CATEGORIES;
  const copy =
    locale === "zh"
      ? {
          eyebrow: "出生时间校准",
          title: "哪些经历，你记得发生时间？",
          body: "只选你确实记得年份或月份的经历。接下来一次只确认一件。",
          hint: "至少选择 2 类。系统通常会核对 4 件互不重叠的具体事件，不需要写人生履历。",
          more: "更多可以核对的经历",
          selected: (count: number) => `已选择 ${count} 项`,
          continue: "开始逐条确认"
        }
      : locale === "ja"
        ? {
            eyebrow: "出生時刻の確認",
            title: "時期を覚えている出来事はどれですか？",
            body: "年または月を覚えている出来事だけを選んでください。この後は一度に一件ずつ確認します。",
            hint: "2分野以上を選択してください。通常は、重ならない4件の具体的な出来事を順番に確認します。",
            more: "その他の確認できる出来事",
            selected: (count: number) => `${count} 項目を選択`,
            continue: "一件ずつ確認する"
          }
        : {
            eyebrow: "Birth-time calibration",
            title: "Which events can you place in time?",
            body: "Choose only events whose year or month you genuinely remember. We will confirm one at a time.",
            hint: "Choose at least two areas. The check usually compares four distinct events; no life-history essay is needed.",
            more: "More events you may remember",
            selected: (count: number) => `${count} selected`,
            continue: "Confirm them one by one"
          };

  function toggle(category: RectificationLifeEventCategory) {
    setSelected((current) =>
      current.includes(category)
        ? current.filter((value) => value !== category)
        : [...current, category]
    );
  }

  function renderCategory(category: RectificationLifeEventCategory) {
    const Icon = LIFE_EVENT_CATEGORY_ICONS[category];
    const active = selected.includes(category);
    const examples = LIFE_EVENT_CHOICES[category]
      .filter((choice) => choice.id !== "other")
      .slice(0, 2)
      .map((choice) => choice.label[locale])
      .join(" · ");
    return (
      <button
        key={category}
        type="button"
        disabled={disabled}
        aria-pressed={active}
        className={cn(
          "group flex min-h-[92px] items-start gap-3 rounded-xl border px-4 py-3.5 text-left transition-[border-color,background,box-shadow]",
          active
            ? "border-gold bg-gold/10 shadow-[0_0_0_2px_rgba(201,169,110,0.11)]"
            : "border-gold/20 bg-cream-2 hover:border-gold/55 hover:bg-gold/5"
        )}
        onClick={() => toggle(category)}
      >
        <span
          className={cn(
            "mt-0.5 grid size-8 shrink-0 place-items-center rounded-full border transition-colors",
            active
              ? "border-gold bg-gold text-white"
              : "border-gold/30 bg-cream text-gold-dim group-hover:border-gold/60"
          )}
        >
          {active ? <CheckCircle2 size={15} /> : <Icon size={15} />}
        </span>
        <span className="min-w-0">
          <span className="block text-[13px] font-semibold leading-5 text-ink">
            {t(`session.events.category.${category}`)}
          </span>
          <span className="mt-1 block text-[11px] leading-[1.55] text-muted">{examples}</span>
        </span>
      </button>
    );
  }

  return (
    <section className="mt-2 grid gap-5">
      <header className="border-b border-gold/20 pb-5 text-center">
        <div className="text-[10px] font-semibold uppercase tracking-[2.4px] text-gold-dim">
          {copy.eyebrow}
        </div>
        <h2 className="mb-0 mt-2 text-[24px] font-semibold leading-tight tracking-normal text-ink sm:text-[28px]">
          {copy.title}
        </h2>
        <p className="mx-auto mb-0 mt-3 max-w-[560px] text-[13px] leading-6 text-body">
          {copy.body}
        </p>
      </header>

      <div className="grid gap-2.5 sm:grid-cols-2">{primary.map(renderCategory)}</div>

      {secondary.length > 0 && (
        <details className="rounded-xl border border-gold/18 bg-cream-2 px-4 py-3">
          <summary className="cursor-pointer select-none text-[12px] font-semibold text-body outline-none">
            {copy.more}
          </summary>
          <div className="mt-3 grid gap-2.5 sm:grid-cols-2">{secondary.map(renderCategory)}</div>
        </details>
      )}

      <div className="rounded-lg border border-gold/18 bg-gold/5 px-3.5 py-2.5 text-[11.5px] leading-5 text-muted">
        <Info className="mr-1.5 inline size-3.5 text-gold-dim" />
        {copy.hint}
      </div>

      <div className="flex flex-col gap-3 border-t border-gold/20 pt-4 sm:flex-row sm:items-center sm:justify-between">
        <span className="text-[12px] font-medium text-body">{copy.selected(selected.length)}</span>
        <Button
          type="button"
          disabled={disabled || selected.length < 2}
          onClick={() => onContinue(selected)}
        >
          {copy.continue} <ChevronRight size={15} />
        </Button>
      </div>
    </section>
  );
}

function partialLifeEventDateRange(value: string): { start: string; end: string } | null {
  if (/^\d{4}$/.test(value)) {
    return { start: `${value}-01-01`, end: `${value}-12-31` };
  }
  if (/^\d{4}-\d{2}$/.test(value)) {
    const [yearValue, monthValue] = value.split("-");
    const year = Number(yearValue);
    const month = Number(monthValue);
    const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
    return {
      start: `${value}-01`,
      end: `${value}-${String(lastDay).padStart(2, "0")}`
    };
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return { start: value, end: value };
  }
  return null;
}

function LifeEventCollector({
  state,
  interviewContent,
  lifeStage,
  birthDate,
  clarification,
  preparing,
  onPrepare,
  submitting,
  onSubmit,
  onReset,
  authLoaded,
  isSignedIn
}: {
  state: RectificationState;
  interviewContent: string;
  lifeStage: string;
  birthDate: string;
  clarification: RectificationClarification | null;
  preparing: boolean;
  onPrepare: (action?: RectificationInterviewAction) => Promise<void>;
  submitting: boolean;
  onSubmit: (events: RectificationLifeEventInput[]) => Promise<void>;
  onReset: () => Promise<void>;
  authLoaded: boolean;
  isSignedIn: boolean;
}) {
  const { locale, t } = useI18n();
  const ui =
    locale === "zh"
      ? {
          preparing: "正在准备下一道问题…",
          notReady: "下一道问题还没有准备好。",
          prepare: "准备问题",
          exhausted: "暂时找不到适合继续确认的经历",
          exhaustedBody: "我们会保留当前的时间范围，不会假装得出没有依据的精确时间。",
          eyebrow: "出生时间校准",
          title: "先选一件你记得清楚的事",
          body: "不用写完整履历。每次只选一个最接近的经历，再告诉我们大概发生在哪一年。",
          progress: (current: number, total: number) => `第 ${current} / ${total} 件`,
          recorded: (count: number, total: number) => `已记录 ${count} / ${total} 件`,
          chooseEvent: "哪一项最符合？",
          dateTitle: "这件事发生在什么时候？",
          dateHint: "按你真实记得的精度填写，不需要为了显得准确而猜日期。",
          dayKnown: "记得具体日期",
          monthKnown: "记得大概月份",
          yearOnly: "只记得年份",
          yearPlaceholder: "年份",
          record: "记录这件事",
          compare: "提交并比较候选",
          skip: "没有这类经历，换一类",
          reset: "重新选择",
          optionalNote: "补充一句（可选）",
          requiredNote: "请补充几个词说明是什么变化",
          notePlaceholder: "例如：第一次被大学录取",
          noteHint: "不用写小作文，几个词就够了。",
          why: "为什么问这个？",
          selected: "已选择",
          saved: "已记录的经历",
          restart: "清空并重新填写",
          overlap: (date: string) =>
            `这个时间范围与已记录的 ${date} 重叠。请补充到更准确的月份/日期，或选择另一个时期的经历。`,
          futureRange: "这个模糊范围包含尚未发生的日期，请补充到已经发生的月份或具体日期。"
        }
      : locale === "ja"
        ? {
            preparing: "次の質問を準備しています…",
            notReady: "次の質問をまだ準備できません。",
            prepare: "質問を準備",
            exhausted: "続けて確認できる適切な出来事がありません",
            exhaustedBody: "根拠のない精密さを示さず、現在の時間範囲を保ちます。",
            eyebrow: "出生時刻の確認",
            title: "まず、覚えている出来事を一つ選んでください",
            body: "人生の履歴を書く必要はありません。近い出来事を一つ選び、おおよその時期を教えてください。",
            progress: (current: number, total: number) => `${current} / ${total} 件目`,
            recorded: (count: number, total: number) => `${count} / ${total} 件を記録済み`,
            chooseEvent: "最も近いものはどれですか？",
            dateTitle: "この出来事はいつ頃でしたか？",
            dateHint: "実際に覚えている精度で入力してください。日付を推測する必要はありません。",
            dayKnown: "日付まで分かる",
            monthKnown: "月まで分かる",
            yearOnly: "年だけ分かる",
            yearPlaceholder: "年",
            record: "この出来事を記録",
            compare: "送信して候補を比較",
            skip: "該当しないため別の種類へ",
            reset: "選び直す",
            optionalNote: "一言を追加（任意）",
            requiredNote: "数語で内容を補足してください",
            notePlaceholder: "例：大学への合格が決まった",
            noteHint: "長い文章は不要です。数語で十分です。",
            why: "なぜ聞くのですか？",
            selected: "選択済み",
            saved: "記録した出来事",
            restart: "消去してやり直す",
            overlap: (date: string) =>
              `この期間は記録済みの ${date} と重なります。月・日を詳しくするか、別の時期の出来事を選んでください。`,
            futureRange:
              "この曖昧な範囲には未来の日付が含まれます。過去の月または日付まで絞ってください。"
          }
        : {
            preparing: "Preparing the next question...",
            notReady: "The next question is not ready yet.",
            prepare: "Prepare question",
            exhausted: "There is no suitable event left to check",
            exhaustedBody:
              "We will keep the current time range instead of claiming unsupported precision.",
            eyebrow: "Birth-time check",
            title: "Choose one event you remember clearly",
            body: "You do not need to write your life story. Pick the closest event, then tell us roughly when it happened.",
            progress: (current: number, total: number) => `${current} / ${total}`,
            recorded: (count: number, total: number) => `${count} / ${total} recorded`,
            chooseEvent: "Which one is closest?",
            dateTitle: "When did this happen?",
            dateHint: "Use the precision you genuinely remember. Do not guess a day to look exact.",
            dayKnown: "I know the date",
            monthKnown: "I remember the month",
            yearOnly: "I only know the year",
            yearPlaceholder: "Year",
            record: "Record this event",
            compare: "Submit and compare candidates",
            skip: "None of these, choose another type",
            reset: "Choose again",
            optionalNote: "Add one short note (optional)",
            requiredNote: "Add a few words about the change",
            notePlaceholder: "For example: accepted to my first university",
            noteHint: "No essay needed. A few words are enough.",
            why: "Why are we asking this?",
            selected: "Selected",
            saved: "Events already recorded",
            restart: "Clear and start again",
            overlap: (date: string) =>
              `This range overlaps the event recorded for ${date}. Add a more precise month or day, or choose another period.`,
            futureRange:
              "This approximate range includes future dates. Narrow it to a past month or exact date."
          };
  const interview = useMemo(
    () => parseRectificationInterview(interviewContent),
    [interviewContent]
  );
  const existingEvents = useMemo(
    () =>
      (state.lifeEventLedger?.events ?? [])
        .filter(
          (
            event
          ): event is Required<
            Pick<RectificationLifeEventInput, "date" | "category" | "description">
          > => Boolean(event.date && event.category && event.description)
        )
        .map((event) => ({
          date: event.date,
          category: event.category,
          description: cleanStoredEventDescription(event.description)
        })),
    [state.lifeEventLedger?.events]
  );
  const [draft, setDraft] = useState<LifeEventDraft | null>(null);
  const [editingAvailability, setEditingAvailability] = useState(false);
  const question = interview?.questions[0];
  const answer = question
    ? (draft ?? {
        questionId: question.questionId,
        date: "",
        category: question.category,
        description: "",
        datePrecision: "month" as const,
        choiceId: "",
        note: ""
      })
    : null;
  const choices = question
    ? (LIFE_EVENT_CHOICES[question.category] ?? []).filter(
        (choice) =>
          !question.allowedSubtypes?.length || question.allowedSubtypes.includes(choice.id)
      )
    : [];
  const todayDate = useMemo(() => {
    const now = new Date();
    const year = String(now.getFullYear()).padStart(4, "0");
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }, []);
  const selectedChoice = choices.find((choice) => choice.id === answer?.choiceId);
  const answerRange = answer?.date ? partialLifeEventDateRange(answer.date) : null;
  const overlappingEvent = answerRange
    ? existingEvents.find((event) => {
        const existingRange = partialLifeEventDateRange(event.date);
        return Boolean(
          existingRange &&
          answerRange.start <= existingRange.end &&
          answerRange.end >= existingRange.start
        );
      })
    : undefined;
  const partialRangeIncludesFuture = Boolean(answerRange && answerRange.end > todayDate);
  const confirmedEventCount =
    interview?.progress.answered ??
    state.lifeEventLedger?.independentEpisodeCount ??
    (state.lifeEventLedger?.events ?? []).length;
  const answerComplete = Boolean(
    answer?.date &&
    selectedChoice &&
    !overlappingEvent &&
    !partialRangeIncludesFuture &&
    (!selectedChoice.requiresNote || answer.note.trim().length >= 3)
  );
  const reachesTarget = Boolean(interview && confirmedEventCount + 1 >= interview.progress.target);
  const currentStep = confirmedEventCount + 1;
  const target = interview?.progress.target ?? 3;
  const CategoryIcon = question ? LIFE_EVENT_CATEGORY_ICONS[question.category] : Target;
  const availableCategories = state.availableRectificationCategories ?? [];
  const needsAvailabilityInventory =
    !interview && existingEvents.length === 0 && availableCategories.length === 0;
  const minimumEventDate = /^\d{4}-\d{2}-\d{2}$/.test(birthDate) ? birthDate : "1900-01-01";

  useEffect(() => {
    setDraft(null);
  }, [interviewContent]);

  function updateAnswer(update: Partial<LifeEventDraft>) {
    if (!question || !answer) return;
    setDraft((current) => ({
      ...(current ?? answer),
      ...update,
      questionId: question.questionId,
      category: question.category
    }));
  }

  function buildDescription(currentAnswer: LifeEventDraft, choice: LifeEventChoice) {
    const label = choice.label[locale];
    const note = currentAnswer.note.trim();
    if (!note) return label;
    return locale === "zh" ? `${label}（${note}）` : `${label} (${note})`;
  }

  function submitCurrent(currentAnswer: LifeEventDraft, choice: LifeEventChoice) {
    if (!interview || !question || !isSignedIn) return;
    void onSubmit([
      {
        questionId: currentAnswer.questionId,
        date: currentAnswer.date,
        eventSubtype: choice.id,
        description: buildDescription(currentAnswer, choice),
        category: currentAnswer.category as RectificationLifeEventCategory
      }
    ]);
  }

  function skipQuestion() {
    if (!question || !interview || !isSignedIn) return;
    void onPrepare({
      currentQuestionId: question.questionId,
      skippedCategory: question.category
    });
  }

  if (submitting) {
    return <RectificationWorkingState mode="comparison" recordedCount={confirmedEventCount} />;
  }

  if (preparing) {
    return <RectificationWorkingState mode="question" recordedCount={confirmedEventCount} />;
  }

  if (needsAvailabilityInventory || editingAvailability) {
    return (
      <>
        <EventAvailabilityStep
          lifeStage={lifeStage}
          initialCategories={availableCategories}
          disabled={!authLoaded || !isSignedIn}
          onContinue={(categories) => {
            setEditingAvailability(false);
            void onPrepare({ availableCategories: categories, resetSkipped: true });
          }}
        />
        {authLoaded && !isSignedIn && <AnonymousCheckpointGate />}
      </>
    );
  }

  if (!interview) {
    return (
      <div className="mt-6 flex min-h-52 flex-col items-center justify-center gap-4 rounded-xl border border-gold/25 bg-cream-2 px-6 text-center">
        <CircleHelp className="size-5 text-gold" />
        <p className="m-0 text-sm text-body">{ui.notReady}</p>
        <Button
          type="button"
          variant="outline"
          disabled={!authLoaded || !isSignedIn}
          onClick={() => void onPrepare()}
        >
          <RefreshCw size={15} /> {ui.prepare}
        </Button>
        {authLoaded && !isSignedIn && <AnonymousCheckpointGate />}
      </div>
    );
  }

  if (!question) {
    return (
      <div className="mt-6 rounded-xl border border-gold/25 bg-cream-2 px-5 py-5">
        <DetailSubtitle>{ui.exhausted}</DetailSubtitle>
        <p className="m-0 text-[13px] leading-7 text-body">
          {interview.stopReason ?? ui.exhaustedBody}
        </p>
        <Button
          type="button"
          variant="outline"
          className="mt-4"
          disabled={!authLoaded || !isSignedIn}
          onClick={() => setEditingAvailability(true)}
        >
          <RefreshCw size={15} /> {ui.reset}
        </Button>
      </div>
    );
  }

  if (!answer) return null;

  return (
    <form
      className="mt-5 grid gap-5"
      onSubmit={(event) => {
        event.preventDefault();
        if (!answerComplete || !answer || !selectedChoice) return;
        const currentAnswer = { ...answer, category: question.category };
        setDraft(currentAnswer);
        submitCurrent(currentAnswer, selectedChoice);
      }}
    >
      {clarification && (
        <div
          className="rounded-xl border border-red/25 bg-red/8 px-4 py-3 text-[12.5px] leading-6 text-body"
          role="alert"
        >
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-1 size-4 shrink-0 text-red" />
            <div>
              <strong className="font-semibold text-ink">
                {locale === "zh"
                  ? "这件经历需要重新确认"
                  : locale === "ja"
                    ? "この出来事をもう一度確認してください"
                    : "This event needs one more confirmation"}
              </strong>
              <p className="m-0 mt-1">{clarification.message}</p>
            </div>
          </div>
        </div>
      )}

      <header className="flex flex-col gap-4 border-b border-gold/20 pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-1 text-[11px] font-bold uppercase tracking-[1.5px] text-gold-dim">
            {ui.eyebrow}
          </div>
          <h3 className="m-0 text-xl font-semibold tracking-normal text-ink">{ui.title}</h3>
          <p className="mt-2 max-w-2xl text-[13px] leading-6 text-body">{ui.body}</p>
        </div>
        <div className="w-full shrink-0 sm:w-36">
          <div className="mb-2 flex items-center justify-between text-[11px] text-muted">
            <span>{ui.progress(currentStep, target)}</span>
            <span>{ui.recorded(confirmedEventCount, target)}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-gold/15">
            <div
              className="h-full rounded-full bg-gold transition-[width] duration-300"
              style={{ width: `${Math.min(100, (confirmedEventCount / target) * 100)}%` }}
            />
          </div>
        </div>
      </header>

      {existingEvents.length > 0 && (
        <div className="border-b border-gold/15 pb-4">
          <div className="mb-2 flex items-center justify-between gap-3">
            <div className="text-[11px] font-semibold uppercase tracking-[1.3px] text-muted">
              {ui.saved}
            </div>
            <button
              type="button"
              disabled={!authLoaded || !isSignedIn}
              className="inline-flex items-center gap-1.5 text-[11px] text-muted transition-colors hover:text-ink"
              onClick={() => void onReset()}
            >
              <RefreshCw className="size-3" />
              {ui.restart}
            </button>
          </div>
          <div className="grid gap-2">
            {existingEvents.map((event) => (
              <div
                className="flex items-start gap-3 text-[12px] leading-5 text-body"
                key={`${event.date}-${event.category}-${event.description}`}
              >
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-gold" />
                <span>
                  <strong className="font-semibold text-ink">{event.date}</strong>
                  <span className="mx-1.5 text-muted">·</span>
                  {event.description}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <section className="rounded-2xl border border-gold/30 bg-cream-2 p-5 shadow-[0_18px_50px_rgba(31,25,17,0.07)] sm:p-6">
        <div className="flex items-start gap-3 border-b border-gold/15 pb-5">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-full border border-gold/35 bg-gold/10 text-gold-dim">
            <CategoryIcon size={18} />
          </div>
          <div className="min-w-0">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-[1.3px] text-gold-dim">
              {t(`session.events.category.${question.category}`)}
            </div>
            <h4 className="m-0 text-lg font-semibold tracking-normal text-ink">{question.title}</h4>
            <p className="m-0 mt-1.5 text-[13px] leading-6 text-body">{question.prompt}</p>
          </div>
        </div>

        <div className="pt-5">
          <div className="mb-3 text-sm font-semibold text-ink">{ui.chooseEvent}</div>
          <div className="grid gap-2.5 sm:grid-cols-2">
            {choices.map((choice) => {
              const selected = answer.choiceId === choice.id;
              return (
                <button
                  key={choice.id}
                  type="button"
                  aria-pressed={selected}
                  className={`flex min-h-12 items-center gap-3 rounded-xl border px-3.5 py-3 text-left transition-[border-color,background,box-shadow] ${
                    selected
                      ? "border-gold bg-gold/10 text-ink shadow-[0_0_0_2px_rgba(201,169,110,0.12)]"
                      : "border-gold/20 bg-cream text-body hover:border-gold/55 hover:bg-gold/5"
                  }`}
                  onClick={() => updateAnswer({ choiceId: choice.id, note: "" })}
                >
                  {selected ? (
                    <CheckCircle2 className="size-4 shrink-0 text-gold" />
                  ) : (
                    <span className="size-4 shrink-0 rounded-full border border-gold/40" />
                  )}
                  <span className="text-[13px] leading-5">{choice.label[locale]}</span>
                </button>
              );
            })}
          </div>
        </div>

        {selectedChoice && (
          <div className="mt-5 grid gap-4 border-t border-gold/15 pt-5">
            <div>
              <div className="mb-1 text-sm font-semibold text-ink">{ui.dateTitle}</div>
              <p className="m-0 text-[12px] leading-5 text-muted">{ui.dateHint}</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-[minmax(0,220px)_minmax(0,1fr)] sm:items-end">
              <div className="grid gap-2">
                <div className="grid grid-cols-3 rounded-lg border border-gold/20 bg-cream p-1">
                  {(["day", "month", "year"] as const).map((precision) => (
                    <button
                      key={precision}
                      type="button"
                      aria-pressed={answer.datePrecision === precision}
                      className={`h-9 rounded-md text-[11px] transition-colors ${
                        answer.datePrecision === precision
                          ? "bg-gold text-white"
                          : "text-muted hover:text-ink"
                      }`}
                      onClick={() =>
                        updateAnswer({
                          datePrecision: precision,
                          date:
                            precision === "year"
                              ? answer.date.slice(0, 4)
                              : precision === "month" && answer.date.length >= 7
                                ? answer.date.slice(0, 7)
                                : precision === "day" && answer.date.length === 10
                                  ? answer.date
                                  : ""
                        })
                      }
                    >
                      {precision === "day"
                        ? ui.dayKnown
                        : precision === "month"
                          ? ui.monthKnown
                          : ui.yearOnly}
                    </button>
                  ))}
                </div>
                <input
                  required
                  aria-label={ui.dateTitle}
                  type={
                    answer.datePrecision === "year"
                      ? "number"
                      : answer.datePrecision === "month"
                        ? "month"
                        : "date"
                  }
                  min={
                    answer.datePrecision === "year"
                      ? Number(minimumEventDate.slice(0, 4))
                      : answer.datePrecision === "month"
                        ? minimumEventDate.slice(0, 7)
                        : minimumEventDate
                  }
                  max={
                    answer.datePrecision === "year"
                      ? Number(todayDate.slice(0, 4))
                      : answer.datePrecision === "month"
                        ? todayDate.slice(0, 7)
                        : todayDate
                  }
                  value={answer.date}
                  placeholder={answer.datePrecision === "year" ? ui.yearPlaceholder : undefined}
                  className="h-11 rounded-lg border border-gold/25 bg-cream px-3 text-[13px] text-ink outline-none focus:border-gold focus:ring-4 focus:ring-gold/10"
                  onChange={(event) => updateAnswer({ date: event.target.value })}
                />
                {overlappingEvent && (
                  <p className="m-0 text-[11.5px] leading-5 text-red" role="alert">
                    {ui.overlap(overlappingEvent.date)}
                  </p>
                )}
                {!overlappingEvent && partialRangeIncludesFuture && (
                  <p className="m-0 text-[11.5px] leading-5 text-red" role="alert">
                    {ui.futureRange}
                  </p>
                )}
              </div>

              {selectedChoice.requiresNote ? (
                <label className="grid gap-2 text-[12px] text-body">
                  <span className="font-semibold text-ink">{ui.requiredNote}</span>
                  <input
                    required
                    maxLength={160}
                    value={answer.note}
                    placeholder={ui.notePlaceholder}
                    className="h-11 rounded-lg border border-gold/25 bg-cream px-3 text-[13px] text-ink outline-none placeholder:text-muted focus:border-gold focus:ring-4 focus:ring-gold/10"
                    onChange={(event) => updateAnswer({ note: event.target.value })}
                  />
                </label>
              ) : (
                <details className="rounded-lg border border-gold/15 bg-cream px-3 py-2">
                  <summary className="cursor-pointer select-none text-[12px] font-semibold text-body outline-none">
                    {ui.optionalNote}
                  </summary>
                  <div className="mt-2 grid gap-1.5">
                    <input
                      maxLength={160}
                      value={answer.note}
                      placeholder={ui.notePlaceholder}
                      className="h-10 rounded-lg border border-gold/20 bg-cream-2 px-3 text-[12px] text-ink outline-none placeholder:text-muted focus:border-gold focus:ring-4 focus:ring-gold/10"
                      onChange={(event) => updateAnswer({ note: event.target.value })}
                    />
                    <span className="text-[11px] text-muted">{ui.noteHint}</span>
                  </div>
                </details>
              )}
            </div>
          </div>
        )}

        <details className="mt-5 border-t border-gold/15 pt-4">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-[12px] text-muted outline-none">
            <Info className="size-3.5" /> {ui.why}
          </summary>
          <p className="m-0 mt-2 pl-5 text-[12px] leading-5 text-muted">{question.whyWeAsk}</p>
        </details>
      </section>

      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Button
          type="button"
          variant="ghost"
          onClick={skipQuestion}
          disabled={submitting || !authLoaded || !isSignedIn}
        >
          {ui.skip}
        </Button>
        <Button disabled={!answerComplete || submitting || !authLoaded || !isSignedIn}>
          {submitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
          {reachesTarget ? ui.compare : ui.record}
          {!reachesTarget && <ChevronRight size={15} />}
        </Button>
      </div>
      {authLoaded && !isSignedIn && <AnonymousCheckpointGate />}
    </form>
  );
}

function ConsultationQuestionPanel({
  sessionId,
  isSignedIn
}: {
  sessionId: string;
  isSignedIn: boolean;
}) {
  const { locale } = useI18n();
  const [question, setQuestion] = useState("");
  const [exchanges, setExchanges] = useState<ConsultationExchangeResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const copy =
    locale === "zh"
      ? {
          eyebrow: "继续咨询",
          title: "问一个与你有关的问题",
          body: "回答只会使用这份报告中已经通过证据门槛的判断；资料不足时会明确告诉你。",
          placeholder: "例如：未来一年里，我在职业选择上更值得关注什么？",
          ask: "询问报告",
          basis: "本回答依据",
          limits: "需要保留的边界",
          claimUnit: "条已批准判断",
          insufficient: "当前报告证据不足",
          suggested: "可以继续问"
        }
      : locale === "ja"
        ? {
            eyebrow: "相談を続ける",
            title: "このリーディングについて質問する",
            body: "回答は証拠基準を通過した判断のみを使用し、判断できない場合は明確に伝えます。",
            placeholder: "例：今年の仕事上の選択で何に注意すべきですか？",
            ask: "リーディングに質問",
            basis: "根拠",
            limits: "重要な限界",
            claimUnit: "件の承認済み判断",
            insufficient: "現在のレポートでは根拠が不足しています",
            suggested: "次に聞けること"
          }
        : {
            eyebrow: "Continue the consultation",
            title: "Ask a question about your reading",
            body: "The answer uses only claims that passed this report's evidence gate and will say when the chart cannot determine something.",
            placeholder:
              "For example: What should I pay attention to in career decisions this year?",
            ask: "Ask the reading",
            basis: "Grounded in",
            limits: "Important limits",
            claimUnit: "approved claim",
            insufficient: "The current report does not contain enough evidence",
            suggested: "Useful next questions"
          };

  useEffect(() => {
    if (!isSignedIn) {
      setExchanges([]);
      return;
    }
    let cancelled = false;
    void api
      .getConsultationConversation(sessionId)
      .then((conversation) => {
        if (!cancelled) setExchanges(conversation.exchanges);
      })
      .catch((caught) => {
        if (!cancelled) {
          setError(userFacingError(caught, "Could not load the consultation history."));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [isSignedIn, sessionId]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || loading || !isSignedIn) return;
    setLoading(true);
    setError("");
    try {
      const askedQuestion = question.trim();
      const response = await api.answerConsultationQuestion({
        sessionId,
        question: askedQuestion
      });
      setExchanges((current) => [
        ...current,
        { ...response, question: askedQuestion, askedAt: new Date().toISOString() }
      ]);
      setQuestion("");
    } catch (caught) {
      setError(userFacingError(caught, "Could not answer this question. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mt-14 border-t border-gold/25 pt-10">
      <div className="mb-2 text-[10px] uppercase tracking-[3px] text-gold">{copy.eyebrow}</div>
      <h2 className="mb-2 text-2xl font-medium tracking-normal text-ink">{copy.title}</h2>
      <p className="mb-5 max-w-2xl text-[13px] leading-7 text-body">{copy.body}</p>
      <form className="grid max-w-3xl gap-3" onSubmit={submit}>
        <Textarea
          rows={3}
          value={question}
          placeholder={copy.placeholder}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <div className="flex justify-end">
          <Button disabled={!question.trim() || loading || !isSignedIn}>
            {loading ? <LoaderCircle className="size-4 animate-spin" /> : <CircleHelp size={15} />}
            {copy.ask}
          </Button>
        </div>
      </form>
      {!isSignedIn && <AnonymousCheckpointGate />}
      {error && <p className="mt-4 text-sm text-danger">{error}</p>}
      {exchanges.length > 0 && (
        <div className="mt-6 grid max-w-3xl gap-4">
          {exchanges.map((exchange, index) => (
            <div key={`${exchange.askedAt}-${index}`} className="grid gap-3">
              <div className="ml-auto max-w-[85%] rounded-xl bg-ink px-4 py-3 text-[13px] leading-6 text-cream">
                {exchange.question}
              </div>
              <div className="rounded-xl border border-gold/25 bg-cream-2 p-5">
                <p className="m-0 whitespace-pre-wrap text-[14px] leading-8 text-ink">
                  {exchange.answer}
                </p>
                <div className="mt-5 border-t border-gold/20 pt-4 text-[12px] leading-6 text-muted">
                  <div>
                    {exchange.answerability === "answered" ? (
                      <>
                        <strong className="font-semibold text-body">{copy.basis}:</strong>{" "}
                        {exchange.supportingClaimIds.length} {copy.claimUnit}
                        {locale === "en" && exchange.supportingClaimIds.length !== 1 ? "s" : ""}
                      </>
                    ) : (
                      <strong className="font-semibold text-body">{copy.insufficient}</strong>
                    )}
                  </div>
                  {exchange.limitations.length > 0 && (
                    <div className="mt-2">
                      <strong className="font-semibold text-body">{copy.limits}:</strong>{" "}
                      {exchange.limitations.join(" · ")}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
          {exchanges.at(-1)?.followUpQuestions.length ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] uppercase tracking-[1.2px] text-muted">
                {copy.suggested}
              </span>
              {exchanges.at(-1)?.followUpQuestions.map((followUp) => (
                <Button
                  key={followUp}
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setQuestion(followUp)}
                >
                  {followUp}
                </Button>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

function RectificationConclusion({
  state,
  submitting,
  onSubmit,
  authLoaded,
  isSignedIn
}: {
  state: RectificationState;
  submitting: boolean;
  onSubmit: (responses: RectificationConfirmationResponse[]) => Promise<void>;
  authLoaded: boolean;
  isSignedIn: boolean;
}) {
  const { locale, t } = useI18n();
  const conclusion = state.rectificationConclusion;
  const examples = (conclusion?.examples ?? []).filter((example) => Boolean(example.exampleId));
  const exampleSignature = examples
    .map((example) => `${example.exampleId}:${example.startDate}:${example.endDate}`)
    .join("|");
  const [answers, setAnswers] = useState<Record<string, RectificationConfirmationAnswer>>({});

  useEffect(() => {
    setAnswers({});
  }, [exampleSignature]);

  const corrected = conclusion?.correctedBirthTime;
  const interval = conclusion?.selectedInterval;
  const evidence = conclusion?.evidenceSummary;
  const methodAssurance = conclusion?.methodAssurance;
  const evidenceHighlights = conclusion?.evidenceHighlights ?? [];
  const answeredCount = examples.filter((example) => answers[example.exampleId ?? ""]).length;
  const allAnswered = examples.length > 0 && answeredCount === examples.length;
  const confidenceLabel =
    conclusion?.confidence === "high"
      ? t("session.rectification.conclusion.confidenceHigh")
      : conclusion?.confidence === "medium"
        ? t("session.rectification.conclusion.confidenceMedium")
        : conclusion?.confidence === "low"
          ? t("session.rectification.conclusion.confidenceLow")
          : t("session.rectification.conclusion.bounded");
  const categoryLabel = (category?: string) => {
    if (category === "input_review") {
      return locale === "zh" ? "结果确认" : locale === "ja" ? "結果の確認" : "Result review";
    }
    if (!category || category === "unknown") return t("session.rectification.conclusion.event");
    return t(`session.events.category.${category}`);
  };
  const formatRange = (start?: string, end?: string) => {
    if (!start) return "—";
    if (!end || end === start) return start;
    if (interval?.boundarySemantics === "start_inclusive_end_exclusive") {
      return t("session.rectification.conclusion.rangeExclusive", { start, end });
    }
    return `${start} – ${end}`;
  };
  const formatCorrectedTime = () => {
    const local = [corrected?.localDate, corrected?.localTime].filter(Boolean).join(" ");
    if (!local) return "—";
    return corrected?.timezoneId ? `${local} · ${corrected.timezoneId}` : local;
  };
  const evidenceValue = t("session.rectification.conclusion.evidenceValue", {
    events: evidence?.calibrationEpisodeCount ?? evidence?.calibrationEventCount ?? 0,
    categories: evidence?.calibrationCategoryCount ?? 0,
    holdout: evidence?.holdoutEpisodeCount ?? evidence?.holdoutEventCount ?? 0
  });
  const checkpointCopy = {
    title: t("session.rectification.conclusion.checkpointTitle"),
    body: t("session.rectification.conclusion.checkpointBody"),
    technical: t("session.rectification.conclusion.technicalDetails")
  };

  function submit() {
    if (!allAnswered || submitting) return;
    void onSubmit(
      examples.map((example) => ({
        exampleId: example.exampleId ?? "",
        answer: answers[example.exampleId ?? ""]
      }))
    );
  }

  return (
    <section className="mt-5 grid gap-5" aria-live="polite">
      <header className="text-center">
        <div className="mx-auto mb-3 grid size-11 place-items-center rounded-full border border-gold/35 bg-gold/12 text-gold-dim">
          <CheckCircle2 className="size-5" aria-hidden="true" />
        </div>
        <div className="mb-1 text-[11px] font-bold uppercase tracking-normal text-gold-dim">
          {t("session.rectification.conclusion.eyebrow")}
        </div>
        <h3 className="m-0 text-[24px] font-semibold leading-tight tracking-normal text-ink">
          {checkpointCopy.title}
        </h3>
        <p className="mx-auto mb-0 mt-2 max-w-[540px] text-[13px] leading-6 text-body">
          {checkpointCopy.body}
        </p>
      </header>

      <section className="overflow-hidden rounded-2xl border border-gold/35 bg-[linear-gradient(145deg,rgba(201,169,110,0.16),rgba(255,255,255,0.52))] shadow-[0_18px_50px_rgba(201,169,110,0.12)]">
        <div className="border-b border-gold/20 px-5 py-5 text-center">
          <div className="text-[10px] uppercase tracking-normal text-gold-dim">
            {t("session.rectification.conclusion.correctedTime")}
          </div>
          <div className="mt-1 text-[22px] font-semibold leading-tight tracking-normal text-ink sm:text-[26px]">
            {formatCorrectedTime()}
          </div>
        </div>
        <div className="grid divide-y divide-gold/18 sm:grid-cols-2 sm:divide-x sm:divide-y-0">
          <div className="px-4 py-4 text-center">
            <div className="text-[10px] uppercase tracking-normal text-muted">
              {t("session.rectification.conclusion.range")}
            </div>
            <div className="mt-1 text-[13px] font-semibold leading-6 text-ink">
              {formatRange(interval?.start, interval?.end)}
            </div>
          </div>
          <div className="px-4 py-4 text-center">
            <div className="text-[10px] uppercase tracking-normal text-muted">
              {t("session.rectification.conclusion.confidence")}
            </div>
            <div className="mt-1 text-[13px] font-semibold leading-6 text-ink">
              {confidenceLabel}
            </div>
          </div>
        </div>
      </section>

      <details className="group rounded-xl border border-gold/18 bg-cream-2 px-4 py-3.5">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-lg text-[12.5px] font-semibold text-body outline-none focus-visible:ring-4 focus-visible:ring-gold/15 [&::-webkit-details-marker]:hidden">
          <span>{checkpointCopy.technical}</span>
          <ChevronRight
            className="size-4 text-gold-dim transition-transform group-open:rotate-90"
            aria-hidden="true"
          />
        </summary>
        <div className="mt-3 grid gap-2 border-t border-gold/15 pt-3 text-[12.5px] leading-6 text-body">
          <InfoRow label={t("session.rectification.conclusion.evidence")} value={evidenceValue} />
          <InfoRow
            label={t("session.rectification.conclusion.methodStatus")}
            value={
              methodAssurance?.independentProfessionalReviewCompleted
                ? t("session.rectification.conclusion.methodReviewed")
                : t("session.rectification.conclusion.methodInternalOnly")
            }
          />
        </div>
      </details>

      {evidenceHighlights.length > 0 && (
        <details className="group rounded-xl border border-gold/18 bg-white/35 px-4 py-3.5">
          <summary className="flex cursor-pointer list-none items-start justify-between gap-3 rounded-lg outline-none focus-visible:ring-4 focus-visible:ring-gold/15 [&::-webkit-details-marker]:hidden">
            <span>
              <span className="block text-[12.5px] font-semibold text-body">
                {t("session.rectification.conclusion.explanationTitle")}
              </span>
              <span className="mt-1 block text-[11.5px] font-normal leading-5 text-muted">
                {t("session.rectification.conclusion.explanationBody")}
              </span>
            </span>
            <ChevronRight
              className="mt-0.5 size-4 shrink-0 text-gold-dim transition-transform group-open:rotate-90"
              aria-hidden="true"
            />
          </summary>
          <div className="mt-3 grid gap-2 border-t border-gold/15 pt-3 sm:grid-cols-2">
            {evidenceHighlights.map((highlight, index) => (
              <article
                key={`${highlight.role}-${highlight.date}-${index}`}
                className="rounded-xl border border-gold/20 bg-cream-2 px-3.5 py-3"
              >
                <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-[1.1px] text-muted">
                  <Badge variant={highlight.role === "holdout" ? "done" : "neutral"}>
                    {t(
                      highlight.role === "holdout"
                        ? "session.rectification.conclusion.holdoutRole"
                        : "session.rectification.conclusion.calibrationRole"
                    )}
                  </Badge>
                  <span>{highlight.date || "—"}</span>
                  <span>·</span>
                  <span>{categoryLabel(highlight.category)}</span>
                </div>
                <p className="m-0 mt-2 text-[13px] leading-6 text-ink">
                  {cleanStoredEventDescription(highlight.description || "")}
                </p>
                <p className="m-0 mt-2 text-[11.5px] leading-5 text-muted">
                  {t(
                    highlight.result === "passed_reserved_cross_check"
                      ? "session.rectification.conclusion.holdoutResult"
                      : "session.rectification.conclusion.calibrationResult"
                  )}
                </p>
              </article>
            ))}
          </div>
        </details>
      )}

      <section className="grid gap-3">
        <div>
          <div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[1.4px] text-gold-dim">
            <ListChecks className="size-4" />
            {t("session.rectification.conclusion.examplesTitle")}
          </div>
          <p className="m-0 text-[13px] leading-6 text-body">
            {t("session.rectification.conclusion.examplesBody")}
          </p>
        </div>

        {examples.length === 0 ? (
          <div className="rounded-xl border border-danger/25 bg-danger/5 px-4 py-3 text-[13px] leading-6 text-body">
            {t("session.rectification.conclusion.noExamples")}
          </div>
        ) : (
          examples.map((example, index) => {
            const exampleId = example.exampleId ?? `example-${index}`;
            const selected = answers[exampleId];
            const prompt =
              example.source === "submitted_evidence"
                ? example.description || example.prompt
                : example.prompt;
            const inputReview = example.source === "deterministic_input_review";
            const inputReviewChoices: Record<
              RectificationConfirmationAnswer,
              { label: string; description: string }
            > =
              locale === "zh"
                ? {
                    accurate: { label: "可以接受", description: "这个校正范围符合我的基本记忆" },
                    partly: {
                      label: "还不确定",
                      description: "我需要保留这个范围，不确认精确时间"
                    },
                    inaccurate: { label: "无法接受", description: "这个范围与我掌握的信息冲突" }
                  }
                : locale === "ja"
                  ? {
                      accurate: { label: "受け入れられる", description: "記憶と大きく矛盾しない" },
                      partly: {
                        label: "まだ不確か",
                        description: "範囲を保留し、時刻を確定しない"
                      },
                      inaccurate: {
                        label: "受け入れられない",
                        description: "把握している情報と矛盾する"
                      }
                    }
                  : {
                      accurate: {
                        label: "I can accept this range",
                        description: "It does not conflict with what I remember"
                      },
                      partly: {
                        label: "I am still unsure",
                        description: "Keep the range without claiming an exact time"
                      },
                      inaccurate: {
                        label: "I cannot accept it",
                        description: "It conflicts with information I trust"
                      }
                    };
            return (
              <article
                className="rounded-2xl border border-gold/25 bg-cream-2 p-4 shadow-[0_14px_34px_rgba(31,25,17,0.06)]"
                key={exampleId}
              >
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[1.2px] text-gold-dim">
                    <span>{categoryLabel(example.category)}</span>
                    <span className="text-muted">·</span>
                    <span className="font-normal text-muted">
                      {formatRange(example.startDate, example.endDate)}
                    </span>
                  </div>
                  <Badge variant="neutral">
                    {inputReview
                      ? categoryLabel("input_review")
                      : t(
                          example.source === "submitted_evidence"
                            ? "session.rectification.conclusion.sourceSubmitted"
                            : "session.rectification.conclusion.sourceAgent"
                        )}
                  </Badge>
                </div>
                <p className="m-0 text-[14px] leading-7 text-ink">{prompt}</p>
                <div className="mt-4 grid gap-2">
                  {VALIDATION_CHOICES.map((choice) => {
                    const isSelected = selected === choice.value;
                    return (
                      <button
                        type="button"
                        key={choice.value}
                        className={cn(
                          "rounded-lg border px-3.5 py-2.5 text-left transition",
                          isSelected
                            ? "border-gold bg-gold text-white shadow-sm"
                            : "border-gold/25 bg-cream text-body hover:border-gold/60 hover:bg-gold/10"
                        )}
                        onClick={() =>
                          setAnswers((current) => ({ ...current, [exampleId]: choice.value }))
                        }
                      >
                        <span className="block text-sm font-semibold">
                          {inputReview
                            ? inputReviewChoices[choice.value].label
                            : t(choice.labelKey)}
                        </span>
                        <span
                          className={cn(
                            "mt-0.5 block text-[12px]",
                            isSelected ? "text-white/80" : "text-muted"
                          )}
                        >
                          {inputReview
                            ? inputReviewChoices[choice.value].description
                            : t(choice.descriptionKey)}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </article>
            );
          })
        )}
      </section>

      {authLoaded && !isSignedIn && <AnonymousCheckpointGate />}
      <div className="rounded-xl border border-gold/18 bg-cream-2 px-4 py-3 text-[12.5px] leading-6 text-muted">
        <Sparkles className="mr-1 inline size-3.5 text-gold" />
        {t("session.rectification.conclusion.guardrail")}
      </div>
      <Button
        type="button"
        className="w-full"
        disabled={!allAnswered || submitting || !authLoaded || !isSignedIn}
        onClick={submit}
      >
        {submitting ? (
          <>
            <LoaderCircle className="size-4 animate-spin" />
            {t("session.rectification.conclusion.confirming")}
          </>
        ) : (
          <>
            <CheckCircle2 className="size-4" />
            {t("session.rectification.conclusion.confirm")}
          </>
        )}
      </Button>
      {!allAnswered && examples.length > 0 && (
        <p className="m-0 text-center text-[12px] text-muted">
          {t("session.rectification.conclusion.answerAll", {
            answered: answeredCount,
            total: examples.length
          })}
        </p>
      )}
    </section>
  );
}

function ReaderDetail({
  session,
  readerRunning,
  readerStartedAt,
  now,
  validationFeedback,
  submittingFeedback,
  submittingLifeEvents,
  rectificationClarification,
  submittingRectificationConfirmation,
  preparingRectificationInterview,
  onValidationFeedbackChange,
  onSubmitFeedback,
  onSubmitLifeEvents,
  onResetLifeEvents,
  onSubmitRectificationConfirmation,
  onPrepareRectificationInterview,
  authLoaded,
  isSignedIn
}: {
  session: SkillSessionResponse | null;
  readerRunning: boolean;
  readerStartedAt: number | null;
  now: number;
  validationFeedback: string;
  submittingFeedback: boolean;
  submittingLifeEvents: boolean;
  rectificationClarification: RectificationClarification | null;
  submittingRectificationConfirmation: boolean;
  preparingRectificationInterview: boolean;
  onValidationFeedbackChange: (value: string) => void;
  onSubmitFeedback: (event: FormEvent) => void;
  onSubmitLifeEvents: (events: RectificationLifeEventInput[]) => Promise<void>;
  onResetLifeEvents: () => Promise<void>;
  onSubmitRectificationConfirmation: (
    responses: RectificationConfirmationResponse[]
  ) => Promise<void>;
  onPrepareRectificationInterview: (action?: RectificationInterviewAction) => Promise<void>;
  authLoaded: boolean;
  isSignedIn: boolean;
}) {
  const { t } = useI18n();
  const prevalidation = findArtifact(session, "reader_prevalidation.md");
  const feedbackArtifact = findArtifact(session, "user_context.md");
  const feedback = hasCurrentValidationFeedback(prevalidation, feedbackArtifact)
    ? feedbackArtifact
    : null;
  const anchors = useMemo(
    () => parseValidationAnchors(prevalidation?.content ?? ""),
    [prevalidation?.content]
  );
  const rectificationState = useMemo(
    () =>
      parseRectificationState(
        findArtifact(session, "chart_rectification_state.json")?.content ?? ""
      ),
    [session]
  );
  const chartRecord = useMemo(() => parseJsonArtifact(session, CHART_RECORD_JSON), [session]);
  const birthAssertion = objectValue(chartRecord, "birthAssertion");
  const birthDate = String(birthAssertion?.localDate ?? "");
  const lifeStage = useMemo(() => {
    return String(objectValue(chartRecord, "subject")?.lifeStage ?? "adult");
  }, [chartRecord]);
  const collectingLifeEvents = rectificationState?.status === "collecting_evidence";
  const continuingLifeEvents =
    rectificationState?.status === "underdetermined" &&
    rectificationState.rectificationPlan?.eventCollectionRequired === true;
  const rectificationConfirmationRequired =
    rectificationState?.status === "rectification_confirmation_required" &&
    rectificationState.rectificationConclusion?.confirmation?.status === "pending";
  const evidenceResetRequired =
    rectificationState?.status === "underdetermined" &&
    rectificationState.evidenceInvalidation?.requiresReset === true;
  const interviewArtifact = findArtifact(session, "rectification_interview.json");
  const collectedLifeEventCount =
    rectificationState?.lifeEventLedger?.independentEpisodeCount ??
    (rectificationState?.lifeEventLedger?.events ?? []).length;
  const needsAvailabilityInventory =
    collectedLifeEventCount === 0 &&
    (rectificationState?.availableRectificationCategories?.length ?? 0) === 0;
  const [activeAnchorIndex, setActiveAnchorIndex] = useState(0);
  const [anchorFeedback, setAnchorFeedback] = useState<
    Record<number, { answer?: ValidationAnswer; note: string }>
  >({});
  const interviewRequestedRef = useRef(false);
  const activeAnchor = anchors[activeAnchorIndex];
  const answeredCount = anchors.filter((anchor) => anchorFeedback[anchor.index]?.answer).length;
  const allAnswered = anchors.length > 0 && answeredCount === anchors.length;
  const recordedFeedback = useMemo(
    () => parseRecordedValidationFeedback(feedback?.content ?? ""),
    [feedback?.content]
  );

  useEffect(() => {
    setActiveAnchorIndex(0);
    setAnchorFeedback({});
    onValidationFeedbackChange("");
  }, [prevalidation?.content, onValidationFeedbackChange]);

  useEffect(() => {
    if (activeAnchorIndex >= anchors.length) setActiveAnchorIndex(Math.max(0, anchors.length - 1));
  }, [activeAnchorIndex, anchors.length]);

  useEffect(() => {
    if (interviewArtifact) interviewRequestedRef.current = false;
  }, [interviewArtifact]);

  useEffect(() => {
    if (
      (collectingLifeEvents || continuingLifeEvents) &&
      !interviewArtifact &&
      !needsAvailabilityInventory &&
      authLoaded &&
      isSignedIn &&
      !preparingRectificationInterview &&
      !interviewRequestedRef.current
    ) {
      interviewRequestedRef.current = true;
      void onPrepareRectificationInterview();
    }
  }, [
    authLoaded,
    collectingLifeEvents,
    continuingLifeEvents,
    interviewArtifact,
    isSignedIn,
    needsAvailabilityInventory,
    onPrepareRectificationInterview,
    preparingRectificationInterview
  ]);

  function updateAnchorFeedback(
    anchor: ValidationAnchor,
    update: Partial<{ answer: ValidationAnswer; note: string }>
  ) {
    const nextFeedback = {
      ...anchorFeedback,
      [anchor.index]: {
        answer: anchorFeedback[anchor.index]?.answer,
        note: anchorFeedback[anchor.index]?.note ?? "",
        ...update
      }
    };
    setAnchorFeedback(nextFeedback);
    onValidationFeedbackChange(buildValidationFeedbackMarkdown(anchors, nextFeedback));
  }

  function moveNext() {
    if (!activeAnchor) return;
    setActiveAnchorIndex((current) => Math.min(current + 1, anchors.length - 1));
  }

  function movePrev() {
    setActiveAnchorIndex((current) => Math.max(0, current - 1));
  }

  if (evidenceResetRequired) {
    return (
      <section className="mt-5 grid gap-4 rounded-2xl border border-danger/25 bg-danger/5 p-5">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-danger" aria-hidden="true" />
          <div>
            <h3 className="m-0 text-lg font-semibold text-ink">
              {t("session.rectification.evidenceReset.title")}
            </h3>
            <p className="m-0 mt-2 text-[13px] leading-6 text-body">
              {t("session.rectification.evidenceReset.body")}
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          disabled={submittingLifeEvents || !authLoaded || !isSignedIn}
          onClick={() => void onResetLifeEvents()}
        >
          {submittingLifeEvents ? (
            <LoaderCircle className="size-4 animate-spin" />
          ) : (
            <RefreshCw className="size-4" />
          )}
          {t("session.rectification.evidenceReset.action")}
        </Button>
        {authLoaded && !isSignedIn && <AnonymousCheckpointGate />}
      </section>
    );
  }

  if (rectificationConfirmationRequired && rectificationState) {
    return (
      <RectificationConclusion
        state={rectificationState}
        submitting={submittingRectificationConfirmation}
        onSubmit={onSubmitRectificationConfirmation}
        authLoaded={authLoaded}
        isSignedIn={isSignedIn}
      />
    );
  }

  if (!prevalidation) {
    if (collectingLifeEvents || continuingLifeEvents) {
      return (
        <LifeEventCollector
          state={rectificationState}
          interviewContent={interviewArtifact?.content ?? ""}
          lifeStage={lifeStage}
          birthDate={birthDate}
          preparing={preparingRectificationInterview}
          onPrepare={onPrepareRectificationInterview}
          submitting={submittingLifeEvents}
          onSubmit={onSubmitLifeEvents}
          onReset={onResetLifeEvents}
          clarification={rectificationClarification}
          authLoaded={authLoaded}
          isSignedIn={isSignedIn}
        />
      );
    }
    return (
      <>
        <div className="my-4">
          <DetailSubtitle>
            {readerRunning ? t("session.reader.preparingNow") : t("session.reader.notStarted")}
          </DetailSubtitle>
          <p className="m-0 text-[13px] leading-[1.7] text-body">
            {readerRunning
              ? t("session.reader.elapsed", {
                  duration: formatElapsed(readerStartedAt, now)
                })
              : t("stage.copy.reader.expected")}
          </p>
        </div>
      </>
    );
  }

  if (readerRunning && feedback) {
    return (
      <div className="my-8 text-center" aria-live="polite">
        <LoaderCircle className="mx-auto size-7 animate-spin text-gold" />
        <h4 className="mb-1 mt-4 text-base font-semibold text-ink">
          {t("session.reader.preparingNextRound")}
        </h4>
        <p className="m-0 text-[13px] leading-[1.7] text-body">
          {t("session.reader.preparingNextRoundBody")}
        </p>
      </div>
    );
  }

  return (
    <>
      {feedback ? (
        <ReaderCompletedDetail
          anchors={anchors}
          feedback={feedback}
          recordedFeedback={recordedFeedback}
        />
      ) : (
        <form className="mt-4 grid gap-4" onSubmit={onSubmitFeedback}>
          <div className="rounded-xl border border-gold/35 bg-gold/10 px-4 py-3 shadow-[0_12px_30px_rgba(201,169,110,0.10)]">
            <div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[1.5px] text-gold-dim">
              <Target className="size-4" />
              {t("session.reader.roundTitle")}
            </div>
            <p className="m-0 text-[13px] leading-[1.65] text-body">
              {t("session.reader.roundBody")}
            </p>
            {anchors.length > 0 && (
              <div
                className="mt-3 h-1.5 overflow-hidden rounded-full bg-cream/60"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={anchors.length}
                aria-valuenow={answeredCount}
              >
                <span
                  className="block h-full rounded-full bg-gold transition-[width] duration-300"
                  style={{ width: `${Math.round((answeredCount / anchors.length) * 100)}%` }}
                />
              </div>
            )}
          </div>

          {activeAnchor ? (
            <div className="rounded-xl border border-gold/25 bg-cream-2 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-[1.8px] text-muted">
                    {t("session.reader.check")}
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-sm font-semibold text-ink">
                    {t("session.reader.cardOf", {
                      current: activeAnchorIndex + 1,
                      total: anchors.length
                    })}
                    {activeAnchor.rationale && (
                      <AnchorRationalePopover
                        label={t("session.reader.why", { number: activeAnchorIndex + 1 })}
                        rationale={activeAnchor.rationale}
                      />
                    )}
                  </div>
                </div>
                <Badge variant="neutral">
                  {t("session.reader.answered", { answered: answeredCount, total: anchors.length })}
                </Badge>
              </div>

              <div className="rounded-lg border border-gold/20 bg-gold/10 px-3.5 py-3 text-[13px] leading-[1.75] text-body">
                {activeAnchor.statement}
              </div>

              <div className="mt-4 grid gap-2">
                {VALIDATION_CHOICES.map((choice) => {
                  const selected = anchorFeedback[activeAnchor.index]?.answer === choice.value;
                  return (
                    <button
                      type="button"
                      key={choice.value}
                      className={cn(
                        "rounded-lg border px-3.5 py-3 text-left transition",
                        selected
                          ? "border-gold bg-gold text-white shadow-sm"
                          : "border-gold/25 bg-cream text-body hover:border-gold/60 hover:bg-gold/10"
                      )}
                      onClick={() => updateAnchorFeedback(activeAnchor, { answer: choice.value })}
                    >
                      <span className="block text-sm font-semibold">{t(choice.labelKey)}</span>
                      <span
                        className={cn(
                          "mt-0.5 block text-[12.5px]",
                          selected ? "text-white/80" : "text-muted"
                        )}
                      >
                        {t(choice.descriptionKey)}
                      </span>
                    </button>
                  );
                })}
              </div>

              <label className="mt-4 block">
                <span className="mb-1.5 block text-[11px] uppercase tracking-[1.4px] text-muted">
                  {t("session.reader.optionalNote")}
                </span>
                <Textarea
                  rows={4}
                  value={anchorFeedback[activeAnchor.index]?.note ?? ""}
                  onChange={(event) =>
                    updateAnchorFeedback(activeAnchor, { note: event.target.value })
                  }
                  placeholder={t("session.reader.notePlaceholder")}
                />
              </label>

              {activeAnchorIndex === anchors.length - 1 &&
                allAnswered &&
                authLoaded &&
                !isSignedIn && <AnonymousCheckpointGate />}

              <div className="mt-4 flex items-center justify-between gap-3">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={activeAnchorIndex === 0}
                  onClick={movePrev}
                >
                  <ChevronLeft size={14} /> {t("session.reader.previous")}
                </Button>
                {activeAnchorIndex < anchors.length - 1 ? (
                  <Button
                    type="button"
                    size="sm"
                    disabled={!anchorFeedback[activeAnchor.index]?.answer}
                    onClick={moveNext}
                  >
                    {t("session.reader.next")} <ChevronRight size={14} />
                  </Button>
                ) : isSignedIn ? (
                  <Button
                    disabled={
                      submittingFeedback ||
                      !authLoaded ||
                      !isSignedIn ||
                      !allAnswered ||
                      !validationFeedback.trim()
                    }
                  >
                    {submittingFeedback ? t("session.reader.saving") : t("session.reader.save")}
                  </Button>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-gold/25 bg-cream-2 p-4">
              <DetailSubtitle>{t("session.reader.response")}</DetailSubtitle>
              <Textarea
                rows={7}
                value={validationFeedback}
                onChange={(event) => onValidationFeedbackChange(event.target.value)}
                placeholder={t("session.reader.responsePlaceholder")}
              />
              <Button
                className="mt-3 w-full"
                disabled={
                  submittingFeedback || !authLoaded || !isSignedIn || !validationFeedback.trim()
                }
              >
                {submittingFeedback ? t("session.reader.saving") : t("session.reader.save")}
              </Button>
              {authLoaded && !isSignedIn && validationFeedback.trim() && (
                <AnonymousCheckpointGate />
              )}
            </div>
          )}
        </form>
      )}
    </>
  );
}

function ReaderCompletedDetail({
  anchors,
  feedback,
  recordedFeedback
}: {
  anchors: ValidationAnchor[];
  feedback: SkillArtifact;
  recordedFeedback: Map<number, ValidationFeedbackSummary>;
}) {
  const { t } = useI18n();
  const structuredCount = recordedFeedback.size;

  return (
    <div className="mt-4 grid gap-4">
      <div className="rounded-xl border border-gold/35 bg-gold/10 px-4 py-3 shadow-[0_12px_30px_rgba(201,169,110,0.10)]">
        <div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[1.5px] text-gold-dim">
          <CheckCircle2 className="size-4" />
          {t("session.reader.complete")}
        </div>
        <p className="m-0 text-[13px] leading-[1.65] text-body">
          {t("session.reader.completeBody")}
        </p>
      </div>

      {structuredCount === 0 && (
        <div className="rounded-xl border border-gold/25 bg-cream-2 px-4 py-3 text-[13px] leading-[1.65] text-body">
          {t("session.reader.generalSaved")}
        </div>
      )}

      {anchors.length > 0 ? (
        <div className="grid gap-3">
          {anchors.map((anchor, anchorIndex) => {
            const summary = recordedFeedback.get(anchor.index);
            return (
              <div className="rounded-xl border border-gold/25 bg-cream-2 p-4" key={anchor.id}>
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[10px] uppercase tracking-[1.8px] text-muted">
                      {t("session.reader.check")}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-sm font-semibold text-ink">
                      {t("session.reader.questionOf", {
                        current: anchorIndex + 1,
                        total: anchors.length
                      })}
                      {anchor.rationale && (
                        <AnchorRationalePopover
                          label={t("session.reader.why", { number: anchorIndex + 1 })}
                          rationale={anchor.rationale}
                        />
                      )}
                    </div>
                  </div>
                  <Badge variant={feedbackBadgeVariant(summary?.answer)}>
                    {summary?.answerLabel ?? "Recorded"}
                  </Badge>
                </div>

                <div className="rounded-lg border border-gold/20 bg-gold/10 px-3.5 py-3 text-[13px] leading-[1.75] text-body">
                  {anchor.statement}
                </div>

                {summary?.note && (
                  <div className="mt-3 rounded-lg border border-gold/20 bg-cream/80 px-3.5 py-3">
                    <div className="mb-1 text-[10px] uppercase tracking-[1.4px] text-muted">
                      {t("session.reader.yourNote")}
                    </div>
                    <p className="m-0 text-[13px] leading-[1.65] text-body">{summary.note}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-xl border border-gold/25 bg-cream-2 p-4">
          <DetailSubtitle>{t("session.reader.savedReplies")}</DetailSubtitle>
          <p className="m-0 text-[13px] leading-[1.65] text-body">
            {excerpt(feedback.content, 420)}
          </p>
        </div>
      )}
    </div>
  );
}

function AnonymousCheckpointGate() {
  const { t } = useI18n();
  return (
    <div className="mt-4 rounded-xl border border-gold/35 bg-cream px-4 py-4 shadow-[0_18px_42px_rgba(44,31,15,0.08)]">
      <div className="mb-1 text-[10px] font-bold uppercase tracking-[1.8px] text-gold">
        {t("session.reader.accountCheckpoint")}
      </div>
      <h4 className="m-0 text-base font-semibold tracking-normal text-ink">
        {t("session.reader.signInToSave")}
      </h4>
      <p className="mb-4 mt-2 text-[13px] leading-[1.7] text-body">
        {t("session.reader.signInBody")}
      </p>
      <div className="flex flex-wrap gap-2">
        <SignUpButton mode="modal">
          <Button>{t("common.createAccount")}</Button>
        </SignUpButton>
        <SignInButton mode="modal">
          <Button variant="outline">{t("common.signIn")}</Button>
        </SignInButton>
      </div>
    </div>
  );
}

function feedbackBadgeVariant(
  answer: ValidationFeedbackSummary["answer"] | undefined
): ComponentProps<typeof Badge>["variant"] {
  if (answer === "accurate") return "done";
  if (answer === "partly") return "gold";
  if (answer === "inaccurate") return "error";
  return "neutral";
}

function AnchorRationalePopover({ label, rationale }: { label: string; rationale: string }) {
  const { t } = useI18n();
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="grid size-5 shrink-0 place-items-center rounded-full border border-gold/25 bg-cream-2 text-gold-dim transition hover:border-gold hover:bg-gold/10 hover:text-gold focus:outline-none focus:ring-4 focus:ring-gold/15"
          aria-label={label}
        >
          <CircleHelp className="size-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(92vw,360px)] p-4" align="start" side="bottom">
        <div className="mb-2 text-[10px] uppercase tracking-[1.6px] text-gold">
          {t("session.reader.rationaleTitle")}
        </div>
        <p className="m-0 whitespace-pre-wrap text-[13px] leading-[1.7] text-body">{rationale}</p>
      </PopoverContent>
    </Popover>
  );
}

function CoreStageDetail({
  stageId,
  session,
  nodes,
  status,
  onResumeCoreReport,
  coreInterrupted
}: {
  stageId: string;
  session: SkillSessionResponse | null;
  nodes: PipelineNode[];
  status: StageStatus;
  onResumeCoreReport: () => Promise<void>;
  coreInterrupted: boolean;
}) {
  const { t } = useI18n();
  const copy = localizedStageCopy(stageId, t);
  const runningNodes = nodes.filter((node) => node.status === "running");
  const completedNodes = nodes.filter(
    (node) => node.status === "completed" || node.status === "skipped"
  );
  const failedNodes = nodes.filter((node) => node.status === "failed");
  const stageDuration = completedNodes.reduce((sum, node) => sum + (node.durationSeconds ?? 0), 0);
  const artifact = findStageArtifact(session, stageId, nodes);
  const progress = nodes.length > 0 ? `${completedNodes.length}/${nodes.length}` : "";

  return (
    <>
      <StageStatusSummary
        status={status}
        copy={copy}
        completed={completedNodes.length}
        total={nodes.length}
        running={runningNodes.length}
        durationSeconds={stageDuration}
        coreInterrupted={coreInterrupted}
      />

      {failedNodes.length > 0 && (
        <div className="my-5 rounded-xl border border-red/30 bg-red/10 px-4 py-3">
          <div className="mb-2.5 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-[12px] font-semibold text-red">
              <AlertTriangle className="size-4" />
              {t("stage.summary.paused.title")}
            </div>
            {coreInterrupted && (
              <Button size="sm" onClick={() => void onResumeCoreReport()}>
                <RefreshCw size={13} /> {t("session.empty.resume")}
              </Button>
            )}
          </div>
          {coreInterrupted && (
            <p className="m-0 mb-3 text-[13px] leading-[1.7] text-body">
              {t("stage.failed.saved")}
            </p>
          )}
          <div className="grid gap-2 border-t border-red/20 pt-3">
            {failedNodes.map((node, index) => (
              <div className="text-[12.5px] leading-[1.6]" key={node.id}>
                <div className="font-semibold text-ink">
                  {t("stage.failed.part", { number: index + 1 })}
                </div>
                <div className="mt-0.5 break-words text-red">
                  {sanitizeUserMessage(node.error, t("stage.failed.fallback"))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {artifact ? (
        <ResultPreview artifact={artifact} status={status} />
      ) : (
        <EmptyResultState status={status} copy={copy} progress={progress} />
      )}
    </>
  );
}

function StageStatusSummary({
  status,
  copy,
  completed,
  total,
  running,
  durationSeconds,
  coreInterrupted
}: {
  status: StageStatus;
  copy: StageCopy;
  completed: number;
  total: number;
  running: number;
  durationSeconds: number;
  coreInterrupted: boolean;
}) {
  const { t } = useI18n();
  const Icon =
    status === "failed"
      ? AlertTriangle
      : status === "running"
        ? Clock3
        : status === "done"
          ? CheckCircle2
          : ListChecks;
  const summary = stageStatusSummary(status, copy, coreInterrupted, t);

  return (
    <section className="my-4 border-y border-gold/25 py-4">
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "grid size-9 shrink-0 place-items-center rounded-full border",
            status === "failed"
              ? "border-red/30 bg-red/10 text-red"
              : status === "done"
                ? "border-gold/35 bg-gold/15 text-gold-dim"
                : "border-gold/25 bg-cream-2 text-gold-dim"
          )}
        >
          <Icon className="size-4" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-ink">{summary.title}</div>
          <p className="m-0 mt-1 text-[13px] leading-[1.7] text-body">{summary.body}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[1.1px] text-muted">
            {total > 0 && (
              <span className="rounded-full border border-gold/25 bg-cream-2 px-2.5 py-1">
                {t("stage.partsReady", { completed, total })}
              </span>
            )}
            {running > 0 && status === "running" && (
              <span className="rounded-full border border-gold/25 bg-gold/10 px-2.5 py-1">
                {t("stage.active", { count: running })}
              </span>
            )}
            {durationSeconds > 0 && (
              <span className="rounded-full border border-gold/25 bg-cream-2 px-2.5 py-1">
                {t("stage.savedDuration", { duration: formatDuration(durationSeconds) })}
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function stageStatusSummary(
  status: StageStatus,
  copy: StageCopy,
  coreInterrupted: boolean,
  t: Translate
) {
  if (status === "failed") {
    return {
      title: t("stage.summary.paused.title"),
      body: coreInterrupted
        ? t("stage.summary.paused.body")
        : t("stage.summary.paused.bodyAttention")
    };
  }
  if (status === "done") {
    return {
      title: t("stage.summary.done.title"),
      body: t("stage.summary.done.body")
    };
  }
  if (status === "running") {
    return {
      title: t("stage.summary.running.title"),
      body: t("stage.summary.running.body")
    };
  }
  if (status === "waiting") {
    return {
      title: t("stage.summary.waiting.title"),
      body: copy.userAction
    };
  }
  return {
    title: t("stage.summary.pending.title"),
    body: t("stage.summary.pending.body")
  };
}

function EmptyResultState({
  status,
  copy,
  progress
}: {
  status: StageStatus;
  copy: StageCopy;
  progress: string;
}) {
  const { t } = useI18n();
  if (status === "done") return null;
  return (
    <section className="my-5 border-t border-gold/25 pt-4">
      <DetailSubtitle>
        {status === "running" ? t("stage.preview") : t("stage.comingNext")}
      </DetailSubtitle>
      <p className="m-0 text-[13px] leading-[1.7] text-body">
        {status === "running"
          ? t("stage.previewWaiting", {
              progress: progress
                ? ` (${t("stage.partsReady", { completed: progress.split("/")[0], total: progress.split("/")[1] })})`
                : ""
            })
          : copy.userResult}
      </p>
    </section>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-gold/25 py-2.5 text-sm">
      <span className="text-muted">{label}</span>
      <span className="text-right font-medium text-ink">{value || "—"}</span>
    </div>
  );
}

function ResultPreview({ artifact, status }: { artifact: SkillArtifact; status: StageStatus }) {
  const { locale, t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const displayContent = useMemo(
    () => sanitizeResultContentForDisplay(artifact.content),
    [artifact.content]
  );
  const sections = useMemo(() => parseResultPreviewSections(displayContent), [displayContent]);
  const visibleSections = expanded ? sections : sections.slice(0, 3);
  const canExpand = sections.length > 0;
  const label = status === "done" ? t("stage.result.previewReady") : t("stage.result.previewSaved");

  return (
    <section className="my-5 border-t border-gold/25 pt-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <div className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border border-gold/25 bg-gold/10 text-gold-dim">
            <FileText className="size-3.5" />
          </div>
          <div className="min-w-0">
            <DetailSubtitle className="mb-1">{label}</DetailSubtitle>
            <div className="text-sm font-semibold text-ink">
              {titleForArtifact(artifact, locale)}
            </div>
          </div>
        </div>
        {canExpand && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setExpanded((value) => !value)}
          >
            <Eye size={13} /> {expanded ? t("stage.result.showLess") : t("stage.result.showFull")}
          </Button>
        )}
      </div>

      {expanded ? (
        <div className="mt-4 max-h-[72vh] overflow-auto rounded-lg border border-gold/25 bg-cream-2 px-3.5 py-3">
          <MarkdownReport content={displayContent} />
        </div>
      ) : (
        <div className="mt-4 divide-y divide-gold/20 border-y border-gold/20">
          {visibleSections.map((section, index) => (
            <article className="py-3 first:pt-0 last:pb-0" key={section.id}>
              <div className="mb-1 flex items-baseline gap-2">
                <span className="text-[10px] font-bold uppercase tracking-[1.4px] text-gold">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <h4 className="m-0 text-sm font-semibold leading-snug text-ink">{section.title}</h4>
              </div>
              <p className="m-0 text-[13px] leading-[1.75] text-body">
                {excerpt(stripMarkdownForPreview(section.body), 360)}
              </p>
            </article>
          ))}
          {sections.length > visibleSections.length && (
            <div className="py-3 text-[12.5px] text-muted">
              {t("stage.result.more", { count: sections.length - visibleSections.length })}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function DetailSubtitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("mb-2 text-[11px] uppercase tracking-[1.4px] text-muted", className)}>
      {children}
    </div>
  );
}

function findStageArtifact(
  session: SkillSessionResponse | null,
  stageId: string,
  nodes: PipelineNode[]
): SkillArtifact | null {
  const candidates = [
    ...(STAGE_ARTIFACT_CANDIDATES[stageId] ?? []),
    ...nodes.flatMap((node) => node.files)
  ];
  for (const path of candidates) {
    const artifact = findArtifact(session, path);
    if (artifact) return artifact;
  }
  return null;
}

function findArtifact(session: SkillSessionResponse | null, path: string): SkillArtifact | null {
  return session?.artifacts.find((artifact) => artifact.path === path) ?? null;
}

function hasCurrentValidationFeedback(
  prevalidation: SkillArtifact | null,
  feedback: SkillArtifact | null
) {
  if (!prevalidation || !feedback) return false;
  const prevalidationTime = Date.parse(prevalidation.updatedAt);
  const feedbackTime = Date.parse(feedback.updatedAt);
  if (Number.isNaN(prevalidationTime) || Number.isNaN(feedbackTime)) return true;
  return feedbackTime >= prevalidationTime;
}

function isBaziSession(session: SkillSessionResponse | null) {
  return Boolean(
    session?.stage.startsWith("bazi_") ||
    session?.artifacts.some((artifact) => artifact.path.startsWith("bazi_"))
  );
}

function getBaziPipelineData(
  session: SkillSessionResponse | null,
  running: boolean
): PipelineData | null {
  if (!session || !isBaziSession(session)) return null;
  const hasChart = Boolean(findArtifact(session, "bazi_chart_foundation.md"));
  const hasReport = Boolean(findArtifact(session, "bazi_life_report.md"));
  const chartStatus = hasChart ? "completed" : "pending";
  const reportStatus = hasReport
    ? "completed"
    : running
      ? "running"
      : hasChart
        ? "waiting"
        : "pending";
  const nodes: PipelineNode[] = [
    {
      id: "bazi_chart",
      label: "BaZi Chart Facts",
      wave: 0,
      status: chartStatus,
      files: ["bazi_chart_foundation.md", "bazi_chart_record.json", "bazi_report_context.md"],
      dependencies: [],
      finishedAt: findArtifact(session, "bazi_chart_foundation.md")?.updatedAt ?? null,
      durationSeconds: null,
      error: null
    },
    {
      id: "bazi_report",
      label: "Classical BaZi Report",
      wave: 1,
      status: reportStatus,
      files: [
        "bazi_data_audit.md",
        "bazi_overview.md",
        "bazi_classics_audit.md",
        "bazi_timing_report.md",
        "bazi_life_report.md",
        "bazi_appendix.md"
      ],
      dependencies: ["bazi_chart"],
      finishedAt: findArtifact(session, "bazi_life_report.md")?.updatedAt ?? null,
      durationSeconds: null,
      error: null
    }
  ];
  const completed = nodes.filter((node) => node.status === "completed").length;
  return {
    nodes,
    status: hasReport ? "completed" : running ? "running" : "waiting",
    percent: Math.round((completed / nodes.length) * 100),
    completed,
    total: nodes.length,
    failed: 0,
    durationSeconds: null
  };
}

function stageLabelFor(stage: StageDef, t: Translate) {
  const key = `stage.${stage.id}.label`;
  const text = t(key);
  return text === key ? stage.label : text;
}

function sanitizeResultContentForDisplay(content: string) {
  return content
    .replace(/\r\n/g, "\n")
    .split("\n")
    .filter((line) => !isPreviewMetaLine(line))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function parseResultPreviewSections(content: string): ResultPreviewSection[] {
  const normalized = content.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];

  const lines = normalized.split("\n");
  const sections: ResultPreviewSection[] = [];
  let currentTitle = "";
  let currentBody: string[] = [];

  function flush() {
    const body = cleanResultPreviewBody(currentBody.join("\n"));
    if (!currentTitle && !body) return;
    sections.push({
      id: `result-section-${sections.length + 1}`,
      title: cleanMarkdownInline(currentTitle || "Overview"),
      body: body || currentTitle
    });
  }

  for (const line of lines) {
    const heading = line.trim().match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flush();
      currentTitle = heading[2].trim();
      currentBody = [];
      continue;
    }
    currentBody.push(line);
  }
  flush();

  if (sections.length === 0) {
    return [
      { id: "result-section-1", title: "Overview", body: cleanResultPreviewBody(normalized) }
    ];
  }
  const readable = sections.filter((section) => stripMarkdownForPreview(section.body).length > 24);
  return (readable.length > 0 ? readable : sections).slice(0, 24);
}

function chartRecordSections(record: Record<string, unknown> | null): ResultPreviewSection[] {
  if (!record) return [];
  const profile = objectValue(record, "calculationProfile");
  const astronomy = objectValue(record, "astronomy");
  const ascendant = objectValue(astronomy, "ascendant");
  const grahas = arrayValue(astronomy, "grahas");
  const charts = arrayValue(record, "charts");
  const timingPeriods = arrayValue(record, "timingPeriods");
  const qualityChecks = arrayValue(record, "qualityChecks");

  const foundation = [
    zodiacSummary("Lagna", ascendant),
    ...grahas
      .map((item) => {
        const graha = objectFromUnknown(item);
        return zodiacSummary(String(graha?.graha ?? "Graha"), objectValue(graha, "position"));
      })
      .filter(Boolean)
  ].filter(Boolean);
  const vargas = charts
    .map((item) => {
      const chart = objectFromUnknown(item);
      const lagna = objectValue(objectValue(chart, "lagna"), "position");
      const label = String(chart?.vargaId ?? "Varga");
      const confidence = String(chart?.confidence ?? "unknown");
      return `${label}: ${String(lagna?.sign ?? "—")} Lagna · ${confidence}`;
    })
    .slice(0, 15);
  const timing = timingPeriods.slice(0, 8).map((item) => {
    const period = objectFromUnknown(item);
    const interval = objectValue(period, "interval");
    const lords = Array.isArray(period?.lords) ? period.lords.join(" / ") : "—";
    return `${String(period?.level ?? "period")}: ${lords} · ${dateOnly(interval?.start)}–${dateOnly(interval?.end)}`;
  });
  const checks = qualityChecks.map((item) => {
    const check = objectFromUnknown(item);
    return `${String(check?.status ?? "unknown").toUpperCase()} · ${String(check?.message ?? check?.checkId ?? "Quality check")}`;
  });

  return [
    {
      id: "chart-section-method",
      title: "Calculation profile",
      body: [
        String(profile?.tradition ?? "Parashari"),
        String(profile?.zodiac ?? "sidereal"),
        `Ayanamsa: ${String(objectValue(profile, "ayanamsa")?.model ?? "lahiri")}`,
        `House model: ${String(profile?.rashiHouseModel ?? "whole sign")}`
      ].join(" · ")
    },
    {
      id: "chart-section-foundation",
      title: "D1 foundation",
      body: foundation.join("\n")
    },
    {
      id: "chart-section-vargas",
      title: "Divisional chart set",
      body: vargas.join("\n")
    },
    {
      id: "chart-section-timing",
      title: "Timing periods",
      body: timing.join("\n") || "No released timing periods."
    },
    {
      id: "chart-section-quality",
      title: "Calculation quality",
      body: checks.join("\n") || "No quality checks recorded."
    }
  ];
}

function zodiacSummary(label: string, position: Record<string, unknown> | null): string {
  if (!position) return "";
  const degree = typeof position.degreeInSign === "number" ? position.degreeInSign.toFixed(2) : "—";
  const nakshatra = objectValue(position, "nakshatra");
  const nakshatraText = nakshatra?.name
    ? ` · ${String(nakshatra.name)} p${String(nakshatra.pada ?? "—")}`
    : "";
  return `${label}: ${String(position.sign ?? "—")} ${degree}°${nakshatraText}`;
}

function objectFromUnknown(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function arrayValue(record: Record<string, unknown> | null, key: string): unknown[] {
  const value = record?.[key];
  return Array.isArray(value) ? value : [];
}

function dateOnly(value: unknown): string {
  return typeof value === "string" ? value.slice(0, 10) : "—";
}

function cleanResultPreviewBody(content: string) {
  return content
    .split("\n")
    .filter((line) => !isPreviewMetaLine(line))
    .join("\n")
    .trim();
}

function isPreviewMetaLine(line: string) {
  const normalized = line.trim().replace(/^>\s*/, "").replace(/\*\*/g, "").replace(/`/g, "");
  if (!normalized || /^---+$/.test(normalized)) return true;
  if (normalized.includes(".runtime/") || normalized.includes("内部shard")) return true;
  if (/^\*.*(数据源|本文件为|交付批次).*\*$/.test(normalized)) return true;
  return /^(交付批次|执行日期|数据锚点|合成框架|规则|分析范围|出生时间精度|扫描范围|数据来源|扫描时点|参与星状态)/.test(
    normalized
  );
}

function stripMarkdownForPreview(content: string) {
  return content
    .replace(/^---+$/gm, "")
    .replace(/^>\s?/gm, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\|[-:\s|]+\|/g, "")
    .replace(/\*\*/g, "")
    .replace(/`/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function excerpt(content: string, max = 1600) {
  const normalized = content.trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max).trimEnd()}\n\n...`;
}

function parseValidationAnchors(content: string): ValidationAnchor[] {
  const normalized = content.trim();
  if (!normalized) return [];

  const markerPattern = /(?:^|\n)\s*(?:\*\*)?(\d+)[.、]\s*(?:\*\*)?\s*/g;
  const markers = Array.from(normalized.matchAll(markerPattern));
  if (markers.length === 0) {
    return [
      {
        id: "anchor-1",
        index: 1,
        statement: stripValidationInstruction(normalized),
        rationale: ""
      }
    ];
  }

  return markers
    .map((marker, markerIndex) => {
      const index = Number(marker[1]);
      const start = (marker.index ?? 0) + marker[0].length;
      const next = markers[markerIndex + 1];
      const end = next?.index ?? normalized.length;
      const block = stripValidationInstruction(normalized.slice(start, end)).trim();
      const lines = block.split("\n");
      const statementLines: string[] = [];
      const rationaleLines: string[] = [];
      let inRationale = false;

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) {
          if (inRationale) rationaleLines.push("");
          continue;
        }
        if (trimmed.startsWith(">")) {
          const quoted = trimmed.replace(/^>\s*/, "");
          if (/^(Candidate|候选盘|候選盤|Field|Fields|字段|不稳定字段)[:：]/i.test(quoted)) {
            continue;
          }
          inRationale = true;
          rationaleLines.push(quoted.replace(/^(推导|Derivation|根拠)[:：]\s*/i, ""));
          continue;
        }
        if (inRationale) rationaleLines.push(trimmed);
        else statementLines.push(trimmed);
      }

      return {
        id: `anchor-${index || markerIndex + 1}`,
        index: index || markerIndex + 1,
        statement: cleanMarkdownInline(statementLines.join("\n")),
        rationale: cleanMarkdownInline(rationaleLines.join("\n").trim())
      };
    })
    .filter((anchor) => anchor.statement);
}

function stripValidationInstruction(content: string) {
  return content
    .replace(/请逐条回复[:：]?[\s\S]*$/m, "")
    .replace(/Reply to each anchor[:：]?[\s\S]*$/im, "")
    .replace(/各項目に返信してください[:：]?[\s\S]*$/m, "")
    .trim();
}

function cleanMarkdownInline(content: string) {
  return content
    .replace(/\*\*/g, "")
    .replace(/`/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function buildValidationFeedbackMarkdown(
  anchors: ValidationAnchor[],
  feedback: Record<number, { answer?: ValidationAnswer; note: string }>
) {
  const answered = anchors.filter((anchor) => feedback[anchor.index]?.answer);
  if (answered.length === 0) return "";

  const lines = ["### Pre-reading validation feedback", ""];
  for (const anchor of answered) {
    const entry = feedback[anchor.index];
    const choice = VALIDATION_CHOICES.find((item) => item.value === entry?.answer);
    lines.push(`#### Anchor ${anchor.index}`);
    lines.push(
      `- User answer: ${choice?.storedLabel ?? entry?.answer ?? ""} (${choice?.value ?? ""})`
    );
    if (entry?.note.trim()) lines.push(`- User note: ${entry.note.trim()}`);
    lines.push(`- Anchor text: ${anchor.statement}`);
    lines.push("");
  }
  return lines.join("\n").trim();
}

function parseRecordedValidationFeedback(content: string): Map<number, ValidationFeedbackSummary> {
  const result = new Map<number, ValidationFeedbackSummary>();
  if (!content.trim()) return result;

  const anchorPattern = /####\s+Anchor\s+(\d+)\s*\n([\s\S]*?)(?=\n####\s+Anchor\s+\d+\s*\n|$)/g;
  for (const match of content.matchAll(anchorPattern)) {
    const index = Number(match[1]);
    const block = match[2] ?? "";
    const answerRaw = block.match(/^- User answer:\s*(.+)$/m)?.[1]?.trim() ?? "";
    const note = block.match(/^- User note:\s*([\s\S]*?)(?=\n- User |\n$|$)/m)?.[1]?.trim() ?? "";
    const anchorText =
      block.match(/^- Anchor text:\s*([\s\S]*?)(?=\n- User |\n$|$)/m)?.[1]?.trim() ?? "";
    const normalized = normalizeRecordedAnswer(answerRaw);
    if (index > 0) {
      result.set(index, {
        answer: normalized.answer,
        answerLabel: normalized.label,
        note,
        anchorText
      });
    }
  }

  return result;
}

function normalizeRecordedAnswer(raw: string): {
  answer: ValidationAnswer | "recorded";
  label: string;
} {
  if (/Not accurate|不准/i.test(raw)) return { answer: "inaccurate", label: "Not accurate" };
  if (/Partly|部分/i.test(raw)) return { answer: "partly", label: "Partly" };
  if (/Accurate|准/i.test(raw)) return { answer: "accurate", label: "Accurate" };
  return { answer: "recorded", label: raw || "Recorded" };
}

function formatElapsed(startedAt: number | null, now: number) {
  if (!startedAt) return "—";
  return formatDuration(Math.max(0, (now - startedAt) / 1000));
}

function resolveBirthInfo(navState: NavState, session: SkillSessionResponse | null): BirthInfo {
  const coordinates = resolveBirthCoordinates(session, navState?.birth?.birthPlace);
  if (navState?.birth) {
    return {
      name: navState.birth.displayName || navState.name?.trim() || "—",
      date: navState.birth.birthDate,
      time: navState.birth.birthTime || "Unknown birth time",
      place: navState.birth.birthPlace,
      latitude: coordinates.latitude,
      longitude: coordinates.longitude,
      gender: displayCollected(GENDER_LABELS[navState.birth.gender] ?? navState.birth.gender),
      relationship: displayCollected(
        RELATIONSHIP_LABELS[navState.birth.relationship] ?? navState.birth.relationship
      ),
      timePrecision: displayMappedValue(navState.birth.birthTimePrecision, PRECISION_LABELS),
      effectivePrecision: reportedTimeWindowLabel(
        navState.birth.birthTimePrecision,
        navState.birth.reportedTimeWindow
      ),
      concern: navState.concern?.trim() ?? ""
    };
  }

  const bazi = session?.artifacts.find((a) => a.path === "bazi_chart_foundation.md")?.content ?? "";
  if (bazi) {
    const grabBazi = (label: string) =>
      bazi.match(new RegExp(`- ${label}:\\s*(.+)`))?.[1]?.trim() ?? "—";
    const birth = grabBazi("Birth");
    const birthMatch = birth.match(/^(\d{4}-\d{2}-\d{2})\s+([^ ]+)/);
    const context =
      session?.artifacts.find((a) => a.path === "bazi_report_context.md")?.content ?? "";
    const topic = context.match(/- Topic priority:\s*(.+)/)?.[1]?.trim() ?? "";
    return {
      name: navState?.name?.trim() || "—",
      date: birthMatch?.[1] ?? birth,
      time: birthMatch?.[2] ?? "—",
      place: grabBazi("Place"),
      latitude: coordinates.latitude,
      longitude: coordinates.longitude,
      gender: displayCollected(grabBazi("Gender")),
      relationship: displayCollected(context.match(/- Relationship:\s*(.+)/)?.[1]?.trim()),
      timePrecision: displayMappedValue(grabBazi("Time precision"), PRECISION_LABELS),
      effectivePrecision: grabBazi("Solar time applied"),
      concern: topic === "[not provided]" ? "" : topic
    };
  }

  const chartRecord = parseJsonArtifact(session, CHART_RECORD_JSON);
  const subject = objectValue(chartRecord, "subject");
  const birthAssertion = objectValue(chartRecord, "birthAssertion");
  const inputContext = parseJsonArtifact(session, "birth_input_context.json");
  const timeContext = objectValue(inputContext, "time");
  const reportedWindow = objectValue(timeContext, "window");
  const timeCertainty = String(birthAssertion?.timeCertainty ?? "unknown");
  const normalizedPrecision =
    {
      exact_minute: "exact",
      bounded_window: "approximate",
      part_of_day: "part_of_day",
      unknown: "unknown"
    }[timeCertainty] ?? timeCertainty;
  const feedback = session?.artifacts.find((a) => a.path === "user_context.md")?.content ?? "";
  return {
    name: String(subject?.displayName ?? "—"),
    date: String(birthAssertion?.localDate ?? "—"),
    time: String(birthAssertion?.reportedLocalTime ?? "—"),
    place: String(birthAssertion?.reportedPlace ?? "—"),
    latitude: coordinates.latitude,
    longitude: coordinates.longitude,
    gender: displayCollected(String(subject?.genderContext ?? "")),
    relationship: displayCollected(String(subject?.relationshipStatus ?? "")),
    timePrecision: displayMappedValue(normalizedPrecision, PRECISION_LABELS),
    effectivePrecision: reportedTimeWindowLabel(normalizedPrecision, reportedWindow),
    concern: extractConcern(feedback)
  };
}

function reportedTimeWindowLabel(
  precision: string,
  window?: { minutesBefore?: unknown; minutesAfter?: unknown } | null
): string {
  if (precision === "unknown") return "00:00–24:00";
  const before = Number(window?.minutesBefore);
  const after = Number(window?.minutesAfter);
  if (!Number.isFinite(before) || !Number.isFinite(after)) return "—";
  if (before === after) return `±${before} min`;
  return `−${before} / +${after} min`;
}

function resolveBirthCoordinates(
  session: SkillSessionResponse | null,
  fallbackPlace?: string
): { latitude: string; longitude: string } {
  const inputContext = parseJsonArtifact(session, "birth_input_context.json");
  const inputCoordinates = objectValue(objectValue(inputContext, "place"), "coordinates");
  const fromInput = coordinatesFromObject(inputCoordinates);
  if (fromInput) return fromInput;

  const chartRecord = parseJsonArtifact(session, CHART_RECORD_JSON);
  const canonicalMoment = objectValue(chartRecord, "canonicalMoment");
  const resolvedPlace = objectValue(canonicalMoment, "place");
  const point = objectValue(resolvedPlace, "point");
  const fromRecord = coordinatesFromObject(point);
  if (fromRecord) return fromRecord;

  const fromText = coordinatesFromText(fallbackPlace ?? "");
  if (fromText) return fromText;

  return { latitude: "", longitude: "" };
}

function parseJsonArtifact(
  session: SkillSessionResponse | null,
  path: string
): Record<string, unknown> | null {
  const artifact = session?.artifacts.find((item) => item.path === path);
  if (!artifact) return null;
  try {
    const parsed = JSON.parse(artifact.content) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function parseRectificationInterview(content: string): RectificationInterview | null {
  if (!content.trim()) return null;
  try {
    const parsed = JSON.parse(content) as RectificationInterview;
    if (
      !/^vedicdust-rectification-interview\/1\.\d+\.0$/.test(parsed.schemaVersion) ||
      !Array.isArray(parsed.questions) ||
      !parsed.progress
    ) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function cleanStoredEventDescription(value: string) {
  return value.replace(/^\s*(?:19|20)\d{2}(?:-\d{2}(?:-\d{2})?)?\s+[a-z_]+\s*:\s*/i, "").trim();
}

function canStartFullReading(session: SkillSessionResponse | null): boolean {
  const prevalidationResult = parseJsonArtifact(session, "prevalidation_result.json");
  const decision = objectValue(prevalidationResult, "decision");
  return decision?.reportAllowed === true && decision.reportScope !== "prevalidation_or_d1_only";
}

type ReadingContinuationAction =
  "full_report" | "reader" | "collect_events" | "confirm_rectification" | "reset_events" | "stop";

const READER_CONTINUATION_STATUSES = new Set(["not_required"]);

function readingContinuationAction(
  session: SkillSessionResponse | null
): ReadingContinuationAction {
  const state = parseJsonArtifact(session, "chart_rectification_state.json");
  if (state) {
    const status = String(state.status ?? "").trim();
    const conclusion = objectValue(state, "rectificationConclusion");
    const confirmation = objectValue(conclusion, "confirmation");
    if (status === "rectification_confirmation_required" || confirmation?.status === "pending") {
      return "confirm_rectification";
    }
  }

  if (canStartFullReading(session)) return "full_report";

  const prevalidationResult = parseJsonArtifact(session, "prevalidation_result.json");
  const prevalidationDecision = objectValue(prevalidationResult, "decision");
  if (prevalidationDecision?.nextStep === "review_birth_details_or_stop") return "stop";

  if (!state) return "reader";

  const status = String(state.status ?? "").trim();
  const plan = objectValue(state, "rectificationPlan");
  const action = String(plan?.action ?? "").trim();
  const gate = objectValue(state, "reportGate");
  if (action === "reset_rectification_evidence") return "reset_events";
  if (status === "corrected_chart_ready" && gate?.fullReportAllowed === true) {
    return "full_report";
  }
  if (
    status === "multiple_equivalent" &&
    gate?.fullReportAllowed === true &&
    gate.reportScope === "stable_intersection_only"
  ) {
    return "full_report";
  }
  if (
    status === "collecting_evidence" ||
    action === "collect_dated_life_events" ||
    (status === "underdetermined" && plan?.eventCollectionRequired === true)
  ) {
    return "collect_events";
  }
  if (READER_CONTINUATION_STATUSES.has(status)) return "reader";
  return "stop";
}

function parseRectificationState(content: string): RectificationState | null {
  if (!content.trim()) return null;
  try {
    const parsed = JSON.parse(content) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    return parsed as RectificationState;
  } catch {
    return null;
  }
}

function objectValue(value: unknown, key: string): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const next = (value as Record<string, unknown>)[key];
  return next && typeof next === "object" && !Array.isArray(next)
    ? (next as Record<string, unknown>)
    : null;
}

function coordinatesFromObject(
  value: Record<string, unknown> | null
): { latitude: string; longitude: string } | null {
  const lat = numberLike(value?.lat ?? value?.latitude ?? value?.latitudeDeg);
  const lon = numberLike(value?.lon ?? value?.lng ?? value?.longitude ?? value?.longitudeDeg);
  if (lat == null || lon == null) return null;
  return { latitude: formatCoordinateDisplay(lat), longitude: formatCoordinateDisplay(lon) };
}

function coordinatesFromText(text: string): { latitude: string; longitude: string } | null {
  const latMatch = text.match(/(?:lat|latitude|纬度|緯度)\s*[:=]\s*(-?\d+(?:\.\d+)?)/i);
  const lonMatch = text.match(/(?:lon|lng|longitude|经度|經度|経度)\s*[:=]\s*(-?\d+(?:\.\d+)?)/i);
  const lat = numberLike(latMatch?.[1]);
  const lon = numberLike(lonMatch?.[1]);
  if (lat == null || lon == null) return null;
  return { latitude: formatCoordinateDisplay(lat), longitude: formatCoordinateDisplay(lon) };
}

function numberLike(value: unknown): number | null {
  const number =
    typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(number) ? number : null;
}

function formatCoordinateDisplay(value: number) {
  return value.toFixed(6).replace(/\.?0+$/, "");
}

function displayMappedValue(value: string | undefined, labels: Record<string, string>) {
  if (!value) return "";
  return labels[value] ?? value;
}

function displayCollected(value: string | undefined) {
  if (!value || value === "—" || value.includes("not-collected") || value.includes("待填"))
    return "";
  return value;
}

function extractConcern(userContext: string) {
  const match = userContext.match(/### 初始关心事项\s+([\s\S]*?)(?:\n### |\n##_|\n## |$)/);
  return match?.[1]?.trim() ?? "";
}
