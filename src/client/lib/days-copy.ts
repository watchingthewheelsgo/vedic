import type { Element } from "./sexagenary";
import type { Fit } from "./patterns";

type Copy = {
  nav: {
    days: string;
    daysShort: string;
    calendar: string;
    ask: string;
    discover: string;
    journal: string;
  };
  fit: Record<Fit, string>;
  fitLong: Record<Fit, string>;
  elements: Record<Element, string>;
  weekdays: string[];
  months: string[];
  yourDay: string;
  todayFit: string;
  quick: string;
  quickSaved: string;
  oneTap: string;
  how: string[];
  startTitle: string;
  startBody: string;
  startVedic: string;
  startBazi: string;
  askToday: string;
  checkedIn: string;
  writeMore: string;
  nextBright: string;
  nextGentle: string;
  noForecast: string;
  askCta: string;
  askHint: string;
  daysTitle: string;
  daysBody: string;
  learned: (days: number) => string;
  rulesTitle: string;
  rule: (key: string, avg: number, count: number, baseline: number) => string;
  ruleLift: string;
  ruleDip: string;
  noRules: string;
  unlock: (have: number, need: number) => string;
  caution: string;
  logged: string;
  notLogged: string;
  writeThis: string;
  viewEntry: string;
  signal: (kind: "stem" | "branch", key: string, avg: number, count: number) => string;
  legend: string;
  prev: string;
  next: string;
  today: string;
  discoverTitle: string;
  discoverBody: string;
  birthDate: string;
  findTwin: string;
  dayMaster: string;
  lateBirth: string;
  sameMaster: string;
  famousTitle: string;
  famousNote: string;
  pillarsOrder: string;
  learnTitle: string;
  tarotTitle: string;
  tarotBody: string;
  soon: string;
  compareAsk: string;
  stems: Record<string, string>;
  lessons: { title: string; body: string }[];
  landingSteps: { title: string; body: string }[];
  goodFor: string;
  avoid: string;
  tenGodDay: (tenGod: string, dayMaster: string) => string;
  addBirthTitle: string;
  addBirthBody: string;
  addBirthAction: string;
  fromNotes: string;
  greeting: (hour: number, name?: string | null) => string;
};

function greet(hour: number, parts: [string, string, string], name?: string | null, sep = ", ") {
  const base = hour < 12 ? parts[0] : hour < 18 ? parts[1] : parts[2];
  return name ? `${base}${sep}${name}` : base;
}

const TEN_GODS_EN: Record<string, string> = {
  比肩: "Friend",
  劫财: "Rob Wealth",
  食神: "Eating God",
  伤官: "Hurting Officer",
  偏财: "Indirect Wealth",
  正财: "Direct Wealth",
  七杀: "Seven Killings",
  正官: "Direct Officer",
  偏印: "Indirect Resource",
  正印: "Direct Resource"
};

const zh: Copy = {
  nav: {
    days: "黄道吉日",
    daysShort: "吉日",
    calendar: "日历",
    ask: "问一问",
    discover: "发现",
    journal: "日记"
  },
  fit: { bright: "顺", steady: "平", gentle: "缓", unknown: "待观察" },
  fitLong: {
    bright: "对你来说是顺日。适合开始、签约、开口。",
    steady: "平稳的一天。适合日常与推进。",
    gentle: "宜放缓。保留弹性，避免正面冲突。",
    unknown: "还在了解这样的日子。继续记录，规律会逐渐清晰。"
  },
  elements: { wood: "木", fire: "火", earth: "土", metal: "金", water: "水" },
  weekdays: ["一", "二", "三", "四", "五", "六", "日"],
  months: ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"],
  yourDay: "你的今天",
  todayFit: "根据你的记录",
  quick: "今天感觉如何？",
  quickSaved: "已与今天的干支一起保存。",
  oneTap: "轻点一下就算打卡，想写再写。",
  how: [
    "每天轻点一下记录心情，想写再写几句。",
    "每一天都有自己的干支，记录会和它一起保存。",
    "同一天干或地支累计 7 天后，日历就会标出适合你的顺日与宜放缓的日子。"
  ],
  startTitle: "先建立你的命盘",
  startBody: "填一次出生信息，就能解锁每日宜忌、Atlas 对话和属于你的顺日分析。",
  startVedic: "创建 Vedic 命盘",
  startBazi: "创建八字命盘",
  askToday: "结合我的命盘和今天的干支，今天我最该把精力放在哪里？",
  checkedIn: "今天已打卡。想补充几句也可以。",
  writeMore: "写下更多",
  nextBright: "接下来的顺日",
  nextGentle: "宜放缓",
  noForecast: "记录满 7 天同类日子后，这里会出现你的个人吉日。",
  askCta: "问问 Atlas 今天怎么过",
  askHint: "结合你的记录、命盘与三种传统视角",
  daysTitle: "你的黄道吉日",
  daysBody: "不是通用黄历，而是从你自己的心情记录里学到的吉日规律。",
  learned: (days) => `来自你 ${days} 天的记录`,
  rulesTitle: "你的日子透露了什么",
  rule: (key, avg, count, baseline) =>
    `「${key}」日平均心情 ${avg}，整体 ${baseline} · ${count} 天`,
  ruleLift: "让你更顺",
  ruleDip: "容易低落",
  noRules: "还没有明显规律。同类日子记录满 7 天后会开始比较。",
  unlock: (have, need) => `最多的一类日子已记录 ${have}/${need} 天`,
  caution: "这是你记录中的关联，不是命运。漏记、星期、睡眠与生活事件都会影响结果。",
  logged: "当天记录",
  notLogged: "这一天还没有记录。",
  writeThis: "记录这一天",
  viewEntry: "查看记录",
  signal: (kind, key, avg, count) =>
    `${kind === "stem" ? "天干" : "地支"}「${key}」的日子，你的平均心情 ${avg}（${count} 天）`,
  legend: "顺 · 平 · 缓",
  prev: "上个月",
  next: "下个月",
  today: "今天",
  discoverTitle: "发现",
  discoverBody: "看看哪些名人与你同一个日主，用传统视角认识自己。",
  birthDate: "出生日期",
  findTwin: "找到我的日主",
  dayMaster: "你的日主",
  lateBirth: "23 点后出生？部分流派从子时换日，日主可能是下一天。",
  sameMaster: "与你同日主",
  famousTitle: "名人命盘",
  famousNote: "名人数据来自公开出生记录，时柱按当地钟表时间。",
  pillarsOrder: "年 · 月 · 日 · 时",
  learnTitle: "三分钟了解",
  tarotTitle: "塔罗",
  tarotBody: "与日记相连的塔罗反思，即将推出。",
  soon: "即将推出",
  compareAsk: "和 AI 深入比较",
  stems: {
    甲: "参天大树，正直向上，喜欢开拓。",
    乙: "花草藤蔓，柔韧灵活，善于变通。",
    丙: "太阳之火，热情外放，照亮他人。",
    丁: "烛火灯光，细腻温暖，专注持久。",
    戊: "高山厚土，稳重可靠，包容沉着。",
    己: "田园之土，细致务实，善于滋养。",
    庚: "刀剑钢铁，果断刚毅，讲求原则。",
    辛: "珠玉首饰，精致敏锐，追求完美。",
    壬: "江河大海，聪明奔放，视野开阔。",
    癸: "雨露泉水，温柔聪慧，善于洞察。"
  },
  lessons: [
    {
      title: "什么是日主？",
      body: "八字中出生那天的天干，代表你自己。其余七个字都围绕日主来解读。"
    },
    { title: "五行", body: "木、火、土、金、水相生相克。命盘的强弱平衡，决定哪些元素对你有帮助。" },
    {
      title: "月宿（Nakshatra）",
      body: "Vedic 占星把黄道分成 27 个月宿，出生时月亮所在的月宿刻画你的情绪本性。"
    }
  ],
  goodFor: "宜",
  avoid: "忌",
  tenGodDay: (tenGod, dayMaster) => `对你的${dayMaster}日主来说，今天是${tenGod}日`,
  addBirthTitle: "解锁你的个人宜忌",
  addBirthBody: "添加出生资料后，每天的宜忌会根据你自己的八字计算，而不是通用黄历。",
  addBirthAction: "添加出生资料",
  fromNotes: "来自你的记录",
  greeting: (hour, name) => greet(hour, ["早上好", "下午好", "晚上好"], name, "，"),
  landingSteps: [
    { title: "记录今天", body: "一个心情、一句话。每条记录都会与当天的干支一起保存。" },
    {
      title: "找到你的黄道吉日",
      body: "记录几周后，Sign Atlas 会告诉你哪些日子真正适合你，并标明有多少天支持这一规律。"
    },
    {
      title: "问一问",
      body: "带着感情、工作或家庭的问题和 AI 聊聊，回答会结合你的命盘与你自己的记录。"
    }
  ]
};

const en: Copy = {
  nav: {
    days: "Auspicious days",
    daysShort: "Days",
    calendar: "Calendar",
    ask: "Ask",
    discover: "Discover",
    journal: "Journal"
  },
  fit: { bright: "Bright", steady: "Steady", gentle: "Go gently", unknown: "Learning" },
  fitLong: {
    bright: "A bright day for you. Good for starting, signing or asking.",
    steady: "A steady day. Fine for routine work and follow-through.",
    gentle: "Go gently. Keep plans flexible and skip confrontations.",
    unknown: "Still learning days like this. Keep logging and the pattern will sharpen."
  },
  elements: { wood: "Wood", fire: "Fire", earth: "Earth", metal: "Metal", water: "Water" },
  weekdays: ["M", "T", "W", "T", "F", "S", "S"],
  months: [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December"
  ],
  yourDay: "Your day",
  todayFit: "From your notes",
  quick: "How's today?",
  quickSaved: "Saved with today's stem-branch.",
  oneTap: "One tap checks you in. Words are optional.",
  how: [
    "Check in each day with one tap. Add a line if you like.",
    "Every day has its own stem-branch, saved with your entry.",
    "After 7 days of the same stem or branch, the calendar marks your bright and go-gently days."
  ],
  startTitle: "Start with your chart",
  startBody:
    "Add your birth details once to unlock daily Good for / Avoid, chats with Atlas and your own auspicious days.",
  startVedic: "Create my Vedic chart",
  startBazi: "Create my BaZi chart",
  askToday: "Given my chart and today's stem-branch, where should I put my energy today?",
  checkedIn: "You're checked in for today. Add a line if you like.",
  writeMore: "Write more",
  nextBright: "Your next bright days",
  nextGentle: "Go gently",
  noForecast: "Once you've logged 7 days of a kind, your personal auspicious days appear here.",
  askCta: "Ask Atlas about today",
  askHint: "Uses your notes, your charts and three traditions",
  daysTitle: "Your auspicious days",
  daysBody: "Not a generic almanac: these are the days your own mood records say suit you.",
  learned: (days) => `Learned from ${days} days of your notes`,
  rulesTitle: "What your days say",
  rule: (key, avg, count, baseline) =>
    `Mood ${avg} on ${key} days vs ${baseline} overall · ${count} days`,
  ruleLift: "Lifts you",
  ruleDip: "Weighs on you",
  noRules: "No clear pattern yet. Days are compared once a kind has 7 entries.",
  unlock: (have, need) => `Your best-covered kind of day: ${have}/${need} entries`,
  caution:
    "These are associations in your notes, not fate. Missed days, weekdays, sleep and events all play a part.",
  logged: "Your entry",
  notLogged: "Nothing logged for this day yet.",
  writeThis: "Log this day",
  viewEntry: "Open entry",
  signal: (kind, key, avg, count) =>
    `On ${key} days (${kind === "stem" ? "stem" : "branch"}) your mood averages ${avg} (${count} days)`,
  legend: "Bright · Steady · Go gently",
  prev: "Previous month",
  next: "Next month",
  today: "Today",
  discoverTitle: "Discover",
  discoverBody: "See which famous people share your Day Master, and learn the traditions.",
  birthDate: "Birth date",
  findTwin: "Find my Day Master",
  dayMaster: "Your Day Master",
  lateBirth: "Born after 11 pm? Some schools start the day at 23:00, so check the next day too.",
  sameMaster: "Same Day Master",
  famousTitle: "Famous charts",
  famousNote: "Famous charts use public birth records. Hour pillars use local clock time.",
  pillarsOrder: "Year · Month · Day · Hour",
  learnTitle: "Learn in 3 minutes",
  tarotTitle: "Tarot",
  tarotBody: "Card readings for reflection, connected to your journal. Coming soon.",
  soon: "Soon",
  compareAsk: "Compare with AI",
  stems: {
    甲: "The tall tree: upright, growing, a pioneer.",
    乙: "The vine and flower: flexible, adaptable, resourceful.",
    丙: "The sun: warm, expressive, lights others up.",
    丁: "The candle: attentive, warm, quietly persistent.",
    戊: "The mountain: steady, dependable, calm.",
    己: "The field: practical, careful, nurturing.",
    庚: "The blade: decisive, principled, direct.",
    辛: "The jewel: refined, perceptive, exacting.",
    壬: "The ocean: bright, free-flowing, far-seeing.",
    癸: "The rain: gentle, intuitive, observant."
  },
  lessons: [
    {
      title: "What is a Day Master?",
      body: "The heavenly stem of your birth day. It stands for you, and the rest of the chart is read in relation to it."
    },
    {
      title: "The five elements",
      body: "Wood, fire, earth, metal and water feed and restrain each other. The balance in your chart shows which ones help you."
    },
    {
      title: "Nakshatras",
      body: "Vedic astrology divides the sky into 27 lunar mansions. The one holding your birth Moon describes your emotional nature."
    }
  ],
  goodFor: "Good for",
  avoid: "Avoid",
  tenGodDay: (tenGod, dayMaster) =>
    `A ${TEN_GODS_EN[tenGod] ?? tenGod} day (${tenGod}) for your ${dayMaster} Day Master`,
  addBirthTitle: "Unlock your personal Good for / Avoid",
  addBirthBody:
    "Add your birth details and each day's guidance is calculated from your own BaZi chart, not a generic almanac.",
  addBirthAction: "Add birth details",
  fromNotes: "From your notes",
  greeting: (hour, name) => greet(hour, ["Good morning", "Good afternoon", "Good evening"], name),
  landingSteps: [
    {
      title: "Log your day",
      body: "A mood and a line. Every entry is saved with that day's stem-branch."
    },
    {
      title: "Find your auspicious days",
      body: "After a few weeks, Sign Atlas shows which days truly suit you, and how many days support each pattern."
    },
    {
      title: "Ask",
      body: "Bring questions about love, work or family. Answers draw on your charts and your own notes."
    }
  ]
};

const ja: Copy = {
  ...en,
  nav: {
    days: "吉日",
    daysShort: "吉日",
    calendar: "カレンダー",
    ask: "相談",
    discover: "発見",
    journal: "日記"
  },
  fit: { bright: "吉", steady: "平", gentle: "控えめに", unknown: "観察中" },
  fitLong: {
    bright: "あなたにとっての吉日。始める・契約する・お願いするのに向いています。",
    steady: "穏やかな一日。日常の作業や継続に向いています。",
    gentle: "控えめに。予定に余裕を持ち、衝突は避けましょう。",
    unknown: "まだ学習中です。記録を続けるとパターンがはっきりします。"
  },
  elements: { wood: "木", fire: "火", earth: "土", metal: "金", water: "水" },
  weekdays: ["月", "火", "水", "木", "金", "土", "日"],
  months: ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"],
  yourDay: "あなたの今日",
  todayFit: "あなたの記録から",
  quick: "今日の気分は？",
  quickSaved: "今日の干支と一緒に保存しました。",
  oneTap: "タップひとつで記録完了。メモは任意です。",
  how: [
    "毎日タップひとつで気分を記録。メモは任意です。",
    "どの日にも干支があり、記録と一緒に保存されます。",
    "同じ天干・地支が7日分たまると、カレンダーにあなたの吉日と控えめに過ごす日が表示されます。"
  ],
  startTitle: "まずはチャートを作りましょう",
  startBody:
    "出生情報を一度入力すると、毎日の宜忌、Atlas との会話、あなただけの吉日分析が使えます。",
  startVedic: "Vedic チャートを作成",
  startBazi: "八字チャートを作成",
  askToday: "私のチャートと今日の干支から、今日はどこに力を注ぐべき？",
  checkedIn: "今日の記録は完了。ひとこと添えてもOK。",
  writeMore: "詳しく書く",
  nextBright: "次の吉日",
  nextGentle: "控えめに",
  noForecast: "同じ種類の日を7日記録すると、あなたの吉日がここに表示されます。",
  askCta: "今日のことを Atlas に聞く",
  askHint: "記録・チャート・3つの伝統を使います",
  daysTitle: "あなたの吉日",
  daysBody: "一般的な暦ではなく、あなた自身の気分の記録から学んだ吉日です。",
  learned: (days) => `${days}日分の記録から`,
  rulesTitle: "記録が示すこと",
  rule: (key, avg, count, baseline) => `${key}の日の気分 ${avg}（全体 ${baseline}）· ${count}日`,
  ruleLift: "上向き",
  ruleDip: "沈みがち",
  noRules: "まだ明確なパターンはありません。同じ種類の日が7日たまると比較します。",
  unlock: (have, need) => `最も多い種類の日：${have}/${need}日`,
  caution: "記録上の関連であり、運命ではありません。記録漏れ、曜日、睡眠、出来事も影響します。",
  logged: "この日の記録",
  notLogged: "この日の記録はまだありません。",
  writeThis: "この日を記録",
  viewEntry: "記録を開く",
  signal: (kind, key, avg, count) =>
    `${kind === "stem" ? "天干" : "地支"}「${key}」の日の平均気分 ${avg}（${count}日）`,
  legend: "吉 · 平 · 控えめに",
  prev: "前の月",
  next: "次の月",
  today: "今日",
  discoverTitle: "発見",
  discoverBody: "同じ日主を持つ有名人を見つけ、伝統を学びましょう。",
  birthDate: "生年月日",
  findTwin: "日主を調べる",
  dayMaster: "あなたの日主",
  lateBirth: "23時以降生まれの場合、流派によっては翌日の日主になります。",
  sameMaster: "同じ日主",
  famousTitle: "有名人の命式",
  famousNote: "公開された出生記録を使用。時柱は現地時刻です。",
  pillarsOrder: "年 · 月 · 日 · 時",
  learnTitle: "3分で学ぶ",
  tarotTitle: "タロット",
  tarotBody: "日記とつながるタロットの振り返り。近日公開。",
  soon: "近日",
  compareAsk: "AI と比較する",
  goodFor: "宜",
  avoid: "忌",
  tenGodDay: (tenGod, dayMaster) => `あなたの日主${dayMaster}にとって今日は${tenGod}の日`,
  addBirthTitle: "あなた専用の宜忌を解放",
  addBirthBody: "出生情報を追加すると、毎日の宜忌があなた自身の命式から計算されます。",
  addBirthAction: "出生情報を追加",
  fromNotes: "あなたの記録から",
  greeting: (hour, name) =>
    greet(hour, ["おはようございます", "こんにちは", "こんばんは"], name, "、"),
  landingSteps: [
    { title: "今日を記録", body: "気分とひとこと。記録はその日の干支と一緒に保存されます。" },
    {
      title: "あなたの吉日を見つける",
      body: "数週間記録すると、本当に自分に合う日と、それを支える日数がわかります。"
    },
    {
      title: "相談する",
      body: "恋愛・仕事・家族の悩みを AI に。チャートとあなた自身の記録をもとに答えます。"
    }
  ]
};

export const daysCopy = { zh, en, ja };
