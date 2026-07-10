"use client";

import { useCallback, useEffect, useState } from "react";

import { SafeMarkdownRenderer } from "../../components/ui/message-renderer";
import {
  deleteThreadMemoryConfig,
  fetchThreadMemory,
  getThreadMemoryConfig,
  regenerateThreadMemory,
  saveThreadMemoryConfig,
} from "../../lib/api-client";
import styles from "./settings.module.css";

const MEMORY_MODEL_FALLBACK = "gemini-2.5-flash-lite";

const modalOverlayStyle = {
  position: "fixed",
  inset: 0,
  zIndex: 90,
  display: "grid",
  placeItems: "center",
  background: "rgba(7, 10, 18, 0.52)",
  padding: "1rem",
};

const keyModalDialogStyle = {
  width: "min(100%, 34rem)",
  border: "1px solid color-mix(in srgb, var(--line) 78%, transparent)",
  borderRadius: "24px",
  background: "var(--surface)",
  boxShadow: "0 30px 90px rgba(0, 0, 0, 0.28)",
  padding: "1.1rem",
};

const summaryModalDialogStyle = {
  width: "min(100%, 48rem)",
  maxHeight: "min(86dvh, 52rem)",
  overflow: "auto",
  border: "1px solid color-mix(in srgb, var(--line) 78%, transparent)",
  borderRadius: "24px",
  background: "var(--surface)",
  boxShadow: "0 30px 90px rgba(0, 0, 0, 0.28)",
  padding: "1.1rem",
};

const modalHeaderStyle = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  gap: "1rem",
  marginBottom: "0.75rem",
};

const sectionTitleRowStyle = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  gap: "1rem",
};

const actionRowStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "flex-end",
  flexWrap: "wrap",
  gap: "0.5rem",
};

const summaryToolbarStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  flexWrap: "wrap",
  gap: "0.65rem",
  marginBottom: "0.75rem",
  borderTop: "1px solid color-mix(in srgb, var(--line) 68%, transparent)",
  borderBottom: "1px solid color-mix(in srgb, var(--line) 68%, transparent)",
  padding: "0.6rem 0",
};

const summaryMetaStyle = {
  display: "flex",
  alignItems: "center",
  flexWrap: "wrap",
  gap: "0.4rem 0.75rem",
  minWidth: 0,
  color: "var(--muted)",
  fontSize: "0.76rem",
};

const summaryCardHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  flexWrap: "wrap",
  gap: "0.55rem",
};

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

function useEscapeToClose(isOpen, onClose) {
  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);
}

export function ThreadMemoryCard({ onUnauthorized }) {
  const [config, setConfig] = useState(null);
  const [configStatus, setConfigStatus] = useState("idle");
  const [configNotice, setConfigNotice] = useState("");
  const [configError, setConfigError] = useState("");
  const [apiKeyDraft, setApiKeyDraft] = useState("");
  const [isKeyModalOpen, setIsKeyModalOpen] = useState(false);

  const handleUnauthorized = useCallback(() => {
    onUnauthorized();
  }, [onUnauthorized]);

  const closeKeyModal = useCallback(() => {
    setApiKeyDraft("");
    setConfigError("");
    setIsKeyModalOpen(false);
  }, []);

  useEscapeToClose(isKeyModalOpen, closeKeyModal);

  const loadConfig = useCallback(async () => {
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
  }, [handleUnauthorized]);

  useEffect(() => {
    const timer = window.setTimeout(loadConfig, 0);
    return () => window.clearTimeout(timer);
  }, [loadConfig]);

  function openKeyModal() {
    setApiKeyDraft("");
    setConfigError("");
    setConfigNotice("");
    setIsKeyModalOpen(true);
  }

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
      setConfigNotice("Thread memory key saved.");
      setConfigStatus("ready");
      setIsKeyModalOpen(false);
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
    if (!window.confirm("Delete the dedicated Google AI Studio key for thread memory?")) {
      return;
    }
    setConfigStatus("saving");
    setConfigNotice("");
    setConfigError("");
    try {
      await deleteThreadMemoryConfig();
      setConfig({ configured: false, provider_name: "google-ai-studio", model_identifier: MEMORY_MODEL_FALLBACK });
      setConfigNotice("Thread memory key deleted. Existing summaries stay stored.");
      setConfigStatus("ready");
      setApiKeyDraft("");
      setIsKeyModalOpen(false);
    } catch (operationError) {
      if (operationError?.status === 401) {
        handleUnauthorized();
        return;
      }
      setConfigError(operationError.message || "Could not delete thread memory key.");
      setConfigStatus("failed");
    }
  }

  const configLabel = config?.configured ? "configured" : "not configured";
  const keyActionLabel = config?.configured ? "Change key" : "Add key";

  return (
    <section className="settings-card settings-card-wide">
      <div className={styles.cardHeaderRow}>
        <div>
          <p className="eyebrow">Thread memory</p>
          <h3>Memory key setup</h3>
          <p className="muted">Manage the separate Google AI Studio key used only for thread summaries.</p>
        </div>
        <StatusPill tone={statusTone(configStatus === "saving" ? "saving" : configLabel)}>
          {configStatus === "saving" ? "saving" : configLabel}
        </StatusPill>
      </div>

      <div className="settings-list">
        <div className="settings-list-item">
          <div className="settings-list-main">
            <div style={sectionTitleRowStyle}>
              <div>
                <strong>Google AI Studio memory key</strong>
                <p className="muted">Stored separately from OpenRouter and NVIDIA chat keys. Summaries are available from the chat header.</p>
              </div>
              <div style={actionRowStyle}>
                <button type="button" className="button-primary" onClick={openKeyModal} disabled={configStatus === "saving"}>
                  {keyActionLabel}
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  onClick={handleDeleteConfig}
                  disabled={configStatus === "saving" || !config?.configured}
                >
                  Delete
                </button>
              </div>
            </div>
            <dl className="definition-list settings-definition-list">
              <div><dt>Provider</dt><dd>{config?.provider_name || "google-ai-studio"}</dd></div>
              <div><dt>Model</dt><dd>{config?.model_identifier || MEMORY_MODEL_FALLBACK}</dd></div>
              <div><dt>Key version</dt><dd>{config?.credential_key_version ?? "Not saved yet"}</dd></div>
              <div><dt>Updated</dt><dd>{formatTimestamp(config?.updated_at)}</dd></div>
            </dl>
            {configNotice ? <p className={styles.diagnosticSuccess}>{configNotice}</p> : null}
            {configError && !isKeyModalOpen ? <p className={styles.diagnosticError}>{configError}</p> : null}
          </div>
        </div>
      </div>

      {isKeyModalOpen ? (
        <div style={modalOverlayStyle} role="presentation" onMouseDown={closeKeyModal}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="thread-memory-key-title"
            style={keyModalDialogStyle}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div style={modalHeaderStyle}>
              <div>
                <p className="eyebrow">Thread memory key</p>
                <h3 id="thread-memory-key-title">{config?.configured ? "Change Google AI Studio key" : "Add Google AI Studio key"}</h3>
              </div>
              <button type="button" className="button-ghost" onClick={closeKeyModal}>Close</button>
            </div>
            <p className="muted">Paste the free Google AI Studio API key. The key is encrypted on save.</p>
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
                  autoFocus
                />
              </label>
              <button type="submit" className="button-primary" disabled={configStatus === "saving" || !apiKeyDraft.trim()}>
                {configStatus === "saving" ? "Saving…" : config?.configured ? "Save replacement key" : "Save key"}
              </button>
              <button type="button" className="button-ghost" onClick={closeKeyModal} disabled={configStatus === "saving"}>
                Cancel
              </button>
            </form>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function ThreadMemoryModal({ open, activeThreadId, activeThreadName, onClose, onUnauthorized, onAfterRegenerate }) {
  const [memory, setMemory] = useState(null);
  const [memoryStatus, setMemoryStatus] = useState("idle");
  const [memoryNotice, setMemoryNotice] = useState("");
  const [memoryError, setMemoryError] = useState("");
  const [config, setConfig] = useState(null);
  const [configError, setConfigError] = useState("");

  const handleUnauthorized = useCallback(() => {
    onUnauthorized();
  }, [onUnauthorized]);

  useEscapeToClose(open, onClose);

  const loadConfig = useCallback(async () => {
    try {
      const payload = await getThreadMemoryConfig();
      setConfig(payload);
      setConfigError("");
    } catch (operationError) {
      if (operationError?.status === 401) {
        handleUnauthorized();
        return;
      }
      setConfigError(operationError.message || "Could not load memory key status.");
    }
  }, [handleUnauthorized]);

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

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      loadConfig();
      loadMemory();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadConfig, loadMemory, open]);

  async function handleRebuildMemory() {
    if (!activeThreadId) {
      return;
    }
    setMemoryStatus("generating");
    setMemoryNotice("");
    setMemoryError("");
    try {
      const payload = await regenerateThreadMemory(activeThreadId);
      setMemory(payload);
      setMemoryNotice("Memory rebuilt from the complete thread. The thread title was reconciled with the current state.");
      setMemoryStatus("ready");
      if (onAfterRegenerate) {
        await onAfterRegenerate();
      }
    } catch (operationError) {
      if (operationError?.status === 401) {
        handleUnauthorized();
        return;
      }
      setMemoryError(operationError.message || "Could not rebuild thread memory.");
      setMemoryStatus("failed");
    }
  }

  if (!open) {
    return null;
  }

  const visibleMemoryStatus = ["loading", "generating"].includes(memoryStatus)
    ? memoryStatus
    : memory?.status || "not selected";
  const summary = memory?.summary_md?.trim() || "";
  const canGenerateMemory = Boolean(
    activeThreadId && config?.configured && !["loading", "generating"].includes(memoryStatus),
  );
  const summarizerLabel = memory?.summarizer_provider && memory?.summarizer_model
    ? `${memory.summarizer_provider} · ${memory.summarizer_model}`
    : config?.model_identifier || MEMORY_MODEL_FALLBACK;

  return (
    <div style={modalOverlayStyle} role="presentation" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="thread-memory-summary-title"
        style={summaryModalDialogStyle}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div style={modalHeaderStyle}>
          <div>
            <p className="eyebrow">Thread memory</p>
            <h3 id="thread-memory-summary-title">Current thread memory</h3>
            <p className="muted">{activeThreadId ? activeThreadName || `Thread ${activeThreadId}` : "No thread selected"}</p>
          </div>
          <div style={actionRowStyle}>
            <StatusPill tone={statusTone(visibleMemoryStatus)}>{visibleMemoryStatus}</StatusPill>
            <button type="button" className="button-ghost" onClick={onClose}>Close</button>
          </div>
        </div>

        <div style={summaryToolbarStyle}>
          <div style={summaryMetaStyle}>
            <span>{summarizerLabel}</span>
            <span>Through message {memory?.last_summarized_message_id ?? "—"}</span>
            <span>{formatTimestamp(memory?.updated_at)}</span>
          </div>
          <div style={actionRowStyle}>
            <button
              type="button"
              className="button-ghost"
              onClick={loadMemory}
              disabled={!activeThreadId || memoryStatus === "loading" || memoryStatus === "generating"}
            >
              {memoryStatus === "loading" ? "Loading…" : "Refresh"}
            </button>
            <button type="button" className="button-primary" onClick={handleRebuildMemory} disabled={!canGenerateMemory}>
              {memoryStatus === "generating" ? "Rebuilding…" : "Rebuild"}
            </button>
          </div>
        </div>

        {!activeThreadId ? <p className="muted">Open a chat thread to view or build memory.</p> : null}
        {activeThreadId && !config?.configured ? <p className={styles.diagnosticError}>Add the Google AI Studio memory key in Settings before rebuilding.</p> : null}
        {configError ? <p className={styles.diagnosticError}>{configError}</p> : null}
        {memoryNotice ? <p className={styles.diagnosticSuccess}>{memoryNotice}</p> : null}
        {memoryError ? <p className={styles.diagnosticError}>{memoryError}</p> : null}
        {memory?.error_message ? <p className={styles.diagnosticError}>{memory.error_message}</p> : null}

        <div className="settings-list-item">
          <div className="settings-list-main">
            <div style={summaryCardHeaderStyle}>
              <strong>Durable AI handoff</strong>
              <StatusPill tone={memory?.has_memory ? "success" : "neutral"}>{memory?.has_memory ? "available" : "empty"}</StatusPill>
            </div>
            {summary ? (
              <div className="message message-assistant" style={{ marginTop: "0.65rem" }}>
                <SafeMarkdownRenderer content={summary} />
              </div>
            ) : (
              <p className="muted" style={{ marginTop: "0.55rem" }}>
                No stored memory yet. Add the key in Settings, then rebuild or continue the conversation.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
