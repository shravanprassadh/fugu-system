"use client";

import Link from "next/link";
import { useState } from "react";

export function StudioSidebar({ username, activeThreadId, onSelectThread, onSignOut }) {
  const [threadValue, setThreadValue] = useState(activeThreadId ? String(activeThreadId) : "1");

  function applyThread(event) {
    event.preventDefault();
    const parsed = Number.parseInt(threadValue, 10);
    if (Number.isInteger(parsed) && parsed > 0) {
      onSelectThread(parsed);
    }
  }

  return (
    <aside className="studio-sidebar" aria-label="Studio navigation">
      <div>
        <p className="eyebrow">Fugu system</p>
        <h1 className="wordmark">Kernel Studio</h1>
        <p className="muted">Signed in as {username}</p>
      </div>

      <form className="thread-selector" onSubmit={applyThread}>
        <label htmlFor="thread-id">Thread identifier</label>
        <div className="thread-selector-row">
          <input
            id="thread-id"
            inputMode="numeric"
            pattern="[0-9]*"
            value={threadValue}
            onChange={(event) => setThreadValue(event.target.value)}
          />
          <button type="submit">Open</button>
        </div>
      </form>

      <nav className="sidebar-nav" aria-label="Workspace pages">
        <Link href="/chat">Conversation</Link>
        <Link href="/settings">Pipeline settings</Link>
      </nav>

      <div className="sidebar-footer">
        <p className="muted">Active thread</p>
        <strong>{activeThreadId ?? "None"}</strong>
        <button className="button-secondary" type="button" onClick={onSignOut}>
          Sign out
        </button>
      </div>
    </aside>
  );
}
