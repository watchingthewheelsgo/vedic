import { AiAllowanceProvider, AiAllowanceSummary } from "./AiAllowance";
import { useRef, useEffect, useCallback, type ReactNode } from "react";
import { NavLink, Link, Outlet, useLocation } from "react-router-dom";
import {
  Sun,
  NotebookPen,
  Sparkles,
  Orbit,
  ArrowUpRight,
  CalendarDays,
  Compass
} from "lucide-react";
import { AccountCenter } from "./AccountCenter";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { useI18n } from "../i18n/provider";
import { DraftContext } from "../lib/workspace-draft";
import { workspaceCopy } from "../lib/workspace";
import { daysCopy } from "../lib/days-copy";

export function WorkspaceLayout() {
  const { locale } = useI18n();
  const w = workspaceCopy[locale];
  const d = daysCopy[locale];
  const location = useLocation();
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
    { to: "/app/explore", label: d.nav.ask, icon: Sparkles, mobile: true },
    { to: "/app/charts", label: w.charts, icon: Orbit, mobile: true },
    { to: "/app/discover", label: d.nav.discover, icon: Compass, mobile: true }
  ];
  const current = location.pathname.startsWith("/app/settings")
    ? w.settings
    : (links.find((item) =>
        item.end ? location.pathname === item.to : location.pathname.startsWith(item.to)
      )?.label ?? w.charts);
  const nav = (mobile = false): ReactNode =>
    links
      .filter((item) => !mobile || item.mobile)
      .map(({ to, label, short, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            `${mobile ? "flex min-h-14 flex-1 flex-col items-center justify-center gap-1 text-[11px]" : "flex h-11 items-center gap-3 rounded-xl px-3.5 text-sm"} transition-colors ${isActive ? (mobile ? "text-gold-light" : "bg-white/[0.07] text-cream") : "text-cream/55 hover:bg-white/5 hover:text-cream"}`
          }
        >
          {({ isActive }) => (
            <>
              <Icon
                size={mobile ? 20 : 18}
                strokeWidth={1.6}
                className={isActive && !mobile ? "text-gold" : undefined}
              />
              <span className={mobile ? "max-w-[72px] truncate" : undefined}>
                {mobile && short ? short : label}
              </span>
            </>
          )}
        </NavLink>
      ));
  return (
    <AiAllowanceProvider>
      <DraftContext.Provider
        value={{ setDirty, confirmLeave: () => !dirty.current || window.confirm(w.discard) }}
      >
        <div
          className="workspace-layout min-h-dvh bg-[#0e0c13] bg-[radial-gradient(ellipse_70%_40%_at_60%_-10%,rgba(110,82,170,0.16),transparent_70%)] text-cream"
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
          <aside className="fixed inset-y-0 left-0 z-40 hidden w-[232px] flex-col border-r border-white/[0.07] bg-[#0c0a10]/90 px-3 py-7 backdrop-blur-xl lg:flex">
            <Link to="/app" className="brand-logo mb-10 px-3.5">
              Sign <span>Atlas</span>
            </Link>
            <nav aria-label={w.space} className="space-y-1">
              {nav()}
            </nav>
            <div className="mt-auto space-y-4 px-3.5 pt-8">
              <Link to="/app/settings" className="block text-sm text-cream/65 hover:text-gold">
                {w.settings}
              </Link>
              <Link
                to="/welcome"
                className="flex items-center gap-2 text-xs text-cream/50 hover:text-gold"
              >
                {w.website}
                <ArrowUpRight size={13} />
              </Link>
            </div>
          </aside>
          <div className="lg:pl-[232px]">
            <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-white/[0.07] bg-[#0e0c13]/85 px-5 backdrop-blur-xl sm:px-8">
              <Link to="/app" className="brand-logo lg:hidden">
                Sign <span>Atlas</span>
              </Link>
              <span className="hidden text-sm text-cream/60 lg:block">
                {w.space}
                <span className="mx-3 text-cream/25">/</span>
                {current}
              </span>
              <div className="flex items-center gap-2">
                <LanguageSwitcher />
                <AccountCenter compact />
              </div>
            </header>
            <AiAllowanceSummary />
            <main id="workspace-content" className="min-w-0 pb-28 lg:pb-0">
              <Outlet />
            </main>
          </div>
          <nav
            aria-label={w.space}
            className="fixed inset-x-0 bottom-0 z-40 flex border-t border-white/10 bg-[#0c0a10]/95 px-1 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
          >
            {nav(true)}
          </nav>
        </div>
      </DraftContext.Provider>
    </AiAllowanceProvider>
  );
}
