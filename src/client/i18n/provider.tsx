import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { localeTags, messages, type LocaleCode } from "./messages";

type I18nContextValue = {
  locale: LocaleCode;
  localeTag: string;
  setLocale: (locale: LocaleCode) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
  formatDate: (date: Date, options?: Intl.DateTimeFormatOptions) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);
const STORAGE_KEY = "vedic.locale";

function detectInitialLocale(): LocaleCode {
  const saved = window.localStorage.getItem(STORAGE_KEY) as LocaleCode | null;
  if (saved && saved in messages) return saved;
  const browser = window.navigator.language.toLowerCase();
  if (browser.startsWith("zh")) return "zh";
  if (browser.startsWith("ja")) return "ja";
  return "en";
}

function formatTemplate(template: string, vars?: Record<string, string | number>) {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = vars[key];
    return value === undefined ? `{${key}}` : String(value);
  });
}

export function AppI18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<LocaleCode>(detectInitialLocale);

  useEffect(() => {
    document.documentElement.lang = localeTags[locale];
  }, [locale]);

  const value = useMemo<I18nContextValue>(() => {
    const localeTag = localeTags[locale];
    return {
      locale,
      localeTag,
      setLocale: (nextLocale) => {
        setLocaleState(nextLocale);
        window.localStorage.setItem(STORAGE_KEY, nextLocale);
        document.documentElement.lang = localeTags[nextLocale];
      },
      t: (key, vars) => {
        const text = messages[locale]?.[key] ?? messages.en[key] ?? key;
        return formatTemplate(text, vars);
      },
      formatDate: (date, options) => date.toLocaleDateString(localeTag, options)
    };
  }, [locale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used within AppI18nProvider");
  return context;
}
