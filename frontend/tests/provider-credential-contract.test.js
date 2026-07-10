import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function readFrontendFile(path) {
  return readFileSync(resolve(frontendRoot, path), "utf8");
}

describe("provider credential lifecycle", () => {
  const controls = readFrontendFile("src/app/settings/provider-credential-controls.js");
  const infrastructure = readFrontendFile("src/app/settings/operator-controls.js");
  const modelSettings = readFrontendFile("src/app/settings/model-preference-card.js");
  const api = readFrontendFile("src/lib/provider-credential-api.js");

  it("removes delete-before-replace from the normal infrastructure interface", () => {
    expect(infrastructure).not.toContain("Delete key");
    expect(infrastructure).not.toContain("Delete the existing");
    expect(infrastructure).not.toContain("provider-credentials");
  });

  it("places provider keys beside the model catalogue for administrators", () => {
    expect(modelSettings).toContain("<ProviderCredentialControls />");
    expect(controls).toContain('userRole !== "admin"');
    expect(controls).toContain("Change key");
    expect(controls).toContain("Add key");
  });

  it("requires candidate testing before activation or replacement", () => {
    expect(controls).toContain("Test candidate");
    expect(controls).toContain("Test this exact candidate key before activation.");
    expect(controls).toContain("candidateResult.secret === secret.trim()");
    expect(controls).toContain("Replace active key");
  });

  it("shows active-key health and version metadata", () => {
    expect(controls).toContain("Last successful test");
    expect(controls).toContain("Last failure");
    expect(controls).toContain("credential?.key_version");
    expect(controls).toContain("credential?.last_successful_test_at");
    expect(controls).toContain("credential?.last_test_failure_at");
  });

  it("uses separate active, candidate, and atomic replacement endpoints", () => {
    expect(api).toContain("/candidate/test");
    expect(api).toContain("testActiveProviderCredential");
    expect(api).toContain('method: "PUT"');
  });
});
