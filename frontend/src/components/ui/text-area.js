"use client";

import { useLayoutEffect, useRef } from "react";

export function PromptTextArea({ value, onChange, onSubmit, disabled }) {
  const elementRef = useRef(null);

  useLayoutEffect(() => {
    const element = elementRef.current;
    if (!element) {
      return;
    }
    element.style.height = "0px";
<<<<<<< Updated upstream
    element.style.height = `${Math.min(element.scrollHeight, 240)}px`;
=======
    element.style.height = `${Math.min(element.scrollHeight, 220)}px`;
>>>>>>> Stashed changes
  }, [value]);

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!disabled && value.trim()) {
        onSubmit();
      }
    }
  }

  return (
    <textarea
      ref={elementRef}
      className="prompt-textarea"
<<<<<<< Updated upstream
      aria-label="Pipeline prompt"
      placeholder="Describe the task for the execution graph…"
=======
      aria-label="Message"
      placeholder="Message Fugu…"
>>>>>>> Stashed changes
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={handleKeyDown}
      disabled={disabled}
      rows={1}
    />
  );
}
