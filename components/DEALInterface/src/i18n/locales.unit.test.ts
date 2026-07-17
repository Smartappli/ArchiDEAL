import { describe, expect, it } from "vitest";
import { defaultLanguageCode, isSupportedLanguageCode, normalizeLanguageCode, supportedLanguages } from "./locales";

describe("supported interface languages", () => {
  it("matches DEALWebsite language routes", () => {
    expect(supportedLanguages.map((language) => language.code)).toEqual([
      "en-US",
      "bg",
      "hr",
      "cs",
      "da",
      "nl",
      "et",
      "fi",
      "fr",
      "de",
      "el",
      "hu",
      "ga",
      "it",
      "lv",
      "lt",
      "mt",
      "pl",
      "pt",
      "ro",
      "sk",
      "sl",
      "es",
      "sv",
    ]);
  });

  it("normalizes browser and route locale values", () => {
    expect(defaultLanguageCode).toBe("en-US");
    expect(isSupportedLanguageCode("fr")).toBe(true);
    expect(isSupportedLanguageCode("zh")).toBe(false);
    expect(normalizeLanguageCode("en")).toBe("en-US");
    expect(normalizeLanguageCode("fr-BE")).toBe("fr");
    expect(normalizeLanguageCode("pt_PT")).toBe("pt");
    expect(normalizeLanguageCode("zh")).toBeUndefined();
  });
});
