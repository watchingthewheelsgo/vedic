import { useClerk, useUser } from "@clerk/clerk-react";
import {
  ArrowLeft,
  CreditCard,
  Crown,
  Download,
  Eye,
  ExternalLink,
  FileText,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  Settings,
  ShieldCheck,
  Sparkles
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { AccountAvatar } from "../components/AccountAvatar";
import { AccountCenter } from "../components/AccountCenter";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { useI18n } from "../i18n/provider";
import { cn } from "../lib/cn";
import { formatDuration } from "../lib/pipeline";
import type {
  AccountProfileResponse,
  AdminSessionListResponse,
  AdminSessionSummary,
  BillingAccountResponse,
  BillingPlanResponse
} from "../../shared/domain";
import { StatusBadge, formatDateTime } from "./AdminSessions";

export function Account() {
  const navigate = useNavigate();
  const { openUserProfile, signOut } = useClerk();
  const { user } = useUser();
  const { t } = useI18n();
  const [profile, setProfile] = useState<AccountProfileResponse | null>(null);
  const [sessions, setSessions] = useState<AdminSessionListResponse | null>(null);
  const [billing, setBilling] = useState<BillingAccountResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [downloadingId, setDownloadingId] = useState("");
  const [billingAction, setBillingAction] = useState<"checkout" | "portal" | "">("");

  const displayName =
    user?.fullName ||
    user?.username ||
    user?.primaryEmailAddress?.emailAddress ||
    t("account.defaultName");
  const email = user?.primaryEmailAddress?.emailAddress ?? profile?.email ?? t("account.noEmail");
  const initials = useMemo(() => initialsFor(displayName), [displayName]);

  const load = useCallback(
    async (options: { quiet?: boolean } = {}) => {
      setError("");
      if (options.quiet) setRefreshing(true);
      else setLoading(true);
      try {
        const [profileResult, sessionResult, billingResult] = await Promise.all([
          api.getMe(),
          api.listMySessions(),
          api.getBillingAccount()
        ]);
        setProfile(profileResult);
        setSessions(sessionResult);
        setBilling(billingResult);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : t("account.page.error"));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [t]
  );

  useEffect(() => {
    void load();
  }, [load]);

  async function downloadPdf(sessionId: string) {
    setError("");
    setDownloadingId(sessionId);
    try {
      await api.downloadReportPdf(sessionId);
      await load({ quiet: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("account.page.downloadError"));
    } finally {
      setDownloadingId("");
    }
  }

  async function startCheckout(plan: BillingPlanResponse) {
    setError("");
    setBillingAction("checkout");
    try {
      const checkout = await api.createBillingCheckout({ planKey: plan.key });
      window.location.assign(checkout.checkoutUrl);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("account.billing.checkoutError"));
      setBillingAction("");
    }
  }

  async function openBillingPortal() {
    setError("");
    setBillingAction("portal");
    try {
      const portal = await api.createBillingPortal();
      window.location.assign(portal.portalUrl);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("account.billing.portalError"));
      setBillingAction("");
    }
  }

  const reports = sessions?.sessions ?? [];
  const completed = reports.filter((item) => item.status === "completed").length;
  const running = reports.filter((item) =>
    ["queued", "running", "stalled", "validation"].includes(item.status)
  ).length;

  return (
    <div className="min-h-screen bg-cream-2 text-ink">
      <header className="border-b border-gold/25 bg-cream/95 px-5 py-4 backdrop-blur-lg sm:px-8">
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            title={t("common.back")}
            onClick={() => navigate("/")}
          >
            <ArrowLeft size={17} />
          </Button>
          <button className="brand-logo border-0 bg-transparent" onClick={() => navigate("/")}>
            Veda<span>Light</span>
          </button>
          <div className="flex-1" />
          <LanguageSwitcher />
          <AccountCenter compact />
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-[1180px] gap-5 px-5 py-6 sm:px-8 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="flex flex-col gap-5">
          <section className="relative overflow-hidden rounded-lg border border-gold/20 bg-night px-5 py-5 text-cream shadow-[0_20px_60px_rgba(44,31,15,0.18)]">
            <div className="pointer-events-none absolute -right-16 -top-20 size-44 rounded-full bg-gold/18 blur-3xl" />
            <div className="pointer-events-none absolute -bottom-20 left-6 size-36 rounded-full bg-green/10 blur-3xl" />

            <div className="relative flex items-start gap-4">
              <AccountAvatar imageUrl={user?.imageUrl} initials={initials} size="xl" showStatus />
              <div className="min-w-0 flex-1">
                <div className="truncate text-lg font-semibold tracking-normal text-cream">
                  {displayName}
                </div>
                <div className="mt-1 truncate text-sm text-cream/55">{email}</div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge variant="gold">{t("account.signedIn")}</Badge>
                  {profile?.isAdmin && (
                    <Badge className="border-green/35 bg-green/15 text-green" variant="done">
                      {t("account.page.adminBadge")}
                    </Badge>
                  )}
                </div>
              </div>
            </div>

            <div className="relative mt-5 grid gap-2">
              <AccountAction
                icon={<Settings size={15} />}
                title={t("account.manageProfile")}
                body={t("account.manageProfileBody")}
                onClick={() => openUserProfile()}
                dark
              />
              {profile?.isAdmin && (
                <AccountAction
                  icon={<ShieldCheck size={15} />}
                  title={t("account.page.adminTitle")}
                  body={t("account.page.adminBody")}
                  onClick={() => navigate("/admin/sessions")}
                  dark
                />
              )}
              <AccountAction
                danger
                dark
                icon={<LockKeyhole size={15} />}
                title={t("account.signOut")}
                body={t("account.page.signOutBody")}
                onClick={() => void signOut({ redirectUrl: "/" })}
              />
            </div>
          </section>

          <section className="rounded-lg border border-gold/25 bg-cream px-5 py-5 shadow-[0_18px_48px_rgba(44,31,15,0.06)]">
            <div className="mb-4 text-[10px] uppercase tracking-[2.2px] text-gold">
              {t("account.page.privateSpace")}
            </div>
            <div className="grid grid-cols-3 gap-3">
              <Metric label={t("account.page.total")} value={reports.length} />
              <Metric label={t("account.page.completed")} value={completed} />
              <Metric label={t("account.page.running")} value={running} />
            </div>
            <p className="mt-4 text-sm leading-[1.7] text-body">{t("account.page.privacyNote")}</p>
          </section>

          <BillingCard
            billing={billing}
            busy={billingAction}
            onCheckout={(plan) => void startCheckout(plan)}
            onPortal={() => void openBillingPortal()}
          />
        </aside>

        <section className="rounded-lg border border-gold/25 bg-cream shadow-[0_18px_48px_rgba(44,31,15,0.07)]">
          <div className="flex flex-col gap-3 border-b border-gold/20 px-5 py-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[2.2px] text-gold">
                {t("account.page.libraryEyebrow")}
              </div>
              <h1 className="mt-1 text-2xl font-semibold tracking-normal">
                {t("account.page.libraryTitle")}
              </h1>
              <p className="mt-1 text-sm text-muted">{t("account.page.libraryBody")}</p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void load({ quiet: true })}
                disabled={refreshing}
              >
                {refreshing ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <RefreshCw size={14} />
                )}
                {t("account.page.refresh")}
              </Button>
              <Button size="sm" onClick={() => navigate("/new")}>
                <Sparkles size={14} />
                {t("account.page.newReading")}
              </Button>
            </div>
          </div>

          {error && (
            <div className="mx-5 mt-5 rounded-md border border-red/30 bg-red/10 px-4 py-3 text-sm text-red">
              {error}
            </div>
          )}

          {loading ? (
            <div className="grid min-h-[420px] place-items-center text-muted">
              <div className="text-center">
                <LoaderCircle className="mx-auto size-8 animate-spin text-gold" />
                <p className="mt-2 text-sm">{t("account.page.loading")}</p>
              </div>
            </div>
          ) : reports.length === 0 ? (
            <EmptyReports onStart={() => navigate("/new")} />
          ) : (
            <div className="divide-y divide-gold/15">
              {reports.map((session) => (
                <ReportRow
                  key={session.sessionId}
                  session={session}
                  downloading={downloadingId === session.sessionId}
                  onOpen={() => navigate(`/session/${encodeURIComponent(session.sessionId)}`)}
                  onDownload={() => void downloadPdf(session.sessionId)}
                />
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function AccountAction({
  icon,
  title,
  body,
  danger = false,
  dark = false,
  onClick
}: {
  icon: ReactNode;
  title: string;
  body: string;
  danger?: boolean;
  dark?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center gap-3 rounded-md px-3 py-3 text-left transition focus:outline-none focus:ring-4 focus:ring-gold/15",
        dark
          ? danger
            ? "bg-cream/5 hover:bg-red/15"
            : "bg-cream/5 hover:bg-cream/10"
          : danger
            ? "hover:bg-red/10"
            : "hover:bg-gold/10"
      )}
      onClick={onClick}
    >
      <span
        className={cn(
          "grid size-8 shrink-0 place-items-center rounded-full border",
          danger
            ? "border-red/30 bg-red/10 text-red"
            : dark
              ? "border-gold/20 bg-gold/10 text-gold"
              : "border-gold/25 bg-cream-2 text-gold-dim"
        )}
      >
        {icon}
      </span>
      <span className="min-w-0">
        <span
          className={cn(
            "block text-sm font-semibold",
            danger ? "text-red" : dark ? "text-cream" : "text-ink"
          )}
        >
          {title}
        </span>
        <span className={cn("block text-xs leading-[1.45]", dark ? "text-cream/55" : "text-muted")}>
          {body}
        </span>
      </span>
    </button>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-gold/20 bg-cream-2 px-3 py-3">
      <div className="text-2xl font-light leading-none tracking-normal">{value}</div>
      <div className="mt-1 text-[10px] uppercase tracking-[1.5px] text-muted">{label}</div>
    </div>
  );
}

function BillingCard({
  billing,
  busy,
  onCheckout,
  onPortal
}: {
  billing: BillingAccountResponse | null;
  busy: "checkout" | "portal" | "";
  onCheckout: (plan: BillingPlanResponse) => void;
  onPortal: () => void;
}) {
  const { t } = useI18n();
  if (!billing) {
    return (
      <section className="rounded-lg border border-gold/25 bg-night px-5 py-5 text-cream shadow-[0_18px_48px_rgba(44,31,15,0.09)]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-[10px] uppercase tracking-[2.2px] text-gold">
              {t("account.billing.eyebrow")}
            </div>
            <h2 className="mt-1 text-lg font-semibold tracking-normal">
              {t("account.billing.title")}
            </h2>
          </div>
          <span className="grid size-9 place-items-center rounded-full border border-gold/25 bg-gold/10 text-gold">
            <LoaderCircle className="size-4 animate-spin" />
          </span>
        </div>
        <p className="mt-4 text-sm text-cream/65">{t("common.loading")}</p>
      </section>
    );
  }

  const preferredPlan =
    billing.plans.find((plan) => plan.key === "pro_monthly" && plan.productIdConfigured) ??
    billing.plans.find((plan) => plan.productIdConfigured) ??
    null;
  const subscription = billing.subscription ?? null;
  const isActive = billing.hasActiveEntitlement;
  const isAdmin = billing.entitlement === "admin";
  const canCheckout = Boolean(billing.configured && preferredPlan && !isActive);
  const planName = subscription?.planKey
    ? planLabel(subscription.planKey, t)
    : preferredPlan
      ? planLabel(preferredPlan.key, t)
      : t("account.billing.plan.free");

  return (
    <section className="rounded-lg border border-gold/25 bg-night px-5 py-5 text-cream shadow-[0_18px_48px_rgba(44,31,15,0.09)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[2.2px] text-gold">
            {t("account.billing.eyebrow")}
          </div>
          <h2 className="mt-1 text-lg font-semibold tracking-normal">
            {t("account.billing.title")}
          </h2>
        </div>
        <span className="grid size-9 place-items-center rounded-full border border-gold/25 bg-gold/10 text-gold">
          {isAdmin ? (
            <ShieldCheck size={17} />
          ) : isActive ? (
            <Crown size={17} />
          ) : (
            <CreditCard size={17} />
          )}
        </span>
      </div>

      <div className="mt-4 rounded-md border border-gold/20 bg-cream/5 px-4 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={isActive ? "gold" : "neutral"}>
            {isAdmin
              ? t("account.billing.status.admin")
              : isActive
                ? t("account.billing.status.active")
                : t("account.billing.status.free")}
          </Badge>
          {billing.testMode && <Badge variant="done">{t("account.billing.testMode")}</Badge>}
        </div>
        <div className="mt-3 text-xl font-semibold tracking-normal">{planName}</div>
        <p className="mt-2 text-sm leading-[1.65] text-cream/70">
          {isAdmin
            ? t("account.billing.adminBody")
            : isActive
              ? t("account.billing.activeBody")
              : t("account.billing.freeBody")}
        </p>
        {subscription?.currentPeriodEnd && (
          <div className="mt-3 text-xs text-cream/55">
            {t("account.billing.renews")} {formatDateTime(subscription.currentPeriodEnd)}
          </div>
        )}
      </div>

      <div className="mt-4 grid gap-2">
        {isActive && billing.canManageBilling ? (
          <Button
            variant="outline"
            className="border-gold/60 text-gold hover:bg-gold/10"
            onClick={onPortal}
            disabled={busy === "portal"}
          >
            {busy === "portal" ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <ExternalLink size={14} />
            )}
            {t("account.billing.manage")}
          </Button>
        ) : (
          <Button
            onClick={() => preferredPlan && onCheckout(preferredPlan)}
            disabled={!canCheckout || busy === "checkout"}
          >
            {busy === "checkout" ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <CreditCard size={14} />
            )}
            {t("account.billing.upgrade")}
          </Button>
        )}
        {!billing.configured && (
          <p className="text-xs leading-[1.55] text-cream/55">{t("account.billing.notReady")}</p>
        )}
      </div>
    </section>
  );
}

function ReportRow({
  session,
  downloading,
  onOpen,
  onDownload
}: {
  session: AdminSessionSummary;
  downloading: boolean;
  onOpen: () => void;
  onDownload: () => void;
}) {
  const { t } = useI18n();
  return (
    <article className="grid gap-4 px-5 py-5 transition hover:bg-gold/5 lg:grid-cols-[minmax(0,1fr)_180px_160px] lg:items-center">
      <div className="min-w-0">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <StatusBadge status={session.status} />
          {session.hasPdf && <Badge variant="done">{t("account.page.pdfReady")}</Badge>}
        </div>
        <button
          type="button"
          className="block max-w-full truncate text-left font-mono text-sm font-semibold text-ink transition hover:text-gold-dim"
          onClick={onOpen}
        >
          {session.sessionId}
        </button>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
          <span>{session.subject?.birthPlace ?? t("account.page.noPlace")}</span>
          <span>{compact([session.subject?.birthDate, session.subject?.birthTime])}</span>
          <span>{formatDateTime(session.updatedAt)}</span>
        </div>
      </div>

      <div>
        <div className="mb-1 flex justify-between text-[11px] text-muted">
          <span>{session.progress.percent}%</span>
          <span>
            {session.progress.completed}/{session.progress.total || 0}
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-cream-3">
          <div
            className={cn(
              "h-full rounded-full",
              session.status === "failed"
                ? "bg-red"
                : session.status === "completed"
                  ? "bg-green"
                  : "bg-gold"
            )}
            style={{ width: `${Math.min(100, Math.max(0, session.progress.percent))}%` }}
          />
        </div>
        <div className="mt-1 text-xs text-muted">{formatDuration(session.durationSeconds)}</div>
      </div>

      <div className="flex gap-2 lg:justify-end">
        <Button variant="outline" size="sm" onClick={onOpen}>
          <Eye size={14} />
          {t("account.page.open")}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          title={t("account.page.download")}
          disabled={!session.hasPdf || downloading}
          onClick={onDownload}
        >
          {downloading ? <LoaderCircle className="size-4 animate-spin" /> : <Download size={15} />}
        </Button>
      </div>
    </article>
  );
}

function EmptyReports({ onStart }: { onStart: () => void }) {
  const { t } = useI18n();
  return (
    <div className="grid min-h-[420px] place-items-center px-6 text-center">
      <div className="max-w-[420px]">
        <div className="mx-auto mb-4 grid size-12 place-items-center rounded-full border border-gold/25 bg-gold/10 text-gold-dim">
          <FileText size={20} />
        </div>
        <h2 className="text-xl font-semibold tracking-normal">{t("account.page.emptyTitle")}</h2>
        <p className="mt-2 text-sm leading-[1.7] text-body">{t("account.page.emptyBody")}</p>
        <Button className="mt-5" onClick={onStart}>
          <Sparkles size={15} />
          {t("account.page.newReading")}
        </Button>
      </div>
    </div>
  );
}

function initialsFor(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].slice(0, 2);
  return `${parts[0][0]}${parts[1][0]}`;
}

function compact(values: Array<string | null | undefined>) {
  return values.filter(Boolean).join(" · ") || "-";
}

function planLabel(planKey: string, t: (key: string) => string) {
  if (planKey === "pro_monthly") return t("account.billing.plan.proMonthly");
  if (planKey === "pro_yearly") return t("account.billing.plan.proYearly");
  if (planKey === "single_report") return t("account.billing.plan.singleReport");
  return planKey;
}
