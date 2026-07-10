import { expect, test } from "@playwright/test";

const sessionToken = "attachment-e2e-token";
const thread = {
  id: 401,
  name: "Review evidence",
  created_at: "2026-07-10T13:00:00Z",
};
const attachment = {
  id: "00000000-0000-4000-8000-000000000401",
  thread_id: thread.id,
  message_id: null,
  filename: "evidence.txt",
  mime_type: "text/plain",
  extension: "txt",
  size_bytes: 24,
  upload_status: "uploaded",
  processing_status: "ready",
  retention_status: "active",
  processing_version: "document-v1",
  processing_warnings: [],
  processing_error_code: null,
  processing_error_message: null,
  created_at: "2026-07-10T13:01:00Z",
  uploaded_at: "2026-07-10T13:01:01Z",
  processed_at: "2026-07-10T13:01:02Z",
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
    'event: run_started\ndata: {"event":"run_started","run_id":901}\n\n',
    'event: step_started\ndata: {"event":"step_started","run_id":901,"step_name":"Reader"}\n\n',
    'event: token\ndata: {"event":"token","token":"Attachment understood."}\n\n',
    'event: run_completed\ndata: {"event":"run_completed","run_id":901}\n\n',
  ].join("");
}

async function installAttachmentApi(page) {
  const requests = [];
  const executeBodies = [];
  let threadExists = false;
  let attachmentExists = false;

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    requests.push({ path, method, authorization: request.headers().authorization || null });

    if (path === "/api/auth/login" && method === "POST") {
      return jsonResponse(route, { access_token: sessionToken, token_type: "bearer" });
    }
    if (path === "/api/auth/me" && method === "GET") {
      return jsonResponse(route, { id: 7, username: "developer", role: "admin", is_active: true });
    }
    if (path === "/api/threads" && method === "GET") {
      return jsonResponse(route, threadExists ? [thread] : []);
    }
    if (path === "/api/threads" && method === "POST") {
      threadExists = true;
      return jsonResponse(route, thread, 201);
    }
    if (path === "/api/attachments/capabilities" && method === "GET") {
      return jsonResponse(route, {
        enabled: true,
        max_file_size_bytes: 26214400,
        supported_extensions: ["txt", "pdf", "png", "jpg", "jpeg", "webp", "csv", "xlsx", "docx"],
      });
    }
    if (path === `/api/threads/${thread.id}/attachments` && method === "GET") {
      return jsonResponse(route, attachmentExists ? [attachment] : []);
    }
    if (path === `/api/threads/${thread.id}/attachments` && method === "POST") {
      attachmentExists = true;
      return jsonResponse(route, attachment, 201);
    }
    if (path === `/api/attachments/${attachment.id}/content` && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "text/plain",
        headers: { "Content-Disposition": "attachment; filename=evidence.txt" },
        body: "Persistent attachment evidence",
      });
    }
    if (path === `/api/threads/${thread.id}/execute` && method === "POST") {
      executeBodies.push(request.postDataJSON());
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: executionStream(),
      });
    }
    if (path === `/api/threads/${thread.id}/messages` && method === "GET") {
      return jsonResponse(route, []);
    }
    if (path === `/api/threads/${thread.id}/memory` && method === "GET") {
      return jsonResponse(route, {
        thread_id: thread.id,
        status: "idle",
        has_memory: false,
        summary_md: "",
        last_summarized_message_id: null,
        summarizer_provider: "google-ai-studio",
        summarizer_model: "gemini-2.5-flash-lite",
        updated_at: null,
        error_message: null,
      });
    }
    return jsonResponse(route, { detail: `Unexpected attachment E2E request: ${method} ${path}` }, 500);
  });

  return { requests, executeBodies };
}

test("uploads, processes, sends, reopens, and reuses a thread attachment", async ({ page }) => {
  const api = await installAttachmentApi(page);

  await page.goto("/");
  await page.getByLabel("Username").fill("developer");
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/chat$/);

  await page.locator('input[type="file"]').setInputFiles({
    name: "evidence.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Persistent attachment evidence"),
  });
  await expect(page.getByText("evidence.txt", { exact: true })).toBeVisible();
  await expect(page.getByText("Ready to upload", { exact: true })).toBeVisible();

  const messageBox = page.getByRole("textbox", { name: "Message" });
  await messageBox.fill("Summarise the attached evidence");
  await messageBox.press("Enter");

  await expect(page.getByText("Attachment understood.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Thread files (1)" })).toBeVisible();
  expect(api.executeBodies[0]).toMatchObject({
    prompt: "Summarise the attached evidence",
    attachment_ids: [attachment.id],
  });

  await page.getByRole("button", { name: "Thread files (1)" }).click();
  await expect(page.getByRole("heading", { name: "Thread attachment history" })).toBeVisible();
  await page.getByLabel("Use evidence.txt in the next request").check();

  await messageBox.fill("Use the same evidence for a second answer");
  await messageBox.press("Enter");
  await expect.poll(() => api.executeBodies.length).toBe(2);
  expect(api.executeBodies[1]).toMatchObject({
    prompt: "Use the same evidence for a second answer",
    attachment_ids: [attachment.id],
  });
  expect(api.requests).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        path: `/api/threads/${thread.id}/attachments`,
        method: "POST",
        authorization: `Bearer ${sessionToken}`,
      }),
      expect.objectContaining({
        path: `/api/threads/${thread.id}/execute`,
        method: "POST",
        authorization: `Bearer ${sessionToken}`,
      }),
    ]),
  );
});
