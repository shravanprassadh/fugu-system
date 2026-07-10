import { expect, test } from "@playwright/test";

const sessionToken = "e2e-session-token";
const thread = {
  id: 101,
  name: "Explain phase one",
  created_at: "2026-07-10T07:30:00Z",
};

const providerCatalogue = {
  providers: [
    {
      identifier: "openrouter",
      display_name: "OpenRouter",
      authentication_type: "bearer_api_key",
      adapter_available: true,
      health_status: "available",
      api_base_url: "https://openrouter.ai/api/v1",
      capabilities: {
        text_generation: true,
        image_understanding: false,
        document_input: false,
        tool_support: false,
        reasoning_support: false,
      },
      models: [
        {
          identifier: "openrouter/free",
          display_name: "OpenRouter Free Tier",
          capabilities: {
            text_generation: true,
            image_understanding: false,
            document_input: false,
            tool_support: false,
            reasoning_support: false,
          },
          context_size: 32768,
          output_limit: 4096,
          temperature: { minimum: 0, maximum: 2, default: 0.7 },
          thinking_budget_minimum: null,
          thinking_budget_maximum: null,
          supported_parameters: ["temperature", "max_output_tokens"],
          availability_status: "available",
        },
      ],
    },
  ],
};

function stage(identifier, position, prerequisites = [], terminal = false) {
  return {
    id: position,
    stable_identifier: identifier,
    name: identifier[0].toUpperCase() + identifier.slice(1),
    description: `${identifier} stage`,
    enabled: true,
    position,
    provider_type: "openrouter",
    model_string: "openrouter/free",
    system_prompt_directives: `Execute ${identifier}.`,
    prerequisite_dependencies: prerequisites,
    is_terminal: terminal,
    temperature: 0.7,
    thinking_budget: null,
    token_limit: 1024,
    timeout_seconds: 45,
    retry_count: 0,
    fallback_provider_type: null,
    fallback_model_string: null,
    input_policy: {},
    output_policy: {},
    required_capabilities: ["text_generation"],
  };
}

function versionPayload({ id, number, state, stages, description, validation = "valid" }) {
  return {
    id,
    version_number: number,
    state,
    change_description: description,
    validation_status: validation,
    validation_issues: [],
    stage_count: stages.length,
    created_by_user_id: 7,
    created_at: "2026-07-10T07:20:00Z",
    validated_at: validation === "pending" ? null : "2026-07-10T07:21:00Z",
    published_at: state === "published" ? "2026-07-10T07:22:00Z" : null,
    stages,
  };
}

function summary(version) {
  const { stages, ...rest } = version;
  return { ...rest, stage_count: stages.length };
}

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
  const publishedStages = [stage("reader", 1), stage("consolidator", 2, ["reader"], true)];
  let published = versionPayload({
    id: 1,
    number: 1,
    state: "published",
    stages: publishedStages,
    description: "Initial pipeline",
  });
  let draft = null;

  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    let requestBody = null;
    try {
      requestBody = request.postDataJSON();
    } catch {
      requestBody = null;
    }

    requests.push({
      path,
      method,
      authorization: request.headers().authorization ?? null,
      body: requestBody,
    });

    if (path === "/api/auth/login" && method === "POST") {
      return jsonResponse(route, { access_token: sessionToken, token_type: "bearer" });
    }
    if (path === "/api/auth/me" && method === "GET") {
      return jsonResponse(route, { id: 7, username: "developer", role: "admin", is_active: true });
    }
    if (path === "/api/auth/logout" && method === "POST") {
      return route.fulfill({ status: 204, body: "" });
    }
    if (path === "/api/admin/users" && method === "GET") {
      return jsonResponse(route, [
        {
          id: 7,
          username: "developer",
          role: "admin",
          is_active: true,
          token_version: 0,
          created_at: "2026-07-10T07:00:00Z",
          thread_count: 1,
        },
      ]);
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
    if (path === "/api/providers/catalogue" && method === "GET") {
      return jsonResponse(route, providerCatalogue);
    }
    if (path === "/api/admin/provider-credentials" && method === "GET") {
      return jsonResponse(route, []);
    }
    if (path === "/api/admin/pipeline-versions" && method === "GET") {
      return jsonResponse(route, [draft, published].filter(Boolean).map(summary));
    }
    if (path === "/api/admin/pipeline-versions/drafts" && method === "POST") {
      draft = versionPayload({
        id: 2,
        number: 2,
        state: "draft",
        stages: published.stages.map((item) => ({ ...item })),
        description: requestBody.change_description,
        validation: "pending",
      });
      return jsonResponse(route, draft, 201);
    }
    if (path === "/api/admin/pipeline-versions/1" && method === "GET") {
      return jsonResponse(route, published);
    }
    if (path === "/api/admin/pipeline-versions/2" && method === "GET") {
      return jsonResponse(route, draft);
    }
    if (path === "/api/admin/pipeline-versions/2" && method === "PUT") {
      draft = {
        ...draft,
        change_description: requestBody.change_description,
        validation_status: "pending",
        validation_issues: [],
        stages: requestBody.stages.map((item, index) => ({ ...item, id: 20 + index })),
        stage_count: requestBody.stages.length,
      };
      return jsonResponse(route, draft);
    }
    if (path === "/api/admin/pipeline-versions/2/validate" && method === "POST") {
      draft = { ...draft, validation_status: "valid", validated_at: "2026-07-10T08:00:00Z" };
      return jsonResponse(route, { version: draft, valid: true, issues: [] });
    }
    if (path === "/api/admin/pipeline-versions/2/publish" && method === "POST") {
      published = {
        ...draft,
        state: "published",
        validation_status: "valid",
        published_at: "2026-07-10T08:01:00Z",
      };
      draft = null;
      return jsonResponse(route, { version: published, valid: true, issues: [], published: true });
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

test("completes chat, memory, and pipeline publication journeys", async ({ page }) => {
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
  await settingsDialog.getByRole("button", { name: "Model" }).click();
  await settingsDialog.getByRole("button", { name: "Open pipeline builder" }).click();

  const pipelineDialog = page.getByRole("dialog", { name: "Pipeline builder" });
  await expect(pipelineDialog).toBeVisible();
  await expect(pipelineDialog.getByRole("heading", { name: "Version 1" })).toBeVisible();
  await pipelineDialog.getByLabel("Change description").fill("Add a verifier stage");
  await pipelineDialog.getByRole("button", { name: "Create draft from this version" }).click();
  await expect(pipelineDialog.getByText("Draft version 2 created.")).toBeVisible();

  await pipelineDialog.getByRole("button", { name: "Add stage" }).click();
  await pipelineDialog.getByLabel("Display name").fill("Verifier");
  await pipelineDialog.getByLabel("Stable identifier").fill("verifier");
  await pipelineDialog.getByRole("button", { name: "Move Verifier up" }).click();
  await pipelineDialog.getByRole("button", { name: "Validate" }).click();
  await expect(pipelineDialog.getByText("Draft validation passed.")).toBeVisible();
  await pipelineDialog.getByRole("button", { name: "Publish", exact: true }).click();
  await expect(pipelineDialog.getByText("Pipeline version 2 is now published.")).toBeVisible();
  await pipelineDialog.getByRole("button", { name: "Close" }).click();

  await settingsDialog.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();

  expect(requests).toEqual(
    expect.arrayContaining([
      expect.objectContaining({
        path: `/api/threads/${thread.id}/execute`,
        method: "POST",
        authorization: `Bearer ${sessionToken}`,
      }),
      expect.objectContaining({
        path: `/api/threads/${thread.id}/memory/regenerate`,
        method: "POST",
        authorization: `Bearer ${sessionToken}`,
      }),
      expect.objectContaining({ path: "/api/admin/pipeline-versions/drafts", method: "POST" }),
      expect.objectContaining({ path: "/api/admin/pipeline-versions/2", method: "PUT" }),
      expect.objectContaining({ path: "/api/admin/pipeline-versions/2/validate", method: "POST" }),
      expect.objectContaining({ path: "/api/admin/pipeline-versions/2/publish", method: "POST" }),
      expect.objectContaining({
        path: "/api/auth/logout",
        method: "POST",
        authorization: `Bearer ${sessionToken}`,
      }),
    ]),
  );
});
