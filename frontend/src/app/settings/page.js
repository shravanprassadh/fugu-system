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
import { ModelPreferenceCard } from "./model-preference-card";
import { OperatorControls } from "./operator-controls";
import styles from "./settings.module.css";

const MAX_USER_ACCOUNTS = 3;

const settingsSections = [
  {
    id: "general",
    label: "General",
    description: "Theme, model and client behavior",
  },
  {
    id: "members",
    label: "Members",
    description: "Users and access",
    adminOnly: true,
  },
  {
    id: "ai",
    label: "AI operations",
    description: "API keys, pipeline, databases and deployment",
    adminOnly: true,
  },
  {
    id: "system",
    label: "System",
    description: "Health, routing and deployment variables",
  },
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
  { label: "Session mode", value: "48-hour persisted browser session", owner: "Browser runtime" },
  { label: "Stream protocol", value: "Server-Sent Events", owner: "Backend API" },
];

const secretRows = [
  { variable: "SYSTEM_SESSION_SECRET", location: "Render env", description: "JWT/session signing secret." },
  { variable: "VAULT_ENCRYPTION_KEY", location: "Render env", description: "Encrypts provider credentials before database storage." },
  { variable: "ALLOWED_ORIGINS", location: "Render env", description: "Exact Vercel origins allowed by CORS." },
  { variable: "NEXT_PUBLIC_FUGU_API_BASE_URL", location: "Vercel env", description: "Public backend origin. Must not include trailing /api." },
];

const emptyNewUser = { username: "", password: "", role: "user", isActive: true };
const emptyPasswordResetDraft = { password: "", confirmation: "" };

const createUserOverlayStyle = {
  position: "fixed",
  inset: 0,
  zIndex: 60,
  display: "grid",
  placeItems: "center",
  background: "rgba(7, 10, 18, 0.52)",
  padding: "1rem",
};

const createUserDialogStyle = {
  width: "min(100%, 34rem)",
  border: "1px solid color-mix(in srgb, var(--line) 78%, transparent)",
  borderRadius: "24px",
  background: "var(--surface)",
  boxShadow: "0 30px 90px rgba(0, 0, 0, 0.28)",
  padding: "1.1rem",
};

const createUserDialogHeaderStyle = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  gap: "1rem",
  marginBottom: "0.85rem",
};

function statusTone(status) {
  const normalized = String(status || "").toLowerCase();
  if (["ready", "connected", "alive", "success", "active", "admin", "user"].includes(normalized)) {
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
  const [activeSection, setActiveSection] = useState("general");
  const [browserOrigin] = useState(getBrowserOrigin);
  const [diagnostics, setDiagnostics] = useState({ status: "idle", payload: null, error: null, checkedAt: null });
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminStatus, setAdminStatus] = useState("idle");
  const [adminError, setAdminError] = useState("");
  const [adminNotice, setAdminNotice] = useState("");
  const [newUser, setNewUser] = useState(emptyNewUser);
  const [isCreateUserOpen, setIsCreateUserOpen] = useState(false);
  const [activePasswordResetUserId, setActivePasswordResetUserId] = useState(null);
  const [passwordDrafts, setPasswordDrafts] = useState({});

  const expireSession = useCallback(() => router.replace("/"), [router]);
  const isAdmin = userRole === "admin";
  const hasReachedUserLimit = adminUsers.length >= MAX_USER_ACCOUNTS;

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

  useEffect(() => {
    if (isAdmin || !["members", "ai"].includes(activeSection)) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setActiveSection("general");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activeSection, isAdmin]);

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

  function openCreateUser() {
    setAdminError("");
    setAdminNotice("");
    setNewUser(emptyNewUser);
    setIsCreateUserOpen(true);
  }

  function cancelCreateUser() {
    setNewUser(emptyNewUser);
    setIsCreateUserOpen(false);
    setAdminError("");
  }

  async function handleCreateUser(event) {
    event.preventDefault();
    if (hasReachedUserLimit) {
      setAdminError(`Fugu is limited to ${MAX_USER_ACCOUNTS} user accounts. Delete an existing user before creating another one.`);
      setAdminStatus("failed");
      return;
    }
    setAdminError("");
    setAdminNotice("");
    setAdminStatus("loading");
    try {
      await createAdminUser(newUser);
      setNewUser(emptyNewUser);
      setIsCreateUserOpen(false);
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

  function beginPasswordReset(targetUser) {
    setAdminError("");
    setAdminNotice("");
    setActivePasswordResetUserId(targetUser.id);
    setPasswordDrafts((current) => ({
      ...current,
      [targetUser.id]: current[targetUser.id] ?? emptyPasswordResetDraft,
    }));
  }

  function cancelPasswordReset(targetUser) {
    setAdminError("");
    setActivePasswordResetUserId((current) => (current === targetUser.id ? null : current));
    setPasswordDrafts((current) => {
      const next = { ...current };
      delete next[targetUser.id];
      return next;
    });
  }

  function updatePasswordDraft(targetUser, field, value) {
    setPasswordDrafts((current) => ({
      ...current,
      [targetUser.id]: {
        ...(current[targetUser.id] ?? emptyPasswordResetDraft),
        [field]: value,
      },
    }));
  }

  async function handleResetPassword(targetUser) {
    const draft = passwordDrafts[targetUser.id] || emptyPasswordResetDraft;
    const password = draft.password || "";
    const confirmation = draft.confirmation || "";
    if (password.length < 8) {
      setAdminError("Passwords must be at least 8 characters.");
      return;
    }
    if (password !== confirmation) {
      setAdminError("Password confirmation does not match.");
      return;
    }
    setAdminError("");
    setAdminNotice("");
    setAdminStatus("loading");
    try {
      await resetAdminUserPassword(targetUser.id, password);
      setPasswordDrafts((current) => {
        const next = { ...current };
        delete next[targetUser.id];
        return next;
      });
      setActivePasswordResetUserId(null);
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
  const visibleSections = settingsSections.filter((section) => !section.adminOnly || isAdmin);
  const currentSection = visibleSections.find((section) => section.id === activeSection) || visibleSections[0];

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
            <p className={styles.headerSubtitle}>Configure Fugu without leaving the app.</p>
          </div>
        </header>

        <div className="settings-shell">
          <aside className="settings-nav" aria-label="Settings sections">
            {visibleSections.map((section) => (
              <button
                key={section.id}
                type="button"
                className={`settings-nav-item ${currentSection.id === section.id ? "settings-nav-item-active" : ""}`}
                onClick={() => setActiveSection(section.id)}
              >
                <span className="settings-nav-label">{section.label}</span>
                <span className="settings-nav-description">{section.description}</span>
              </button>
            ))}
            <div style={{ marginTop: "auto", paddingTop: "0.75rem" }}>
              <button
                type="button"
                className="settings-nav-item"
                onClick={signOut}
                style={{ width: "100%", color: "var(--danger)" }}
              >
                <span className="settings-nav-label">Log out</span>
                <span className="settings-nav-description">End current session</span>
              </button>
            </div>
          </aside>

          <div className="settings-content">
            <div className="settings-section-heading">
              <p className="eyebrow">{currentSection.label}</p>
              <h2>{currentSection.description}</h2>
            </div>

            {currentSection.id === "general" ? (
              <div className="settings-stack">
                <section className="settings-pane">
                  <div className="settings-row">
                    <div>
                      <h3>Theme</h3>
                      <p className="muted">Choose a fixed theme or follow your device preference.</p>
                    </div>
                    <ThemeModePicker />
                  </div>
                </section>

                <ModelPreferenceCard />

                <section className="settings-pane">
                  <div className="settings-row settings-row-top">
                    <div>
                      <h3>Client safety</h3>
                      <p className="muted">Browser-side safeguards for rendering, sessions, cancellation, and stream errors.</p>
                    </div>
                  </div>
                  <ul className="check-list settings-check-list">
                    <li>Session state resets after expiry</li>
                    <li>Messages render through an element-only markdown renderer; raw HTML is never interpreted</li>
                    <li>Cancellation terminates the active request</li>
                    <li>Malformed stream frames surface controlled errors</li>
                  </ul>
                </section>
              </div>
            ) : null}

            {currentSection.id === "members" ? (
              <div className="settings-stack">
                <section className="settings-pane">
                  <div className="settings-row settings-row-top">
                    <div>
                      <h3>Members</h3>
                      <p className="muted">View and maintain existing accounts. New account creation is kept separate from the member list.</p>
                    </div>
                    <div className={styles.headerActions}>
                      <StatusPill status={hasReachedUserLimit ? "limit reached" : adminStatus} />
                      <button type="button" className="button-ghost" onClick={loadAdminUsers} disabled={adminStatus === "loading"}>
                        {adminStatus === "loading" ? "Loading…" : "Refresh"}
                      </button>
                      <button
                        type="button"
                        className="button-primary"
                        onClick={openCreateUser}
                        disabled={adminStatus === "loading" || hasReachedUserLimit}
                      >
                        New user
                      </button>
                    </div>
                  </div>
                  <p className="muted">{adminUsers.length}/{MAX_USER_ACCOUNTS} accounts used.</p>
                  {adminError ? <p className={styles.diagnosticError}>{adminError}</p> : null}
                  {adminNotice ? <p className={styles.diagnosticSuccess}>{adminNotice}</p> : null}
                  {hasReachedUserLimit ? <p className={styles.diagnosticError}>Fugu is limited to {MAX_USER_ACCOUNTS} user accounts. Delete an existing user before creating another one.</p> : null}
                </section>

                <section className="settings-pane">
                  <div className="settings-row settings-row-top">
                    <div>
                      <h3>Current members</h3>
                      <p className="muted">Each row contains only that account's state and controls.</p>
                    </div>
                  </div>
                  <div className="settings-list">
                    {adminUsers.length === 0 && adminStatus !== "loading" ? (
                      <div className="settings-list-item">
                        <div className="settings-list-main">
                          <strong>No members loaded</strong>
                          <p className="muted">Refresh the member list to load current accounts.</p>
                        </div>
                      </div>
                    ) : null}
                    {adminUsers.map((account) => {
                      const isSelf = account.id === userId;
                      const isResettingPassword = activePasswordResetUserId === account.id;
                      const passwordDraft = passwordDrafts[account.id] || emptyPasswordResetDraft;
                      const canSavePassword = passwordDraft.password.length >= 8 && passwordDraft.password === passwordDraft.confirmation;
                      return (
                        <article className={`settings-list-item ${styles.memberListItem}`} key={account.id}>
                          <div className="settings-list-main">
                            <div className="settings-list-title-row">
                              <strong>{account.username}</strong>
                              {isSelf ? <span className="settings-meta-pill">you</span> : null}
                              <StatusPill status={account.role} />
                              <StatusPill status={account.is_active ? "active" : "inactive"} />
                            </div>
                            <p className="muted">ID {account.id} · token v{account.token_version} · {account.thread_count} threads</p>
                          </div>
                          <div className={styles.adminActions}>
                            <button type="button" className="button-ghost" disabled={isSelf || adminStatus === "loading"} onClick={() => handleUpdateUser(account, { role: account.role === "admin" ? "user" : "admin" })}>
                              {account.role === "admin" ? "Make user" : "Make admin"}
                            </button>
                            <button type="button" className="button-ghost" disabled={isSelf || adminStatus === "loading"} onClick={() => handleUpdateUser(account, { isActive: !account.is_active })}>
                              {account.is_active ? "Deactivate" : "Reactivate"}
                            </button>
                            <button type="button" className="button-ghost" disabled={adminStatus === "loading"} onClick={() => (isResettingPassword ? cancelPasswordReset(account) : beginPasswordReset(account))}>
                              {isResettingPassword ? "Cancel reset" : "Reset password"}
                            </button>
                            <button type="button" className="button-ghost" disabled={isSelf || adminStatus === "loading"} onClick={() => handleDeleteUser(account)}>Delete</button>
                          </div>
                          {isResettingPassword ? (
                            <form className={styles.passwordResetPanel} onSubmit={(event) => { event.preventDefault(); handleResetPassword(account); }}>
                              <label>
                                New password
                                <input type="password" autoComplete="new-password" minLength={8} placeholder="At least 8 characters" value={passwordDraft.password} onChange={(event) => updatePasswordDraft(account, "password", event.target.value)} required />
                              </label>
                              <label>
                                Confirm password
                                <input type="password" autoComplete="new-password" minLength={8} placeholder="Repeat new password" value={passwordDraft.confirmation} onChange={(event) => updatePasswordDraft(account, "confirmation", event.target.value)} required />
                              </label>
                              <div className={styles.passwordResetActions}>
                                <button type="button" className="button-ghost" onClick={() => cancelPasswordReset(account)} disabled={adminStatus === "loading"}>Cancel</button>
                                <button type="submit" className="button-primary" disabled={adminStatus === "loading" || !canSavePassword}>Save password</button>
                              </div>
                            </form>
                          ) : null}
                        </article>
                      );
                    })}
                  </div>
                </section>
              </div>
            ) : null}

            {currentSection.id === "ai" ? <OperatorControls isAdmin={isAdmin} onUnauthorized={expireSession} /> : null}

            {currentSection.id === "system" ? (
              <div className="settings-stack">
                <section className="settings-pane">
                  <div className="settings-row settings-row-top">
                    <div>
                      <h3>Backend readiness</h3>
                      <p className="muted">Sanitized pool health from the live backend readiness endpoint.</p>
                    </div>
                    <div className={styles.headerActions}>
                      <StatusPill status={readinessStatus} />
                      <button type="button" className="button-ghost" onClick={refreshDiagnostics} disabled={diagnostics.status === "loading"}>
                        {diagnostics.status === "loading" ? "Checking…" : "Refresh"}
                      </button>
                    </div>
                  </div>
                  {diagnostics.error ? <p className={styles.diagnosticError}>{diagnostics.error}</p> : null}
                  <div className="settings-list">
                    {databaseRows.map((row) => (
                      <div className="settings-list-item" key={row.key}>
                        <div className="settings-list-main">
                          <div className="settings-list-title-row">
                            <strong>{row.label}</strong>
                            <StatusPill status={connectionStatuses[row.key] || (diagnostics.status === "loading" ? "checking" : "not checked")} />
                          </div>
                          <p className="muted"><code className={styles.inlineCode}>{row.variable}</code></p>
                          <p className="muted">{row.purpose}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="muted">Last checked: {formatCheckedAt(diagnostics.checkedAt)}.</p>
                </section>

                <section className="settings-pane">
                  <div className="settings-row settings-row-top">
                    <div>
                      <h3>Deployment boundary</h3>
                      <p className="muted">Frontend, backend, browser, and stream routing.</p>
                    </div>
                  </div>
                  {apiConfigurationProblem ? <p className={styles.diagnosticError}>{apiConfigurationProblem}</p> : null}
                  <dl className="definition-list settings-definition-list">
                    <div><dt>Browser origin</dt><dd>{browserOrigin}</dd></div>
                    {runtimeRows.map((row) => (
                      <div key={row.label}>
                        <dt>{row.label}</dt>
                        <dd><span className={styles.valueBlock}>{row.value}</span><span className={styles.valueOwner}>{row.owner}</span></dd>
                      </div>
                    ))}
                  </dl>
                </section>

                <section className="settings-pane">
                  <div className="settings-row settings-row-top">
                    <div>
                      <h3>Deployment variables</h3>
                      <p className="muted">Deployment-level variables still owned by Render and Vercel.</p>
                    </div>
                  </div>
                  <div className="settings-list">
                    {secretRows.map((row) => (
                      <div className="settings-list-item" key={row.variable}>
                        <div className="settings-list-main">
                          <div className="settings-list-title-row">
                            <code className={styles.inlineCode}>{row.variable}</code>
                            <span className="settings-meta-pill">{row.location}</span>
                          </div>
                          <p className="muted">{row.description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      {isCreateUserOpen ? (
        <div style={createUserOverlayStyle} role="presentation" onClick={cancelCreateUser}>
          <section style={createUserDialogStyle} role="dialog" aria-modal="true" aria-labelledby="create-user-title" onClick={(event) => event.stopPropagation()}>
            <div style={createUserDialogHeaderStyle}>
              <div>
                <h3 id="create-user-title" style={{ margin: 0 }}>Create user</h3>
                <p className="muted">Add a new account only when you need one. Limit: {adminUsers.length}/{MAX_USER_ACCOUNTS}.</p>
              </div>
              <button type="button" className="button-ghost" onClick={cancelCreateUser} disabled={adminStatus === "loading"}>Close</button>
            </div>
            <form className={styles.adminForm} onSubmit={handleCreateUser} style={{ margin: 0 }}>
              <label>
                Username
                <input value={newUser.username} minLength={3} maxLength={255} onChange={(event) => setNewUser((current) => ({ ...current, username: event.target.value }))} required autoFocus />
              </label>
              <label>
                Initial password
                <input type="password" autoComplete="new-password" value={newUser.password} minLength={8} onChange={(event) => setNewUser((current) => ({ ...current, password: event.target.value }))} required />
              </label>
              <label>
                Role
                <select value={newUser.role} onChange={(event) => setNewUser((current) => ({ ...current, role: event.target.value }))}>
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </label>
              <label className={styles.checkboxLabel}>
                <input type="checkbox" checked={newUser.isActive} onChange={(event) => setNewUser((current) => ({ ...current, isActive: event.target.checked }))} />
                Active
              </label>
              <button type="button" className="button-ghost" onClick={cancelCreateUser} disabled={adminStatus === "loading"}>Cancel</button>
              <button type="submit" className="button-primary" disabled={adminStatus === "loading" || hasReachedUserLimit}>Create user</button>
            </form>
          </section>
        </div>
      ) : null}
    </main>
  );
}
