import { createElement } from "react";

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
