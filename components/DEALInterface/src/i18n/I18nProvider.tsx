import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  defaultLanguageCode,
  normalizeLanguageCode,
  supportedLanguages,
  type SupportedLanguageCode,
} from "./locales";
import { englishMessages, localizedMessages, type MessageKey, type MessageParams } from "./messages";

const storageKey = "dealinterface.language";

interface I18nContextValue {
  language: SupportedLanguageCode;
  setLanguage: (language: SupportedLanguageCode) => void;
  supportedLanguages: typeof supportedLanguages;
  t: (key: MessageKey, params?: MessageParams) => string;
}

const I18nContext = createContext<I18nContextValue | undefined>(undefined);

function readStoredLanguage() {
  try {
    return normalizeLanguageCode(window.localStorage.getItem(storageKey));
  } catch {
    return undefined;
  }
}

function readPathLanguage() {
  const firstSegment = window.location.pathname.split("/").filter(Boolean)[0];

  return normalizeLanguageCode(firstSegment);
}

function readNavigatorLanguage() {
  const navigatorLanguages = window.navigator.languages?.length
    ? window.navigator.languages
    : [window.navigator.language];

  for (const language of navigatorLanguages) {
    const normalized = normalizeLanguageCode(language);

    if (normalized) {
      return normalized;
    }
  }

  return undefined;
}

function getInitialLanguage() {
  if (typeof window === "undefined") {
    return defaultLanguageCode;
  }

  return readStoredLanguage() ?? readPathLanguage() ?? readNavigatorLanguage() ?? defaultLanguageCode;
}

function interpolate(message: string, params?: MessageParams) {
  if (!params) {
    return message;
  }

  return message.replace(/\{(\w+)}/g, (match, key) => String(params[key] ?? match));
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<SupportedLanguageCode>(getInitialLanguage);

  const messages = useMemo(
    () => ({
      ...englishMessages,
      ...(localizedMessages[language] ?? {}),
    }),
    [language],
  );

  const t = useCallback(
    (key: MessageKey, params?: MessageParams) => interpolate(messages[key] ?? englishMessages[key], params),
    [messages],
  );

  useEffect(() => {
    const selectedLanguage = supportedLanguages.find((candidate) => candidate.code === language);

    document.documentElement.lang = selectedLanguage?.hreflang ?? defaultLanguageCode;
    document.documentElement.dir = "ltr";
    document.documentElement.dataset.language = language;

    try {
      window.localStorage.setItem(storageKey, language);
    } catch {
      // Browsers can disable localStorage; language still works for the current session.
    }
  }, [language]);

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      supportedLanguages,
      t,
    }),
    [language, t],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);

  if (!context) {
    throw new Error("useI18n must be used inside I18nProvider");
  }

  return context;
}
