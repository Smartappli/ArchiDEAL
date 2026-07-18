import { describe, expect, it } from "vitest";
import { localizedMessages } from "./messages";

describe("French messages", () => {
  it("preserves French diacritics as normalized UTF-8 text", () => {
    expect(localizedMessages.fr).toMatchObject({
      "activity.title": "Événements récents du plan de contrôle",
      "command.access": "Accès",
      "hero.consoleDescription":
        "Les surfaces partagées d'accès, d'audit et d'opérations sont prêtes pour l'intégration API.",
      "hero.title": "Pilotez DEALHost, DEALIot et DEALData depuis une interface unifiée.",
      "production.liveOnlyTitle": "Mode de validation en direct",
      "service.refresh": "Rafraîchir",
      "status.copyOnline":
        "Les sondes requises sont saines dans cet environnement de validation.",
      "status.degraded": "Dégradé",
      "status.online": "Opérationnel",
    });

    for (const message of Object.values(localizedMessages.fr ?? {})) {
      expect(message).toBe(message.normalize("NFC"));
      expect(message).not.toMatch(/Ã.|�/u);
    }
  });
});
