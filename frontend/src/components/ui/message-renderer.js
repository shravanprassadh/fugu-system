"use client";

import { createElement, Fragment, useState } from "react";

export function SafePlaintextRenderer({ rawContentText = "" }) {
  const lines = String(rawContentText).split("\n");
  return createElement(
    "div",
    { className: "message-text" },
    lines.map((line, index) =>
      createElement(
        "span",
        { className: "message-line", key: `${index}-${line.length}` },
        line || "\u00a0",
      ),
    ),
  );
}

/*
 * SafeMarkdownRenderer renders a restricted markdown subset by building React
 * elements only. It never uses dangerouslySetInnerHTML and never interprets
 * raw HTML, so `<script>` or `<img onerror=…>` in model output stays inert
 * escaped text — the same safety boundary as SafePlaintextRenderer.
 *
 * Supported blocks: fenced code, headings (#, ##, ###), unordered and ordered
 * lists, blockquotes, horizontal rules, paragraphs.
 * Supported inline: `code`, **bold**, *italic*, and [links](https://…) where
 * only http/https destinations become anchors.
 */

const INLINE_TOKEN_PATTERN = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[[^\]\n]+\]\((?:https?:\/\/)[^)\s]+\))/;

function renderInline(text, keyPrefix) {
  const segments = String(text).split(INLINE_TOKEN_PATTERN);
  return segments.map((segment, index) => {
    const key = `${keyPrefix}-${index}`;
    if (!segment) {
      return null;
    }
    if (segment.startsWith("`") && segment.endsWith("`") && segment.length > 2) {
      return createElement("code", { className: "md-inline-code", key }, segment.slice(1, -1));
    }
    if (segment.startsWith("**") && segment.endsWith("**") && segment.length > 4) {
      return createElement("strong", { key }, renderInline(segment.slice(2, -2), key));
    }
    if (segment.startsWith("*") && segment.endsWith("*") && segment.length > 2 && !segment.startsWith("**")) {
      return createElement("em", { key }, renderInline(segment.slice(1, -1), key));
    }
    if (segment.startsWith("[")) {
      const closingBracket = segment.indexOf("](");
      const label = segment.slice(1, closingBracket);
      const href = segment.slice(closingBracket + 2, -1);
      if (href.startsWith("http://") || href.startsWith("https://")) {
        return createElement(
          "a",
          { key, href, target: "_blank", rel: "noopener noreferrer", className: "md-link" },
          label,
        );
      }
      return createElement(Fragment, { key }, segment);
    }
    return createElement(Fragment, { key }, segment);
  });
}

function CodeBlock({ language, code }) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard access can be denied; the button simply stays in its idle state.
    }
  }

  // Built with createElement (no JSX) so this module stays parseable by
  // Vitest's plain-JS pipeline, matching the rest of this file.
  return createElement(
    "div",
    { className: "md-code-block" },
    createElement(
      "div",
      { className: "md-code-header" },
      createElement("span", { className: "md-code-language" }, language || "code"),
      createElement(
        "button",
        { type: "button", className: "md-code-copy", onClick: copyCode },
        copied ? "Copied" : "Copy",
      ),
    ),
    createElement("pre", null, createElement("code", null, code)),
  );
}

function flushParagraph(blocks, pendingLines, keyPrefix) {
  if (pendingLines.length === 0) {
    return;
  }
  const key = `${keyPrefix}-p-${blocks.length}`;
  const children = [];
  pendingLines.forEach((line, index) => {
    if (index > 0) {
      children.push(createElement("br", { key: `${key}-br-${index}` }));
    }
    children.push(
      createElement(Fragment, { key: `${key}-l-${index}` }, renderInline(line, `${key}-l-${index}`)),
    );
  });
  blocks.push(createElement("p", { className: "md-paragraph", key }, children));
  pendingLines.length = 0;
}

function flushList(blocks, listState, keyPrefix) {
  if (!listState.items.length) {
    return;
  }
  const key = `${keyPrefix}-list-${blocks.length}`;
  blocks.push(
    createElement(
      listState.ordered ? "ol" : "ul",
      { className: "md-list", key },
      listState.items.map((item, index) =>
        createElement("li", { key: `${key}-${index}` }, renderInline(item, `${key}-${index}`)),
      ),
    ),
  );
  listState.items = [];
}

export function SafeMarkdownRenderer({ rawContentText = "" }) {
  const lines = String(rawContentText).split("\n");
  const blocks = [];
  const pendingParagraph = [];
  const listState = { ordered: false, items: [] };
  let codeState = null;

  const flushText = () => {
    flushList(blocks, listState, "md");
    flushParagraph(blocks, pendingParagraph, "md");
  };

  lines.forEach((rawLine, lineIndex) => {
    if (codeState) {
      if (rawLine.trimEnd() === "```") {
        blocks.push(
          createElement(CodeBlock, {
            key: `md-code-${blocks.length}`,
            language: codeState.language,
            code: codeState.lines.join("\n"),
          }),
        );
        codeState = null;
      } else {
        codeState.lines.push(rawLine);
      }
      return;
    }

    const line = rawLine.trimEnd();
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      flushText();
      codeState = { language: trimmed.slice(3).trim().slice(0, 24), lines: [] };
      return;
    }
    if (trimmed === "") {
      flushText();
      return;
    }
    const headingMatch = /^(#{1,3})\s+(.*)$/.exec(trimmed);
    if (headingMatch) {
      flushText();
      const level = headingMatch[1].length;
      blocks.push(
        createElement(
          `h${level + 2}`,
          { className: `md-heading md-heading-${level}`, key: `md-h-${lineIndex}` },
          renderInline(headingMatch[2], `md-h-${lineIndex}`),
        ),
      );
      return;
    }
    if (/^(---|\*\*\*|___)$/.test(trimmed)) {
      flushText();
      blocks.push(createElement("hr", { className: "md-rule", key: `md-hr-${lineIndex}` }));
      return;
    }
    if (trimmed.startsWith("> ")) {
      flushText();
      blocks.push(
        createElement(
          "blockquote",
          { className: "md-quote", key: `md-q-${lineIndex}` },
          renderInline(trimmed.slice(2), `md-q-${lineIndex}`),
        ),
      );
      return;
    }
    const unorderedMatch = /^[-*]\s+(.*)$/.exec(trimmed);
    const orderedMatch = /^\d{1,3}\.\s+(.*)$/.exec(trimmed);
    if (unorderedMatch || orderedMatch) {
      flushParagraph(blocks, pendingParagraph, "md");
      const ordered = Boolean(orderedMatch);
      if (listState.items.length && listState.ordered !== ordered) {
        flushList(blocks, listState, "md");
      }
      listState.ordered = ordered;
      listState.items.push(ordered ? orderedMatch[1] : unorderedMatch[1]);
      return;
    }
    flushList(blocks, listState, "md");
    pendingParagraph.push(line);
  });

  if (codeState) {
    // An unterminated fence (common mid-stream) still renders as code.
    blocks.push(
      createElement(CodeBlock, {
        key: `md-code-${blocks.length}`,
        language: codeState.language,
        code: codeState.lines.join("\n"),
      }),
    );
  }
  flushText();

  return createElement("div", { className: "message-markdown" }, blocks);
}
