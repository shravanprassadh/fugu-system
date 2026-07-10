import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function readFrontendFile(path) {
  return readFileSync(resolve(frontendRoot, path), "utf8");
}

describe("canonical settings surface", () => {
  const settingsDialog = readFrontendFile("src/components/settings-dialog.js");
  const settingsRoute = readFrontendFile("src/app/settings/page.js");
  const chatPage = readFrontendFile("src/app/chat/page.js");

  it("keeps the legacy settings route as a redirect rather than a second implementation", () => {
    expect(settingsRoute).toContain('redirect("/chat")');
    expect(settingsRoute).not.toContain("StudioSidebar");
    expect(settingsRoute).not.toContain("OperatorControls");
    expect(settingsRoute).not.toContain("ModelPreferenceCard");
  });

  it("opens the canonical settings dialog from chat and closes it through the supplied callback", () => {
    expect(chatPage).toContain("onOpenSettings={() => setIsSettingsOpen(true)}");
    expect(chatPage).toContain("open={isSettingsOpen}");
    expect(chatPage).toContain("onClose={() => setIsSettingsOpen(false)}");
    expect(settingsDialog).toContain("if (!open)");
    expect(settingsDialog).toContain("return null;");
    expect(settingsDialog).toContain("onMouseDown={onClose}");
    expect(settingsDialog).toContain('event.key === "Escape"');
  });

  it("retains the required settings sections and section navigation", () => {
    for (const sectionId of ["general", "model", "members", "system"]) {
      expect(settingsDialog).toContain(`id: "${sectionId}"`);
    }
    expect(settingsDialog).toContain("visibleSections.map((section)");
    expect(settingsDialog).toContain("setActiveSection(section.id)");
  });
});
