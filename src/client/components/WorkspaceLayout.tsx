import { useRef, useEffect, useCallback, type ReactNode } from "react";
import { NavLink, Link, Outlet, useLocation } from "react-router-dom";
import { Sun, NotebookPen, Sparkles, Orbit, ArrowUpRight } from "lucide-react";
import { AccountCenter } from "./AccountCenter";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { useI18n } from "../i18n/provider";
import { DraftContext } from "../lib/workspace-draft";
import { workspaceCopy } from "../lib/workspace";

export function WorkspaceLayout() {
  const { locale } = useI18n();
  const w = workspaceCopy[locale];
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
    { to: "/app", label: w.today, icon: Sun, end: true },
    { to: "/app/records", label: w.records, icon: NotebookPen },
    { to: "/app/explore", label: w.explore, icon: Sparkles },
    { to: "/app/charts", label: w.charts, icon: Orbit }
  ];
  const current = location.pathname.startsWith("/app/settings")
    ? w.settings
    : (links.find((item) =>
        item.end ? location.pathname === item.to : location.pathname.startsWith(item.to)
      )?.label ?? w.charts);
  const nav = (mobile = false): ReactNode =>
    links.map(({ to, label, icon: Icon, end }) => (
      <NavLink
        key={to}
        to={to}
        end={end}
        className={({ isActive }) =>
          `${mobile ? "flex flex-1 flex-col items-center gap-1 py-3 text-[11px]" : "flex items-center gap-3 rounded-xl px-4 py-3 text-sm"} transition-colors ${isActive ? "bg-gold/10 text-gold-light" : "text-cream/60 hover:bg-white/5 hover:text-cream"}`
        }
      >
        <Icon size={mobile ? 19 : 18} strokeWidth={1.6} />
        {label}
      </NavLink>
    ));
  return (
    <DraftContext.Provider
      value={{ setDirty, confirmLeave: () => !dirty.current || window.confirm(w.discard) }}
    >
      <div
        className="workspace-layout min-h-dvh bg-[#100d16] text-cream"
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
        <aside className="fixed inset-y-0 left-0 z-40 hidden w-[224px] flex-col border-r border-white/8 bg-[#100c16] px-4 py-8 lg:flex">
          <Link to="/app" className="brand-logo mb-12 px-4">
            Sign <span>Atlas</span>
          </Link>
          <p className="mb-4 px-4 text-[10px] tracking-[.2em] text-cream/40">{w.personal}</p>
          <nav aria-label={w.space} className="space-y-2">
            {nav()}
          </nav>
          <div className="mt-auto space-y-4 px-4 pt-8">
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
        <div className="lg:pl-[224px]">
          <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-white/8 bg-[#100d16]/95 px-5 backdrop-blur-xl sm:px-8">
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
          <main id="workspace-content" className="min-w-0 pb-24 lg:pb-0">
            <Outlet />
          </main>
        </div>
        <nav
          aria-label={w.space}
          className="fixed inset-x-0 bottom-0 z-40 flex border-t border-white/10 bg-[#100c16]/98 px-2 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden"
        >
          {nav(true)}
        </nav>
      </div>
    </DraftContext.Provider>
  );
}
