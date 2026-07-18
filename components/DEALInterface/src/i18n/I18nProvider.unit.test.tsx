import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider, useI18n } from "./I18nProvider";

function Probe() {
  const { language, setLanguage, t } = useI18n();

  return (
    <div>
      <p>{language}</p>
      <h1>{t("hero.title")}</h1>
      <p>{t("module.liveProbesHealthy", { online: 2, total: 3 })}</p>
      <p>{t("hero.title", { unused: "value" })}</p>
      <button onClick={() => setLanguage("fr")} type="button">
        French
      </button>
    </div>
  );
}

function renderProbe() {
  return render(
    <I18nProvider>
      <Probe />
    </I18nProvider>,
  );
}

afterEach(() => {
  window.localStorage.clear();
  window.history.pushState({}, "", "/");
  vi.restoreAllMocks();
});

describe("I18nProvider", () => {
  it("initializes from a DEALWebsite-style route segment", () => {
    window.history.pushState({}, "", "/fr/control-plane");

    renderProbe();

    expect(screen.getByText("fr")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "Pilotez DEALHost, DEALIot et DEALData depuis une interface unifiée.",
      }),
    ).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("fr");
  });

  it("prefers a stored language over route and navigator detection", () => {
    window.localStorage.setItem("dealinterface.language", "de");
    window.history.pushState({}, "", "/fr/control-plane");

    renderProbe();

    expect(screen.getByText("de")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("de");
  });

  it("falls back to the first supported browser language", () => {
    vi.spyOn(window.navigator, "languages", "get").mockReturnValue(["zh-CN", "sv-SE"]);

    renderProbe();

    expect(screen.getByText("sv")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("sv");
  });

  it("uses the default language when browser languages are unsupported", () => {
    vi.spyOn(window.navigator, "languages", "get").mockReturnValue(["zh-CN"]);

    renderProbe();

    expect(screen.getByText("en-US")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en-US");
  });

  it("keeps the session usable when localStorage is unavailable", async () => {
    const user = userEvent.setup();

    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });

    renderProbe();

    expect(screen.getByText("en-US")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "French" }));

    expect(screen.getByText("fr")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("fr");
  });

  it("throws when the hook is used outside its provider", () => {
    function InvalidConsumer() {
      useI18n();

      return null;
    }

    expect(() => render(<InvalidConsumer />)).toThrow("useI18n must be used inside I18nProvider");
  });
});
