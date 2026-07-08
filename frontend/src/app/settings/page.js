"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { StudioSidebar } from "../../components/sidebar";
import { useStudioStore } from "../../components/store";
import { ThemeModePicker } from "../../components/theme-toggle";
import {
  apiUrl,
  createAdminUser,
  deleteAdminUser,
  getApiConfigurationProblem,
  listAdminUsers,
  logout,
  resetAdminUserPassword,
  updateAdminUser,
} from "../../lib/api-client";
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

const emptyNewUser = { username: "", password: "", role: "user", isActive: true };

function statusTone(status) {
  const normalized = String(status || "").toLowerCase();
  if (["ready", "connected", "alive", "success", "active"].includes(normalized)) {
    return "success";
  }
  if (["loading", "checking", "pending"].includes(normalized)) {
    return "loading";
  }
  if (["idle", "not checked", "not exposed", "inactive"].includes(normalized)) {
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
  const userRole = useStudioStore((state) => state.userRole);
  const userId = useStudioStore((state) => state.userId);
  const threads = useStudioStore((state) => state.threads);
  const activeThreadId = useStudioStore((state) => state.activeThreadId);
  const setActiveThread = useStudioStore((state) => state.setActiveThread);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [browserOrigin] = useState(getBrowserOrigin);
  const [diagnostics, setDiagnostics] = useState({ status: "idle", payload: null, error: null, checkedAt: null });
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminStatus, setAdminStatus] = useState("idle");
  const [adminError, setAdminError] = useState("");
  const [adminNotice, setAdminNotice] = useState("");
  const [newUser, setNewUser] = useState(emptyNewUser);
  const [passwordDrafts, setPasswordDrafts] = useState({});

  const expireSession = useCallback(() => router.replace("/"), [router]);
  const isAdmin = userRole === "admin";

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

  const loadAdminUsers = useCallback(async () => {
    if (!isAdmin) {
      return;
    }
    setAdminStatus("loading");
    setAdminError("");
    try {
      const users = await listAdminUsers();
      setAdminUsers(users);
      setAdminStatus("ready");
    } catch (error) {
      if (error?.status === 401) {
        expireSession();
      }
      setAdminError(error.message || "Could not load users.");
      setAdminStatus("failed");
    }
  }, [expireSession, isAdmin]);

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
    const adminTimer = isAdmin
      ? window.setTimeout(() => {
          loadAdminUsers();
        }, 0)
      : null;
    return () => {
      window.clearTimeout(diagnosticsTimer);
      if (adminTimer) {
        window.clearTimeout(adminTimer);
      }
    };
  }, [isAuthenticated, expireSession, refreshDiagnostics, isAdmin, loadAdminUsers]);

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

  async function handleCreateUser(event) {
    event.preventDefault();
    setAdminError("");
    setAdminNotice("");
    setAdminStatus("loading");
    try {
      await createAdminUser(newUser);
      setNewUser(emptyNewUser);
      setAdminNotice(`Created ${newUser.username.trim()}.`);
      await loadAdminUsers();
    } catch (error) {
      if (error?.status === 401) {
        expireSession();
      }
      setAdminError(error.message || "Could not create user.");
      setAdminStatus("failed");
    }
  }

  async function handleUpdateUser(targetUser, update) {
    setAdminError("");
    setAdminNotice("");
    setAdminStatus("loading");
    try {
      await updateAdminUser(targetUser.id, update);
      setAdminNotice(`Updated ${targetUser.username}.`);
      await loadAdminUsers();
    } catch (error) {
      if (error?.status === 401) {
        expireSession();
      }
      setAdminError(error.message || "Could not update user.");
      setAdminStatus("failed");
    }
  }

  async function handleResetPassword(targetUser) {
    const password = passwordDrafts[targetUser.id] || "";
    if (password.length < 8) {
      setAdminError("Passwords must be at least 8 characters.");
      return;
    }
    setAdminError("");
    setAdminNotice("");
    setAdminStatus("loading");
    try {
      await resetAdminUserPassword(targetUser.id, password);
      setPasswordDrafts((current) => ({ ...current, [targetUser.id]: "" }));
      setAdminNotice(`Reset password for ${targetUser.username}.`);
      await loadAdminUsers();
    } catch (error) {
      if (error?.status === 401) {
        expireSession();
      }
      setAdminError(error.message || "Could not reset password.");
      setAdminStatus("failed");
    }
  }

  async function handleDeleteUser(targetUser) {
    if (!window.confirm(`Delete user "${targetUser.username}" and all owned threads?`)) {
      return;
    }
    setAdminError("");
    setAdminNotice("");
    setAdminStatus("loading");
    try {
      await deleteAdminUser(targetUser.id);
      setAdminNotice(`Deleted ${targetUser.username}.`);
      await loadAdminUsers();
    } catch (error) {
      if (error?.status === 401) {
        expireSession();
      }
      setAdminError(error.message || "Could not delete user.");
      setAdminStatus("failed");
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
            <p className={styles.headerSubtitle}>Deployment, runtime, database, users, and client controls for this Fugu environment.</p>
          </div>
        </header>

        <div className="settings-grid">
          <section className="settings-card settings-card-wide">
            <div className={styles.cardHeaderRow}>
              <div>
                <p className="eyebrow">Admin console</p>
                <h3>User management</h3>
              </div>
              <div className={styles.headerActions}>
                <StatusPill status={isAdmin ? adminStatus : "not exposed"} />
                {isAdmin ? (
                  <button type="button" className="button-ghost" onClick={loadAdminUsers} disabled={adminStatus === "loading"}>
                    {adminStatus === "loading" ? "Loading…" : "Refresh users"}
                  </button>
                ) : null}
              </div>
            </div>
            {isAdmin ? (
              <>
                <p className="muted">Create users, disable access, change roles, reset passwords, and delete accounts without opening Neon.</p>
                {adminError ? <p className={styles.diagnosticError}>{adminError}</p> : null}
                {adminNotice ? <p className={styles.diagnosticSuccess}>{adminNotice}</p> : null}
                <form className={styles.adminForm} onSubmit={handleCreateUser}>
                  <label>
                    Username
                    <input
                      value={newUser.username}
                      minLength={3}
                      maxLength={255}
                      onChange={(event) => setNewUser((current) => ({ ...current, username: event.target.value }))}
                      required
                    />
                  </label>
                  <label>
                    Initial password
                    <input
                      type="password"
                      autoComplete="new-password"
                      value={newUser.password}
                      minLength={8}
                      onChange={(event) => setNewUser((current) => ({ ...current, password: event.target.value }))}
                      required
                    />
                  </label>
                  <label>
                    Role
                    <select value={newUser.role} onChange={(event) => setNewUser((current) => ({ ...current, role: event.target.value }))}>
                      <option value="user">user</option>
                      <option value="admin">admin</option>
                    </select>
                  </label>
                  <label className={styles.checkboxLabel}>
                    <input
                      type="checkbox"
                      checked={newUser.isActive}
                      onChange={(event) => setNewUser((current) => ({ ...current, isActive: event.target.checked }))}
                    />
                    Active
                  </label>
                  <button type="submit" className="button-primary" disabled={adminStatus === "loading"}>Create user</button>
                </form>
                <div className="matrix-wrapper" tabIndex="0">
                  <table className="settings-matrix">
                    <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Threads</th><th>Actions</th></tr></thead>
                    <tbody>
                      {adminUsers.map((account) => {
                        const isSelf = account.id === userId;
                        return (
                          <tr key={account.id}>
                            <td>
                              <span className={styles.valueBlock}>{account.username}</span>
                              <span className={styles.valueOwner}>ID {account.id} · token v{account.token_version}</span>
                            </td>
                            <td><StatusPill status={account.role} /></td>
                            <td><StatusPill status={account.is_active ? "active" : "inactive"} /></td>
                            <td>{account.thread_count}</td>
                            <td>
                              <div className={styles.adminActions}>
                                <button
                                  type="button"
                                  className="button-ghost"
                                  disabled={isSelf || adminStatus === "loading"}
                                  onClick={() => handleUpdateUser(account, { role: account.role === "admin" ? "user" : "admin" })}
                                >
                                  {account.role === "admin" ? "Make user" : "Make admin"}
                                </button>
                                <button
                                  type="button"
                                  className="button-ghost"
                                  disabled={isSelf || adminStatus === "loading"}
                                  onClick={() => handleUpdateUser(account, { isActive: !account.is_active })}
                                >
                                  {account.is_active ? "Deactivate" : "Reactivate"}
                                </button>
                                <details className={styles.passwordReset}>
                                  <summary>Reset password</summary>
                                  <div className={styles.passwordResetFields}>
                                    <input
                                      type="password"
                                      autoComplete="new-password"
                                      minLength={8}
                                      placeholder="New password"
                                      value={passwordDrafts[account.id] || ""}
                                      onChange={(event) => setPasswordDrafts((current) => ({ ...current, [account.id]: event.target.value }))}
                                    />
                                    <button type="button" className="button-primary" onClick={() => handleResetPassword(account)} disabled={adminStatus === "loading"}>
                                      Save
                                    </button>
                                  </div>
                                </details>
                                <button
                                  type="button"
                                  className="button-ghost"
                                  disabled={isSelf || adminStatus === "loading"}
                                  onClick={() => handleDeleteUser(account)}
                                >
                                  Delete
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <p className="muted">Sign in as an admin to manage users. Regular users can view personal settings only.</p>
            )}
          </section>

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
