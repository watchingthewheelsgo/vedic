import { AiAllowanceProvider } from "./AiAllowance";
import { useRef, useEffect, useCallback, type ReactNode } from "react";
import { NavLink, Link, Outlet, useLocation } from "react-router-dom";
import { Sun, NotebookPen, Sparkles, Orbit, CalendarDays, Compass } from "lucide-react";
import { useUser } from "@clerk/clerk-react";
import { AccountAvatar } from "./AccountAvatar";
import { OnboardingGate } from "./OnboardingGate";
import { AtlasLauncher, AtlasPanel, AtlasProvider, useAtlas } from "./Atlas";
import { useI18n } from "../i18n/provider";
import { DraftContext } from "../lib/workspace-draft";
import { workspaceCopy } from "../lib/workspace";
import { daysCopy } from "../lib/days-copy";
import { uniqueCharts } from "../lib/atlas";

export function WorkspaceLayout() {
  return (
    <AiAllowanceProvider>
      <AtlasProvider>
        <WorkspaceShell />
      </AtlasProvider>
    </AiAllowanceProvider>
  );
}

function WorkspaceShell() {
  const { locale } = useI18n();
  const w = workspaceCopy[locale];
  const d = daysCopy[locale];
  const location = useLocation();
  const onAsk = location.pathname.startsWith("/app/ask");
  const { hasChart } = useAtlas();
  // Chart creation, existing charts and account settings stay reachable without a chart.
  const needsOnboarding =
    hasChart === false && !/^\/app\/(charts\/.+|settings)/.test(location.pathname);
  const dirty = useRef(false);
  const setDirty = useCallback((value: boolean) => {
    dirty.current = value;
  }, []);
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (dirty.current) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);
  const links = [
    { to: "/app", label: w.today, icon: Sun, end: true, mobile: true },
    {
      to: "/app/days",
      label: d.nav.days,
      short: d.nav.daysShort,
      icon: CalendarDays,
      mobile: true
    },
    { to: "/app/records", label: d.nav.journal, icon: NotebookPen, mobile: false },
    { to: "/app/charts", label: w.readings, icon: Orbit, mobile: true, sidebar: false },
    { to: "/app/ask", label: d.nav.ask, icon: Sparkles, mobile: true },
    { to: "/app/discover", label: d.nav.discover, icon: Compass, mobile: true }
  ];
  const current = location.pathname.startsWith("/app/settings")
    ? w.settings
    : (links.find((item) =>
        item.end ? location.pathname === item.to : location.pathname.startsWith(item.to)
      )?.label ?? w.readings);
  const nav = (mobile = false): ReactNode =>
    links
      .filter((item) => (mobile ? item.mobile : item.sidebar !== false))
      .map(({ to, label, short, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            `${mobile ? "flex min-h-14 flex-1 flex-col items-center justify-center gap-1 text-[11px]" : "flex h-11 items-center gap-3 rounded-xl px-3.5 text-[14px]"} transition-colors ${isActive ? (mobile ? "text-cream" : "bg-night-3 text-cream") : "text-cream/50 hover:bg-white/[0.04] hover:text-cream"}`
          }
        >
          <Icon size={mobile ? 20 : 18} strokeWidth={1.6} />
          <span className={mobile ? "max-w-[72px] truncate" : undefined}>
            {mobile && short ? short : label}
          </span>
        </NavLink>
      ));
  return (
    <DraftContext.Provider
      value={{ setDirty, confirmLeave: () => !dirty.current || window.confirm(w.discard) }}
    >
      <div
        className="workspace-layout min-h-dvh bg-night text-cream"
        onClickCapture={(event) => {
          const anchor = (event.target as HTMLElement).closest("a[href]");
          if (
            anchor &&
            dirty.current &&
            anchor.getAttribute("href") !== location.pathname + location.search &&
            !window.confirm(w.discard)
          ) {
            event.preventDefault();
            event.stopPropagation();
          }
        }}
      >
        <a
          href="#workspace-content"
          className="sr-only focus:not-sr-only focus:fixed focus:z-[100] focus:bg-night focus:p-4"
        >
          {current}
        </a>
        <aside className="fixed inset-y-0 left-0 z-40 hidden w-[248px] flex-col border-r border-white/[0.07] bg-night px-3 pb-4 pt-7 lg:flex">
          <Link to="/app" className="brand-logo mb-9 px-3">
            Sign Atlas
          </Link>
          <nav aria-label={w.space} className="space-y-0.5">
            {nav()}
          </nav>
          <SidebarReadings />
          <div className="mt-auto pt-6">
            <SidebarAccount />
          </div>
        </aside>

        <div className="lg:pl-[248px]">
          <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-3 border-b border-white/[0.07] bg-night/90 px-4 backdrop-blur-xl lg:hidden">
            <Link to="/app" className="brand-logo text-[20px]">
              Sign Atlas
            </Link>
            <Link to="/app/settings" aria-label={w.settings}>
              <AccountBadge size="sm" />
            </Link>
          </header>
          <main id="workspace-content" className="@container min-w-0 pb-28 lg:pb-12">
            <Outlet />
          </main>
        </div>

        {!onAsk && !needsOnboarding && (
          <>
            <AtlasPanel />
            <AtlasLauncher />
          </>
        )}
        {needsOnboarding && <OnboardingGate />}

        <nav
          aria-label={w.space}
          className="fixed inset-x-0 bottom-0 z-40 flex border-t border-white/10 bg-night/95 px-1 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
        >
          {nav(true)}
        </nav>
      </div>
    </DraftContext.Provider>
  );
}

function useDisplayName() {
  const { user } = useUser();
  return user?.fullName || user?.username || user?.primaryEmailAddress?.emailAddress || "";
}

function AccountBadge({ size = "sm" }: { size?: "sm" | "md" }) {
  const { user } = useUser();
  const name = useDisplayName();
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const initials = parts.length > 1 ? `${parts[0][0]}${parts[1][0]}` : name.slice(0, 2);
  return <AccountAvatar imageUrl={user?.imageUrl} initials={initials || "·"} size={size} />;
}

/** The whole row opens the Account page (plan, language, feedback, sign out). */
function SidebarAccount() {
  const { locale } = useI18n();
  const w = workspaceCopy[locale];
  const { user } = useUser();
  const name = useDisplayName();
  return (
    <NavLink
      to="/app/settings"
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-2xl p-2 transition-colors ${isActive ? "bg-night-3" : "hover:bg-white/[0.04]"}`
      }
    >
      <AccountBadge />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-cream/90">{user?.firstName || name}</span>
        <span className="block truncate text-xs text-cream/40">{w.settings}</span>
      </span>
    </NavLink>
  );
}

/** The three traditions are first-class entries; recent charts sit under them. */
function SidebarReadings() {
  const { locale } = useI18n();
  const d = daysCopy[locale];
  const w = workspaceCopy[locale];
  const { charts } = useAtlas();
  const location = useLocation();
  const tab = new URLSearchParams(location.search).get("tab") ?? "vedic";
  const onCharts = location.pathname === "/app/charts";
  const traditions = [
    { key: "vedic", label: w.vedic, dot: "bg-gold" },
    { key: "bazi", label: w.baziName, dot: "bg-jade" },
    {
      key: "tarot",
      label: `${d.tarotTitle} · ${d.soon}`,
      dot: "border border-dashed border-cream/40"
    }
  ];
  const recent = uniqueCharts(charts).slice(0, 3);
  return (
    <div className="mt-7">
      <Link
        to="/app/charts"
        className="mb-1 block px-3.5 text-[11px] uppercase tracking-[0.14em] text-cream/35 hover:text-cream/70"
      >
        {w.readings}
      </Link>
      <ul className="space-y-0.5">
        {traditions.map((item) => (
          <li key={item.key}>
            <Link
              to={`/app/charts?tab=${item.key}`}
              className={`flex h-10 items-center gap-3 rounded-xl px-3.5 text-[14px] transition-colors ${onCharts && tab === item.key ? "bg-night-3 text-cream" : item.key === "tarot" ? "text-cream/35 hover:text-cream/60" : "text-cream/60 hover:bg-white/[0.04] hover:text-cream"}`}
            >
              <span className={`size-2 shrink-0 rounded-full ${item.dot}`} />
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
      {recent.length > 0 && (
        <ul className="mt-3 space-y-0.5 border-l border-white/[0.07] ml-[18px] pl-3">
          {recent.map((chart) => (
            <li key={chart.sessionId}>
              <Link
                to={`/app/charts/${encodeURIComponent(chart.sessionId)}`}
                className="flex min-h-8 items-center gap-2 text-[12.5px] text-cream/45 hover:text-cream"
              >
                <span className="truncate">{chart.label || chart.sessionId}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
