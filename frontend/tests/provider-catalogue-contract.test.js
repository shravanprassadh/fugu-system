import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function readFrontendFile(path) {
  return readFileSync(resolve(frontendRoot, path), "utf8");
}

describe("backend-owned provider catalogue", () => {
  const modelOptions = readFrontendFile("src/lib/model-options.js");
  const modelSettings = readFrontendFile("src/app/settings/model-preference-card.js");
  const apiClient = readFrontendFile("src/lib/api-client.js");

  it("removes the duplicated frontend model inventory", () => {
    expect(modelOptions).not.toContain("nvidiaChatModelIds");
    expect(modelOptions).not.toContain("supportedModelsByProvider");
    expect(modelOptions).not.toContain("meta/llama-3.1-70b-instruct");
  });

  it("loads provider and model definitions from the backend", () => {
    expect(apiClient).toContain('authorizedRequest("/api/providers/catalogue"');
    expect(modelSettings).toContain("getProviderCatalogue");
    expect(modelSettings).toContain("provider.adapter_available");
    expect(modelSettings).toContain('provider.health_status === "available"');
  });

  it("shows backend capability and limit metadata", () => {
    expect(modelSettings).toContain("model.capabilities.image_understanding");
    expect(modelSettings).toContain("model.capabilities.reasoning_support");
    expect(modelSettings).toContain("selectedModel.context_size");
    expect(modelSettings).toContain("selectedModel.output_limit");
  });

  it("normalizes stale local preferences against the fetched catalogue", () => {
    expect(modelOptions).toContain("normalizePreferenceAgainstCatalogue");
    expect(modelSettings).toContain("normalizePreferenceAgainstCatalogue(current, availableProviders)");
  });
});
