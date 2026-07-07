import { useClerk, useUser } from "@clerk/clerk-react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  CreditCard,
  LayoutDashboard,
  LogOut,
  Settings,
  UserRound
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import { cn } from "../lib/cn";
import { AccountAvatar } from "./AccountAvatar";
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
          className={cn(
            "group inline-flex h-11 items-center gap-2 rounded-full border border-gold/25 bg-cream px-2.5 text-left text-ink shadow-[0_12px_30px_rgba(44,31,15,0.1)] transition hover:-translate-y-px hover:border-gold/45 hover:bg-cream-2 focus:outline-none focus:ring-4 focus:ring-gold/15",
            compact ? "pr-2.5" : "pr-3"
          )}
          aria-label={t("account.open")}
        >
          <AccountAvatar initials={initials} imageUrl={avatarUrl} size="sm" showStatus />
          {!compact && (
            <span className="hidden max-w-[150px] flex-col leading-tight sm:flex">
              <span className="truncate text-xs font-semibold text-ink">{displayName}</span>
              <span className="truncate text-[10.5px] text-muted">{t("account.center")}</span>
            </span>
          )}
          {!compact && (
            <ChevronDown
              size={14}
              className="hidden text-muted transition group-data-[state=open]:rotate-180 sm:block"
            />
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(92vw,380px)] overflow-hidden p-0" align="end">
        <div className="relative overflow-hidden border-b border-gold/20 bg-night px-4 py-4 text-cream">
          <div className="pointer-events-none absolute -right-14 -top-16 size-36 rounded-full bg-gold/18 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-20 left-8 size-32 rounded-full bg-green/10 blur-3xl" />
          <div className="relative mb-4 flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <AccountAvatar initials={initials} imageUrl={avatarUrl} size="lg" showStatus />
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-cream">{displayName}</div>
                <div className="mt-0.5 truncate text-xs text-cream/55">{email}</div>
              </div>
            </div>
            <Badge variant="gold">{t("account.signedIn")}</Badge>
          </div>
          <p className="relative m-0 text-[12.5px] leading-[1.65] text-cream/68">
            {t("account.description")}
          </p>
        </div>

        <div className="grid gap-1.5 bg-cream p-2">
          <AccountMenuAction
            icon={<UserRound size={17} />}
            title={t("account.center")}
            body={t("account.centerBody")}
            onClick={() => navigate("/account")}
          />
          <AccountMenuAction
            icon={<BookOpen size={17} />}
            title={t("account.savedReadings")}
            body={t("account.savedReadingsBody")}
            onClick={() => navigate("/account")}
          />
          <AccountMenuAction
            icon={<CreditCard size={17} />}
            title={t("account.billing.title")}
            body={t("account.billing.freeBody")}
            onClick={() => navigate("/account")}
          />
          <AccountMenuAction
            icon={<Settings size={17} />}
            title={t("account.manageProfile")}
            body={t("account.manageProfileBody")}
            onClick={() => openUserProfile()}
          />

          {isAdmin && (
            <AccountMenuAction
              icon={<LayoutDashboard size={17} />}
              tone="admin"
              title={t("account.adminConsole")}
              body={t("account.adminConsoleBody")}
              onClick={() => navigate("/admin/sessions")}
            />
          )}
        </div>

        <div className="border-t border-gold/20 bg-cream-2 p-2">
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

function AccountMenuAction({
  icon,
  title,
  body,
  tone = "default",
  onClick
}: {
  icon: ReactNode;
  title: string;
  body: string;
  tone?: "default" | "admin";
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="group flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left text-sm text-ink transition hover:bg-gold/10 focus:outline-none focus:ring-4 focus:ring-gold/15"
      onClick={onClick}
    >
      <span
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-lg border transition group-hover:scale-[1.03]",
          tone === "admin"
            ? "border-green/25 bg-green/10 text-green"
            : "border-gold/25 bg-cream-2 text-gold-dim"
        )}
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold leading-tight">{title}</span>
        <span className="mt-0.5 block truncate text-xs leading-[1.45] text-muted">{body}</span>
      </span>
      <ChevronRight
        size={16}
        className="shrink-0 text-muted transition group-hover:text-gold-dim"
      />
    </button>
  );
}

function initialsFor(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].slice(0, 2);
  return `${parts[0][0]}${parts[1][0]}`;
}
