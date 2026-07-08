"use client";

import { useCallback, useEffect, useState } from "react";

import {
  listPipelineSteps,
  listProviderCredentials,
  updatePipelineStep,
  upsertProviderCredential,
} from "../../lib/api-client";
import styles from "./settings.module.css";

const emptyProviderForm = { providerName: "openrouter", secret: "" };

function StatusPill({ children, tone = "neutral" }) {
  const className = `${styles.statusPill} ${styles[`statusPill${tone[0].toUpperCase()}${tone.slice(1)}`]}`;
  return <span className={className}>{children}</span>;
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

function dependencyText(step) {
  return step.prerequisite_dependencies?.length ? step.prerequisite_dependencies.join(", ") : "";
}

export function OperatorControls({ isAdmin, onUnauthorized }) {
  const [providerCredentials, setProviderCredentials] = useState([]);
  const [pipelineSteps, setPipelineSteps] = useState([]);
  const [providerForm, setProviderForm] = useState(emptyProviderForm);
  const [pipelineDrafts, setPipelineDrafts] = useState({});
  const [status, setStatus] = useState("idle");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const handleError = useCallback((operationError, fallback) => {
    if (operationError?.status === 401) {
      onUnauthorized();
    }
    setError(operationError.message || fallback);
    setStatus("failed");
  }, [onUnauthorized]);

  const refreshOperatorState = useCallback(async () => {
    if (!isAdmin) {
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const [credentials, steps] = await Promise.all([listProviderCredentials(), listPipelineSteps()]);
      setProviderCredentials(credentials);
      setPipelineSteps(steps);
      setPipelineDrafts((currentDrafts) => {
        const nextDrafts = {};
        for (const step of steps) {
          nextDrafts[step.id] = currentDrafts[step.id] || {
            providerType: step.provider_type,
            modelString: step.model_string,
            systemPromptDirectives: step.system_prompt_directives || "",
            prerequisiteDependencies: dependencyText(step),
            isTerminal: step.is_terminal,
          };
        }
        return nextDrafts;
      });
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not load operator controls.");
    }
  }, [handleError, isAdmin]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshOperatorState();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshOperatorState]);

  async function handleProviderSubmit(event) {
    event.preventDefault();
    setStatus("loading");
    setNotice("");
    setError("");
    try {
      await upsertProviderCredential(providerForm);
      setProviderForm((current) => ({ ...current, secret: "" }));
      setNotice(`Rotated credential for ${providerForm.providerName.trim().toLowerCase()}.`);
      await refreshOperatorState();
    } catch (operationError) {
      handleError(operationError, "Could not rotate provider credential.");
    }
  }

  function updateDraft(stepId, patch) {
    setPipelineDrafts((current) => ({
      ...current,
      [stepId]: { ...current[stepId], ...patch },
    }));
  }

  async function savePipelineStep(step) {
    const draft = pipelineDrafts[step.id];
    if (!draft) {
      return;
    }
    setStatus("loading");
    setNotice("");
    setError("");
    try {
      await updatePipelineStep(step.id, {
        providerType: draft.providerType,
        modelString: draft.modelString,
        systemPromptDirectives: draft.systemPromptDirectives,
        prerequisiteDependencies: draft.prerequisiteDependencies
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        isTerminal: draft.isTerminal,
      });
      setNotice(`Updated pipeline step ${step.step_name}.`);
      await refreshOperatorState();
    } catch (operationError) {
      handleError(operationError, "Could not update pipeline step.");
    }
  }

  if (!isAdmin) {
    return null;
  }

  return (
    <>
      <section className="settings-card settings-card-wide">
        <div className={styles.cardHeaderRow}>
          <div>
            <p className="eyebrow">Secrets</p>
            <h3>Provider credentials</h3>
          </div>
          <div className={styles.headerActions}>
            <StatusPill tone={status === "failed" ? "danger" : status === "loading" ? "loading" : "success"}>{status}</StatusPill>
            <button type="button" className="button-ghost" onClick={refreshOperatorState} disabled={status === "loading"}>
              Refresh operator state
            </button>
          </div>
        </div>
        <p className="muted">
          Rotate provider API keys without opening Neon. Existing secret values are write-only: they are encrypted server-side and never rendered back into the browser.
        </p>
        {error ? <p className={styles.diagnosticError}>{error}</p> : null}
        {notice ? <p className={styles.diagnosticSuccess}>{notice}</p> : null}
        <form className={styles.adminForm} onSubmit={handleProviderSubmit}>
          <label>
            Provider
            <input
              value={providerForm.providerName}
              onChange={(event) => setProviderForm((current) => ({ ...current, providerName: event.target.value }))}
              minLength={2}
              maxLength={100}
              required
            />
          </label>
          <label>
            New API key / secret
            <input
              type="password"
              autoComplete="new-password"
              value={providerForm.secret}
              onChange={(event) => setProviderForm((current) => ({ ...current, secret: event.target.value }))}
              minLength={8}
              required
            />
          </label>
          <button type="submit" className="button-primary" disabled={status === "loading"}>Save encrypted secret</button>
        </form>
        <div className="matrix-wrapper" tabIndex="0">
          <table className="settings-matrix">
            <thead><tr><th>Provider</th><th>Configured</th><th>Key version</th><th>Last rotated</th></tr></thead>
            <tbody>
              {providerCredentials.map((credential) => (
                <tr key={credential.provider_name}>
                  <td><code className={styles.inlineCode}>{credential.provider_name}</code></td>
                  <td><StatusPill tone="success">configured</StatusPill></td>
                  <td>{credential.key_version}</td>
                  <td>{formatTimestamp(credential.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="settings-card settings-card-wide">
        <p className="eyebrow">Execution graph</p>
        <h3>Pipeline editor</h3>
        <p className="muted">
          These changes apply to future runs because the backend loads pipeline steps from the database at execution time.
        </p>
        <div className={styles.pipelineEditorList}>
          {pipelineSteps.map((step) => {
            const draft = pipelineDrafts[step.id] || {};
            return (
              <article className={styles.pipelineEditorCard} key={step.id}>
                <div className={styles.cardHeaderRow}>
                  <div>
                    <p className="eyebrow">Step {step.sequence_order_position}</p>
                    <h4>{step.step_name}</h4>
                  </div>
                  <StatusPill tone={draft.isTerminal ? "success" : "neutral"}>{draft.isTerminal ? "terminal" : "internal"}</StatusPill>
                </div>
                <div className={styles.pipelineFields}>
                  <label>
                    Provider
                    <input value={draft.providerType || ""} onChange={(event) => updateDraft(step.id, { providerType: event.target.value })} />
                  </label>
                  <label>
                    Model
                    <input value={draft.modelString || ""} onChange={(event) => updateDraft(step.id, { modelString: event.target.value })} />
                  </label>
                  <label>
                    Prerequisites, comma-separated
                    <input value={draft.prerequisiteDependencies || ""} onChange={(event) => updateDraft(step.id, { prerequisiteDependencies: event.target.value })} />
                  </label>
                  <label className={styles.checkboxLabel}>
                    <input type="checkbox" checked={Boolean(draft.isTerminal)} onChange={(event) => updateDraft(step.id, { isTerminal: event.target.checked })} />
                    Terminal output step
                  </label>
                </div>
                <label className={styles.fullWidthLabel}>
                  System prompt directives
                  <textarea value={draft.systemPromptDirectives || ""} rows={5} onChange={(event) => updateDraft(step.id, { systemPromptDirectives: event.target.value })} />
                </label>
                <button type="button" className="button-primary" onClick={() => savePipelineStep(step)} disabled={status === "loading"}>Save step</button>
              </article>
            );
          })}
        </div>
      </section>
    </>
  );
}
