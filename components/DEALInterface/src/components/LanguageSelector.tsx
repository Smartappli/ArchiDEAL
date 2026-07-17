import type { SupportedLanguageCode } from "../i18n/locales";
import { useI18n } from "../i18n/I18nProvider";

export function LanguageSelector() {
  const { language, setLanguage, supportedLanguages, t } = useI18n();

  return (
    <label className="language-selector">
      <span>{t("language.label")}</span>
      <select
        aria-label={t("language.ariaLabel")}
        onChange={(event) => setLanguage(event.currentTarget.value as SupportedLanguageCode)}
        value={language}
      >
        {supportedLanguages.map((supportedLanguage) => (
          <option key={supportedLanguage.code} value={supportedLanguage.code}>
            {supportedLanguage.label}
          </option>
        ))}
      </select>
      <small>{t("language.fallbackNote")}</small>
    </label>
  );
}
