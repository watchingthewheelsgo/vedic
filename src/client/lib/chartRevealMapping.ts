import {
  WORKSHOP_STAGES,
  aggregateWorkshopStages,
  type StageDef
} from "../components/PipelineFlow";
import type { PipelineData } from "./pipeline";

/**
 * Maps the native Sign Atlas pipeline onto the
 * ChartRevealProgress visual. This is the single place that translates
 * "what the backend is doing" into "what lights up on the chart wheel" —
 * Pipeline stage details and this reveal view read the exact
 * same aggregation, they just render it differently.
 */

export type PlanetKey =
  "Sun" | "Moon" | "Mars" | "Mercury" | "Jupiter" | "Venus" | "Saturn" | "Rahu" | "Ketu";

const PLANET_SLUG: Record<string, PlanetKey> = {
  sun: "Sun",
  moon: "Moon",
  mars: "Mars",
  mercury: "Mercury",
  jupiter: "Jupiter",
  venus: "Venus",
  saturn: "Saturn",
  rahu: "Rahu",
  ketu: "Ketu"
};

export type ChartRevealFocus =
  | { kind: "lagna" }
  | { kind: "planet"; planet: PlanetKey }
  | { kind: "house"; house: number }
  | { kind: "d9" }
  | { kind: "dasha" }
  | { kind: "synthesis" };

export interface ChartRevealState {
  title: string;
  caption: string;
  focus: ChartRevealFocus;
  lagnaRevealed: boolean;
  planetsRevealed: boolean;
  housesCompleted: number[];
  progressLabel: string;
}

export interface ChartRevealCoordinates {
  lagnaLongitude: number;
  planetLongitudes: Partial<Record<PlanetKey, number>>;
}

export function chartRevealCoordinatesFromRecord(
  record: Record<string, unknown> | null
): ChartRevealCoordinates | null {
  const astronomy = objectRecord(record?.astronomy);
  const ascendant = objectRecord(astronomy?.ascendant);
  const grahas = Array.isArray(astronomy?.grahas) ? astronomy.grahas : [];
  const lagnaLongitude = finiteNumber(ascendant?.longitudeDeg);
  if (lagnaLongitude == null) return null;

  const planetLongitudes: Partial<Record<PlanetKey, number>> = {};
  for (const item of grahas) {
    const graha = objectRecord(item);
    const planet = typeof graha?.graha === "string" ? PLANET_SLUG[graha.graha.toLowerCase()] : null;
    const longitude = finiteNumber(objectRecord(graha?.position)?.longitudeDeg);
    if (planet && longitude != null) planetLongitudes[planet] = longitude;
  }
  return { lagnaLongitude, planetLongitudes };
}

// Generic per-stage messaging for stages that aren't further subdivided by a
// specific planet/house. Stage ids match WORKSHOP_STAGES exactly.
type StageMessage = { title: string; caption: string; focus: ChartRevealFocus };
type RevealLocale = "zh" | "en" | "ja";

const STAGE_FOCUS: Record<string, ChartRevealFocus> = {
  src: { kind: "lagna" },
  chart: { kind: "lagna" },
  reader: { kind: "lagna" },
  judgement: { kind: "synthesis" },
  consultation: { kind: "synthesis" }
};

const STAGE_TEXT: Record<RevealLocale, Record<string, { title: string; caption: string }>> = {
  zh: {
    src: { title: "接收出生信息", caption: "已收到你的出生日期、时间、地点——排盘马上开始。" },
    chart: {
      title: "确定上升点与行星落位",
      caption: "正在计算你的上升点和9颗行星的位置——这是你星盘的基础骨架。"
    },
    reader: {
      title: "校准出生时间",
      caption: "正在核对你之前确认过的几条推断，用来校准这张盘的可信度。"
    },
    judgement: {
      title: "合成有证据的判断",
      caption: "正在把本命承诺、能力强弱、可用分盘与时间周期合成为少量可追溯结论。"
    },
    consultation: {
      title: "撰写你的解读",
      caption: "正在按你的关注重点组织结论、时间窗口、现实启示与专业证据。"
    }
  },
  en: {
    src: {
      title: "Receiving your birth details",
      caption: "Your birth date, time and place are in. Your chart is about to be drawn."
    },
    chart: {
      title: "Placing your ascendant and planets",
      caption: "Calculating your rising sign and the nine planets: the skeleton of your chart."
    },
    reader: {
      title: "Checking your birth time",
      caption: "Weighing what you confirmed earlier to judge how firm this chart is."
    },
    judgement: {
      title: "Building evidence-backed findings",
      caption:
        "Combining your natal promise, strengths, divisional charts and life periods into a few traceable findings."
    },
    consultation: {
      title: "Writing your reading",
      caption:
        "Organizing findings, timing windows and practical takeaways around what you asked about."
    }
  },
  ja: {
    src: {
      title: "出生情報を受け取りました",
      caption: "生年月日・時刻・場所を受け取りました。まもなくチャートを作成します。"
    },
    chart: {
      title: "上昇点と惑星を配置中",
      caption: "上昇宮と9つの惑星の位置を計算しています。チャートの骨格です。"
    },
    reader: {
      title: "出生時刻を確認中",
      caption: "確認済みの内容から、このチャートの確かさを見極めています。"
    },
    judgement: {
      title: "根拠のある判断を統合中",
      caption: "出生図の約束、強さ、分割図、時期を少数の追跡可能な結論にまとめています。"
    },
    consultation: {
      title: "リーディングを執筆中",
      caption: "ご相談のテーマに沿って、結論・時期・実践的なポイントを整理しています。"
    }
  }
};

function stageMessage(stageId: string, locale: RevealLocale): StageMessage | null {
  const text = STAGE_TEXT[locale]?.[stageId] ?? STAGE_TEXT.en[stageId];
  return text ? { ...text, focus: STAGE_FOCUS[stageId] ?? { kind: "synthesis" } } : null;
}

function pickActiveStage(
  agg: Record<string, { status: string; done: number; total: number }>,
  stages: StageDef[]
): StageDef {
  const running = stages.find(
    (s) => agg[s.id]?.status === "running" || agg[s.id]?.status === "waiting"
  );
  if (running) return running;
  let lastDone = stages[0];
  for (const stage of stages) {
    if (agg[stage.id]?.status === "done") lastDone = stage;
  }
  return lastDone;
}

export function deriveChartRevealState(
  data: PipelineData | null,
  locale: RevealLocale = "en"
): ChartRevealState {
  const initial = stageMessage("src", locale)!;
  if (!data || data.nodes.length === 0) {
    return {
      title: initial.title,
      caption: initial.caption,
      focus: initial.focus,
      lagnaRevealed: false,
      planetsRevealed: false,
      housesCompleted: [],
      progressLabel: "0/0"
    };
  }

  const agg = aggregateWorkshopStages(data.nodes, WORKSHOP_STAGES);
  const activeStage = pickActiveStage(agg, WORKSHOP_STAGES);
  const chartDone = agg.chart?.status === "done";

  const housesCompleted =
    agg.judgement?.status === "done" || agg.consultation?.status === "done"
      ? Array.from({ length: 12 }, (_, index) => index + 1)
      : [];

  const message = stageMessage(activeStage.id, locale);
  const title = message?.title ?? activeStage.label;
  const caption = message?.caption ?? "";
  const focus: ChartRevealFocus = message?.focus ?? { kind: "synthesis" };

  return {
    title,
    caption,
    focus,
    lagnaRevealed: chartDone || activeStage.id !== "src",
    planetsRevealed: chartDone,
    housesCompleted,
    progressLabel: `${data.completed}/${data.total}`
  };
}

function objectRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
