import { SignInButton, SignUpButton, useAuth } from "@clerk/clerk-react";
import { lazy, Suspense, useEffect, useLayoutEffect, useState, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation, useSearchParams, useParams } from "react-router-dom";
import { api, setAuthFailureHandler, setAuthTokenProvider } from "./api";
import { WorkspaceLayout } from "./components/WorkspaceLayout";
import { safeWorkspaceReturn } from "./lib/workspace";
import { CosmicBackdrop } from "./components/CosmicBackdrop";
import { Button } from "./components/ui/button";
import { useI18n } from "./i18n/provider";

const Daily = lazy(() => import("./screens/Daily").then((module) => ({ default: module.Daily })));

const Landing = lazy(() =>
  import("./screens/Landing").then((module) => ({ default: module.Landing }))
);
const Intake = lazy(() =>
  import("./screens/Intake").then((module) => ({ default: module.Intake }))
);
const BaziWorkshop = lazy(() =>
  import("./screens/BaziWorkshop").then((module) => ({ default: module.BaziWorkshop }))
);
const Account = lazy(() =>
  import("./screens/Account").then((module) => ({ default: module.Account }))
);
const Session = lazy(() =>
  import("./screens/Session").then((module) => ({ default: module.Session }))
);
const AdminSessions = lazy(() =>
  import("./screens/AdminSessions").then((module) => ({ default: module.AdminSessions }))
);
const AdminSessionDetail = lazy(() =>
  import("./screens/AdminSessionDetail").then((module) => ({
    default: module.AdminSessionDetail
  }))
);
const ChartRevealPreview = lazy(() =>
  import("./screens/ChartRevealPreview").then((module) => ({
    default: module.ChartRevealPreview
  }))
);

export function App() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const { t } = useI18n();
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
      setSessionExpired(true);
    });
    return () => setAuthFailureHandler(null);
  }, []);

  useEffect(() => {
    if (isSignedIn) setSessionExpired(false);
  }, [isSignedIn]);

  return (
    <div className="cosmic-site relative min-h-screen overflow-x-clip bg-night text-cream">
      <CosmicBackdrop />
      {sessionExpired && (
        <div className="fixed inset-x-4 top-4 z-[90] mx-auto flex max-w-[720px] flex-col gap-3 rounded-lg border border-gold/30 bg-[rgba(16,12,22,0.88)] px-4 py-3 text-cream shadow-[0_18px_48px_rgba(0,0,0,0.36)] backdrop-blur-xl sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-sm font-semibold">{t("auth.sessionExpiredTitle")}</div>
            <div className="mt-0.5 text-xs leading-relaxed text-cream/65">
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
      <div className="relative z-10 min-h-screen">
        <Suspense fallback={<RouteLoadingState />}>
          <Routes>
            <Route
              path="/"
              element={
                !isLoaded ? (
                  <RouteLoadingState />
                ) : isSignedIn ? (
                  <Navigate to="/app" replace />
                ) : (
                  <Landing />
                )
              }
            />
            <Route path="/welcome" element={<Landing />} />
            <Route
              path="/sign-in"
              element={<SignInPage isLoaded={isLoaded} isSignedIn={Boolean(isSignedIn)} />}
            />
            <Route
              path="/app"
              element={
                <RequireAuth isLoaded={isLoaded} isSignedIn={Boolean(isSignedIn)}>
                  <WorkspaceLayout />
                </RequireAuth>
              }
            >
              <Route index element={<Daily view="today" />} />
              <Route path="records" element={<Daily view="records" />} />
              <Route path="explore" element={<Daily view="explore" />} />
              <Route path="charts" element={<Account view="charts" />} />
              <Route path="settings" element={<Account view="settings" />} />
              <Route path="charts/new" element={<Intake />} />
              <Route path="charts/bazi" element={<BaziWorkshop />} />
              <Route path="charts/:id" element={<Session />} />
            </Route>
            <Route path="/daily" element={<Navigate to="/app" replace />} />
            <Route path="/account" element={<Navigate to="/app/settings" replace />} />
            <Route path="/new" element={<Navigate to="/app/charts/new" replace />} />
            <Route path="/bazi" element={<Navigate to="/app/charts/bazi" replace />} />
            <Route path="/session/:id" element={<LegacySession />} />
            {import.meta.env.DEV && (
              <Route path="/dev/chart-reveal" element={<ChartRevealPreview />} />
            )}
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
        </Suspense>
      </div>
    </div>
  );
}

function RouteLoadingState() {
  return (
    <div className="grid min-h-screen place-items-center" role="status" aria-live="polite">
      <div className="size-7 animate-spin rounded-full border border-gold/25 border-t-gold-light" />
    </div>
  );
}

function LegacySession() {
  const { id } = useParams();
  const location = useLocation();
  return (
    <Navigate
      to={`/app/charts/${encodeURIComponent(id ?? "")}${location.search}${location.hash}`}
      replace
    />
  );
}

function SignInPage({ isLoaded, isSignedIn }: { isLoaded: boolean; isSignedIn: boolean }) {
  const [params] = useSearchParams();
  const { t } = useI18n();
  const destination = safeWorkspaceReturn(params.get("returnTo"));
  if (!isLoaded) return <RouteLoadingState />;
  if (isSignedIn) return <Navigate to={destination} replace />;
  return (
    <div className="mx-auto grid min-h-dvh max-w-lg place-content-center gap-5 px-6 text-center">
      <a href="/welcome" className="brand-logo mb-6">
        Sign <span>Atlas</span>
      </a>
      <h1 className="text-3xl">{t("auth.requiredTitle")}</h1>
      <p className="text-sm leading-7 text-cream/65">{t("auth.requiredBody")}</p>
      <div className="flex justify-center gap-3">
        <SignInButton mode="modal" forceRedirectUrl={destination}>
          <Button>{t("common.signIn")}</Button>
        </SignInButton>
        <SignUpButton mode="modal" forceRedirectUrl={destination}>
          <Button variant="outline">{t("common.createAccount")}</Button>
        </SignUpButton>
      </div>
    </div>
  );
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
  const location = useLocation();

  if (!isLoaded) {
    return (
      <div className="grid min-h-screen place-items-center px-6 text-cream/55">
        {t("auth.loading")}
      </div>
    );
  }

  if (!isSignedIn) {
    return (
      <Navigate
        to={`/sign-in?returnTo=${encodeURIComponent(location.pathname + location.search)}`}
        replace
      />
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
      <div className="grid min-h-screen place-items-center px-6 text-cream/55">
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
      <div className="grid min-h-screen place-items-center px-6 text-cream/55">
        {t("auth.adminChecking")}
      </div>
    );
  }

  if (!allowed) {
    return (
      <div className="grid min-h-screen place-items-center px-6 text-cream">
        <div className="max-w-[460px] rounded-lg border border-gold/25 bg-[rgba(16,12,22,0.72)] p-6 text-center shadow-[0_24px_80px_rgba(0,0,0,0.38)] backdrop-blur-xl">
          <div className="mb-2 text-[10px] uppercase tracking-[2px] text-gold">
            {t("auth.adminDeniedEyebrow")}
          </div>
          <h1 className="mb-3 text-2xl font-semibold tracking-normal">
            {t("auth.adminDeniedTitle")}
          </h1>
          <p className="mb-5 text-sm leading-[1.7] text-cream/68">
            {error || t("auth.adminDeniedBody")}
          </p>
          <Button onClick={() => (window.location.href = "/account")}>{t("account.center")}</Button>
        </div>
      </div>
    );
  }

  return children;
}
