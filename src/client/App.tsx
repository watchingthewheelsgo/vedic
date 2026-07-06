import { SignInButton, SignUpButton, useAuth } from "@clerk/clerk-react";
import { useEffect, useLayoutEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { api, setAnonymousIdProvider, setAuthFailureHandler, setAuthTokenProvider } from "./api";
import { Button } from "./components/ui/button";
import { useI18n } from "./i18n/provider";
import { Landing } from "./screens/Landing";
import { Intake } from "./screens/Intake";
import { BaziWorkshop } from "./screens/BaziWorkshop";
import { Account } from "./screens/Account";
import { Session } from "./screens/Session";
import { AdminSessions } from "./screens/AdminSessions";
import { AdminSessionDetail } from "./screens/AdminSessionDetail";

export function App() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const { t } = useI18n();
  const anonymousId = useMemo(() => ensureAnonymousId(), []);
  const [sessionExpired, setSessionExpired] = useState(false);

  useLayoutEffect(() => {
    setAuthTokenProvider(async () => {
      if (!isLoaded || !isSignedIn) return null;
      const token = await getToken();
      if (!token) throw new Error("Clerk session token is unavailable");
      return token;
    });
    return () => setAuthTokenProvider(null);
  }, [getToken, isLoaded, isSignedIn]);

  useLayoutEffect(() => {
    setAuthFailureHandler(async () => {
      // Temporary dev behavior: keep the Clerk client session alive even when
      // the backend cannot verify the short-lived JWT. The backend has a local
      // bypass switch for this while Clerk JWKS/network verification is fixed.
      return;
    });
    return () => setAuthFailureHandler(null);
  }, []);

  useEffect(() => {
    if (isSignedIn) setSessionExpired(false);
  }, [isSignedIn]);

  useLayoutEffect(() => {
    setAnonymousIdProvider(() => anonymousId);
    return () => setAnonymousIdProvider(null);
  }, [anonymousId]);

  return (
    <>
      {sessionExpired && (
        <div className="fixed inset-x-4 top-4 z-[90] mx-auto flex max-w-[720px] flex-col gap-3 rounded-lg border border-gold/30 bg-cream px-4 py-3 text-ink shadow-[0_18px_48px_rgba(44,31,15,0.16)] sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-sm font-semibold">{t("auth.sessionExpiredTitle")}</div>
            <div className="mt-0.5 text-xs leading-relaxed text-body">
              {t("auth.sessionExpiredBody")}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <SignInButton mode="modal">
              <Button size="sm">{t("auth.signInAgain")}</Button>
            </SignInButton>
            <Button size="sm" variant="ghost" onClick={() => setSessionExpired(false)}>
              {t("common.dismiss")}
            </Button>
          </div>
        </div>
      )}
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/new" element={<Intake />} />
        <Route path="/bazi" element={<BaziWorkshop />} />
        <Route path="/session/:id" element={<Session />} />
        <Route
          path="/account"
          element={
            <RequireAuth isLoaded={isLoaded} isSignedIn={Boolean(isSignedIn)}>
              <Account />
            </RequireAuth>
          }
        />
        <Route path="/admin" element={<Navigate to="/admin/sessions" replace />} />
        <Route
          path="/admin/sessions"
          element={
            <RequireAdmin isLoaded={isLoaded} isSignedIn={Boolean(isSignedIn)}>
              <AdminSessions />
            </RequireAdmin>
          }
        />
        <Route
          path="/admin/sessions/:id"
          element={
            <RequireAdmin isLoaded={isLoaded} isSignedIn={Boolean(isSignedIn)}>
              <AdminSessionDetail />
            </RequireAdmin>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

function ensureAnonymousId() {
  const key = "vedic.anonymousUserId";
  const existing = window.localStorage.getItem(key);
  if (existing?.match(/^anonym_[A-Za-z0-9_-]{8,64}$/)) return existing;
  const random =
    "randomUUID" in crypto
      ? crypto.randomUUID().replaceAll("-", "").slice(0, 18)
      : Math.random().toString(36).slice(2, 20);
  const value = `anonym_${random}`;
  window.localStorage.setItem(key, value);
  return value;
}

function RequireAuth({
  children,
  isLoaded,
  isSignedIn
}: {
  children: ReactNode;
  isLoaded: boolean;
  isSignedIn: boolean;
}) {
  const { t } = useI18n();

  if (!isLoaded) {
    return (
      <div className="grid min-h-screen place-items-center bg-cream px-6 text-muted">
        {t("auth.loading")}
      </div>
    );
  }

  if (!isSignedIn) {
    return (
      <div className="grid min-h-screen place-items-center bg-cream px-6 text-ink">
        <div className="max-w-[460px] rounded-lg border border-gold/25 bg-cream-2 p-6 text-center shadow-[0_18px_48px_rgba(44,31,15,0.08)]">
          <div className="mb-2 text-[10px] uppercase tracking-[2px] text-gold">
            {t("auth.requiredEyebrow")}
          </div>
          <h1 className="mb-3 text-2xl font-semibold tracking-normal">{t("auth.requiredTitle")}</h1>
          <p className="mb-5 text-sm leading-[1.7] text-body">{t("auth.requiredBody")}</p>
          <div className="flex justify-center gap-2">
            <SignInButton mode="modal">
              <Button>{t("common.signIn")}</Button>
            </SignInButton>
            <SignUpButton mode="modal">
              <Button variant="outline">{t("common.createAccount")}</Button>
            </SignUpButton>
          </div>
        </div>
      </div>
    );
  }

  return children;
}

function RequireAdmin({
  children,
  isLoaded,
  isSignedIn
}: {
  children: ReactNode;
  isLoaded: boolean;
  isSignedIn: boolean;
}) {
  const { t } = useI18n();
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    let cancelled = false;
    setAllowed(null);
    setError("");
    void api
      .getMe()
      .then((profile) => {
        if (!cancelled) setAllowed(profile.isAdmin);
      })
      .catch((caught) => {
        if (!cancelled) {
          setAllowed(false);
          setError(caught instanceof Error ? caught.message : t("auth.adminDeniedBody"));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, t]);

  if (!isLoaded) {
    return (
      <div className="grid min-h-screen place-items-center bg-cream px-6 text-muted">
        {t("auth.loading")}
      </div>
    );
  }

  if (!isSignedIn) {
    return (
      <RequireAuth isLoaded={isLoaded} isSignedIn={isSignedIn}>
        {children}
      </RequireAuth>
    );
  }

  if (allowed === null) {
    return (
      <div className="grid min-h-screen place-items-center bg-cream px-6 text-muted">
        {t("auth.adminChecking")}
      </div>
    );
  }

  if (!allowed) {
    return (
      <div className="grid min-h-screen place-items-center bg-cream px-6 text-ink">
        <div className="max-w-[460px] rounded-lg border border-gold/25 bg-cream-2 p-6 text-center shadow-[0_18px_48px_rgba(44,31,15,0.08)]">
          <div className="mb-2 text-[10px] uppercase tracking-[2px] text-gold">
            {t("auth.adminDeniedEyebrow")}
          </div>
          <h1 className="mb-3 text-2xl font-semibold tracking-normal">
            {t("auth.adminDeniedTitle")}
          </h1>
          <p className="mb-5 text-sm leading-[1.7] text-body">
            {error || t("auth.adminDeniedBody")}
          </p>
          <Button onClick={() => (window.location.href = "/account")}>{t("account.center")}</Button>
        </div>
      </div>
    );
  }

  return children;
}
