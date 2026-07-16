import React from "react";
import { ClerkProvider } from "@clerk/clerk-react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { AppI18nProvider, useI18n } from "./i18n/provider";
import "./styles.css";

const clerkPublishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined;
const clerkAppearance = {
  variables: {
    colorPrimary: "#c9a96e",
    colorBackground: "#100c16",
    colorInputBackground: "rgba(255,255,255,0.06)",
    colorInputText: "#faf5ec",
    colorText: "#faf5ec",
    colorTextSecondary: "rgba(245,239,230,0.68)",
    colorNeutral: "rgba(245,239,230,0.48)",
    borderRadius: "8px",
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif"
  },
  elements: {
    cardBox: "shadow-[0_28px_90px_rgba(0,0,0,0.46)]",
    card: "border border-gold/25 bg-[rgba(16,12,22,0.96)] backdrop-blur-xl",
    headerTitle: "text-cream",
    headerSubtitle: "text-cream/65",
    socialButtonsBlockButton:
      "border-gold/25 bg-white/5 text-cream hover:bg-gold/10 hover:border-gold/50",
    formButtonPrimary:
      "bg-gold text-white shadow-none hover:bg-gold-dim focus:ring-4 focus:ring-gold/20",
    formFieldInput:
      "border-gold/30 bg-white/5 text-cream focus:border-gold focus:ring-4 focus:ring-gold/15",
    footerActionLink: "text-gold-light hover:text-gold",
    dividerLine: "bg-gold/25",
    dividerText: "text-cream/45"
  }
};

createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AppI18nProvider>
      {clerkPublishableKey ? (
        <ClerkProvider publishableKey={clerkPublishableKey} appearance={clerkAppearance}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ClerkProvider>
      ) : (
        <MissingClerkConfig />
      )}
    </AppI18nProvider>
  </React.StrictMode>
);

function MissingClerkConfig() {
  const { t } = useI18n();
  return (
    <div className="grid min-h-screen place-items-center bg-night px-6 text-cream">
      <div className="max-w-[520px] rounded-lg border border-gold/25 bg-white/5 p-6 shadow-[0_24px_80px_rgba(0,0,0,0.36)]">
        <div className="mb-2 text-[10px] uppercase tracking-[2px] text-gold">
          {t("clerk.missingEyebrow")}
        </div>
        <h1 className="mb-3 text-2xl font-semibold tracking-normal">{t("clerk.missingTitle")}</h1>
        <p className="text-sm leading-[1.7] text-cream/70">
          {t("clerk.missingBody", { key: "VITE_CLERK_PUBLISHABLE_KEY" })}
        </p>
      </div>
    </div>
  );
}
