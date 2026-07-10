import { expect, test } from "@playwright/test";

const sessionToken = "execution-inspector-session";

function jsonResponse(route, payload, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

function runSummary(overrides = {}) {
  return {
    id: 88,
    thread_id: 101,
    thread_name: "Investigate failed answer",
    user_id: 7,
    username: "developer",
    pipeline_version_id: 4,
    pipeline_version_number: 4,
    source_run_id: null,
    retry_kind: null,
    retry_stage_name: null,
    status: "failed",
    started_at: "2026-07-10T09:00:00Z",
    completed_at: "2026-07-10T09:00:03Z",
    latency_ms: 3000,
    failed_stage: "verifier",
    error_category: "provider_timeout",
    error_message: "The verifier stage timed out while waiting for the configured provider.",
    retryable: true,
    ...overrides,
  };
}

function runDetail(overrides = {}) {
  const summary = runSummary(overrides);
  return {
    ...summary,
    final_result: null,
    cancellation_requested_at: null,
    cancelled_at: null,
    stages: [
      {
        id: 1,
        step_name: "reader",
        display_name: "Reader",
        provider: "openrouter",
        model: "openrouter/free",
        status: "completed",
        started_at: "2026-07-10T09:00:00Z",
        completed_at: "2026-07-10T09:00:01Z",
        latency_ms: 1000,
        configured_retry_count: 0,
        actual_retry_count: 0,
        sanitised_input: "Current user request",
        sanitised_output: "Reader output",
        input_token_usage: 12,
        output_token_usage: 8,
        side_effect_free: true,
        error_category: null,
        error_message: null,
        retryable: null,
      },
      {
        id: 2,
        step_name: "verifier",
        display_name: "Verifier",
        provider: "openrouter",
        model: "openrouter/free",
        status: "failed",
        started_at: "2026-07-10T09:00:01Z",
        completed_at: "2026-07-10T09:00:03Z",
        latency_ms: 2000,
        configured_retry_count: 1,
        actual_retry_count: 1,
        sanitised_input: "Reader output",
        sanitised_output: "Partial safe output",
        input_token_usage: 8,
        output_token_usage: 4,
        side_effect_free: true,
        error_category: "provider_timeout",
        error_message: "The verifier stage timed out while waiting for the configured provider.",
        retryable: true,
      },
    ],
  };
}

async function installApi(page) {
  const requests = [];
  let failed = runDetail();
  let active = runDetail({
    id: 87,
    thread_name: "Long running request",
    status: "running",
    completed_at: null,
    latency_ms: null,
    failed_stage: null,
    error_category: null,
    error_message: null,
    retryable: null,
  });
  let recovery = null;

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    requests.push({ path, method, search: url.search, authorization: request.headers().authorization ?? null });

    if (path === "/api/auth/login" && method === "POST") {
      return jsonResponse(route, { access_token: sessionToken, token_type: "bearer" });
    }
    if (path === "/api/auth/me" && method === "GET") {
      return jsonResponse(route, { id: 7, username: "developer", role: "admin", is_active: true });
    }
    if (path === "/api/threads" && method === "GET") {
      return jsonResponse(route, []);
    }
    if (path === "/api/admin/execution-runs" && method === "GET") {
      const allRuns = [recovery, failed, active].filter(Boolean);
      const status = url.searchParams.get("status");
      return jsonResponse(route, status ? allRuns.filter((run) => run.status === status) : allRuns);
    }
    if (path === "/api/admin/execution-runs/88" && method === "GET") {
      return jsonResponse(route, failed);
    }
    if (path === "/api/admin/execution-runs/87" && method === "GET") {
      return jsonResponse(route, active);
    }
    if (path === "/api/admin/execution-runs/89" && method === "GET") {
      return jsonResponse(route, recovery);
    }
    if (path === "/api/admin/execution-runs/88/diagnostics" && method === "GET") {
      return jsonResponse(route, { generated_at: "2026-07-10T09:05:00Z", run: failed });
    }
    if (path === "/api/admin/execution-runs/88/stages/verifier/retry" && method === "POST") {
      recovery = runDetail({
        id: 89,
        source_run_id: 88,
        retry_kind: "stage",
        retry_stage_name: "verifier",
        status: "completed",
        failed_stage: null,
        error_category: null,
        error_message: null,
        retryable: null,
        final_result: "Recovered answer",
      });
      recovery.final_result = "Recovered answer";
      recovery.stages = recovery.stages.map((stage) => ({
        ...stage,
        status: "completed",
        error_category: null,
        error_message: null,
        retryable: null,
      }));
      return jsonResponse(route, {
        run_id: 89,
        status: "running",
        source_run_id: 88,
        retry_kind: "stage",
        retry_stage_name: "verifier",
      }, 202);
    }
    if (path === "/api/admin/execution-runs/87/cancel" && method === "POST") {
      active = {
        ...active,
        status: "cancelled",
        completed_at: "2026-07-10T09:06:00Z",
        cancellation_requested_at: "2026-07-10T09:05:59Z",
        cancelled_at: "2026-07-10T09:06:00Z",
        error_category: "cancelled",
        error_message: "The pipeline was cancelled before completion.",
        retryable: true,
      };
      return jsonResponse(route, { run_id: 87, status: "cancelling" }, 202);
    }

    return jsonResponse(route, { detail: `Unexpected E2E request: ${method} ${path}` }, 500);
  });

  return requests;
}

test("inspects a failed run, copies diagnostics, retries its stage, and cancels an active run", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const requests = await installApi(page);

  await page.goto("/");
  await page.getByLabel("Username").fill("developer");
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/chat$/);

  await page.getByRole("link", { name: "Execution inspector" }).click();
  await expect(page).toHaveURL(/\/runs$/);
  await expect(page.getByRole("heading", { name: "Execution inspector" })).toBeVisible();
  await expect(page.getByText("Failed at verifier")).toBeVisible();

  await page.getByLabel("Run status").selectOption("failed");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByRole("button", { name: "Inspect run 88" })).toBeVisible();
  expect(requests.some((item) => item.path === "/api/admin/execution-runs" && item.search.includes("status=failed"))).toBe(true);

  await page.getByRole("button", { name: "Copy diagnostics" }).click();
  await expect(page.getByText("Copied sanitised diagnostics for run #88.")).toBeVisible();
  const clipboard = await page.evaluate(() => navigator.clipboard.readText());
  expect(clipboard).toContain('"run"');
  expect(clipboard).not.toContain("private-provider-key");

  await page.getByRole("button", { name: "Retry failed stage" }).click();
  await expect(page.getByText("Created stage retry run #89 from run #88.")).toBeVisible();
  await expect(page.getByText("stage retry of #88")).toBeVisible();
  await expect(page.getByText("Recovered answer")).toBeVisible();

  await page.getByRole("button", { name: "Clear" }).click();
  await page.getByRole("button", { name: "Inspect run 87" }).click();
  await expect(page.getByRole("button", { name: "Cancel run" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel run" }).click();
  await expect(page.getByText("Run #87 is cancelling.")).toBeVisible();
  await expect(page.getByText("cancelled", { exact: true }).first()).toBeVisible();

  for (const expected of [
    ["/api/admin/execution-runs/88/diagnostics", "GET"],
    ["/api/admin/execution-runs/88/stages/verifier/retry", "POST"],
    ["/api/admin/execution-runs/87/cancel", "POST"],
  ]) {
    expect(requests).toContainEqual(expect.objectContaining({
      path: expected[0],
      method: expected[1],
      authorization: `Bearer ${sessionToken}`,
    }));
  }
});
