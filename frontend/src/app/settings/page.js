"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { StudioSidebar } from "../../components/sidebar";
import { useStudioStore } from "../../components/store";
import { ThemeModePicker } from "../../components/theme-toggle";
import { apiUrl, getApiConfigurationProblem, logout } from "../../lib/api-client";
import {
  deleteThreadEverywhere,
  openThread,
  refreshThreads,
  renameThreadEverywhere,
} from "../../lib/workspace";
import styles from "./settings.module.css";

const pipelineRows = [
  { step: "Input analysis", provider: "Server configuration", mode: "internal" },
  { step: "Reasoning branch", provider: "Server configuration", mode: "internal" },
  { step: "Terminal synthesis", provider: "Server configuration", mode: "streamed" },
];

const databaseRows = [
  {
    key: "master",
    label: "Master router",
    variable: "MASTER_ROUTER_DB_URL",
    purpose: "Users, sessions, pipeline steps, provider credential metadata.",
  },
  {
    key: "metadata",
    label: "Metadata sidebar",
    variable: "METADATA_SIDEBAR_DB_URL",
    purpose: "Thread list, workspace metadata, message history indexes.",
  },
  {
    key: "logs",
    label: "Transactional logs",
    variable: "TRANSACTIONAL_LOGS_DB_URL",
    purpose: "Execution run records, stream events, audit-oriented transaction history.",
  },
];

const runtimeRows = [
  { label: "Frontend API origin", value: process.env.NEXT_PUBLIC_FUGU_API_BASE_URL || "Same origin", owner: "Vercel env" },
  { label: "Backend live probe", value: apiUrl("/api/health/live"), owner: "Render route" },
  { label: "Backend ready probe", value: apiUrl("/api/health/ready"), owner: "Render route" },
  { label: "Session mode", value: "Volatile memory", owner: "Browser runtime" },
  { label: "Stream protocol", value: "Server-Sent Events", owner: "Backend API" },
  { label: "Reconnect policy", value: "Pre-connection retry only", owner: "Client runtime" },
];

const secretRows = [
  { variable: "SYSTEM_SESSION_SECRET", location: "Render env", description: "JWT/session signing secret." },
  { variable: "VAULT_ENCRYPTION_KEY", location: "Render env + GitHub secret", description: "Encrypts provider credentials before database storage." },
  { variable: "FUGU_PROVIDER_SECRET", location: "GitHub secret only", description: "Provider API key used by the bootstrap workflow." },
  { variable: "ALLOWED_ORIGINS", location: "Render env", description: "Exact Vercel origins allowed by CORS." },
  { variable: "NEXT_PUBLIC_FUGU_API_BASE_URL", location: "Vercel env", description: "Public backend origin. Must not include trailing /api." },
];

function statusTone(status) {
  const normalized = String(status || "").toLowerCase();
  if (["ready", "connected", "alive", "success"].includes(normalized)) {
    return "success";
  }
  if (["loading", "checking", "pending"].includes(normalized)) {
    return "loading";
  }
  if (["idle", "not checked", "not exposed"].includes(normalized)) {
    return "neutral";
  }
  return "danger";
}

function StatusPill({ status }) {
  const label = status || "not checked";
  const tone = statusTone(label);
  return <span className={`${styles.statusPill} ${styles[`statusPill${tone[0].toUpperCase()}${tone.slice(1)}`]}`}>{label}</span>;
}

function formatCheckedAt(value) {
  if (!value) {
    return "Not checked yet";
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(value);
}

function getBrowserOrigin() {
  return typeof window === "undefined" ? "Resolving…" : window.location.origin;
}

export default function SettingsPage() {
  const router = useRouter();
  const isAuthenticated = useStudioStore((state) => state.isAuthenticated);
  const username = useStudioStore((state) => state.username);
  const threads = useStudioStore((state) => state.threads);
  const activeThreadId = useStudioStore((state) => state.activeThreadId);
  const setActiveThread = useStudioStore((state) => state.setActiveThread);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [browserOrigin] = useState(getBrowserOrigin);
  const [diagnostics, setDiagnostics] = useState({ status: "idle", payload: null, error: null, checkedAt: null });

  const expireSession = useCallback(() => router.replace("/"), [router]);

  const refreshDiagnostics = useCallback(async () => {
    setDiagnostics((current) => ({ ...current, status: "loading", error: null }));
    try {
      const response = await fetch(apiUrl("/api/health/ready"), { cache: "no-store" });
      let payload = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
      if (!response.ok) {
        throw new Error(payload?.status || `Readiness check failed with HTTP ${response.status}.`);
      }
      setDiagnostics({
        status: payload?.status || "ready",
        payload,
        error: null,
        checkedAt: new Date(),
      });
    } catch (error) {
      setDiagnostics({
        status: "unavailable",
        payload: null,
        error: error instanceof Error ? error.message : "Could not reach backend readiness endpoint.",
        checkedAt: new Date(),
      });
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/");
    }
  }, [isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated) {
      return undefined;
    }
    refreshThreads().catch((error) => {
      if (error?.status === 401) {
        expireSession();
      }
    });
    const diagnosticsTimer = window.setTimeout(() => {
      refreshDiagnostics();
    }, 0);
    return () => window.clearTimeout(diagnosticsTimer);
  }, [isAuthenticated, expireSession, refreshDiagnostics]);

  async function signOut() {
    await logout();
    router.replace("/");
  }

  function openThreadFromSettings(threadId) {
    router.push("/chat");
    openThread(threadId).catch((error) => {
      if (error?.status === 401) {
        expireSession();
      }
    });
  }

  async function handleRenameThread(threadId, name) {
    try {
      await renameThreadEverywhere(threadId, name);
    } catch (error) {
      if (error?.status === 401) {
        expireSession();
      }
    }
  }

  async function handleDeleteThread(threadId, name) {
    if (window.confirm(`Delete "${name}"? Its messages and run history are removed permanently.`)) {
      try {
        await deleteThreadEverywhere(threadId);
      } catch (error) {
        if (error?.status === 401) {
          expireSession();
        }
      }
    }
  }

  if (!isAuthenticated) {
    return <main className="loading-shell">Restoring workspace…</main>;
  }

  const apiConfigurationProblem = getApiConfigurationProblem();
  const readinessStatus = diagnostics.payload?.status || diagnostics.status;
  const connectionStatuses = diagnostics.payload?.connections || {};

  return (
    <main className="studio-shell">
      <StudioSidebar
        username={username}
        threads={threads}
        activeThreadId={activeThreadId}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        onSelectThread={openThreadFromSettings}
        onNewChat={() => {
          setActiveThread(null);
          router.push("/chat");
        }}
        onRenameThread={handleRenameThread}
        onDeleteThread={handleDeleteThread}
        onSignOut={signOut}
      />
      <section className="settings-panel" aria-labelledby="settings-title">
        <header className="workspace-header">
          <button
            type="button"
            className="icon-button sidebar-toggle"
            aria-label="Open navigation"
            onClick={() => setIsSidebarOpen(true)}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <div>
            <h1 className="workspace-title" id="settings-title">Settings</h1>
            <p className={styles.headerSubtitle}>Deployment, runtime, database, and client controls for this Fugu environment.</p>
          </div>
        </header>

        <div className="settings-grid">
          <section className="settings-card settings-card-wide">
            <div className={styles.cardHeaderRow}>
              <div>
                <p className="eyebrow">System diagnostics</p>
                <h3>Backend and database readiness</h3>
              </div>
              <div className={styles.headerActions}>
                <StatusPill status={readinessStatus} />
                <button type="button" className="button-ghost" onClick={refreshDiagnostics} disabled={diagnostics.status === "loading"}>
                  {diagnostics.status === "loading" ? "Checking…" : "Refresh"}
                </button>
              </div>
            </div>
            <p className="muted">
              This checks the live backend readiness endpoint and reports sanitized pool health. Full SQL URLs are intentionally not exposed to the browser.
            </p>
            {diagnostics.error ? <p className={styles.diagnosticError}>{diagnostics.error}</p> : null}
            <div className="matrix-wrapper" tabIndex="0">
              <table className="settings-matrix">
                <thead><tr><th>Database</th><th>Env variable</th><th>Status</th><th>Purpose</th></tr></thead>
                <tbody>
                  {databaseRows.map((row) => (
                    <tr key={row.key}>
                      <td>{row.label}</td>
                      <td><code className={styles.inlineCode}>{row.variable}</code></td>
                      <td><StatusPill status={connectionStatuses[row.key] || (diagnostics.status === "loading" ? "checking" : "not checked")} /></td>
                      <td>{row.purpose}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted">Last checked: {formatCheckedAt(diagnostics.checkedAt)}.</p>
          </section>

          <section className="settings-card settings-card-wide">
            <p className="eyebrow">Deployment boundary</p>
            <h3>Frontend, backend, and routing</h3>
            {apiConfigurationProblem ? <p className={styles.diagnosticError}>{apiConfigurationProblem}</p> : null}
            <dl className="definition-list">
              <div><dt>Browser origin</dt><dd>{browserOrigin}</dd></div>
              {runtimeRows.map((row) => (
                <div key={row.label}>
                  <dt>{row.label}</dt>
                  <dd><span className={styles.valueBlock}>{row.value}</span><span className={styles.valueOwner}>{row.owner}</span></dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="settings-card settings-card-wide">
            <p className="eyebrow">Operator configuration</p>
            <h3>Secrets and server-side variables</h3>
            <p className="muted">
              These are the values that belong in Render, Vercel, or GitHub Actions. The Settings page shows names and responsibility only; secret values stay server-side.
            </p>
            <div className="matrix-wrapper" tabIndex="0">
              <table className="settings-matrix">
                <thead><tr><th>Variable</th><th>Where set</th><th>Use</th></tr></thead>
                <tbody>
                  {secretRows.map((row) => (
                    <tr key={row.variable}>
                      <td><code className={styles.inlineCode}>{row.variable}</code></td>
                      <td>{row.location}</td>
                      <td>{row.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="settings-card">
            <p className="eyebrow">Appearance</p>
            <h3>Theme</h3>
            <p className="muted">
              Light is the default. System follows your device preference and updates live when it changes.
            </p>
            <ThemeModePicker />
          </section>

          <section className="settings-card">
            <p className="eyebrow">Client boundary</p>
            <h3>Rendering and lifecycle</h3>
            <ul className="check-list">
              <li>Session state resets after expiry</li>
              <li>Messages render through an element-only markdown renderer; raw HTML is never interpreted</li>
              <li>Cancellation terminates the active request</li>
              <li>Malformed frames surface controlled errors</li>
            </ul>
          </section>

          <section className="settings-card settings-card-wide">
            <p className="eyebrow">Graph topology</p>
            <h3>Configured execution stages</h3>
            <div className="matrix-wrapper" tabIndex="0">
              <table className="settings-matrix">
                <thead><tr><th>Stage</th><th>Provider</th><th>Visibility</th></tr></thead>
                <tbody>
                  {pipelineRows.map((row) => (
                    <tr key={row.step}>
                      <td>{row.step}</td><td>{row.provider}</td><td>{row.mode}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted">Pipeline definitions and provider configuration remain controlled by the backend bootstrap workflow.</p>
          </section>
        </div>
      </section>
    </main>
  );
}
