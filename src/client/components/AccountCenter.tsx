import { useClerk, useUser } from "@clerk/clerk-react";
import { FileText, LayoutDashboard, LogOut, Settings, UserRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

export function AccountCenter({ compact = false }: { compact?: boolean }) {
  const { signOut, openUserProfile } = useClerk();
  const { isLoaded, isSignedIn, user } = useUser();
  const navigate = useNavigate();
  const { t } = useI18n();
  const [isAdmin, setIsAdmin] = useState(false);

  const displayName =
    user?.fullName ||
    user?.username ||
    user?.primaryEmailAddress?.emailAddress ||
    t("account.defaultName");
  const email = user?.primaryEmailAddress?.emailAddress ?? t("account.noEmail");
  const initials = useMemo(() => initialsFor(displayName), [displayName]);
  const avatarUrl = user?.imageUrl;

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    let cancelled = false;
    void api
      .getMe()
      .then((profile) => {
        if (!cancelled) setIsAdmin(profile.isAdmin);
      })
      .catch(() => {
        if (!cancelled) setIsAdmin(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn]);

  if (!isLoaded || !isSignedIn) return null;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="group inline-flex h-10 items-center gap-2 rounded-full border border-gold/25 bg-cream-2 px-2.5 text-left text-ink shadow-[0_10px_28px_rgba(44,31,15,0.08)] transition hover:border-gold/45 hover:bg-gold/10 focus:outline-none focus:ring-4 focus:ring-gold/15"
          aria-label={t("account.open")}
        >
          <Avatar initials={initials} avatarUrl={avatarUrl} />
          {!compact && (
            <span className="hidden max-w-[150px] flex-col leading-tight sm:flex">
              <span className="truncate text-xs font-semibold text-ink">{displayName}</span>
              <span className="truncate text-[10.5px] text-muted">{t("account.center")}</span>
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(92vw,340px)] p-0" align="end">
        <div className="border-b border-gold/20 bg-cream-2 px-4 py-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <Avatar initials={initials} avatarUrl={avatarUrl} large />
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-ink">{displayName}</div>
                <div className="mt-0.5 truncate text-xs text-muted">{email}</div>
              </div>
            </div>
            <Badge variant="done">{t("account.signedIn")}</Badge>
          </div>
          <p className="m-0 text-[12.5px] leading-[1.65] text-body">{t("account.description")}</p>
        </div>

        <div className="grid gap-1 p-2">
          <button
            type="button"
            className="flex items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm text-ink transition hover:bg-gold/10 focus:outline-none focus:ring-4 focus:ring-gold/15"
            onClick={() => navigate("/account")}
          >
            <span className="grid size-8 place-items-center rounded-full border border-gold/25 bg-cream text-gold-dim">
              <UserRound size={15} />
            </span>
            <span className="min-w-0">
              <span className="block font-semibold">{t("account.center")}</span>
              <span className="block text-xs text-muted">{t("account.centerBody")}</span>
            </span>
          </button>
          <button
            type="button"
            className="flex items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm text-ink transition hover:bg-gold/10 focus:outline-none focus:ring-4 focus:ring-gold/15"
            onClick={() => openUserProfile()}
          >
            <span className="grid size-8 place-items-center rounded-full border border-gold/25 bg-cream text-gold-dim">
              <Settings size={15} />
            </span>
            <span className="min-w-0">
              <span className="block font-semibold">{t("account.manageProfile")}</span>
              <span className="block text-xs text-muted">{t("account.manageProfileBody")}</span>
            </span>
          </button>

          <button
            type="button"
            className="flex items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm text-ink transition hover:bg-gold/10 focus:outline-none focus:ring-4 focus:ring-gold/15"
            onClick={() => navigate("/account")}
          >
            <span className="grid size-8 place-items-center rounded-full border border-gold/25 bg-cream text-gold-dim">
              <FileText size={15} />
            </span>
            <span className="min-w-0">
              <span className="block font-semibold">{t("account.savedReadings")}</span>
              <span className="block text-xs text-muted">{t("account.savedReadingsBody")}</span>
            </span>
          </button>

          {isAdmin && (
            <button
              type="button"
              className="flex items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm text-ink transition hover:bg-gold/10 focus:outline-none focus:ring-4 focus:ring-gold/15"
              onClick={() => navigate("/admin/sessions")}
            >
              <span className="grid size-8 place-items-center rounded-full border border-gold/25 bg-cream text-gold-dim">
                <LayoutDashboard size={15} />
              </span>
              <span className="min-w-0">
                <span className="block font-semibold">{t("account.adminConsole")}</span>
                <span className="block text-xs text-muted">{t("account.adminConsoleBody")}</span>
              </span>
            </button>
          )}
        </div>

        <div className="border-t border-gold/20 p-2">
          <Button
            type="button"
            variant="ghost"
            className="w-full justify-start text-red hover:bg-red/10 hover:text-red"
            onClick={() => void signOut({ redirectUrl: "/" })}
          >
            <LogOut size={15} />
            {t("account.signOut")}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function Avatar({
  initials,
  avatarUrl,
  large = false
}: {
  initials: string;
  avatarUrl?: string;
  large?: boolean;
}) {
  const sizeClass = large ? "size-11" : "size-7";
  return (
    <span
      className={`${sizeClass} grid shrink-0 place-items-center overflow-hidden rounded-full border border-gold/35 bg-night text-[11px] font-semibold uppercase tracking-normal text-gold`}
    >
      {avatarUrl ? (
        <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
      ) : initials ? (
        initials
      ) : (
        <UserRound size={large ? 17 : 13} />
      )}
    </span>
  );
}

function initialsFor(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].slice(0, 2);
  return `${parts[0][0]}${parts[1][0]}`;
}
