import { expect, test } from "@playwright/test";

const sessionToken = "e2e-session-token";
const thread = {
  id: 101,
  name: "Explain phase one",
  created_at: "2026-07-10T07:30:00Z",
};

function jsonResponse(route, payload, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

function executionStream() {
  return [
    'event: run_started\ndata: {"event":"run_started","run_id":501}\n\n',
    'event: step_started\ndata: {"event":"step_started","run_id":501,"step_name":"Consolidator"}\n\n',
    'event: token\ndata: {"event":"token","token":"Verified baseline "}\n\n',
    'event: token\ndata: {"event":"token","token":"response."}\n\n',
    'event: run_completed\ndata: {"event":"run_completed","run_id":501}\n\n',
  ].join("");
}

function memoryPayload(hasMemory) {
  return {
    thread_id: thread.id,
    status: "completed",
    has_memory: hasMemory,
    summary_md: hasMemory
      ? "# Thread Memory\n\n## Objective\n- Stabilise the Fugu baseline before adding new systems."
      : "",
    last_summarized_message_id: hasMemory ? 22 : null,
    summarizer_provider: "google-ai-studio",
    summarizer_model: "gemini-2.5-flash-lite",
    updated_at: hasMemory ? "2026-07-10T07:32:00Z" : null,
    error_message: null,
  };
}

async function installDeterministicApi(page) {
  const requests = [];
  let threadExists = false;
  let memoryBuilt = false;

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    requests.push({
      path,
      method,
      authorization: request.headers().authorization ?? null,
    });

    if (path === "/api/auth/login" && method === "POST") {
      return jsonResponse(route, { access_token: sessionToken, token_type: "bearer" });
    }
    if (path === "/api/auth/me" && method === "GET") {
      return jsonResponse(route, { id: 7, username: "developer", role: "user", is_active: true });
    }
    if (path === "/api/auth/logout" && method === "POST") {
      return route.fulfill({ status: 204, body: "" });
    }
    if (path === "/api/threads" && method === "GET") {
      return jsonResponse(route, threadExists ? [thread] : []);
    }
    if (path === "/api/threads" && method === "POST") {
      threadExists = true;
      return jsonResponse(route, thread, 201);
    }
    if (path === `/api/threads/${thread.id}/execute` && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        headers: { "Cache-Control": "no-cache" },
        body: executionStream(),
      });
    }
    if (path === "/api/admin/thread-memory/config" && method === "GET") {
      return jsonResponse(route, {
        configured: true,
        provider_name: "google-ai-studio",
        model_identifier: "gemini-2.5-flash-lite",
        credential_key_version: 3,
        updated_at: "2026-07-10T07:31:00Z",
      });
    }
    if (path === `/api/threads/${thread.id}/memory` && method === "GET") {
      return jsonResponse(route, memoryPayload(memoryBuilt));
    }
    if (path === `/api/threads/${thread.id}/memory/regenerate` && method === "POST") {
      memoryBuilt = true;
      return jsonResponse(route, memoryPayload(true));
    }
    if (path === "/api/health/ready" && method === "GET") {
      return jsonResponse(route, {
        status: "ready",
        connections: { master: "ready", metadata: "ready", logs: "ready" },
      });
    }

    return jsonResponse(route, { detail: `Unexpected E2E request: ${method} ${path}` }, 500);
  });

  return requests;
}

test("completes the core chat and memory journey", async ({ page }) => {
  const requests = await installDeterministicApi(page);

  await page.goto("/");
  await page.getByLabel("Username").fill("developer");
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByRole("heading", { name: "New conversation" })).toBeVisible();

  const messageBox = page.getByRole("textbox", { name: "Message" });
  await messageBox.fill("Explain phase one");
  await messageBox.press("Enter");

  await expect(page.locator(".message-user").getByText("Explain phase one", { exact: true })).toBeVisible();
  await expect(page.getByText("Verified baseline response.", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Open thread memory summary" }).click();
  const memoryDialog = page.getByRole("dialog", { name: "Current thread memory" });
  await expect(memoryDialog).toBeVisible();
  await memoryDialog.getByRole("button", { name: "Rebuild" }).click();

  await expect(memoryDialog.getByText("Stabilise the Fugu baseline before adding new systems.")).toBeVisible();
  await expect(memoryDialog.getByText("Through message 22", { exact: true })).toBeVisible();
  await expect(memoryDialog.getByText("available", { exact: true })).toBeVisible();
  await memoryDialog.getByRole("button", { name: "Close" }).click();

  await page.getByRole("button", { name: "Open settings" }).click();
  const settingsDialog = page.getByRole("dialog");
  await expect(settingsDialog).toBeVisible();
  await settingsDialog.getByRole("button", { name: "Log out" }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();

  await page.goto("/chat");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();

  expect(requests).toContainEqual({
    path: `/api/threads/${thread.id}/execute`,
    method: "POST",
    authorization: `Bearer ${sessionToken}`,
  });
  expect(requests).toContainEqual({
    path: `/api/threads/${thread.id}/memory/regenerate`,
    method: "POST",
    authorization: `Bearer ${sessionToken}`,
  });
  expect(requests).toContainEqual({
    path: "/api/auth/logout",
    method: "POST",
    authorization: `Bearer ${sessionToken}`,
  });
});
