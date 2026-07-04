import { SignInButton, SignUpButton, useAuth } from "@clerk/clerk-react";
import { useEffect, useMemo, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { setAnonymousIdProvider, setAuthTokenProvider } from "./api";
import { Button } from "./components/ui/button";
import { Landing } from "./screens/Landing";
import { Intake } from "./screens/Intake";
import { Session } from "./screens/Session";
import { AdminSessions } from "./screens/AdminSessions";
import { AdminSessionDetail } from "./screens/AdminSessionDetail";

export function App() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const anonymousId = useMemo(() => ensureAnonymousId(), []);

  useEffect(() => {
    setAuthTokenProvider(() => getToken());
    return () => setAuthTokenProvider(null);
  }, [getToken]);

  useEffect(() => {
    setAnonymousIdProvider(() => anonymousId);
    return () => setAnonymousIdProvider(null);
  }, [anonymousId]);

  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/new" element={<Intake />} />
      <Route path="/session/:id" element={<Session />} />
      <Route path="/admin" element={<Navigate to="/admin/sessions" replace />} />
      <Route
        path="/admin/sessions"
        element={
          <RequireAuth isLoaded={isLoaded} isSignedIn={Boolean(isSignedIn)}>
            <AdminSessions />
          </RequireAuth>
        }
      />
      <Route
        path="/admin/sessions/:id"
        element={
          <RequireAuth isLoaded={isLoaded} isSignedIn={Boolean(isSignedIn)}>
            <AdminSessionDetail />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
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
  if (!isLoaded) {
    return (
      <div className="grid min-h-screen place-items-center bg-cream px-6 text-muted">
        Loading account...
      </div>
    );
  }

  if (!isSignedIn) {
    return (
      <div className="grid min-h-screen place-items-center bg-cream px-6 text-ink">
        <div className="max-w-[460px] rounded-lg border border-gold/25 bg-cream-2 p-6 text-center shadow-[0_18px_48px_rgba(44,31,15,0.08)]">
          <div className="mb-2 text-[10px] uppercase tracking-[2px] text-gold">
            Account required
          </div>
          <h1 className="mb-3 text-2xl font-semibold tracking-normal">Sign in to continue</h1>
          <p className="mb-5 text-sm leading-[1.7] text-body">
            Your reports and generated artifacts are private to your account.
          </p>
          <div className="flex justify-center gap-2">
            <SignInButton mode="modal">
              <Button>Sign in</Button>
            </SignInButton>
            <SignUpButton mode="modal">
              <Button variant="outline">Create account</Button>
            </SignUpButton>
          </div>
        </div>
      </div>
    );
  }

  return children;
}
