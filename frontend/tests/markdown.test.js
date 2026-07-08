import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SafeMarkdownRenderer } from "../src/components/ui/message-renderer";

function renderMarkdown(rawContentText) {
  return renderToStaticMarkup(createElement(SafeMarkdownRenderer, { rawContentText }));
}

describe("markdown rendering safety boundary", () => {
  it("keeps raw HTML escaped instead of creating elements", () => {
    const rawText = Buffer.from("PHNjcmlwdD5leGFtcGxlPC9zY3JpcHQ+", "base64").toString("utf8");
    const markup = renderMarkdown(`Intro line\n\n${rawText}`);

    expect(markup).not.toContain(rawText);
    expect(markup).toContain("&lt;script&gt;");
    expect(markup).toContain("&lt;/script&gt;");
  });

  it("keeps raw HTML escaped inside code fences", () => {
    const markup = renderMarkdown("```html\n<strong>bold</strong>\n```");

    expect(markup).toContain("<pre>");
    expect(markup).toContain("&lt;strong&gt;bold&lt;/strong&gt;");
    expect(markup).not.toContain("<strong>bold</strong>");
  });

  it("only turns http and https destinations into anchors", () => {
    const safe = renderMarkdown("[docs](https://example.com/docs)");
    const unsafe = renderMarkdown("[click](javascript:alert(1))");

    expect(safe).toContain('href="https://example.com/docs"');
    expect(safe).toContain('rel="noopener noreferrer"');
    expect(unsafe).not.toContain("<a");
    expect(unsafe).not.toContain("href=");
  });
});

describe("markdown rendering features", () => {
  it("renders emphasis, inline code, headings, and lists", () => {
    const markup = renderMarkdown(
      "# Title\n\nSome **bold** and `code` text.\n\n- first\n- second\n\n1. one\n2. two",
    );

    expect(markup).toContain("<h3");
    expect(markup).toContain("<strong>bold</strong>");
    expect(markup).toContain(">code</code>");
    expect(markup).toContain("<ul");
    expect(markup).toContain("<ol");
    expect(markup).toContain("<li>first</li>");
  });

  it("renders an unterminated fence as code so mid-stream output stays stable", () => {
    const markup = renderMarkdown("```python\nprint('partial')");

    expect(markup).toContain("<pre>");
    expect(markup).toContain("print(&#x27;partial&#x27;)");
  });

  it("renders blockquotes and horizontal rules", () => {
    const markup = renderMarkdown("> quoted insight\n\n---");

    expect(markup).toContain("<blockquote");
    expect(markup).toContain("quoted insight");
    expect(markup).toContain("<hr");
  });
});
