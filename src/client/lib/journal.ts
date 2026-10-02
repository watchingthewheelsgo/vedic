export type JournalInput = {
  day: string;
  timezone: string;
  mood: number;
  note: string;
  topic: string;
};
export type CalendarDay = {
  day: string;
  timezone: string;
  pillar: string;
  stem: string;
  branch: string;
  stemElement: string;
  branchElement: string;
  calendarVersion: string;
};
export type Reflection = {
  requestId: string;
  question: string;
  tarotCard: string;
  actionStates?: Partial<Record<"bazi" | "vedic" | "tarot", "planned" | "done">>;
  vedicSessionId: string | null;
  noteSnapshot: string;
  createdAt: string;
  answer: { summary: string; bazi: Lens; vedic: Lens; tarot: Lens; questionToReflectOn: string };
};
type Lens = { interpretation: string; action: string };
export type JournalEntry = JournalInput & { calendar: CalendarDay; reflections: Reflection[] };
export type JournalResponse = {
  today: CalendarDay;
  entries: JournalEntry[];
  summary: {
    recordedDays: number;
    averageMood: number | null;
    byStem: { stem: string; count: number; averageMood: number | null }[];
    byBranch: { stem: string; count: number; averageMood: number | null }[];
    byPillar: { stem: string; count: number; averageMood: number | null }[];
  };
  limit: number;
};
// Personal BaZi 宜/忌 for a day: deterministic backend rules (bazi-daily-guidance/v1)
// comparing the civil day pillar with the user's natal pillars. Never LLM-generated.
export type GuidanceItem = { id: string; zh: string; en: string; ja: string; ruleIds: string[] };
export type BranchRelation = { natalPillar: "year" | "month" | "day" | "hour"; branches: string };
export type DailyGuidance = {
  version: string;
  catalogVersion: string;
  dayPillar: string;
  goodFor: GuidanceItem[];
  avoid: GuidanceItem[];
  ruleIds: string[];
  facts: {
    dayMaster: string;
    tenGod: string;
    stemCombination: string | null;
    clashes: BranchRelation[];
    combinations: (BranchRelation & { label: string })[];
    trines: { branches: string; label: string; kind: "三合" | "半合" }[];
    punishments: (BranchRelation & { label: string })[];
    harms: BranchRelation[];
  };
  limitations: string[];
  natal: {
    source: "bazi_chart_record" | "vedic_chart_record";
    sessionId: string;
    dayMaster: string;
    dayMasterElement: string | null;
    pillars: Record<"year" | "month" | "day", string> & { hour: string | null };
    warnings: string[];
  };
};
export type DailyGuidanceResponse =
  | { calendar: CalendarDay; guidance: DailyGuidance; reason: null }
  | { calendar: CalendarDay; guidance: null; reason: "no_birth_details" };

export function guidanceText(item: GuidanceItem, locale: string): string {
  return locale === "zh" || locale === "ja" ? item[locale] : item.en;
}

export const journalCopy = {
  zh: {
    title: "我的日常",
    subtitle: "记录生活，观察节奏，找到自己的方向。",
    today: "今日历法",
    facts: "当地民用日期 · 午夜换日 · 非个人八字",
    record: "记录这一天",
    mood: "此刻的心情",
    moods: ["很低落", "有些低落", "平静", "不错", "很开心"],
    note: "今天发生了什么？",
    placeholder: "发生的事、当时的感受，以及你想记住的细节……",
    save: "保存记录",
    saved: "已保存",
    history: "我的时间线",
    empty: "从今天的一件小事开始。记录会只保存在你的账户下。",
    topic: "生活领域",
    topics: ["日常", "工作", "关系", "身心", "学习"],
    ask: "一起想一想",
    question: "你想从这件事中理解什么？",
    consent:
      "点击提问，会将这篇已保存的记录、问题及所选命盘发送给本站 AI 服务处理。不会发送其他日记。",
    send: "从三个视角探索",
    thinking: "正在结合你的记录思考…",
    chart: "关联 Vedic 命盘（可选）",
    noChart: "不关联命盘 · 使用一般反思视角",
    snapshot: "本次解读基于提问时保存的记录",
    reflection: "留给自己的问题",
    action: "可以尝试",
    trends: "观察自己的节奏",
    caution:
      "这是已记录日期中的关联，不是干支导致情绪的证据。遗漏记录、星期、睡眠和生活事件都可能影响结果。每组至少 7 天才展示平均心情。",
    samples: "个记录日",
    insufficient: "样本不足",
    baseline: "整体平均心情",
    recent: "最多展示最近 365 个记录日",
    remove: "删除这一天",
    removeConfirm: "删除这一天的记录及解读？此操作无法撤销。",
    error: "暂时无法完成，请重试。",
    retry: "重试",
    back: "返回首页",
    account: "报告与账户",
    bazi: "八字 · 当日干支",
    vedic: "Vedic · 命盘与反思",
    tarot: "塔罗 · 象征视角",
    export: "导出我的记录",
    noSave: "请先保存当天记录，再提问。",
    edit: "你正在编辑历史记录",
    privacy: "私密空间 · 日记不会自动交给 AI",
    loading: "正在加载你的空间…"
  },
  en: {
    title: "My daily space",
    subtitle: "Notice your life. Explore its rhythms. Find your direction.",
    today: "Today's calendar",
    facts: "Local civil date · midnight boundary · not a personal birth chart",
    record: "Capture this day",
    mood: "How are you feeling?",
    moods: ["Very low", "Low", "Neutral", "Good", "Very good"],
    note: "What happened today?",
    placeholder: "An event, a feeling, a detail you want to remember…",
    save: "Save entry",
    saved: "Saved",
    history: "My timeline",
    empty: "Start with one small moment. Entries belong to your account.",
    topic: "Life area",
    topics: ["Everyday", "Work", "Relationships", "Wellbeing", "Learning"],
    ask: "Reflect together",
    question: "What would you like to understand about this?",
    consent:
      "Asking sends this saved entry, your question and the selected chart to our AI provider. Other entries are not sent.",
    send: "Explore three perspectives",
    thinking: "Reflecting on your entry…",
    chart: "Connect a Vedic chart (optional)",
    noChart: "No chart · general reflection only",
    snapshot: "Based on the entry saved when you asked",
    reflection: "A question to take with you",
    action: "Try this",
    trends: "Notice your rhythms",
    caution:
      "Associations in recorded days are not evidence that calendar signs cause feelings. Missing entries, weekdays, sleep and events may affect results. A group needs 7 days before its average is shown.",
    samples: "recorded days",
    insufficient: "Not enough data",
    baseline: "Overall average mood",
    recent: "Up to 365 recent recorded days",
    remove: "Delete this day",
    removeConfirm: "Delete this entry and its reflections? This cannot be undone.",
    error: "Unable to finish. Please try again.",
    retry: "Retry",
    back: "Home",
    account: "Reports & account",
    bazi: "BaZi · calendar day",
    vedic: "Vedic · chart & reflection",
    tarot: "Tarot · symbolic lens",
    export: "Export my entries",
    noSave: "Save this day's entry before asking.",
    edit: "Editing a past entry",
    privacy: "Private space · no automatic AI sharing",
    loading: "Loading your space…"
  },
  ja: {
    title: "日々の記録",
    subtitle: "日常を記録し、リズムを観察し、自分の方向を見つける。",
    today: "今日の暦",
    facts: "現地の日付・午前0時で日替わり・個人の命式ではありません",
    record: "この日を記録",
    mood: "今の気分",
    moods: ["とても低い", "少し低い", "穏やか", "良い", "とても良い"],
    note: "何がありましたか？",
    placeholder: "出来事、感じたこと、覚えておきたいこと…",
    save: "保存",
    saved: "保存しました",
    history: "タイムライン",
    empty: "小さな出来事から始めましょう。記録は自分のアカウントに保存されます。",
    topic: "分野",
    topics: ["日常", "仕事", "関係", "心身", "学び"],
    ask: "一緒に振り返る",
    question: "この出来事から何を理解したいですか？",
    consent:
      "質問すると、保存したこの記録・質問・選択した命盤をAIサービスに送信します。他の日記は送信しません。",
    send: "3つの視点で考える",
    thinking: "記録を振り返っています…",
    chart: "Vedic命盤を関連付ける（任意）",
    noChart: "命盤なし・一般的な振り返り",
    snapshot: "質問時に保存されていた記録に基づきます",
    reflection: "自分への問い",
    action: "試せること",
    trends: "リズムを観察",
    caution:
      "記録日の関連であり、干支が感情の原因である証拠ではありません。未記録の日、曜日、睡眠、出来事も影響します。各群7日以上で平均を表示します。",
    samples: "記録日",
    insufficient: "データ不足",
    baseline: "気分の全体平均",
    recent: "直近365記録日まで表示",
    remove: "この日を削除",
    removeConfirm: "この記録と解読を削除しますか？元に戻せません。",
    error: "完了できませんでした。再試行してください。",
    retry: "再試行",
    back: "ホーム",
    account: "レポートと設定",
    bazi: "八字・日の干支",
    vedic: "Vedic・命盤と内省",
    tarot: "タロット・象徴",
    export: "記録をエクスポート",
    noSave: "先にこの日の記録を保存してください。",
    edit: "過去の記録を編集中",
    privacy: "プライベート・AIへの自動共有なし",
    loading: "読み込み中…"
  }
};
