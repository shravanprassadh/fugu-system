"use client";

import { useCallback, useEffect, useState } from "react";

import {
  getDatabaseConnections,
  getRenderConfig,
  persistDatabaseTargetEnvToRender,
  saveRenderConfig,
  testCandidateDatabaseConnection,
  testCurrentDatabaseConnection,
  testRenderConfig,
} from "../../lib/api-client";
import styles from "./settings.module.css";

const emptyRenderForm = { serviceId: "", apiToken: "" };
const emptyDatabaseDraft = { databaseUrl: "", triggerRenderDeploy: true };

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

function databaseStatusTone(status) {
  if (["connected", "copied", "active", "updated", "configured"].includes(status)) {
    return "success";
  }
  if (status === "failed") {
    return "danger";
  }
  return "neutral";
}

function databaseDraftFor(drafts, target) {
  return drafts[target] || emptyDatabaseDraft;
}

function isCandidateSaveReady(result, draft) {
  return result?.kind === "candidate" && result.status === "connected" && result.candidateUrl === draft.databaseUrl;
}

export function OperatorControls({ isAdmin, onUnauthorized }) {
  const [renderForm, setRenderForm] = useState(emptyRenderForm);
  const [renderConfig, setRenderConfig] = useState(null);
  const [renderResult, setRenderResult] = useState(null);
  const [renderEditMode, setRenderEditMode] = useState(false);
  const [databaseConnections, setDatabaseConnections] = useState(null);
  const [databaseDrafts, setDatabaseDrafts] = useState({});
  const [databaseEditTarget, setDatabaseEditTarget] = useState(null);
  const [databaseResults, setDatabaseResults] = useState({});
  const [status, setStatus] = useState("idle");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const handleError = useCallback(
    (operationError, fallback) => {
      if (operationError?.status === 401) {
        onUnauthorized();
      }
      setError(operationError.message || fallback);
      setStatus("failed");
    },
    [onUnauthorized],
  );

  const refreshOperatorState = useCallback(async () => {
    if (!isAdmin) {
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const [renderState, databaseState] = await Promise.all([
        getRenderConfig(),
        getDatabaseConnections(),
      ]);
      setRenderConfig(renderState);
      setRenderForm((current) => ({
        ...current,
        serviceId: current.serviceId || renderState.service_id || "",
        apiToken: "",
      }));
      setDatabaseConnections(databaseState);
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not load infrastructure controls.");
    }
  }, [handleError, isAdmin]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshOperatorState();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshOperatorState]);

  function beginRenderEdit() {
    setRenderForm({ serviceId: renderConfig?.service_id || "", apiToken: "" });
    setRenderEditMode(true);
    setNotice("");
    setError("");
  }

  function cancelRenderEdit() {
    setRenderForm({ serviceId: renderConfig?.service_id || "", apiToken: "" });
    setRenderEditMode(false);
    setError("");
  }

  async function handleRenderConfigSubmit(event) {
    event.preventDefault();
    setStatus("loading");
    setNotice("");
    setError("");
    try {
      const result = await saveRenderConfig(renderForm);
      setRenderConfig(result);
      setRenderForm((current) => ({ ...current, apiToken: "" }));
      setRenderEditMode(false);
      setNotice("Render integration saved. The token remains encrypted and write-only.");
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not save Render integration.");
    }
  }

  async function handleRenderConfigTest() {
    setStatus("loading");
    setNotice("");
    setError("");
    try {
      const result = await testRenderConfig();
      setRenderConfig(result);
      setNotice("Render API token and service ID are valid.");
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not validate Render integration.");
    }
  }

  function beginDatabaseEdit(target) {
    setNotice("");
    setError("");
    setDatabaseEditTarget(target);
    setDatabaseDrafts((current) => ({
      ...current,
      [target]: current[target] || emptyDatabaseDraft,
    }));
  }

  function cancelDatabaseEdit(target) {
    setError("");
    setDatabaseEditTarget((current) => (current === target ? null : current));
    setDatabaseDrafts((current) => {
      const next = { ...current };
      delete next[target];
      return next;
    });
    setDatabaseResults((current) => ({ ...current, [target]: null }));
  }

  function updateDatabaseDraft(target, update) {
    setDatabaseDrafts((current) => ({
      ...current,
      [target]: {
        ...databaseDraftFor(current, target),
        ...update,
      },
    }));
    setDatabaseResults((current) => {
      if (current[target]?.kind !== "candidate") {
        return current;
      }
      return { ...current, [target]: null };
    });
  }

  async function handleCurrentDatabaseTest(target, label) {
    setStatus("loading");
    setNotice("");
    setError("");
    try {
      const result = await testCurrentDatabaseConnection(target);
      setDatabaseResults((current) => ({ ...current, [target]: { ...result, kind: "current" } }));
      setNotice(`${label} current SQL record is ${result.status}.`);
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, `Could not test ${label}.`);
    }
  }

  async function handleCandidateDatabaseTest(target, label) {
    const draft = databaseDraftFor(databaseDrafts, target);
    if (!draft.databaseUrl.trim()) {
      setError(`Paste a replacement ${label} URL before testing.`);
      setStatus("failed");
      return;
    }
    setStatus("loading");
    setNotice("");
    setError("");
    try {
      const result = await testCandidateDatabaseConnection(target, draft.databaseUrl.trim());
      setDatabaseResults((current) => ({
        ...current,
        [target]: { ...result, kind: "candidate", candidateUrl: draft.databaseUrl.trim() },
      }));
      setNotice(`${label} replacement URL passed its connection test. Save is now enabled.`);
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, `Could not test replacement ${label} URL.`);
    }
  }

  async function handlePersistDatabaseTarget(target, label) {
    const draft = databaseDraftFor(databaseDrafts, target);
    const result = databaseResults[target];
    if (!isCandidateSaveReady(result, draft)) {
      setError(`Test the replacement ${label} URL before saving it.`);
      setStatus("failed");
      return;
    }
    setStatus("loading");
    setNotice("");
    setError("");
    try {
      const renderUpdate = await persistDatabaseTargetEnvToRender(target, {
        databaseUrl: draft.databaseUrl.trim(),
        triggerDeploy: draft.triggerRenderDeploy,
      });
      setRenderResult(renderUpdate);
      setNotice(`${label} SQL record saved to Render${draft.triggerRenderDeploy ? " and redeploy triggered" : ""}.`);
      cancelDatabaseEdit(target);
      await refreshOperatorState();
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, `Could not save ${label} SQL record to Render.`);
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
            <p className="eyebrow">Render control plane</p>
            <h3>Deployment API integration</h3>
          </div>
          <div className={styles.headerActions}>
            <StatusPill tone={renderConfig?.configured ? "success" : "neutral"}>
              {renderConfig?.configured ? "configured" : "not configured"}
            </StatusPill>
            <button
              type="button"
              className="button-ghost"
              onClick={handleRenderConfigTest}
              disabled={status === "loading" || !renderConfig?.configured}
            >
              Test
            </button>
            <button
              type="button"
              className="button-primary"
              onClick={renderEditMode ? cancelRenderEdit : beginRenderEdit}
              disabled={status === "loading"}
            >
              {renderEditMode ? "Cancel" : "Change"}
            </button>
          </div>
        </div>
        <p className="muted">
          Render details are stored once and shown as masked metadata. Plain tokens are requested only when you choose Change.
        </p>
        {error ? <p className={styles.diagnosticError}>{error}</p> : null}
        {notice ? <p className={styles.diagnosticSuccess}>{notice}</p> : null}
        <div className="settings-list">
          <div className="settings-list-item">
            <div className="settings-list-main">
              <div className="settings-list-title-row">
                <strong>Service ID</strong>
                <StatusPill tone={renderConfig?.service_id ? "success" : "neutral"}>
                  {renderConfig?.service_id ? "stored" : "missing"}
                </StatusPill>
              </div>
              <p className="muted">
                <code className={styles.inlineCode}>{renderConfig?.service_id || "Not configured"}</code>
              </p>
            </div>
          </div>
          <div className="settings-list-item">
            <div className="settings-list-main">
              <div className="settings-list-title-row">
                <strong>API token</strong>
                <StatusPill tone={renderConfig?.has_api_token ? "success" : "neutral"}>
                  {renderConfig?.has_api_token ? "stored" : "missing"}
                </StatusPill>
              </div>
              <p className="muted">
                <code className={styles.inlineCode}>
                  {renderConfig?.has_api_token ? "••••••••••••••••••••" : "Not configured"}
                </code>
              </p>
            </div>
          </div>
        </div>
        {renderEditMode || !renderConfig?.configured ? (
          <form className={styles.adminForm} onSubmit={handleRenderConfigSubmit}>
            <label>
              Render service ID
              <input
                value={renderForm.serviceId}
                onChange={(event) => setRenderForm((current) => ({ ...current, serviceId: event.target.value }))}
                placeholder="srv-..."
                minLength={3}
                required
              />
            </label>
            <label>
              Render API token
              <input
                type="password"
                autoComplete="new-password"
                value={renderForm.apiToken}
                onChange={(event) => setRenderForm((current) => ({ ...current, apiToken: event.target.value }))}
                placeholder={renderConfig?.has_api_token ? "Leave blank to keep stored token" : "Paste token once"}
                minLength={renderConfig?.has_api_token ? undefined : 20}
              />
            </label>
            <button type="submit" className="button-primary" disabled={status === "loading"}>
              Save changes
            </button>
          </form>
        ) : null}
        {renderResult ? (
          <div className="matrix-wrapper" tabIndex="0">
            <table className="settings-matrix">
              <thead>
                <tr><th>Render status</th><th>Service</th><th>Deploy</th><th>Env vars</th></tr>
              </thead>
              <tbody>
                <tr>
                  <td><StatusPill tone={databaseStatusTone(renderResult.status)}>{renderResult.status}</StatusPill></td>
                  <td><code className={styles.inlineCode}>{renderResult.service_id}</code></td>
                  <td>{renderResult.deploy_triggered ? renderResult.deploy_id || "triggered" : "not triggered"}</td>
                  <td>{renderResult.updated_env_keys.join(", ")}</td>
                </tr>
              </tbody>
            </table>
            <p className="muted">{renderResult.note}</p>
          </div>
        ) : null}
      </section>

      <section className="settings-card settings-card-wide">
        <div className={styles.cardHeaderRow}>
          <div>
            <p className="eyebrow">Database records</p>
            <h3>Runtime SQL connections</h3>
          </div>
          <div className={styles.headerActions}>
            <StatusPill tone={databaseConnections?.configured ? "success" : "neutral"}>
              {databaseConnections?.configured ? "configured" : "not checked"}
            </StatusPill>
            <button type="button" className="button-ghost" onClick={refreshOperatorState} disabled={status === "loading"}>
              Refresh
            </button>
          </div>
        </div>
        <p className="muted">
          Each SQL record is managed separately. Test the current record, or change one URL at a time. Replacement URLs are write-only and must pass Test before Save.
        </p>
        <div className="settings-list">
          {(databaseConnections?.targets || []).map((target) => {
            const draft = databaseDraftFor(databaseDrafts, target.target);
            const result = databaseResults[target.target];
            const isEditing = databaseEditTarget === target.target;
            const canSave = isCandidateSaveReady(result, draft) && renderConfig?.configured;
            return (
              <div className="settings-list-item" key={target.target}>
                <div className="settings-list-main">
                  <div className="settings-list-title-row">
                    <strong>{target.label}</strong>
                    <StatusPill tone={databaseStatusTone(result?.status || "runtime")}>
                      {result?.status || "runtime"}
                    </StatusPill>
                  </div>
                  <p className="muted"><code className={styles.inlineCode}>{target.env_key}</code></p>
                  <p className="muted"><code className={styles.inlineCode}>{target.masked_url}</code></p>
                  {result ? (
                    <p className="muted">
                      Last test: {result.status} · {formatTimestamp(result.checked_at)} · <code className={styles.inlineCode}>{result.masked_url}</code>
                    </p>
                  ) : null}
                </div>
                <div className={styles.adminActions}>
                  <button
                    type="button"
                    className="button-ghost"
                    onClick={() => handleCurrentDatabaseTest(target.target, target.label)}
                    disabled={status === "loading"}
                  >
                    Test
                  </button>
                  <button
                    type="button"
                    className="button-primary"
                    onClick={() => (isEditing ? cancelDatabaseEdit(target.target) : beginDatabaseEdit(target.target))}
                    disabled={status === "loading"}
                  >
                    {isEditing ? "Cancel" : "Change"}
                  </button>
                </div>
                {isEditing ? (
                  <form
                    className={styles.databaseTransferForm}
                    onSubmit={(event) => {
                      event.preventDefault();
                      handleCandidateDatabaseTest(target.target, target.label);
                    }}
                  >
                    <label>
                      Replacement {target.label} URL
                      <input
                        type="password"
                        autoComplete="off"
                        value={draft.databaseUrl}
                        onChange={(event) => updateDatabaseDraft(target.target, { databaseUrl: event.target.value })}
                        placeholder="Paste the replacement Postgres URL"
                        required
                      />
                    </label>
                    <label className={styles.checkboxLabel}>
                      <input
                        type="checkbox"
                        checked={draft.triggerRenderDeploy}
                        onChange={(event) => updateDatabaseDraft(target.target, { triggerRenderDeploy: event.target.checked })}
                      />
                      Trigger Render deploy after save
                    </label>
                    <button type="submit" className="button-ghost" disabled={status === "loading" || !draft.databaseUrl.trim()}>
                      Test replacement
                    </button>
                    <button
                      type="button"
                      className="button-primary"
                      onClick={() => handlePersistDatabaseTarget(target.target, target.label)}
                      disabled={status === "loading" || !canSave}
                    >
                      Save this SQL record
                    </button>
                    {!renderConfig?.configured ? (
                      <p className="muted">Configure Render control plane before saving database records.</p>
                    ) : null}
                    {result?.kind === "candidate" && result.status === "connected" ? (
                      <p className="muted">Replacement test passed. Save is now enabled.</p>
                    ) : null}
                  </form>
                ) : null}
              </div>
            );
          })}
        </div>
      </section>
    </>
  );
}
