import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function readFrontendFile(path) {
  return readFileSync(resolve(frontendRoot, path), "utf8");
}

describe("capability-driven model parameters", () => {
  const preferences = readFrontendFile("src/lib/model-options.js");
  const settings = readFrontendFile("src/app/settings/model-preference-card.js");
  const streamClient = readFrontendFile("src/lib/stream-client.js");

  it("normalizes stored parameters against backend ranges", () => {
    expect(preferences).toContain("model.temperature?.default");
    expect(preferences).toContain("normalized.temperature >= temperature.minimum");
    expect(preferences).toContain("normalized.maxOutputTokens <= selectedModel.output_limit");
    expect(preferences).toContain("normalized.thinkingBudget >= selectedModel.thinking_budget_minimum");
  });

  it("renders only parameters supported by the selected model", () => {
    expect(settings).toContain("selectedModel.temperature ?");
    expect(settings).toContain('selectedModel.supported_parameters.includes("max_output_tokens")');
    expect(settings).toContain('selectedModel.supported_parameters.includes("thinking_budget")');
    expect(settings).toContain("Thinking budget is not supported by this model and will not be sent.");
  });

  it("uses backend limits as HTML input constraints", () => {
    expect(settings).toContain("min={selectedModel.temperature.minimum}");
    expect(settings).toContain("max={selectedModel.temperature.maximum}");
    expect(settings).toContain("max={selectedModel.output_limit}");
    expect(settings).toContain("min={selectedModel.thinking_budget_minimum}");
    expect(settings).toContain("max={selectedModel.thinking_budget_maximum}");
  });

  it("sends only non-null validated parameters with execution", () => {
    expect(streamClient).toContain("body.temperature = modelPreference.temperature");
    expect(streamClient).toContain("body.max_output_tokens = modelPreference.maxOutputTokens");
    expect(streamClient).toContain("body.thinking_budget = modelPreference.thinkingBudget");
    expect(streamClient).toContain("modelPreference.thinkingBudget !== null");
  });
});
