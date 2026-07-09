"use client";

import { useCallback, useEffect, useState } from "react";

import { useStudioStore } from "../../components/store";
import { SafeMarkdownRenderer } from "../../components/ui/message-renderer";
import {
  deleteThreadMemoryConfig,
  fetchThreadMemory,
  getThreadMemoryConfig,
  regenerateThreadMemory,
  saveThreadMemoryConfig,
} from "../../lib/api-client";
import styles from "./settings.module.css";

function StatusPill({ children, tone = "neutral" }) {
  const className = `${styles.statusPill} ${styles[`statusPill${tone[0].toUpperCase()}${tone.slice(1)}`]}`;
  return <span className={className}>{children}</span>;
}

function statusTone(status) {
  if (["completed", "ready", "active", "configured", "generated"].includes(status)) {
    return "success";
  }
  if (["running", "queued", "loading", "saving", "generating"].includes(status)) {
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
  const userRole = useStudioStore((state) => state.userRole);
  const isAdmin = userRole === "admin";
  const [memory, setMemory] = useState(null);
  const [memoryStatus, setMemoryStatus] = useState("idle");
  const [memoryNotice, setMemoryNotice] = useState("");
  const [memoryError, setMemoryError] = useState("");
  const [config, setConfig] = useState(null);
  const [configStatus, setConfigStatus] = useState("idle");
  const [configNotice, setConfigNotice] = useState("");
  const [configError, setConfigError] = useState("");
  const [apiKeyDraft, setApiKeyDraft] = useState("");

  const handleUnauthorized = useCallback(() => {
    onUnauthorized();
  }, [onUnauthorized]);

  const loadMemory = useCallback(async () => {
    if (!activeThreadId) {
      setMemory(null);
      setMemoryStatus("idle");
      setMemoryNotice("");
      setMemoryError("");
      return;
    }
    setMemoryStatus("loading");
    setMemoryNotice("");
    setMemoryError("");
    try {
      const payload = await fetchThreadMemory(activeThreadId);
      setMemory(payload);
      setMemoryStatus("ready");
    } catch (operationError) {
      if (operationError?.status === 401) {
        handleUnauthorized();
        return;
      }
      setMemoryError(operationError.message || "Could not load thread memory.");
      setMemoryStatus("failed");
    }
  }, [activeThreadId, handleUnauthorized]);

  const loadConfig = useCallback(async () => {
    if (!isAdmin) {
      setConfig(null);
      setConfigStatus("idle");
      setConfigError("");
      return;
    }
    setConfigStatus("loading");
    setConfigError("");
    try {
      const payload = await getThreadMemoryConfig();
      setConfig(payload);
      setConfigStatus("ready");
    } catch (operationError) {
      if (operationError?.status === 401) {
        handleUnauthorized();
        return;
      }
      setConfigError(operationError.message || "Could not load thread memory key setup.");
      setConfigStatus("failed");
    }
  }, [handleUnauthorized, isAdmin]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadMemory();
      loadConfig();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadConfig, loadMemory]);

  async function handleSaveConfig(event) {
    event.preventDefault();
    const apiKey = apiKeyDraft.trim();
    if (!apiKey) {
      setConfigError("Paste a Google AI Studio API key before saving.");
      setConfigStatus("failed");
      return;
    }
    setConfigStatus("saving");
    setConfigNotice("");
    setConfigError("");
    try {
      const payload = await saveThreadMemoryConfig(apiKey);
      setConfig(payload);
      setApiKeyDraft("");
      setConfigNotice("Thread memory Google AI Studio key saved. You can generate this thread's memory now.");
      setConfigStatus("ready");
    } catch (operationError) {
      if (operationError?.status === 401) {
        handleUnauthorized();
        return;
      }
      setConfigError(operationError.message || "Could not save thread memory key.");
      setConfigStatus("failed");
    }
  }

  async function handleDeleteConfig() {
    if (!window.confirm("Delete the dedicated Google AI Studio key for thread memory? Thread summaries will stop updating until a new key is saved.")) {
      return;
    }
    setConfigStatus("saving");
    setConfigNotice("");
    setConfigError("");
    try {
      await deleteThreadMemoryConfig();
      setConfig({ configured: false, provider_name: "google-ai-studio", model_identifier: "gemini-3.5-flash" });
      setConfigNotice("Thread memory key deleted. Existing summaries stay stored, but new answers will not update memory.");
      setConfigStatus("ready");
    } catch (operationError) {
      if (operationError?.status === 401) {
        handleUnauthorized();
        return;
      }
      setConfigError(operationError.message || "Could not delete thread memory key.");
      setConfigStatus("failed");
    }
  }

  async function handleRegenerateMemory() {
    if (!activeThreadId) {
      return;
    }
    setMemoryStatus("generating");
    setMemoryNotice("");
    setMemoryError("");
    try {
      const payload = await regenerateThreadMemory(activeThreadId);
      setMemory(payload);
      setMemoryNotice("Thread memory generated and saved for the active thread.");
      setMemoryStatus("ready");
    } catch (operationError) {
      if (operationError?.status === 401) {
        handleUnauthorized();
        return;
      }
      setMemoryError(operationError.message || "Could not regenerate thread memory.");
      setMemoryStatus("failed");
    }
  }

  const visibleMemoryStatus = ["loading", "generating"].includes(memoryStatus) ? memoryStatus : memory?.status || "not selected";
  const summary = memory?.summary_md?.trim() || "";
  const configLabel = config?.configured ? "configured" : "not configured";
  const canGenerateMemory = Boolean(activeThreadId && config?.configured && !["loading", "generating"].includes(memoryStatus));

  return (
    <section className="settings-card settings-card-wide">
      <div className={styles.cardHeaderRow}>
        <div>
          <p className="eyebrow">Thread memory</p>
          <h3>Summary model and current thread memory</h3>
        </div>
        <div className={styles.headerActions}>
          <StatusPill tone={statusTone(visibleMemoryStatus)}>{visibleMemoryStatus}</StatusPill>
          <button type="button" className="button-ghost" onClick={loadMemory} disabled={!activeThreadId || memoryStatus === "loading" || memoryStatus === "generating"}>
            {memoryStatus === "loading" ? "Loading…" : "Refresh"}
          </button>
          <button type="button" className="button-primary" onClick={handleRegenerateMemory} disabled={!canGenerateMemory}>
            {memoryStatus === "generating" ? "Generating…" : "Regenerate now"}
          </button>
        </div>
      </div>

      {isAdmin ? (
        <div className="settings-list" style={{ marginBottom: "0.9rem" }}>
          <div className="settings-list-item">
            <div className="settings-list-main">
              <div className="settings-list-title-row">
                <strong>Dedicated Google AI Studio key</strong>
                <StatusPill tone={statusTone(configStatus === "saving" ? "saving" : configLabel)}>
                  {configStatus === "saving" ? "saving" : configLabel}
                </StatusPill>
              </div>
              <p className="muted">
                This key is used only for thread-memory summarisation. It is separate from normal chat providers and does not appear in the Model selector.
              </p>
              <dl className="definition-list settings-definition-list">
                <div><dt>Provider</dt><dd>{config?.provider_name || "google-ai-studio"}</dd></div>
                <div><dt>Model</dt><dd>{config?.model_identifier || "gemini-3.5-flash"}</dd></div>
                <div><dt>Key version</dt><dd>{config?.credential_key_version ?? "Not saved yet"}</dd></div>
                <div><dt>Updated</dt><dd>{formatTimestamp(config?.updated_at)}</dd></div>
              </dl>
              {configNotice ? <p className={styles.diagnosticSuccess}>{configNotice}</p> : null}
              {configError ? <p className={styles.diagnosticError}>{configError}</p> : null}
              <form className={styles.adminForm} onSubmit={handleSaveConfig}>
                <label>
                  Google AI Studio API key
                  <input
                    type="password"
                    autoComplete="new-password"
                    value={apiKeyDraft}
                    onChange={(event) => setApiKeyDraft(event.target.value)}
                    placeholder={config?.configured ? "Paste a replacement key" : "Paste free Google AI Studio key"}
                    minLength={8}
                  />
                </label>
                <button type="submit" className="button-primary" disabled={configStatus === "saving" || !apiKeyDraft.trim()}>
                  {config?.configured ? "Replace memory key" : "Save memory key"}
                </button>
                <button type="button" className="button-ghost" onClick={handleDeleteConfig} disabled={configStatus === "saving" || !config?.configured}>
                  Delete key
                </button>
              </form>
            </div>
          </div>
        </div>
      ) : null}

      {!activeThreadId ? (
        <p className="muted">Open a chat thread to view or generate its stored memory summary.</p>
      ) : (
        <>
          <p className="muted">
            Memory updates automatically after each completed assistant answer when the dedicated Google AI Studio key is saved. Use Regenerate now to build it immediately for this thread.
          </p>
          {!config?.configured && isAdmin ? <p className={styles.diagnosticError}>Save the dedicated Google AI Studio key before generating memory.</p> : null}
          <dl className="definition-list settings-definition-list">
            <div><dt>Thread</dt><dd>{activeThreadName || `Thread ${activeThreadId}`}</dd></div>
            <div><dt>Summarizer</dt><dd>{memory?.summarizer_provider && memory?.summarizer_model ? `${memory.summarizer_provider} · ${memory.summarizer_model}` : "Waiting for memory key / first update"}</dd></div>
            <div><dt>Last summarized message</dt><dd>{memory?.last_summarized_message_id ?? "Not summarized yet"}</dd></div>
            <div><dt>Updated</dt><dd>{formatTimestamp(memory?.updated_at)}</dd></div>
          </dl>
          {memoryNotice ? <p className={styles.diagnosticSuccess}>{memoryNotice}</p> : null}
          {memoryError ? <p className={styles.diagnosticError}>{memoryError}</p> : null}
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
                  <p className="muted">No memory summary exists yet. Save the dedicated Google AI Studio key, then click Regenerate now or continue the conversation.</p>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
