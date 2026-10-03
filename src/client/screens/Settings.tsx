import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useClerk, useUser } from "@clerk/clerk-react";
import {
  ArrowUpRight,
  ChevronRight,
  Globe2,
  Inbox,
  LogOut,
  MessageSquare,
  PencilLine,
  ShieldCheck,
  Sparkles
} from "lucide-react";
import { api } from "../api";
import { AccountAvatar } from "../components/AccountAvatar";
import { useAiAllowance } from "../components/AiAllowance";
import { useI18n } from "../i18n/provider";
import { LOCALES, localeNames } from "../i18n/messages";
import type { LocaleCode } from "../i18n/messages";
import { openFeedback, openUpgradeRequest } from "../lib/feedback";

const copy: Record<
  LocaleCode,
  {
    title: string;
    edit: string;
    signOut: string;
    plan: string;
    left: string;
    requestMore: string;
    preferences: string;
    language: string;
    support: string;
    feedback: string;
    feedbackBody: string;
    website: string;
    admin: string;
    adminConsole: string;
    feedbackInbox: string;
    privacy: string;
  }
> = {
  en: {
    title: "Account",
    edit: "Edit profile",
    signOut: "Sign out",
    plan: "Plan & credits",
    left: "credits left this month",
    requestMore: "Request more",
    preferences: "Preferences",
    language: "Language",
    support: "Help",
    feedback: "Send feedback",
    feedbackBody: "An idea, a problem, or something you'd love to see",
    website: "Visit the Sign Atlas website",
    admin: "Admin",
    adminConsole: "Admin console",
    feedbackInbox: "Feedback inbox",
    privacy:
      "Your charts and journal are private to your account. AI is used only when you ask for it."
  },
  zh: {
    title: "账户",
    edit: "编辑资料",
    signOut: "退出登录",
    plan: "方案与额度",
    left: "本月剩余额度",
    requestMore: "申请更多",
    preferences: "偏好设置",
    language: "语言",
    support: "帮助",
    feedback: "发送反馈",
    feedbackBody: "想法、问题，或你希望看到的功能",
    website: "访问 Sign Atlas 官网",
    admin: "管理",
    adminConsole: "管理后台",
    feedbackInbox: "反馈与升级申请",
    privacy: "你的命盘与日记只属于你的账户。只有在你主动使用时才会调用 AI。"
  },
  ja: {
    title: "アカウント",
    edit: "プロフィールを編集",
    signOut: "ログアウト",
    plan: "プランとクレジット",
    left: "今月の残りクレジット",
    requestMore: "追加を申請",
    preferences: "設定",
    language: "言語",
    support: "ヘルプ",
    feedback: "フィードバックを送る",
    feedbackBody: "アイデア、不具合、欲しい機能など",
    website: "Sign Atlas のウェブサイト",
    admin: "管理",
    adminConsole: "管理コンソール",
    feedbackInbox: "フィードバック受信箱",
    privacy: "チャートと日記はあなたのアカウント専用です。AI はあなたが使うときだけ動きます。"
  }
};

function initialsFor(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts.length > 1 ? `${parts[0][0]}${parts[1][0]}` : name.slice(0, 2);
}

export function Settings() {
  const { locale, localeTag, setLocale } = useI18n();
  const c = copy[locale];
  const navigate = useNavigate();
  const { user } = useUser();
  const { openUserProfile, signOut } = useClerk();
  const { allowance, copy: credits } = useAiAllowance();
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .getMe()
      .then((profile) => alive && setIsAdmin(profile.isAdmin))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const name =
    user?.fullName || user?.username || user?.primaryEmailAddress?.emailAddress || c.title;
  const email = user?.primaryEmailAddress?.emailAddress;
  const share =
    allowance && !allowance.unlimited && allowance.limit > 0
      ? Math.max(0, Math.min(1, allowance.remaining / allowance.limit))
      : 1;

  return (
    <div className="mx-auto max-w-[720px] px-5 py-8 sm:px-8 sm:py-10">
      <h1 className="sr-only">{c.title}</h1>

      <section className="rise-in flex flex-col items-center text-center">
        <AccountAvatar
          imageUrl={user?.imageUrl}
          initials={initialsFor(name)}
          size="xl"
          className="size-20"
        />
        <p className="mt-4 font-display text-4xl leading-tight">{name}</p>
        {email && email !== name && <p className="mt-1 text-sm text-cream/50">{email}</p>}
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          <button
            type="button"
            onClick={() => openUserProfile()}
            className="inline-flex h-10 items-center gap-2 rounded-full bg-paper px-4 text-sm font-medium text-[#16130e]"
          >
            <PencilLine size={15} />
            {c.edit}
          </button>
          <button
            type="button"
            onClick={() => void signOut({ redirectUrl: "/" })}
            className="inline-flex h-10 items-center gap-2 rounded-full border border-white/14 px-4 text-sm text-cream/75 hover:bg-white/[0.05]"
          >
            <LogOut size={15} />
            {c.signOut}
          </button>
        </div>
      </section>

      <section id="billing" className="surface mt-10 scroll-mt-20 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="eyebrow">{c.plan}</p>
            <p className="mt-2 font-display text-3xl leading-none">
              {allowance ? credits[allowance.plan] : "…"}
            </p>
          </div>
          <button
            type="button"
            onClick={openUpgradeRequest}
            className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-gold/40 px-3.5 text-xs text-gold-light hover:bg-gold/10"
          >
            <Sparkles size={13} />
            {c.requestMore}
          </button>
        </div>
        {allowance && (
          <div className="mt-6">
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="tabular-nums text-cream">
                {allowance.unlimited ? (
                  credits.unlimited
                ) : (
                  <>
                    <span className="text-2xl">{allowance.remaining}</span>
                    <span className="text-cream/45"> / {allowance.limit}</span>
                  </>
                )}
              </span>
              {!allowance.unlimited && <span className="text-cream/45">{c.left}</span>}
            </div>
            <div
              className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/[0.08]"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={allowance.limit}
              aria-valuenow={allowance.remaining}
            >
              <span
                className="block h-full origin-left rounded-full bg-linear-to-r from-gold to-gold-light transition-transform duration-700"
                style={{ transform: `scaleX(${share})` }}
              />
            </div>
            <p className="mt-3 text-xs leading-5 text-cream/45">
              {credits.costs} {credits.reset}:{" "}
              {new Date(allowance.resetsAt).toLocaleDateString(localeTag, { timeZone: "UTC" })}
            </p>
          </div>
        )}
      </section>

      <Group title={c.preferences}>
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
          <span className="flex items-center gap-3 text-[15px]">
            <Globe2 size={17} className="text-cream/50" />
            {c.language}
          </span>
          <div className="flex rounded-full bg-night p-1" role="radiogroup" aria-label={c.language}>
            {LOCALES.map((code) => (
              <button
                key={code}
                type="button"
                role="radio"
                aria-checked={locale === code}
                onClick={() => setLocale(code)}
                className={`h-8 rounded-full px-3.5 text-xs transition-colors ${locale === code ? "bg-paper text-[#16130e]" : "text-cream/60 hover:text-cream"}`}
              >
                {localeNames[code]}
              </button>
            ))}
          </div>
        </div>
      </Group>

      <Group title={c.support}>
        <Row
          icon={<MessageSquare size={17} />}
          label={c.feedback}
          hint={c.feedbackBody}
          onClick={openFeedback}
        />
        <Row icon={<ArrowUpRight size={17} />} label={c.website} to="/welcome" />
      </Group>

      {isAdmin && (
        <Group title={c.admin}>
          <Row
            icon={<ShieldCheck size={17} />}
            label={c.adminConsole}
            onClick={() => navigate("/admin/sessions")}
          />
          <Row
            icon={<Inbox size={17} />}
            label={c.feedbackInbox}
            onClick={() => navigate("/admin/feedback")}
          />
        </Group>
      )}

      <p className="mt-10 text-center text-xs leading-5 text-cream/35">{c.privacy}</p>
    </div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-8">
      <p className="eyebrow mb-2 px-1">{title}</p>
      <div className="divide-y divide-white/[0.06] overflow-hidden rounded-3xl border border-white/[0.08] bg-night-2">
        {children}
      </div>
    </section>
  );
}

function Row({
  icon,
  label,
  hint,
  onClick,
  to
}: {
  icon: ReactNode;
  label: string;
  hint?: string;
  onClick?: () => void;
  to?: string;
}) {
  const inner = (
    <>
      <span className="text-cream/50">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-[15px] text-cream">{label}</span>
        {hint && <span className="block truncate text-xs text-cream/45">{hint}</span>}
      </span>
      <ChevronRight size={16} className="text-cream/30" />
    </>
  );
  const className =
    "flex min-h-14 w-full items-center gap-3 px-5 py-3 text-left transition-colors hover:bg-white/[0.03]";
  return to ? (
    <Link to={to} className={className}>
      {inner}
    </Link>
  ) : (
    <button type="button" onClick={onClick} className={className}>
      {inner}
    </button>
  );
}
