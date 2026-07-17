export const defaultLanguageCode = "en-US";

export const supportedLanguages = [
  { code: "en-US", hreflang: "en-US", websitePath: "/", label: "English" },
  { code: "bg", hreflang: "bg", websitePath: "bg", label: "Bulgarian" },
  { code: "hr", hreflang: "hr", websitePath: "hr", label: "Croatian" },
  { code: "cs", hreflang: "cs", websitePath: "cs", label: "Czech" },
  { code: "da", hreflang: "da", websitePath: "da", label: "Danish" },
  { code: "nl", hreflang: "nl", websitePath: "nl", label: "Dutch" },
  { code: "et", hreflang: "et", websitePath: "et", label: "Estonian" },
  { code: "fi", hreflang: "fi", websitePath: "fi", label: "Finnish" },
  { code: "fr", hreflang: "fr", websitePath: "fr", label: "French" },
  { code: "de", hreflang: "de", websitePath: "de", label: "German" },
  { code: "el", hreflang: "el", websitePath: "el", label: "Greek" },
  { code: "hu", hreflang: "hu", websitePath: "hu", label: "Hungarian" },
  { code: "ga", hreflang: "ga", websitePath: "ga", label: "Irish" },
  { code: "it", hreflang: "it", websitePath: "it", label: "Italian" },
  { code: "lv", hreflang: "lv", websitePath: "lv", label: "Latvian" },
  { code: "lt", hreflang: "lt", websitePath: "lt", label: "Lithuanian" },
  { code: "mt", hreflang: "mt", websitePath: "mt", label: "Maltese" },
  { code: "pl", hreflang: "pl", websitePath: "pl", label: "Polish" },
  { code: "pt", hreflang: "pt", websitePath: "pt", label: "Portuguese" },
  { code: "ro", hreflang: "ro", websitePath: "ro", label: "Romanian" },
  { code: "sk", hreflang: "sk", websitePath: "sk", label: "Slovak" },
  { code: "sl", hreflang: "sl", websitePath: "sl", label: "Slovenian" },
  { code: "es", hreflang: "es", websitePath: "es", label: "Spanish" },
  { code: "sv", hreflang: "sv", websitePath: "sv", label: "Swedish" },
] as const;

export type SupportedLanguageCode = (typeof supportedLanguages)[number]["code"];

const supportedLanguageByCode = new Map<string, SupportedLanguageCode>(
  supportedLanguages.map((language) => [language.code.toLowerCase(), language.code]),
);

export function isSupportedLanguageCode(value: string): value is SupportedLanguageCode {
  return supportedLanguageByCode.has(value.toLowerCase());
}

export function normalizeLanguageCode(value?: string | null) {
  if (!value) {
    return undefined;
  }

  const normalized = value.trim().replace("_", "-").toLowerCase();
  const exactMatch = supportedLanguageByCode.get(normalized);

  if (exactMatch) {
    return exactMatch;
  }

  const primarySubtag = normalized.split("-")[0];

  if (primarySubtag === "en") {
    return defaultLanguageCode;
  }

  return supportedLanguageByCode.get(primarySubtag);
}
