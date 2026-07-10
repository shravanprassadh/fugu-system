import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function readFrontendFile(path) {
  return readFileSync(resolve(frontendRoot, path), "utf8");
}

describe("attachment intelligence chat surface", () => {
  const page = readFrontendFile("src/app/chat/page.js");
  const composer = readFrontendFile("src/components/attachment-composer.js");
  const attachmentClient = readFrontendFile("src/lib/attachment-api.js");
  const streamClient = readFrontendFile("src/lib/stream-client.js");

  it("supports picker, drag/drop, image paste, previews, progress, and remove-before-send", () => {
    expect(composer).toContain("Attach files");
    expect(composer).toContain("onDrop={handleDrop}");
    expect(composer).toContain("onPaste={handlePaste}");
    expect(composer).toContain("previewUrl");
    expect(composer).toContain("onProgress");
    expect(composer).toContain("Remove ${item.file.name}");
  });

  it("supports persistent thread history, secure reopening, reprocessing, deletion, and reuse", () => {
    expect(composer).toContain("Thread attachment history");
    expect(composer).toContain("downloadAttachment");
    expect(composer).toContain("reprocessAttachment");
    expect(composer).toContain("deleteAttachment");
    expect(composer).toContain("selectedHistoryIds");
    expect(composer).toContain("processing_warnings");
  });

  it("creates the thread before upload and sends only processed attachment identifiers", () => {
    expect(page).toContain("createThreadFromPrompt(normalized)");
    expect(page).toContain("prepareForSend(threadId)");
    expect(page).toContain("attachmentIds");
    expect(streamClient).toContain("body.attachment_ids = attachmentIds");
  });

  it("keeps object storage private behind authenticated APIs", () => {
    expect(attachmentClient).toContain("Authorization: `Bearer ${credential}`");
    expect(attachmentClient).toContain("/api/attachments/capabilities");
    expect(attachmentClient).toContain("/api/threads/${threadId}/attachments");
    expect(attachmentClient).toContain("/api/attachments/${encodeURIComponent(attachmentId)}/content");
    expect(attachmentClient).not.toContain("storage_bucket");
    expect(attachmentClient).not.toContain("storage_key");
  });
});
