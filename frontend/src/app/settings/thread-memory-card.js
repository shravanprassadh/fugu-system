"use client";

import { useCallback, useEffect, useState } from "react";

import { SafeMarkdownRenderer } from "../../components/ui/message-renderer";
import { fetchThreadMemory } from "../../lib/api-client";
import styles from "./settings.module.css";

function StatusPill({ children, tone = "neutral" }) {
  const className = `${styles.statusPill} ${styles[`statusPill${tone[0].toUpperCase()}${tone.slice(1)}`]}`;
  return <span className={className}>{children}</span>;
}

function statusTone(status) {
  if (["completed", "ready", "active"].includes(status)) {
    return "success";
  }
  if (["running", "queued", "loading"].includes(status)) {
    return "loading";
  }
  if (["failed", "error"].includes(status)) {
    return "danger";
  }
  return "neutral";
}

function formatTimestamp(value) {
  if (!value) {
    return "Not available";
  }
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function ThreadMemoryCard({ activeThreadId, activeThreadName, onUnauthorized }) {
  const [memory, setMemory] = useState(null);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");

  const loadMemory = useCallback(async () => {
    if (!activeThreadId) {
      setMemory(null);
      setStatus("idle");
      setError("");
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const payload = await fetchThreadMemory(activeThreadId);
      setMemory(payload);
      setStatus("ready");
    } catch (operationError) {
      if (operationError?.status === 401) {
        onUnauthorized();
        return;
      }
      setError(operationError.message || "Could not load thread memory.");
      setStatus("failed");
    }
  }, [activeThreadId, onUnauthorized]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadMemory();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadMemory]);

  const memoryStatus = status === "loading" ? "loading" : memory?.status || "not selected";
  const summary = memory?.summary_md?.trim() || "";

  return (
    <section className="settings-card settings-card-wide">
      <div className={styles.cardHeaderRow}>
        <div>
          <p className="eyebrow">Thread memory</p>
          <h3>Current thread summary</h3>
        </div>
        <div className={styles.headerActions}>
          <StatusPill tone={statusTone(memoryStatus)}>{memoryStatus}</StatusPill>
          <button type="button" className="button-ghost" onClick={loadMemory} disabled={!activeThreadId || status === "loading"}>
            {status === "loading" ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {!activeThreadId ? (
        <p className="muted">Open a chat thread to view its stored memory summary.</p>
      ) : (
        <>
          <p className="muted">
            Memory is updated automatically after each completed assistant answer. Raw messages remain stored separately.
          </p>
          <dl className="definition-list settings-definition-list">
            <div><dt>Thread</dt><dd>{activeThreadName || `Thread ${activeThreadId}`}</dd></div>
            <div><dt>Summarizer</dt><dd>{memory?.summarizer_provider && memory?.summarizer_model ? `${memory.summarizer_provider} · ${memory.summarizer_model}` : "Waiting for Google Gemini key / first update"}</dd></div>
            <div><dt>Last summarized message</dt><dd>{memory?.last_summarized_message_id ?? "Not summarized yet"}</dd></div>
            <div><dt>Updated</dt><dd>{formatTimestamp(memory?.updated_at)}</dd></div>
          </dl>
          {error ? <p className={styles.diagnosticError}>{error}</p> : null}
          {memory?.error_message ? <p className={styles.diagnosticError}>{memory.error_message}</p> : null}
          <div className="settings-list">
            <div className="settings-list-item">
              <div className="settings-list-main">
                <div className="settings-list-title-row">
                  <strong>Stored summary</strong>
                  <StatusPill tone={memory?.has_memory ? "success" : "neutral"}>{memory?.has_memory ? "available" : "empty"}</StatusPill>
                </div>
                {summary ? (
                  <div className="message message-assistant" style={{ marginTop: "0.85rem" }}>
                    <SafeMarkdownRenderer content={summary} />
                  </div>
                ) : (
                  <p className="muted">No memory summary exists yet. Add a Google Gemini key, then continue the conversation to generate one.</p>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
