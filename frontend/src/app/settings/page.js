"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { StudioSidebar } from "../../components/sidebar";
import { useStudioStore } from "../../components/store";
import { logout } from "../../lib/api-client";

const pipelineRows = [
  { step: "Input analysis", provider: "Server configuration", mode: "internal" },
  { step: "Reasoning branch", provider: "Server configuration", mode: "internal" },
  { step: "Terminal synthesis", provider: "Server configuration", mode: "streamed" },
];

export default function SettingsPage() {
  const router = useRouter();
  const isAuthenticated = useStudioStore((state) => state.isAuthenticated);
  const username = useStudioStore((state) => state.username);
  const activeThreadId = useStudioStore((state) => state.activeThreadId);
  const setActiveThread = useStudioStore((state) => state.setActiveThread);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/");
    }
  }, [isAuthenticated, router]);

  async function signOut() {
    await logout();
    router.replace("/");
  }

  if (!isAuthenticated) {
    return <main className="loading-shell">Restoring workspace…</main>;
  }

  return (
    <main className="studio-shell">
      <StudioSidebar
        username={username}
        activeThreadId={activeThreadId}
        onSelectThread={setActiveThread}
        onSignOut={signOut}
      />
      <section className="settings-panel" aria-labelledby="settings-title">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">Configuration matrix</p>
            <h2 id="settings-title">Pipeline settings</h2>
          </div>
          <span className="status-tag status-idle">Read-only client view</span>
        </header>
        <div className="settings-grid">
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
          <section className="settings-card">
            <p className="eyebrow">Client boundary</p>
            <h3>Rendering and lifecycle</h3>
            <ul className="check-list">
              <li>Session state resets after expiry</li>
              <li>Messages render as plain text</li>
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
            <p className="muted">Pipeline definitions and provider configuration remain controlled by the backend.</p>
          </section>
        </div>
      </section>
    </main>
  );
}
