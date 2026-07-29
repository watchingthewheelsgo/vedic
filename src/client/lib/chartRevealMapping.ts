import {
  WORKSHOP_STAGES,
  aggregateWorkshopStages,
  type StageDef
} from "../components/PipelineFlow";
import type { PipelineData } from "./pipeline";

/**
 * Maps the real backend pipeline (WORKSHOP_STAGES + node IDs from
 * skill_runtime.py, e.g. p2_sun, p4_house_01..12, p3a_d9_sun) onto the
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

export function chartRevealCoordinatesFromFacts(
  facts: Record<string, unknown> | null
): ChartRevealCoordinates | null {
  const rashi = objectRecord(facts?.rashi);
  const lagna = objectRecord(rashi?.lagna);
  const planets = objectRecord(rashi?.planets);
  const lagnaLongitude = finiteNumber(lagna?.longitude);
  if (lagnaLongitude == null || !planets) return null;

  const planetLongitudes: Partial<Record<PlanetKey, number>> = {};
  for (const planet of Object.keys(PLANET_SLUG).map((slug) => PLANET_SLUG[slug])) {
    const longitude = finiteNumber(objectRecord(planets[planet])?.longitude);
    if (longitude != null) planetLongitudes[planet] = longitude;
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
    p1: {
      title: "核心性格结构",
      caption: "正在综合上升、月亮和主要行星，勾勒你的核心性格结构。",
      focus: { kind: "synthesis" }
    },
    yoga: {
      title: "扫描格局",
      caption: "正在扫描你的格局：财富格、权力格……这些是行星组合出的特殊潜力。",
      focus: { kind: "synthesis" }
    },
    d9: {
      title: "九分盘深度审计",
      caption: "正在核对你的九分盘——这是检验命盘承诺能不能兑现的关键一层。",
      focus: { kind: "d9" }
    },
    div: {
      title: "事业与居所分盘",
      caption: "正在交叉核对事业分盘(D10)和不动产分盘(D4)，看物质层面的证据是否一致。",
      focus: { kind: "d9" }
    },
    dasha: {
      title: "合成大运时间线",
      caption: "正在合成你的大运时间线——9颗行星依次「当家」，决定了什么时候轮到谁的能量登场。",
      focus: { kind: "dasha" }
    },
    pari: {
      title: "交叉验证",
      caption: "正在检查行星之间的互溶关系——某些组合会把两个宫位的命运绑在一起。",
      focus: { kind: "synthesis" }
    },
    life: {
      title: "十大人生板块合成",
      caption: "正在把前面所有层次的证据，合成到事业、感情、财富等十个具体人生板块。",
      focus: { kind: "synthesis" }
    },
    appx: {
      title: "最终校核",
      caption: "正在做最后的质量校核，确认报告的每一条结论都有数据支撑。",
      focus: { kind: "synthesis" }
    }
  };

const PLANET_CAPTION: Record<PlanetKey, string> = {
  Sun: "正在评估太阳的力量——这关系到你的自信、权威感和身体元气。",
  Moon: "正在评估月亮的力量——这关系到你的情绪稳定度和直觉。",
  Mars: "正在评估火星的力量——这关系到你的行动力和处理冲突的方式。",
  Mercury: "正在评估水星的力量——这关系到你的沟通和分析能力。",
  Jupiter: "正在评估木星的力量——这决定了你智慧和好运信号有多「响」。",
  Venus: "正在评估金星的力量——这关系到你的审美、亲密关系和享受能力。",
  Saturn: "正在评估土星的力量——这关系到你的纪律性和长期耐力。",
  Rahu: "正在评估罗睺的力量——这关系到你的欲望和不寻常的野心。",
  Ketu: "正在评估计都的力量——这关系到你天生放下的课题。"
};

const HOUSE_CAPTION: Record<number, string> = {
  1: "正在诊断第1宫（自我）：你的外在形象和身体底色。",
  2: "正在诊断第2宫（财富/家庭）：你的收入模式和语言表达。",
  3: "正在诊断第3宫（沟通/勇气）：你和兄弟姐妹的关系、学习新技能的方式。",
  4: "正在诊断第4宫（家庭/教育）：你的成长环境和内心安全感的来源。",
  5: "正在诊断第5宫（创造力/恋爱）：你的创造力和恋爱模式。",
  6: "正在诊断第6宫（竞争/健康）：你面对压力和竞争的方式。",
  7: "正在诊断第7宫（婚姻/合作）：这个宫位的状态决定了关系中的模式。",
  8: "正在诊断第8宫（变化/危机）：你面对深度转变的能力。",
  9: "正在诊断第9宫（运气/导师）：你的信念体系和贵人运。",
  10: "正在诊断第10宫（事业）：你的事业主星落在哪，决定了你的职场生态位。",
  11: "正在诊断第11宫（收入/社交）：你的社交圈和收入增长模式。",
  12: "正在诊断第12宫（损耗/灵性）：你的休息方式和精神成长课题。"
};

function houseNumberFromNodeId(nodeId: string): number | null {
  const match = nodeId.match(/^p4_house_(\d{2})$/);
  return match ? parseInt(match[1], 10) : null;
}

function planetFromNodeId(prefix: string, nodeId: string): PlanetKey | null {
  if (!nodeId.startsWith(prefix)) return null;
  const slug = nodeId.slice(prefix.length);
  return PLANET_SLUG[slug] ?? null;
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

  const housesCompleted = data.nodes
    .filter((node) => node.status === "completed" || node.status === "skipped")
    .map((node) => houseNumberFromNodeId(node.id))
    .filter((n): n is number => n !== null);

  let title = STAGE_MESSAGING[activeStage.id]?.title ?? activeStage.label;
  let caption = STAGE_MESSAGING[activeStage.id]?.caption ?? "";
  let focus: ChartRevealFocus = STAGE_MESSAGING[activeStage.id]?.focus ?? { kind: "synthesis" };

  if (activeStage.id === "p2") {
    const activeNode = data.nodes.find(
      (node) =>
        node.id.startsWith("p2_") &&
        node.id !== "p2_yoga" &&
        (node.status === "running" || node.status === "waiting")
    );
    const planet = activeNode ? planetFromNodeId("p2_", activeNode.id) : null;
    if (planet) {
      title = `评估${planet}的信号`;
      caption = PLANET_CAPTION[planet];
      focus = { kind: "planet", planet };
    } else {
      title = "评估行星信号";
      caption = "正在逐一评估9颗行星的力量强弱——这决定了每个人生领域执行起来顺不顺。";
      focus = { kind: "synthesis" };
    }
  }

  if (activeStage.id === "house") {
    const activeNode = data.nodes.find(
      (node) =>
        node.id.startsWith("p4_house_") && (node.status === "running" || node.status === "waiting")
    );
    const house = activeNode ? houseNumberFromNodeId(activeNode.id) : null;
    if (house) {
      title = `诊断第${house}宫`;
      caption = HOUSE_CAPTION[house];
      focus = { kind: "house", house };
    }
  }

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
