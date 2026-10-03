import type { LocaleCode } from "../i18n/messages";

export type AtlasRequest = {
  message: string;
  history: { role: "user" | "atlas"; text: string }[];
  locale: LocaleCode;
  timezone: string;
  sessionId?: string | null;
  useNotes: boolean;
};

export type AtlasLens = { source: "vedic" | "bazi" | "notes"; text: string; refs: string[] };

export type AtlasResponse = {
  headline: string;
  answer: string;
  lenses: AtlasLens[];
  followUps: string[];
  day: string;
  sources: { vedic: boolean; journalDays: number; notesShared: boolean };
};

export type AtlasTurn =
  { id: string; role: "user"; text: string } | { id: string; role: "atlas"; answer: AtlasResponse };

export type AtlasContextKey =
  "today" | "days" | "journal" | "charts" | "reading" | "discover" | "ask";

export function atlasContextFor(pathname: string): AtlasContextKey {
  if (pathname.startsWith("/app/days")) return "days";
  if (pathname.startsWith("/app/records") || pathname.startsWith("/app/explore")) return "journal";
  if (/^\/app\/charts\/(?!new|bazi)[^/]+/.test(pathname)) return "reading";
  if (pathname.startsWith("/app/charts")) return "charts";
  if (pathname.startsWith("/app/discover")) return "discover";
  if (pathname.startsWith("/app/ask")) return "ask";
  return "today";
}

const MAX_STORED_TURNS = 30;

/** Saved conversation; storage can be missing or blocked, so every access is guarded. */
export function readStoredTurns(key: string): AtlasTurn[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(key) ?? "[]");
    return Array.isArray(parsed)
      ? parsed.filter(
          (turn): turn is AtlasTurn =>
            typeof turn === "object" &&
            turn !== null &&
            ((turn as AtlasTurn).role === "user" || (turn as AtlasTurn).role === "atlas")
        )
      : [];
  } catch {
    return [];
  }
}

export function storeTurns(key: string, turns: AtlasTurn[]) {
  try {
    if (turns.length) localStorage.setItem(key, JSON.stringify(turns.slice(-MAX_STORED_TURNS)));
    else localStorage.removeItem(key);
  } catch {
    // Private mode or blocked storage: the conversation simply isn't kept.
  }
}

type ChartSubject = { birthDate?: string | null; birthPlace?: string | null } | null | undefined;

/** "May 18, 1992 · Shanghai"; raw coordinates are never shown as a place. */
export function chartLabel(subject: ChartSubject, localeTag: string): string {
  const place = subject?.birthPlace?.split("|")[0].trim();
  let date = subject?.birthDate ?? "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    date = new Intl.DateTimeFormat(localeTag, {
      year: "numeric",
      month: "short",
      day: "numeric",
      timeZone: "UTC"
    }).format(new Date(`${date}T00:00:00Z`));
  }
  return [date, place && !place.startsWith("lat=") ? place : null].filter(Boolean).join(" · ");
}

/** One row per person and tradition: the newest finished chart, else the newest. */
export function uniqueCharts<T extends { kind: string; label: string; completed: boolean }>(
  charts: T[]
): T[] {
  const picked = new Map<string, T>();
  for (const chart of charts) {
    const key = `${chart.kind}|${chart.label}`;
    const current = picked.get(key);
    if (!current || (!current.completed && chart.completed)) picked.set(key, chart);
  }
  return [...picked.values()];
}

/** Plain-text transcript entry sent back as conversation history. */
export function turnText(turn: AtlasTurn): string {
  return turn.role === "user" ? turn.text : `${turn.answer.headline}\n${turn.answer.answer}`;
}

type Copy = {
  name: string;
  tagline: string;
  placeholder: string;
  send: string;
  thinking: string;
  open: string;
  close: string;
  newChat: string;
  useNotes: string;
  notesHint: string;
  chart: string;
  noChart: string;
  journalDays: (n: number) => string;
  lens: Record<AtlasLens["source"], string>;
  disclaimer: string;
  error: string;
  emptyTitle: string;
  emptyBody: string;
  chartFirstTitle: string;
  chartFirstBody: string;
  chartFirstVedic: string;
  chartFirstBazi: string;
  suggestions: Record<AtlasContextKey, string[]>;
};

const zh: Copy = {
  name: "Atlas",
  tagline: "结合你的命盘与记录",
  placeholder: "问问感情、事业、家庭……",
  send: "发送",
  thinking: "Atlas 正在思考……",
  open: "打开 Atlas",
  close: "关闭",
  newChat: "新对话",
  useNotes: "参考我最近的记录",
  notesHint: "会把最近 7 天的记录内容发送给 AI 服务。",
  chart: "Vedic 报告",
  noChart: "暂无完成的报告",
  journalDays: (n) => `${n} 天记录`,
  lens: { vedic: "Vedic", bazi: "八字", notes: "你的记录" },
  disclaimer: "仅供反思，不是确定的预言。",
  error: "Atlas 暂时无法回答，请稍后再试。",
  emptyTitle: "想聊点什么？",
  emptyBody: "Atlas 会结合你的命盘、今天的干支和你的记录来回答。",
  chartFirstTitle: "先认识你，再陪你聊",
  chartFirstBody:
    "Atlas 需要你的命盘才能给出属于你的回答。填一次出生信息，就能解锁对话、每日宜忌和顺日分析。",
  chartFirstVedic: "创建 Vedic 命盘",
  chartFirstBazi: "创建八字命盘",
  suggestions: {
    today: ["今天我该关注什么？", "这周哪几天适合做重要的事？"],
    days: ["为什么有些日子对我更顺？", "下个月有哪些顺日？"],
    journal: ["最近我的情绪有什么规律？", "帮我回顾这一周"],
    charts: ["用三句话总结我的报告", "我的事业重点在哪里？"],
    reading: ["这一章对我意味着什么？", "接下来一年要注意什么？"],
    discover: ["我的日主说明了我什么？", "我和李小龙的命盘有什么不同？"],
    ask: ["今天我该关注什么？", "我的感情会怎样发展？", "适合换工作吗？"]
  }
};

const en: Copy = {
  name: "Atlas",
  tagline: "Reads your charts and notes together",
  placeholder: "Ask about love, career, family…",
  send: "Send",
  thinking: "Atlas is thinking…",
  open: "Open Atlas",
  close: "Close",
  newChat: "New chat",
  useNotes: "Use my recent notes",
  notesHint: "Sends your last 7 journal entries to our AI provider.",
  chart: "Vedic reading",
  noChart: "No finished reading yet",
  journalDays: (n) => `${n} journal days`,
  lens: { vedic: "Vedic", bazi: "BaZi", notes: "Your notes" },
  disclaimer: "A reflection to think with, not a certainty.",
  error: "Atlas couldn't answer just now. Please try again.",
  emptyTitle: "What's on your mind?",
  emptyBody: "Atlas answers from your chart, today's stem-branch and your journal.",
  chartFirstTitle: "Let Atlas get to know you",
  chartFirstBody:
    "Atlas needs your chart to answer about you, not people in general. Add your birth details once to unlock chat, daily Good for / Avoid and your auspicious days.",
  chartFirstVedic: "Create my Vedic chart",
  chartFirstBazi: "Create my BaZi chart",
  suggestions: {
    today: ["What should I focus on today?", "Which days this week suit big decisions?"],
    days: ["Why are some days brighter for me?", "What are my bright days next month?"],
    journal: ["What patterns do you see in my moods?", "Help me review this week"],
    charts: ["Summarize my reading in three sentences", "Where is my career focus?"],
    reading: ["What does this chapter mean for me?", "What should I watch for this year?"],
    discover: [
      "What does my Day Master say about me?",
      "How is my chart different from Bruce Lee's?"
    ],
    ask: [
      "What should I focus on today?",
      "How will my relationship develop?",
      "Is this a good time to change jobs?"
    ]
  }
};

const ja: Copy = {
  ...en,
  tagline: "チャートと記録をあわせて読み解く",
  placeholder: "恋愛・仕事・家族について質問…",
  send: "送信",
  thinking: "Atlas が考えています…",
  open: "Atlas を開く",
  close: "閉じる",
  newChat: "新しい会話",
  useNotes: "最近の記録を参考にする",
  notesHint: "直近7日分の記録を AI サービスに送信します。",
  chart: "Vedic レポート",
  noChart: "完了したレポートはまだありません",
  journalDays: (n) => `${n}日分の記録`,
  lens: { vedic: "Vedic", bazi: "八字", notes: "あなたの記録" },
  disclaimer: "確定的な予言ではなく、考えるための視点です。",
  error: "Atlas が応答できませんでした。もう一度お試しください。",
  emptyTitle: "何を話しましょう？",
  emptyBody: "あなたのチャート、今日の干支、記録をもとに答えます。",
  chartFirstTitle: "まずはあなたのことを教えてください",
  chartFirstBody:
    "Atlas はあなたのチャートをもとに答えます。出生情報を一度入力すると、チャット、毎日の宜忌、吉日分析が使えるようになります。",
  chartFirstVedic: "Vedic チャートを作成",
  chartFirstBazi: "八字チャートを作成",
  suggestions: {
    today: ["今日は何に集中すべき？", "今週、大事な決断に向く日は？"],
    days: ["なぜ一部の日が自分に合うの？", "来月の吉日は？"],
    journal: ["気分にどんなパターンがある？", "今週を振り返りたい"],
    charts: ["レポートを3文で要約して", "仕事の重点はどこ？"],
    reading: ["この章は私にとって何を意味する？", "今年気をつけることは？"],
    discover: ["私の日主は何を表している？", "ブルース・リーとの違いは？"],
    ask: ["今日は何に集中すべき？", "恋愛はどう進む？", "転職に向いている時期？"]
  }
};

export const atlasCopy = { zh, en, ja };
