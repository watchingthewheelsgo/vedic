import { useI18n } from "../i18n/provider";

const copy = {
  zh: {
    title: "方法与来源",
    intro:
      "传统文化提供解释视角，你的生活经历始终是主角。我们将历法与星盘计算、文献整理和 AI 辅助表达分开看待。",
    vedic: "印度占星 · Jyotish",
    vedicBody:
      "Vedic 星盘使用 PyJHora 计算。解读规则参考 P. V. R. Narasimha Rao 的现代 Jyotish 教材，包括《Vedic Astrology: An Integrated Approach》和《Lessons on Vedic Astrology, Volume I》。",
    classical:
      "Brihat Parashara Hora Shastra、Brihat Jataka、Phaladeepika 和 Jaimini Sutras 已列入来源目录，但具体版本与原文定位仍待核定，不能视为每份报告已经逐条引用的原典。",
    bazi: "东方八字 · 三种方法",
    baziBody:
      "八字分析方法整理自《穷通宝鉴》的调候、《子平真诠评注》的格局与用神，以及《滴天髓》的气势、体用与中和。产品使用方法摘要，不提供这些书的全文，也不保证每次回答都有原文引句。",
    ai: "AI 与个人探索",
    aiBody:
      "记录心情与日常，再用不同传统提出反思问题。塔罗视角使用牌意与象征联想；它与 Vedic 星盘、八字历法是不同的方法，不互相充当验证。",
    limits:
      "计算结果可复现，不等于传统解释已经得到科学验证。AI 可能出错；日记中的相关性不代表因果关系。内容用于文化探索与自我反思，不保证未来、关系、财富或健康结果，也不能代替专业意见。",
    textbook: "Jyotish 教材（PDF）",
    lessons: "课程讲义（PDF）",
    software: "计算库 PyJHora"
  },
  en: {
    title: "Methods & sources",
    intro:
      "Traditional frameworks offer perspectives; your lived experience stays at the center. We distinguish calendar and chart calculations, source summaries, and AI-assisted explanations.",
    vedic: "Indian astrology · Jyotish",
    vedicBody:
      "Vedic charts are calculated with PyJHora. Interpretation rules reference modern Jyotish teaching by P. V. R. Narasimha Rao, including Vedic Astrology: An Integrated Approach and Lessons on Vedic Astrology, Volume I.",
    classical:
      "Brihat Parashara Hora Shastra, Brihat Jataka, Phaladeepika and Jaimini Sutras are listed in our source catalog, but editions and passage locations remain unverified. Their listing does not mean every report directly cites these original texts.",
    bazi: "Chinese BaZi · Three approaches",
    baziBody:
      "Our BaZi methodology summarizes seasonal balance from Qiong Tong Bao Jian, structures and useful elements from Zi Ping Zhen Quan Ping Zhu, and balance and flow from Di Tian Sui. We use method summaries, not full-text editions, and do not promise a source quotation in every answer.",
    ai: "AI & personal reflection",
    aiBody:
      "Record moods and everyday events, then explore questions through different traditions. The Tarot lens uses card symbolism and associations; it is distinct from Vedic charts and the BaZi calendar. These methods do not validate one another.",
    limits:
      "Reproducible calculations do not establish scientific validity for traditional interpretations. AI can make mistakes, and correlations in your journal do not establish causation. Content is for cultural exploration and reflection, does not guarantee future, relationship, financial or health outcomes, and cannot replace professional advice.",
    textbook: "Jyotish textbook (PDF)",
    lessons: "Class notes (PDF)",
    software: "PyJHora calculation library"
  },
  ja: {
    title: "方法と参考文献",
    intro:
      "伝統は物事を見る視点を提供します。中心にあるのは、あなた自身の経験です。暦・チャートの計算、文献の要約、AI による説明を区別しています。",
    vedic: "インド占星術 · Jyotish",
    vedicBody:
      "ヴェーダのチャートは PyJHora で計算します。解釈の規則は P. V. R. Narasimha Rao の現代の教材 Vedic Astrology: An Integrated Approach と Lessons on Vedic Astrology, Volume I などを参照しています。",
    classical:
      "Brihat Parashara Hora Shastra、Brihat Jataka、Phaladeepika、Jaimini Sutras は文献一覧に登録されていますが、版と該当箇所は未確定です。すべてのレポートがこれらの原典を直接引用するという意味ではありません。",
    bazi: "四柱推命 · 三つの方法",
    baziBody:
      "四柱推命の方法は『窮通宝鑑』の調候、『子平真詮評注』の格局・用神、『滴天髄』の気勢・体用・中和を要約しています。全文を提供するものではなく、各回答に原文引用があることを保証しません。",
    ai: "AI と日々の内省",
    aiBody:
      "気分や出来事を記録し、異なる伝統の視点から問いを考えます。タロットの視点はカードの象徴や連想を使います。ヴェーダのチャートや四柱推命の暦とは異なる方法であり、互いの正しさを証明するものではありません。",
    limits:
      "計算の再現性は、伝統的な解釈の科学的妥当性を示すものではありません。AI は誤ることがあり、日記の相関関係は因果関係ではありません。文化の探究と内省のための内容であり、未来・人間関係・財産・健康の結果を保証せず、専門家の助言に代わるものでもありません。",
    textbook: "Jyotish 教材（PDF）",
    lessons: "講義ノート（PDF）",
    software: "計算ライブラリ PyJHora"
  }
};

export function Methodology() {
  const { locale } = useI18n();
  const c = copy[locale];
  return (
    <section
      id="sources"
      aria-labelledby="sources-title"
      className="scroll-mt-24 border-y border-gold/20 px-6 py-16 sm:px-10"
    >
      <div className="mx-auto max-w-[1100px]">
        <h2 id="sources-title" className="text-3xl font-medium text-cream">
          {c.title}
        </h2>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-body">{c.intro}</p>
        <div className="mt-8 grid gap-8 md:grid-cols-3">
          {[
            [c.vedic, c.vedicBody],
            [c.bazi, c.baziBody],
            [c.ai, c.aiBody]
          ].map(([title, body]) => (
            <article key={title}>
              <h3 className="text-lg font-medium text-gold">{title}</h3>
              <p className="mt-3 text-sm leading-7 text-body">{body}</p>
            </article>
          ))}
        </div>
        <div className="mt-8 flex flex-wrap gap-x-6 gap-y-3 text-sm text-gold">
          {[
            [c.textbook, "https://www.vedicastrologer.org/articles/vedic_astro_textbook.pdf"],
            [c.lessons, "https://vedicastrologer.org/classes/book1-for-CD.pdf"],
            [c.software, "https://github.com/naturalstupid/PyJHora"]
          ].map(([label, href]) => (
            <a
              key={href}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-4"
            >
              {label} ↗
            </a>
          ))}
        </div>
        <p className="mt-6 text-sm leading-7 text-body">{c.classical}</p>
        <p className="mt-6 rounded-lg border border-gold/20 bg-gold/5 p-5 text-sm leading-7 text-cream/80">
          {c.limits}
        </p>
      </div>
    </section>
  );
}
