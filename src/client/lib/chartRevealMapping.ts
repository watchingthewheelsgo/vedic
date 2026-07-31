import {
  WORKSHOP_STAGES,
  aggregateWorkshopStages,
  type StageDef
} from "../components/PipelineFlow";
import type { PipelineData } from "./pipeline";

/**
 * Maps the native VedicDust pipeline onto the
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
const STAGE_MESSAGING: Record<string, { title: string; caption: string; focus: ChartRevealFocus }> =
  {
    src: {
      title: "接收出生信息",
      caption: "已收到你的出生日期、时间、地点——排盘马上开始。",
      focus: { kind: "lagna" }
    },
    chart: {
      title: "确定上升点与行星落位",
      caption: "正在计算你的上升点和9颗行星的位置——这是你星盘的基础骨架。",
      focus: { kind: "lagna" }
    },
    reader: {
      title: "校准出生时间",
      caption: "正在核对你之前确认过的几条推断，用来校准这张盘的可信度。",
      focus: { kind: "lagna" }
    },
    judgement: {
      title: "合成有证据的判断",
      caption: "正在把本命承诺、能力强弱、可用分盘与时间周期合成为少量可追溯结论。",
      focus: { kind: "synthesis" }
    },
    consultation: {
      title: "生成专业咨询档案",
      caption: "正在按你的关注重点组织结论、时间窗口、现实启示与专业证据。",
      focus: { kind: "synthesis" }
    }
  };

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

export function deriveChartRevealState(data: PipelineData | null): ChartRevealState {
  if (!data || data.nodes.length === 0) {
    return {
      title: STAGE_MESSAGING.src.title,
      caption: STAGE_MESSAGING.src.caption,
      focus: STAGE_MESSAGING.src.focus,
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

  const title = STAGE_MESSAGING[activeStage.id]?.title ?? activeStage.label;
  const caption = STAGE_MESSAGING[activeStage.id]?.caption ?? "";
  const focus: ChartRevealFocus = STAGE_MESSAGING[activeStage.id]?.focus ?? {
    kind: "synthesis"
  };

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
