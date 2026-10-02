import { useClerk, useUser } from "@clerk/clerk-react";
import {
  BookOpen,
  NotebookPen,
  ChevronDown,
  ChevronRight,
  CreditCard,
  LayoutDashboard,
  LogOut,
  Settings,
  UserRound
} from "lucide-react";
import { useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { DraftContext } from "../lib/workspace-draft";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import { workspaceCopy } from "../lib/workspace";
import { cn } from "../lib/cn";
import { AccountAvatar } from "./AccountAvatar";
import { Button } from "./ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

export function AccountCenter({ compact = false }: { compact?: boolean }) {
  const { signOut, openUserProfile } = useClerk();
  const { confirmLeave } = useContext(DraftContext);
  const { isLoaded, isSignedIn, user } = useUser();
  const navigate = useNavigate();
  const { t, locale } = useI18n();
  const [isAdmin, setIsAdmin] = useState(false);
  const [open, setOpen] = useState(false);
  const visit = (path: string) => {
    if (!confirmLeave()) return;
    setOpen(false);
    navigate(path);
  };

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
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "group inline-flex h-11 shrink-0 items-center gap-2.5 rounded-xl border border-white/15 bg-white/5 px-2 text-left text-cream transition-colors hover:border-gold/45 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/60",
            compact ? "pr-2.5" : "pr-3"
          )}
          aria-label={t("account.open")}
        >
          <AccountAvatar initials={initials} imageUrl={avatarUrl} size="sm" />
          {!compact && (
            <span className="hidden max-w-[150px] flex-col leading-tight sm:flex">
              <span className="truncate text-[13px] font-medium text-cream">{displayName}</span>
              <span className="truncate text-[11px] text-cream/60">{t("account.center")}</span>
            </span>
          )}
          {!compact && (
            <ChevronDown
              size={14}
              className="hidden text-cream/60 transition-transform duration-150 group-data-[state=open]:rotate-180 sm:block"
            />
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[min(calc(100vw-24px),352px)] max-h-[var(--radix-popover-content-available-height)] overflow-y-auto rounded-2xl border-white/15 bg-[#19151f] p-0"
        align="end"
        collisionPadding={12}
      >
        <div className="relative overflow-hidden border-b border-white/10 bg-white/[0.03] px-5 py-5 text-cream">
          <div className="pointer-events-none absolute -right-14 -top-16 size-36 rounded-full bg-gold/18 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-20 left-8 size-32 rounded-full bg-green/10 blur-3xl" />
          <div className="relative flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <AccountAvatar initials={initials} imageUrl={avatarUrl} size="md" />
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-cream">{displayName}</div>
                <div className="mt-0.5 truncate text-xs text-cream/65">{email}</div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-1 p-2">
          <AccountMenuAction
            icon={<NotebookPen size={17} />}
            title={workspaceCopy[locale].space}
            body={workspaceCopy[locale].todayBody}
            onClick={() => visit("/app")}
          />
          <AccountMenuAction
            icon={<UserRound size={17} />}
            title={t("account.center")}
            body={t("account.centerBody")}
            onClick={() => visit("/app/settings")}
          />
          <AccountMenuAction
            icon={<BookOpen size={17} />}
            title={t("account.savedReadings")}
            body={t("account.savedReadingsBody")}
            onClick={() => visit("/app/charts")}
          />
          <AccountMenuAction
            icon={<CreditCard size={17} />}
            title={t("account.billing.title")}
            body={t("account.billing.freeBody")}
            onClick={() => visit("/app/settings#billing")}
          />
          <AccountMenuAction
            icon={<Settings size={17} />}
            title={t("account.manageProfile")}
            body={t("account.manageProfileBody")}
            onClick={() => {
              setOpen(false);
              openUserProfile();
            }}
          />

          {isAdmin && (
            <AccountMenuAction
              icon={<LayoutDashboard size={17} />}
              tone="admin"
              title={t("account.adminConsole")}
              body={t("account.adminConsoleBody")}
              onClick={() => visit("/admin/sessions")}
            />
          )}
          <AccountMenuAction
            icon={<BookOpen size={17} />}
            title={workspaceCopy[locale].website}
            body="Sign Atlas"
            onClick={() => visit("/welcome")}
          />
        </div>

        <div className="border-t border-white/10 p-2">
          <Button
            type="button"
            variant="ghost"
            className="w-full justify-start text-[#ef9a87] hover:bg-red/10 hover:text-[#ffb5a4]"
            onClick={() => {
              if (confirmLeave()) void signOut({ redirectUrl: "/welcome" });
            }}
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
      className="group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm text-cream transition-colors hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-gold/60"
      onClick={onClick}
    >
      <span
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-lg",
          tone === "admin" ? "border-green/25 bg-green/10 text-green" : "bg-gold/10 text-gold"
        )}
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold leading-tight">{title}</span>
        <span className="mt-0.5 block truncate text-xs leading-[1.45] text-cream/65">{body}</span>
      </span>
      <ChevronRight
        size={16}
        className="shrink-0 text-cream/40 transition-colors group-hover:text-gold"
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
