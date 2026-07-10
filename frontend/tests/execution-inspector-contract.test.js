import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function readFrontendFile(path) {
  return readFileSync(resolve(frontendRoot, path), "utf8");
}

describe("execution inspector surface", () => {
  const page = readFrontendFile("src/app/runs/page.js");
  const client = readFrontendFile("src/lib/execution-api.js");
  const sidebar = readFrontendFile("src/components/sidebar.js");

  it("links administrators to a dedicated run workspace", () => {
    expect(sidebar).toContain('userRole === "admin"');
    expect(sidebar).toContain('href="/runs"');
    expect(sidebar).toContain("Execution inspector");
    expect(page).toContain('router.replace("/chat")');
  });

  it("exposes complete history filters and sanitised stage diagnostics", () => {
    for (const label of [
      "Run status",
      "User ID",
      "Provider",
      "Model",
      "Thread ID",
      "Date from",
      "Date to",
    ]) {
      expect(page).toContain(`aria-label="${label}"`);
    }
    expect(page).toContain("sanitised_input");
    expect(page).toContain("sanitised_output");
    expect(page).toContain("actual_retry_count");
    expect(page).toContain("input_token_usage");
    expect(page).toContain("side_effect_free");
  });

  it("wires export, cancellation, whole-run retry, and safe stage retry", () => {
    expect(page).toContain("exportExecutionDiagnostics");
    expect(page).toContain("cancelExecutionRun");
    expect(page).toContain("retryExecutionRun");
    expect(page).toContain("retryExecutionStage");
    expect(page).toContain('stage.status === "failed" && stage.side_effect_free');
    expect(page).toContain("navigator.clipboard.writeText");
  });

  it("targets only the admin execution control-plane endpoints", () => {
    expect(client).toContain("/api/admin/execution-runs");
    expect(client).toContain("/diagnostics");
    expect(client).toContain("/cancel");
    expect(client).toContain("/retry");
    expect(client).toContain("encodeURIComponent(stageName)");
  });
});
