"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useStudioStore } from "../../components/store";
import { listProviderCredentials, upsertProviderCredential } from "../../lib/api-client";
import {
  replaceProviderCredential,
  testActiveProviderCredential,
  testCandidateProviderCredential,
} from "../../lib/provider-credential-api";
import { supportedProviders } from "../../lib/model-options";
import styles from "./settings.module.css";

const overlayStyle = {
  position: "fixed",
  inset: 0,
  zIndex: 90,
  display: "grid",
  placeItems: "center",
  background: "rgba(7, 10, 18, 0.58)",
  padding: "1rem",
};

const dialogStyle = {
  width: "min(100%, 34rem)",
  maxHeight: "calc(100dvh - 2rem)",
  overflowY: "auto",
  border: "1px solid color-mix(in srgb, var(--line) 78%, transparent)",
  borderRadius: "24px",
  background: "var(--surface)",
  boxShadow: "0 30px 90px rgba(0, 0, 0, 0.32)",
  padding: "1.1rem",
};

function StatusPill({ children, tone = "neutral" }) {
  const className = `${styles.statusPill} ${styles[`statusPill${tone[0].toUpperCase()}${tone.slice(1)}`]}`;
  return <span className={className}>{children}</span>;
}

function formatTimestamp(value) {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function credentialMap(credentials) {
  return new Map(credentials.map((credential) => [credential.provider_name, credential]));
}

export function ProviderCredentialControls() {
  const router = useRouter();
  const userRole = useStudioStore((state) => state.userRole);
  const clearSession = useStudioStore((state) => state.clearSession);
  const [credentials, setCredentials] = useState([]);
  const [status, setStatus] = useState("idle");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [editor, setEditor] = useState(null);
  const [secret, setSecret] = useState("");
  const [candidateResult, setCandidateResult] = useState(null);

  const expireSession = useCallback(() => {
    clearSession();
    router.replace("/");
  }, [clearSession, router]);

  const handleError = useCallback(
    (operationError, fallback) => {
      if (operationError?.status === 401) {
        expireSession();
      }
      setError(operationError.message || fallback);
      setStatus("failed");
    },
    [expireSession],
  );

  const refreshCredentials = useCallback(async () => {
    if (userRole !== "admin") {
      return;
    }
    setStatus("loading");
    setError("");
    try {
      setCredentials(await listProviderCredentials());
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not load provider credentials.");
    }
  }, [handleError, userRole]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      refreshCredentials();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshCredentials]);

  const closeEditor = useCallback(() => {
    setEditor(null);
    setSecret("");
    setCandidateResult(null);
  }, []);

  useEffect(() => {
    if (!editor) {
      return undefined;
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        closeEditor();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [closeEditor, editor]);

  function openEditor(providerName, mode) {
    setEditor({ providerName, mode });
    setSecret("");
    setCandidateResult(null);
    setError("");
    setNotice("");
  }

  function updateSecret(value) {
    setSecret(value);
    setCandidateResult(null);
    setError("");
  }

  async function handleActiveTest(providerName) {
    setStatus("loading");
    setError("");
    setNotice("");
    try {
      const result = await testActiveProviderCredential(providerName);
      await refreshCredentials();
      if (result.valid) {
        setNotice(`${providerName} active key passed validation.`);
        setStatus("ready");
      } else {
        setError(result.message);
        setStatus("failed");
      }
    } catch (operationError) {
      handleError(operationError, `Could not test the active ${providerName} key.`);
    }
  }

  async function handleCandidateTest() {
    if (!editor || secret.trim().length < 8) {
      setError("Enter a candidate key with at least 8 characters before testing.");
      return;
    }
    setStatus("loading");
    setError("");
    setNotice("");
    try {
      const result = await testCandidateProviderCredential(editor.providerName, secret.trim());
      setCandidateResult({ ...result, secret: secret.trim() });
      if (result.valid) {
        setNotice("Candidate validation passed. Activation is now enabled.");
        setStatus("ready");
      } else {
        setError(result.message);
        setStatus("failed");
      }
    } catch (operationError) {
      handleError(operationError, `Could not test the candidate ${editor.providerName} key.`);
    }
  }

  async function handleActivation() {
    if (!editor || !candidateResult?.valid || candidateResult.secret !== secret.trim()) {
      setError("Test this exact candidate key before activation.");
      return;
    }
    setStatus("loading");
    setError("");
    setNotice("");
    try {
      const result =
        editor.mode === "create"
          ? await upsertProviderCredential({ providerName: editor.providerName, secret: secret.trim() })
          : await replaceProviderCredential(editor.providerName, secret.trim());
      if (!result.activated) {
        setCandidateResult({ valid: false, message: result.message, secret: secret.trim() });
        setError(result.message);
        setStatus("failed");
        return;
      }
      const providerName = editor.providerName;
      const action = editor.mode === "create" ? "activated" : "replaced";
      closeEditor();
      await refreshCredentials();
      setNotice(`${providerName} key was ${action} after successful validation.`);
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, `Could not activate the ${editor.providerName} candidate key.`);
    }
  }

  if (userRole !== "admin") {
    return null;
  }

  const configured = credentialMap(credentials);
  const candidateReady = candidateResult?.valid === true && candidateResult.secret === secret.trim();

  return (
    <section className="settings-card settings-card-wide">
      <div className={styles.cardHeaderRow}>
        <div>
          <p className="eyebrow">Provider access</p>
          <h3>API credentials</h3>
        </div>
        <button
          type="button"
          className="button-ghost"
          onClick={refreshCredentials}
          disabled={status === "loading"}
        >
          Refresh
        </button>
      </div>
      <p className="muted">
        Each provider has exactly one active key. Test it at any time, or validate a candidate before replacing it. A rejected candidate never interrupts the current key.
      </p>
      {error ? <p className={styles.diagnosticError}>{error}</p> : null}
      {notice ? <p className={styles.diagnosticSuccess}>{notice}</p> : null}
      <div className="matrix-wrapper" tabIndex="0">
        <table className="settings-matrix">
          <thead>
            <tr>
              <th>Provider</th>
              <th>Status</th>
              <th>Version</th>
              <th>Last updated</th>
              <th>Last successful test</th>
              <th>Last failure</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {supportedProviders.map((provider) => {
              const credential = configured.get(provider.value);
              return (
                <tr key={provider.value}>
                  <td>
                    <strong>{provider.label}</strong>
                    <br />
                    <code className={styles.inlineCode}>{provider.value}</code>
                  </td>
                  <td>
                    <StatusPill tone={credential ? "success" : "neutral"}>
                      {credential ? "configured" : "missing"}
                    </StatusPill>
                  </td>
                  <td>{credential?.key_version ?? "—"}</td>
                  <td>{formatTimestamp(credential?.updated_at)}</td>
                  <td>{formatTimestamp(credential?.last_successful_test_at)}</td>
                  <td>
                    {credential?.last_test_failure_at ? (
                      <span title={credential.last_test_failure_message || "Validation failed"}>
                        {formatTimestamp(credential.last_test_failure_at)}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    <div className={styles.adminActions}>
                      <button
                        type="button"
                        className="button-ghost"
                        disabled={!credential || status === "loading"}
                        onClick={() => handleActiveTest(provider.value)}
                      >
                        Test
                      </button>
                      <button
                        type="button"
                        className="button-primary"
                        disabled={status === "loading"}
                        onClick={() => openEditor(provider.value, credential ? "replace" : "create")}
                      >
                        {credential ? "Change key" : "Add key"}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {editor ? (
        <div style={overlayStyle} role="presentation" onMouseDown={closeEditor}>
          <div
            style={dialogStyle}
            role="dialog"
            aria-modal="true"
            aria-labelledby="provider-key-dialog-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className={styles.cardHeaderRow}>
              <div>
                <p className="eyebrow">Write-only credential</p>
                <h3 id="provider-key-dialog-title">
                  {editor.mode === "create" ? "Add" : "Change"} {editor.providerName} key
                </h3>
              </div>
              <button type="button" className="button-ghost" onClick={closeEditor}>
                Close
              </button>
            </div>
            <p className="muted">
              The candidate is tested without being stored. The active key changes only after validation succeeds again during activation.
            </p>
            <label>
              Candidate API key
              <input
                type="password"
                autoComplete="new-password"
                value={secret}
                onChange={(event) => updateSecret(event.target.value)}
                minLength={8}
                autoFocus
                required
              />
            </label>
            {candidateResult ? (
              <p className={candidateResult.valid ? styles.diagnosticSuccess : styles.diagnosticError}>
                {candidateResult.message}
              </p>
            ) : null}
            <div className={styles.adminActions}>
              <button
                type="button"
                className="button-ghost"
                onClick={handleCandidateTest}
                disabled={status === "loading" || secret.trim().length < 8}
              >
                Test candidate
              </button>
              <button
                type="button"
                className="button-primary"
                onClick={handleActivation}
                disabled={status === "loading" || !candidateReady}
              >
                {editor.mode === "create" ? "Activate key" : "Replace active key"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
