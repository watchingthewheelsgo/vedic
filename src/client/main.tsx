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
    colorBackground: "#faf5ec",
    colorInputBackground: "#fffaf1",
    colorInputText: "#2c1f0f",
    colorText: "#2c1f0f",
    colorTextSecondary: "#5a4a35",
    colorNeutral: "#8a7a65",
    borderRadius: "8px",
    fontFamily:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif"
  },
  elements: {
    cardBox: "shadow-[0_24px_80px_rgba(44,31,15,0.18)]",
    card: "border border-gold/25 bg-cream",
    headerTitle: "text-ink",
    headerSubtitle: "text-body",
    socialButtonsBlockButton:
      "border-gold/25 bg-cream-2 text-ink hover:bg-gold/10 hover:border-gold/50",
    formButtonPrimary:
      "bg-gold text-white shadow-none hover:bg-gold-dim focus:ring-4 focus:ring-gold/20",
    formFieldInput:
      "border-gold/30 bg-white text-ink focus:border-gold focus:ring-4 focus:ring-gold/15",
    footerActionLink: "text-gold-dim hover:text-gold",
    dividerLine: "bg-gold/25",
    dividerText: "text-muted"
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
    <div className="grid min-h-screen place-items-center bg-cream px-6 text-ink">
      <div className="max-w-[520px] rounded-lg border border-gold/25 bg-cream-2 p-6 shadow-[0_18px_48px_rgba(44,31,15,0.08)]">
        <div className="mb-2 text-[10px] uppercase tracking-[2px] text-gold">
          {t("clerk.missingEyebrow")}
        </div>
        <h1 className="mb-3 text-2xl font-semibold tracking-normal">{t("clerk.missingTitle")}</h1>
        <p className="text-sm leading-[1.7] text-body">
          {t("clerk.missingBody", { key: "VITE_CLERK_PUBLISHABLE_KEY" })}
        </p>
      </div>
    </div>
  );
}
