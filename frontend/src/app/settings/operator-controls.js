"use client";

import { useCallback, useEffect, useState } from "react";

import { studioStore } from "../../components/store";
import {
  apiUrl,
  getDatabaseConnections,
  getRenderConfig,
  listProviderCredentials,
  persistDatabaseEnvToRender,
  saveRenderConfig,
  testDatabaseTransferTargets,
  testRenderConfig,
  transferDatabases,
  upsertProviderCredential,
} from "../../lib/api-client";
import { supportedProviders } from "../../lib/model-options";
import styles from "./settings.module.css";

const supportedProviderNames = new Set(supportedProviders.map((provider) => provider.value));
const emptyProviderForm = { providerName: "openrouter", secret: "" };
const emptyRenderForm = { serviceId: "", apiToken: "" };
const emptyDatabaseForm = {
  masterRouterDbUrl: "",
  metadataSidebarDbUrl: "",
  transactionalLogsDbUrl: "",
  confirmation: "",
  replaceExisting: false,
  applyToCurrentProcess: true,
  persistToRender: true,
  triggerRenderDeploy: true,
};

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

function supportedCredentialMap(credentials) {
  return new Map(
    credentials
      .filter((credential) => supportedProviderNames.has(credential.provider_name))
      .map((credential) => [credential.provider_name, credential])
  );
}

function missingProviderOptions(credentials) {
  const configured = supportedCredentialMap(credentials);
  return supportedProviders.filter((provider) => !configured.has(provider.value));
}

async function responseErrorMessage(response) {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload.detail) {
      return JSON.stringify(payload.detail);
    }
  } catch {
    // Fall through to generic status message.
  }
  return `Request failed with status ${response.status}.`;
}

export function OperatorControls({ isAdmin, onUnauthorized }) {
  const [providerCredentials, setProviderCredentials] = useState([]);
  const [providerForm, setProviderForm] = useState(emptyProviderForm);
  const [renderForm, setRenderForm] = useState(emptyRenderForm);
  const [renderConfig, setRenderConfig] = useState(null);
  const [renderResult, setRenderResult] = useState(null);
  const [renderEditMode, setRenderEditMode] = useState(false);
  const [databaseConnections, setDatabaseConnections] = useState(null);
  const [databaseForm, setDatabaseForm] = useState(emptyDatabaseForm);
  const [databaseResult, setDatabaseResult] = useState(null);
  const [databaseEditMode, setDatabaseEditMode] = useState(false);
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
      const [credentials, renderState, databaseState] = await Promise.all([
        listProviderCredentials(),
        getRenderConfig(),
        getDatabaseConnections(),
      ]);
      const missingProviders = missingProviderOptions(credentials);
      setProviderCredentials(credentials);
      setProviderForm((current) => ({
        ...current,
        providerName: missingProviders.some((provider) => provider.value === current.providerName)
          ? current.providerName
          : missingProviders[0]?.value ?? current.providerName,
        secret: "",
      }));
      setRenderConfig(renderState);
      setRenderForm((current) => ({
        ...current,
        serviceId: current.serviceId || renderState.service_id || "",
        apiToken: "",
      }));
      setDatabaseConnections(databaseState);
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
    const configured = supportedCredentialMap(providerCredentials);
    if (configured.has(providerForm.providerName)) {
      setError(`Delete the existing ${providerForm.providerName} key before adding another one.`);
      setStatus("failed");
      return;
    }
    setStatus("loading");
    setNotice("");
    setError("");
    try {
      await upsertProviderCredential(providerForm);
      setProviderForm((current) => ({ ...current, secret: "" }));
      setNotice(`Added credential for ${providerForm.providerName}.`);
      await refreshOperatorState();
    } catch (operationError) {
      handleError(operationError, "Could not add provider credential.");
    }
  }

  async function handleDeleteProviderCredential(providerName) {
    if (!window.confirm(`Delete the ${providerName} API key? Pipeline steps using this provider will fail until you add a new key.`)) {
      return;
    }
    const sessionCredential = studioStore.getState().sessionCredential;
    if (!sessionCredential) {
      onUnauthorized();
      return;
    }
    setStatus("loading");
    setNotice("");
    setError("");
    try {
      const response = await fetch(apiUrl(`/api/admin/provider-credentials/${encodeURIComponent(providerName)}`), {
        method: "DELETE",
        headers: { ["Authori" + "zation"]: `Bearer ${sessionCredential}` },
        cache: "no-store",
      });
      if (response.status === 401) {
        studioStore.getState().clearSession();
        onUnauthorized();
        return;
      }
      if (!response.ok) {
        throw new Error(await responseErrorMessage(response));
      }
      setNotice(`Deleted credential for ${providerName}. Add a new key when needed.`);
      await refreshOperatorState();
    } catch (operationError) {
      handleError(operationError, "Could not delete provider credential.");
    }
  }

  function beginRenderEdit() {
    setRenderForm({ serviceId: renderConfig?.service_id || "", apiToken: "" });
    setRenderEditMode(true);
  }

  function cancelRenderEdit() {
    setRenderForm({ serviceId: renderConfig?.service_id || "", apiToken: "" });
    setRenderEditMode(false);
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
      setNotice("Render integration saved. The token is encrypted and shown only as a masked stored credential.");
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

  function beginDatabaseEdit() {
    setDatabaseForm(emptyDatabaseForm);
    setDatabaseEditMode(true);
  }

  function cancelDatabaseEdit() {
    setDatabaseForm(emptyDatabaseForm);
    setDatabaseEditMode(false);
  }

  async function handleDatabaseTest(event) {
    event.preventDefault();
    setStatus("loading");
    setNotice("");
    setError("");
    try {
      const result = await testDatabaseTransferTargets(databaseForm);
      setDatabaseResult(result);
      setNotice("Candidate database URLs accepted test connections.");
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not test candidate database URLs.");
    }
  }

  async function handleDatabaseTransfer() {
    setStatus("loading");
    setNotice("");
    setError("");
    try {
      const result = await transferDatabases(databaseForm);
      setDatabaseResult(result);
      let renderUpdate = null;
      if (databaseForm.persistToRender) {
        renderUpdate = await persistDatabaseEnvToRender(databaseForm);
        setRenderResult(renderUpdate);
      }
      setNotice(
        renderUpdate
          ? "Database transfer completed, Render env vars were updated, and Render deploy was triggered."
          : "Database transfer completed. Runtime pools have been updated for this process."
      );
      setDatabaseForm(emptyDatabaseForm);
      setDatabaseEditMode(false);
      await refreshOperatorState();
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not transfer databases or persist them to Render.");
    }
  }

  if (!isAdmin) {
    return null;
  }

  const configuredCredentials = supportedCredentialMap(providerCredentials);
  const addableProviderOptions = missingProviderOptions(providerCredentials);

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
            <button type="button" className="button-ghost" onClick={handleRenderConfigTest} disabled={status === "loading" || !renderConfig?.configured}>
              Test
            </button>
            <button type="button" className="button-primary" onClick={renderEditMode ? cancelRenderEdit : beginRenderEdit} disabled={status === "loading"}>
              {renderEditMode ? "Cancel" : "Change"}
            </button>
          </div>
        </div>
        <p className="muted">
          Render details are stored once and shown as masked metadata. Plain tokens are write-only and only requested when you choose Change.
        </p>
        {error ? <p className={styles.diagnosticError}>{error}</p> : null}
        {notice ? <p className={styles.diagnosticSuccess}>{notice}</p> : null}
        <div className="settings-list">
          <div className="settings-list-item">
            <div className="settings-list-main">
              <div className="settings-list-title-row"><strong>Service ID</strong><StatusPill tone={renderConfig?.service_id ? "success" : "neutral"}>{renderConfig?.service_id ? "stored" : "missing"}</StatusPill></div>
              <p className="muted"><code className={styles.inlineCode}>{renderConfig?.service_id || "Not configured"}</code></p>
            </div>
          </div>
          <div className="settings-list-item">
            <div className="settings-list-main">
              <div className="settings-list-title-row"><strong>API token</strong><StatusPill tone={renderConfig?.has_api_token ? "success" : "neutral"}>{renderConfig?.has_api_token ? "stored" : "missing"}</StatusPill></div>
              <p className="muted"><code className={styles.inlineCode}>{renderConfig?.has_api_token ? "••••••••••••••••••••" : "Not configured"}</code></p>
            </div>
          </div>
        </div>
        {(renderEditMode || !renderConfig?.configured) ? (
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
            <button type="submit" className="button-primary" disabled={status === "loading"}>Save changes</button>
          </form>
        ) : null}
        {renderResult ? (
          <div className="matrix-wrapper" tabIndex="0">
            <table className="settings-matrix">
              <thead><tr><th>Render status</th><th>Service</th><th>Deploy</th><th>Env vars</th></tr></thead>
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
            <p className="eyebrow">Database transfer</p>
            <h3>Connection migration and controlled reconnect</h3>
          </div>
          <div className={styles.headerActions}>
            <StatusPill tone={databaseConnections?.configured ? "success" : "neutral"}>{databaseConnections?.configured ? "configured" : "not checked"}</StatusPill>
            <button type="button" className="button-primary" onClick={databaseEditMode ? cancelDatabaseEdit : beginDatabaseEdit} disabled={status === "loading"}>
              {databaseEditMode ? "Cancel" : "Change"}
            </button>
          </div>
        </div>
        <p className="muted">
          Current runtime database URLs are shown masked. Full Postgres URLs are write-only and only requested when you choose Change.
        </p>
        <div className="settings-list">
          {(databaseConnections?.targets || []).map((target) => (
            <div className="settings-list-item" key={target.target}>
              <div className="settings-list-main">
                <div className="settings-list-title-row"><strong>{target.label}</strong><StatusPill tone="success">runtime</StatusPill></div>
                <p className="muted"><code className={styles.inlineCode}>{target.env_key}</code></p>
                <p className="muted"><code className={styles.inlineCode}>{target.masked_url}</code></p>
              </div>
            </div>
          ))}
        </div>
        {databaseEditMode ? (
          <>
            <form className={styles.databaseTransferForm} onSubmit={handleDatabaseTest}>
              <label>
                Master router DB URL
                <input type="password" autoComplete="off" value={databaseForm.masterRouterDbUrl} onChange={(event) => setDatabaseForm((current) => ({ ...current, masterRouterDbUrl: event.target.value }))} required />
              </label>
              <label>
                Metadata sidebar DB URL
                <input type="password" autoComplete="off" value={databaseForm.metadataSidebarDbUrl} onChange={(event) => setDatabaseForm((current) => ({ ...current, metadataSidebarDbUrl: event.target.value }))} required />
              </label>
              <label>
                Transactional logs DB URL
                <input type="password" autoComplete="off" value={databaseForm.transactionalLogsDbUrl} onChange={(event) => setDatabaseForm((current) => ({ ...current, transactionalLogsDbUrl: event.target.value }))} required />
              </label>
              <div className={styles.transferToggles}>
                <label className={styles.checkboxLabel}><input type="checkbox" checked={databaseForm.replaceExisting} onChange={(event) => setDatabaseForm((current) => ({ ...current, replaceExisting: event.target.checked }))} />Replace rows in destination</label>
                <label className={styles.checkboxLabel}><input type="checkbox" checked={databaseForm.applyToCurrentProcess} onChange={(event) => setDatabaseForm((current) => ({ ...current, applyToCurrentProcess: event.target.checked }))} />Use new pools now</label>
                <label className={styles.checkboxLabel}><input type="checkbox" checked={databaseForm.persistToRender} onChange={(event) => setDatabaseForm((current) => ({ ...current, persistToRender: event.target.checked }))} />Persist to Render env</label>
                <label className={styles.checkboxLabel}><input type="checkbox" checked={databaseForm.triggerRenderDeploy} onChange={(event) => setDatabaseForm((current) => ({ ...current, triggerRenderDeploy: event.target.checked }))} disabled={!databaseForm.persistToRender} />Trigger Render deploy</label>
              </div>
              <button type="submit" className="button-ghost" disabled={status === "loading"}>Test connections</button>
            </form>
            <div className={styles.transferConfirmRow}>
              <label>
                Confirmation phrase
                <input value={databaseForm.confirmation} onChange={(event) => setDatabaseForm((current) => ({ ...current, confirmation: event.target.value }))} placeholder="TRANSFER DATABASES" />
              </label>
              <button type="button" className="button-primary" onClick={handleDatabaseTransfer} disabled={status === "loading" || databaseForm.confirmation !== "TRANSFER DATABASES"}>
                Transfer, persist, and redeploy
              </button>
            </div>
          </>
        ) : null}
        {databaseResult ? (
          <div className="matrix-wrapper" tabIndex="0">
            <table className="settings-matrix">
              <thead><tr><th>Target</th><th>Status</th><th>Rows copied</th><th>Masked URL</th></tr></thead>
              <tbody>
                {databaseResult.targets.map((target) => (
                  <tr key={target.target}>
                    <td>{target.target}</td>
                    <td><StatusPill tone={databaseStatusTone(target.status)}>{target.status}</StatusPill></td>
                    <td>{target.row_count ?? "—"}</td>
                    <td><code className={styles.inlineCode}>{target.masked_url}</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted">{databaseResult.note}</p>
          </div>
        ) : null}
      </section>

      <section className="settings-card settings-card-wide">
        <div className={styles.cardHeaderRow}>
          <div>
            <p className="eyebrow">Secrets</p>
            <h3>Provider credentials</h3>
          </div>
          <div className={styles.headerActions}>
            <button type="button" className="button-ghost" onClick={refreshOperatorState} disabled={status === "loading"}>Refresh operator state</button>
          </div>
        </div>
        <p className="muted">Each supported provider can have exactly one active key. Delete the existing key before adding a replacement.</p>
        {addableProviderOptions.length ? (
          <form className={styles.adminForm} onSubmit={handleProviderSubmit}>
            <label>
              Provider
              <select value={providerForm.providerName} onChange={(event) => setProviderForm((current) => ({ ...current, providerName: event.target.value }))} required>
                {addableProviderOptions.map((provider) => (<option key={provider.value} value={provider.value}>{provider.label}</option>))}
              </select>
            </label>
            <label>
              API key / secret
              <input type="password" autoComplete="new-password" value={providerForm.secret} onChange={(event) => setProviderForm((current) => ({ ...current, secret: event.target.value }))} minLength={8} required />
            </label>
            <button type="submit" className="button-primary" disabled={status === "loading"}>Add encrypted key</button>
          </form>
        ) : <p className="muted">Both supported providers already have keys. Delete a key before adding another one.</p>}
        <div className="matrix-wrapper" tabIndex="0">
          <table className="settings-matrix">
            <thead><tr><th>Provider</th><th>Status</th><th>Key version</th><th>Last updated</th><th>Action</th></tr></thead>
            <tbody>{supportedProviders.map((provider) => {
              const credential = configuredCredentials.get(provider.value);
              return (
                <tr key={provider.value}>
                  <td><code className={styles.inlineCode}>{provider.value}</code></td>
                  <td><StatusPill tone={credential ? "success" : "neutral"}>{credential ? "configured" : "missing"}</StatusPill></td>
                  <td>{credential?.key_version ?? "—"}</td>
                  <td>{credential ? formatTimestamp(credential.updated_at) : "—"}</td>
                  <td><button type="button" className="button-ghost" disabled={!credential || status === "loading"} onClick={() => handleDeleteProviderCredential(provider.value)}>Delete key</button></td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      </section>
    </>
  );
}
