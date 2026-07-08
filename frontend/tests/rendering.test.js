import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SafePlaintextRenderer } from "../src/components/ui/message-renderer";

describe("plaintext rendering boundary", () => {
  it("encodes executable element text instead of creating an element", () => {
    const rawText = Buffer.from(
      "PHNjcmlwdD5leGFtcGxlPC9zY3JpcHQ+",
      "base64",
    ).toString("utf8");
    const markup = renderToStaticMarkup(
      createElement(SafePlaintextRenderer, { rawContentText: rawText }),
    );

    expect(markup).not.toContain(rawText);
    expect(markup).toContain("&lt;script&gt;");
    expect(markup).toContain("&lt;/script&gt;");
  });

  it("preserves line boundaries without interpreting markup", () => {
    const markup = renderToStaticMarkup(
      createElement(SafePlaintextRenderer, {
        rawContentText: "first\n<strong>second</strong>",
      }),
    );

    expect(markup).toContain("first");
    expect(markup).toContain("&lt;strong&gt;second&lt;/strong&gt;");
  });
});
