"use client";

import { useRouter } from "next/navigation";
<<<<<<< Updated upstream
import { useEffect } from "react";

import { StudioSidebar } from "../../components/sidebar";
import { useStudioStore } from "../../components/store";
import { logout } from "../../lib/api-client";
=======
import { useCallback, useEffect, useState } from "react";

import { StudioSidebar } from "../../components/sidebar";
import { useStudioStore } from "../../components/store";
import { ThemeModePicker } from "../../components/theme-toggle";
import { logout } from "../../lib/api-client";
import {
  deleteThreadEverywhere,
  openThread,
  refreshThreads,
  renameThreadEverywhere,
} from "../../lib/workspace";
>>>>>>> Stashed changes

const pipelineRows = [
  { step: "Input analysis", provider: "Server configuration", mode: "internal" },
  { step: "Reasoning branch", provider: "Server configuration", mode: "internal" },
  { step: "Terminal synthesis", provider: "Server configuration", mode: "streamed" },
];

export default function SettingsPage() {
  const router = useRouter();
  const isAuthenticated = useStudioStore((state) => state.isAuthenticated);
  const username = useStudioStore((state) => state.username);
<<<<<<< Updated upstream
  const activeThreadId = useStudioStore((state) => state.activeThreadId);
  const setActiveThread = useStudioStore((state) => state.setActiveThread);
=======
  const threads = useStudioStore((state) => state.threads);
  const activeThreadId = useStudioStore((state) => state.activeThreadId);
  const setActiveThread = useStudioStore((state) => state.setActiveThread);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const expireSession = useCallback(() => router.replace("/"), [router]);
>>>>>>> Stashed changes

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/");
    }
  }, [isAuthenticated, router]);

<<<<<<< Updated upstream
=======
  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }
    refreshThreads().catch((error) => {
      if (error?.status === 401) {
        expireSession();
      }
    });
  }, [isAuthenticated, expireSession]);

>>>>>>> Stashed changes
  async function signOut() {
    await logout();
    router.replace("/");
  }

<<<<<<< Updated upstream
=======
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

>>>>>>> Stashed changes
  if (!isAuthenticated) {
    return <main className="loading-shell">Restoring workspace…</main>;
  }

  return (
    <main className="studio-shell">
      <StudioSidebar
        username={username}
<<<<<<< Updated upstream
        activeThreadId={activeThreadId}
        onSelectThread={setActiveThread}
=======
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
>>>>>>> Stashed changes
        onSignOut={signOut}
      />
      <section className="settings-panel" aria-labelledby="settings-title">
        <header className="workspace-header">
<<<<<<< Updated upstream
          <div>
            <p className="eyebrow">Configuration matrix</p>
            <h2 id="settings-title">Pipeline settings</h2>
          </div>
          <span className="status-tag status-idle">Read-only client view</span>
        </header>
        <div className="settings-grid">
=======
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
          <h1 className="workspace-title" id="settings-title">Settings</h1>
        </header>

        <div className="settings-grid">
          <section className="settings-card settings-card-wide">
            <p className="eyebrow">Appearance</p>
            <h3>Theme</h3>
            <p className="muted">
              Light is the default. System follows your device preference and updates live when it changes.
            </p>
            <ThemeModePicker />
          </section>

>>>>>>> Stashed changes
          <section className="settings-card">
            <p className="eyebrow">Transport</p>
            <h3>Runtime boundary</h3>
            <dl className="definition-list">
              <div><dt>API origin</dt><dd>{process.env.NEXT_PUBLIC_FUGU_API_BASE_URL || "Same origin"}</dd></div>
              <div><dt>Session mode</dt><dd>Volatile memory</dd></div>
              <div><dt>Stream protocol</dt><dd>Server-Sent Events</dd></div>
              <div><dt>Reconnect policy</dt><dd>Pre-connection retry only</dd></div>
            </dl>
          </section>
<<<<<<< Updated upstream
=======

>>>>>>> Stashed changes
          <section className="settings-card">
            <p className="eyebrow">Client boundary</p>
            <h3>Rendering and lifecycle</h3>
            <ul className="check-list">
              <li>Session state resets after expiry</li>
<<<<<<< Updated upstream
              <li>Messages render as plain text</li>
=======
              <li>Messages render through an element-only markdown renderer; raw HTML is never interpreted</li>
>>>>>>> Stashed changes
              <li>Cancellation terminates the active request</li>
              <li>Malformed frames surface controlled errors</li>
            </ul>
          </section>
<<<<<<< Updated upstream
=======

>>>>>>> Stashed changes
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
            <p className="muted">Pipeline definitions and provider configuration remain controlled by the backend.</p>
          </section>
        </div>
      </section>
    </main>
  );
}
