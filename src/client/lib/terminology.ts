// Single-source Vedic/Jyotish terminology glossary.
//
// This is the canonical place to define what a term means when it shows up
// in a report. The MarkdownReport wiki-card popover reads from here, and
// the wording here should match how skills translate the same terms inline
// (see .claude/skills/vedic/*/SKILL.md "术语使用规则" sections) — if this
// drifts from what a skill says, fix whichever one is wrong rather than
// letting the UI and the report text disagree.

export interface TermEntry {
  /** Canonical display term as it appears in report text. */
  term: string;
  /** Additional surface forms that should also trigger the same card. */
  aliases?: string[];
  /** One-line, plain-language explanation. */
  short: string;
  /** Optional deeper/technical note, shown when expanded. */
  detail?: string;
  /** Original Sanskrit/Devanagari-derived name, if different from `term`. */
  sanskrit?: string;
}

export const TERMINOLOGY: TermEntry[] = [
  {
    term: "Lagna",
    aliases: ["上升点", "上升星座"],
    short: "出生那一刻，东方地平线升起的星座——你的星盘第1宫，代表自我、身体和性格底色。",
    detail: "整宫制下，Lagna所在星座即为第1宫，其余11宫按星座顺序依次排列。"
  },
  {
    term: "Bhava",
    aliases: ["宫位"],
    short: "星盘被划分成的12个生活领域，每宫对应一类人生主题（如7宫=婚姻，10宫=事业）。"
  },
  {
    term: "Varga",
    aliases: ["分盘"],
    short: "把本命盘按特定规则再切分出的一张「聚焦盘」，用来放大观察某个具体领域。",
    detail:
      "经典体系有十六分盘（Shodasavarga）：D1(本身)/D9(婚姻)/D10(事业)/D4(不动产)等，每张对应不同主题。"
  },
  {
    term: "Nakshatra",
    aliases: ["星宿"],
    short: "把黄道分成27份的「月宿」系统，比星座更细，用来描述行星更精确的性格底色。",
    detail: "每个Nakshatra跨13°20'，进一步分为4个Pada（音步），共108份。"
  },
  {
    term: "Dasha",
    aliases: ["大运", "达萨"],
    short:
      "吠陀占星的运程时间轴，把人生120年划分给9颗行星依次「当家」，决定「什么时候轮到谁的能量登场」。",
    detail: "本产品使用Vimshottari Dasha（最主流的达萨系统），起算点由出生时Moon所在Nakshatra决定。"
  },
  {
    term: "Mahadasha",
    aliases: ["大运"],
    short: "达萨系统里的「大周期」，一段长达数年到二十年的主运程。"
  },
  {
    term: "Antardasha",
    aliases: ["小运"],
    short: "大运内部再切分出的「子周期」，决定大运基调下更具体的阶段性变化。"
  },
  {
    term: "Karaka",
    aliases: ["指示星"],
    short: "某个人生领域的「专属代言行星」——比如DK代表配偶，AmK代表事业。",
    detail:
      "本产品采用KN Rao的7K体系（Sun~Saturn七颗行星按度数排序），不含Rahu；这是流派选择，Sanjay Rath一派使用含Rahu的8K体系。"
  },
  {
    term: "AK",
    short: "灵魂指示星（Atma Karaka）——本命盘中度数最高的行星，代表这一世灵魂最想完成的课题。"
  },
  {
    term: "AmK",
    short: "事业指示星（Amatya Karaka）——排名第二的指示星，指向你适合的事业/工作方向。"
  },
  {
    term: "DK",
    short: "配偶指示星（Daraka Karaka）——指向配偶的品质和婚姻的整体走向。",
    detail: "本产品DK固定取7K体系（不含Rahu）；8K体系（含Rahu）仅作参考展示，不作为主判据。"
  },
  {
    term: "PK",
    short: "本产品中用于恋爱分析的指示星之一，传统定义为子女指示星（Putra Karaka）。",
    detail:
      "⚠️ 这是本产品对PK的延伸用法：多数流派用DK/7宫/5宫/Venus判断恋爱，PK本义只管子女/创造力，请结合其他信号交叉验证，不单独依赖。"
  },
  {
    term: "Shadbala",
    aliases: ["六重力量"],
    short: "衡量一颗行星「有没有力气做事」的综合评分，由六种独立力量加总而成。",
    detail:
      "≥150%=强，100-149%=中，<100%=弱。PyJHora计算存在已知系统偏差，建议只参考排序和强弱分级，不参考绝对数值。"
  },
  {
    term: "Vargeeya Bala",
    aliases: ["多分盘综合力量"],
    short:
      "把行星在多张分盘中的表现加权合成的一个分数，用来判断「这颗星整体强不强」，和Shadbala互为交叉验证。",
    detail:
      "Shadbala只看D1单盘；Vargeeya Bala看该行星在Pancha(5张)/Dwadhasa(12张)分盘中重复处于旺相位置的比例。"
  },
  {
    term: "SAV",
    aliases: ["Sarvashtakavarga"],
    short: "衡量某个星座/宫位「资源带宽」的点数系统，分数越高代表这个领域天生的可用资源越充裕。",
    detail:
      "SAV>32=溢出，26-32=平稳，20-25=紧张，<20=匮乏；总分固定为337分，是排盘正确性的自检指标之一。"
  },
  {
    term: "BAV",
    aliases: ["Bhinnashtakavarga"],
    short: "SAV的行星专属版本，看某一颗行星在12个星座各自的资源强弱。"
  },
  {
    term: "Yoga",
    aliases: ["格局"],
    short: "行星之间形成的特殊组合模式，会放大或改变盘面的某种潜力（如财富格、权力格）。"
  },
  {
    term: "Vargottama",
    short:
      "行星在本命盘(D1)和九分盘(D9)落在同一个星座——传统上认为这会让该行星的力量和承诺感明显增强。"
  },
  {
    term: "Ayanamsa",
    short:
      "吠陀占星（恒星黄道）与西方占星（回归黄道）之间的度数偏移量，决定了同一时刻算出的星座是否一致。",
    detail:
      "本产品默认使用Lahiri（行业事实标准，多数吠陀软件/官方历书采用），同时计算True Chitrapaksha作为交叉校验，两者差异通常<2角分。"
  },
  {
    term: "Rahu",
    aliases: ["罗睺"],
    short: "月亮北交点，象征欲望、扩张和现代性；在吠陀体系里被当作一颗「行星」参与分析。"
  },
  {
    term: "Ketu",
    aliases: ["计都"],
    short: "月亮南交点，永远与Rahu相差180°，象征放下、内省和过去的业力。"
  }
];

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Flattened lookup: every term/alias string -> its owning TermEntry. */
export const TERMINOLOGY_INDEX: Map<string, TermEntry> = new Map(
  TERMINOLOGY.flatMap((entry) => [
    [entry.term, entry] as const,
    ...(entry.aliases ?? []).map((alias) => [alias, entry] as const)
  ])
);

/**
 * Matches the longest known term/alias first so e.g. "Vargeeya Bala" wins
 * over a bare "Bala" if one were ever added. ASCII terms get \b word
 * boundaries; CJK terms don't use \b since CJK characters aren't "word"
 * characters in JS regex.
 */
export const TERMINOLOGY_PATTERN = new RegExp(
  Array.from(TERMINOLOGY_INDEX.keys())
    .sort((a, b) => b.length - a.length)
    .map((key) => {
      const escaped = escapeRegExp(key);
      return /^[A-Za-z0-9\s]+$/.test(key) ? `\\b${escaped}\\b` : escaped;
    })
    .join("|"),
  "g"
);
