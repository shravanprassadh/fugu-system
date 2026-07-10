import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function readFrontendFile(path) {
  return readFileSync(resolve(frontendRoot, path), "utf8");
}

describe("versioned pipeline builder", () => {
  const apiClient = readFrontendFile("src/lib/api-client.js");
  const builder = readFrontendFile("src/app/settings/pipeline-builder-card.js");
  const modelSettings = readFrontendFile("src/app/settings/model-preference-card.js");

  it("uses versioned draft, publication, rollback, and deletion endpoints", () => {
    for (const path of [
      "/api/admin/pipeline-versions",
      "/drafts",
      "/validate",
      "/publish",
      "/rollback",
    ]) {
      expect(apiClient).toContain(path);
    }
    expect(apiClient).not.toContain("/api/admin/pipeline-steps");
    expect(apiClient).toContain("acceptedStatuses: [422]");
  });

  it("exposes the builder only to administrators", () => {
    expect(modelSettings).toContain('userRole === "admin" ? <PipelineBuilderCard /> : null');
    expect(builder).toContain('role="dialog"');
    expect(builder).toContain('aria-labelledby="pipeline-builder-title"');
  });

  it("supports complete structured stage editing", () => {
    for (const control of [
      "Stable identifier",
      "Display name",
      "System instructions",
      "Prerequisite stages",
      "Required model capabilities",
      "Fallback provider",
      "Fallback model",
      "Timeout in seconds",
      "Retry count",
      "Input policy JSON",
      "Output policy JSON",
    ]) {
      expect(builder).toContain(control);
    }
    expect(builder).toContain("Add stage");
    expect(builder).toContain("onDuplicate={handleDuplicateStage}");
    expect(builder).toContain("onMove={(identifier, direction)");
    expect(builder).toContain("onRemove={handleRemoveStage}");
  });

  it("saves before validation and publication", () => {
    expect(builder).toContain("const saved = await persistDraft({ announce: false });");
    expect(builder).toContain("await validatePipelineDraft(saved.id)");
    expect(builder).toContain("await publishPipelineDraft(saved.id)");
  });

  it("keeps immutable history separate from draft actions", () => {
    expect(builder).toContain('pipeline.state === "draft"');
    expect(builder).toContain("Create draft from this version");
    expect(builder).toContain("Roll back to this version");
    expect(builder).toContain("Delete draft");
  });
});
