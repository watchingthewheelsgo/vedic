import { openUpgradeRequest } from "../lib/feedback";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useUser } from "@clerk/clerk-react";
import { Link, useLocation } from "react-router-dom";
import { Mail, RefreshCw } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import type { AiAllowance } from "../../shared/domain";

const copy = {
  zh: {
    title: "方案与 AI 额度",
    free: "免费版",
    member: "会员版",
    admin: "管理员",
    body: "记事、心情、日历、基础回顾与已有内容始终免费。新的 AI 解读使用额度。",
    left: "本月剩余",
    units: "额度",
    reset: "补充时间",
    expires: "会员有效期",
    costs: "普通问答与简读每次 1 额度，完整报告每次 10 额度。生成失败退还额度。",
    upgrade: "申请升级",
    emailHelp:
      "在反馈窗口留下联系方式和升级需求，我们会回复方案与开通方式。提交申请不会自动扣款或开通会员。",
    memberHelp: "需要更多额度或续期，请在反馈窗口提交申请。",
    fallback: "也可以复制邮箱联系我们",
    copied: "邮箱已复制",
    copyError: "复制失败，请手动复制下方邮箱",
    error: "暂时无法加载额度",
    retry: "重试",
    exhausted: "本月 AI 额度已用完，记录和已有内容仍可使用。",
    quote: "本次 AI 生成消耗",
    unlimited: "内部使用",
    subject: "Sign Atlas 升级申请",
    request: "你好，我想了解 Sign Atlas 会员升级方案。",
    account: "账号",
    empty: "升级申请按人工回复确认，暂不自动续费。"
  },
  en: {
    title: "Plan & AI credits",
    free: "Free",
    member: "Member",
    admin: "Admin",
    body: "Notes, moods, calendar, basic reviews and saved content stay free. New AI interpretations use credits.",
    left: "Credits remaining",
    units: "credits",
    reset: "Refills",
    expires: "Membership ends",
    costs:
      "Questions and short readings cost 1 credit; a full report costs 10. Failed generations are refunded.",
    upgrade: "Request an upgrade",
    emailHelp:
      "Leave your contact and upgrade request in the feedback window. We will reply with plan details. Submitting does not charge you or activate membership.",
    memberHelp: "Request more credits or renewal through the feedback window.",
    fallback: "Or copy our email address",
    copied: "Email copied",
    copyError: "Copy failed. Please copy the address below manually.",
    error: "Could not load credits",
    retry: "Retry",
    exhausted: "Your monthly AI credits are used up. Records and saved content remain available.",
    quote: "This AI generation costs",
    unlimited: "Internal access",
    subject: "Sign Atlas upgrade request",
    request: "Hello, I would like to learn about upgrading my Sign Atlas membership.",
    account: "Account",
    empty: "Upgrades are reviewed manually. No automatic renewal."
  },
  ja: {
    title: "プランと AI クレジット",
    free: "無料プラン",
    member: "メンバー",
    admin: "管理者",
    body: "日記、気分、暦、基本的な振り返りと保存済みコンテンツは無料です。新しい AI 解釈にクレジットを使用します。",
    left: "今月の残り",
    units: "クレジット",
    reset: "補充日時",
    expires: "会員期限",
    costs: "質問と簡易解釈は1、完全レポートは10クレジット。生成に失敗した場合は返還されます。",
    upgrade: "アップグレードを申請",
    emailHelp:
      "フォームに連絡先とご希望を記入してください。確認後に返信します。自動課金はありません。",
    memberHelp: "追加クレジットや更新はフォームから申請してください。",
    fallback: "メールアドレスをコピー",
    copied: "コピーしました",
    copyError: "下記アドレスを手動でコピーしてください。",
    error: "クレジットを読み込めませんでした",
    retry: "再試行",
    exhausted:
      "今月の AI クレジットを使い切りました。記録と保存済みコンテンツは引き続き利用できます。",
    quote: "この AI 生成の消費量",
    unlimited: "内部利用",
    subject: "Sign Atlas アップグレード申請",
    request: "Sign Atlas の会員プランについて教えてください。",
    account: "アカウント",
    empty: "申請を確認後に開始します。自動更新はありません。"
  }
};

const Context = createContext<{
  allowance: AiAllowance | null;
  error: boolean;
  refresh: () => Promise<void>;
}>({ allowance: null, error: false, refresh: async () => {} });

export function AiAllowanceProvider({ children }: { children: ReactNode }) {
  const { user } = useUser();
  const { pathname } = useLocation();
  const [allowance, setAllowance] = useState<AiAllowance | null>(null);
  const [error, setError] = useState(false);
  const refresh = useCallback(async () => {
    try {
      const result = await api.getBillingAccount();
      setAllowance(result.aiAllowance ?? null);
      setError(!result.aiAllowance);
    } catch {
      setError(true);
    }
  }, []);
  useEffect(() => {
    setAllowance(null);
    void refresh();
  }, [user?.id, refresh]);
  useEffect(() => {
    const update = () => {
      void refresh();
    };
    window.addEventListener("ai-allowance-changed", update);
    window.addEventListener("focus", update);
    update();
    return () => {
      window.removeEventListener("ai-allowance-changed", update);
      window.removeEventListener("focus", update);
    };
  }, [refresh, pathname]);
  return <Context.Provider value={{ allowance, error, refresh }}>{children}</Context.Provider>;
}

export function AiAllowanceSummary() {
  const { allowance } = useContext(Context);
  const { locale } = useI18n();
  const c = copy[locale];
  if (!allowance) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/8 px-5 py-3 text-xs text-cream/65 sm:px-8">
      <span>
        {allowance.unlimited
          ? c.unlimited
          : `${c.left} ${allowance.remaining} / ${allowance.limit} ${c.units}`}
      </span>
      <Link to="/app/settings#billing" className="text-gold underline-offset-4 hover:underline">
        {c.title}
      </Link>
    </div>
  );
}

export function AiCostNotice({ report = false }: { report?: boolean }) {
  const { locale } = useI18n();
  const c = copy[locale];
  const { allowance } = useContext(Context);
  return (
    <p className="my-3 text-xs leading-6 text-cream/65">
      {report ? c.costs : `${c.quote} ${allowance?.standardCost ?? 1} ${c.units}`} ·{" "}
      <Link className="text-gold underline" to="/app/settings#billing">
        {c.title}
      </Link>
    </p>
  );
}

export function AiAllowanceCard() {
  const { allowance, error, refresh } = useContext(Context);
  const { locale } = useI18n();
  const c = copy[locale];
  const [notice, setNotice] = useState("");
  const email = "lizero.why@gmail.com";
  return (
    <section className="rounded-2xl border border-gold/25 bg-night p-5 text-cream sm:p-6">
      <h2 className="text-xl font-medium">{c.title}</h2>
      <p className="mt-3 text-sm leading-7 text-cream/70">{c.body}</p>
      {allowance ? (
        <div className="my-5 rounded-xl border border-white/10 bg-white/5 p-4">
          <p className="text-sm text-gold">{c[allowance.plan]}</p>
          <p className="mt-3 text-2xl tabular-nums">
            {allowance.unlimited ? c.unlimited : `${allowance.remaining} / ${allowance.limit}`}{" "}
            <span className="text-sm text-cream/65">{!allowance.unlimited && c.units}</span>
          </p>
          <p className="mt-2 text-xs text-cream/60">
            {c.reset}: {new Date(allowance.resetsAt).toLocaleString(locale, { timeZone: "UTC" })}{" "}
            (UTC)
          </p>
          {allowance.expiresAt && (
            <p className="mt-2 text-xs text-cream/60">
              {c.expires}: {new Date(allowance.expiresAt).toLocaleDateString(locale)}
            </p>
          )}
          {!allowance.unlimited && allowance.remaining === 0 && (
            <p className="mt-3 text-sm text-gold">{c.exhausted}</p>
          )}
        </div>
      ) : (
        <p className="my-5 text-sm text-cream/60" role="status">
          {error ? c.error : "…"}
        </p>
      )}
      {error && (
        <button
          type="button"
          onClick={() => void refresh()}
          className="mb-4 flex min-h-11 items-center gap-2 text-sm text-gold"
        >
          <RefreshCw size={14} />
          {c.retry}
        </button>
      )}
      <p className="mb-4 text-xs leading-6 text-cream/65">{c.costs}</p>
      <button
        type="button"
        onClick={openUpgradeRequest}
        className="flex min-h-11 items-center justify-center gap-2 rounded-xl bg-gold px-4 py-3 font-medium text-night hover:bg-gold-light"
      >
        <Mail size={16} />
        {c.upgrade}
      </button>
      <p className="mt-3 text-xs leading-6 text-cream/65">
        {allowance?.plan === "member" ? c.memberHelp : c.emailHelp} {c.empty}
      </p>
      <button
        type="button"
        className="mt-2 min-h-11 text-left text-xs text-gold underline"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(email);
            setNotice(c.copied);
          } catch {
            setNotice(c.copyError);
          }
        }}
      >
        {c.fallback}
      </button>
      <p className="break-all text-xs text-cream/65">{email}</p>
      <p role="status" className="mt-2 text-xs text-gold">
        {notice}
      </p>
    </section>
  );
}
