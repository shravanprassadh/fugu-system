"use client";

import Link from "next/link";
import { useState } from "react";

import { useStudioStore } from "./store";
import { ThemeCycleButton } from "./theme-toggle";

function PlusIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function PencilIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6" />
    </svg>
  );
}

function ThreadListItem({ thread, isActive, onSelect, onRename, onDelete }) {
  const [isRenaming, setIsRenaming] = useState(false);
  const [draftName, setDraftName] = useState(thread.name);

  async function commitRename() {
    const nextName = draftName.trim();
    setIsRenaming(false);
    if (nextName && nextName !== thread.name) {
      await onRename(thread.id, nextName);
    } else {
      setDraftName(thread.name);
    }
  }

  if (isRenaming) {
    return (
      <li className="thread-item thread-item-editing">
        <input
          className="thread-rename-input"
          value={draftName}
          autoFocus
          maxLength={255}
          aria-label={`Rename ${thread.name}`}
          onChange={(event) => setDraftName(event.target.value)}
          onBlur={commitRename}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commitRename();
            }
            if (event.key === "Escape") {
              setDraftName(thread.name);
              setIsRenaming(false);
            }
          }}
        />
      </li>
    );
  }

  return (
    <li className={`thread-item${isActive ? " thread-item-active" : ""}`}>
      <button
        type="button"
        className="thread-open"
        onClick={() => onSelect(thread.id)}
        title={thread.name}
      >
        <span className="thread-name">{thread.name}</span>
      </button>
      <span className="thread-actions">
        <button
          type="button"
          className="icon-button icon-button-small"
          aria-label={`Rename ${thread.name}`}
          onClick={() => {
            setDraftName(thread.name);
            setIsRenaming(true);
          }}
        >
          <PencilIcon />
        </button>
        <button
          type="button"
          className="icon-button icon-button-small icon-button-danger"
          aria-label={`Delete ${thread.name}`}
          onClick={() => onDelete(thread.id, thread.name)}
        >
          <TrashIcon />
        </button>
      </span>
    </li>
  );
}

export function StudioSidebar({
  username,
  threads = [],
  threadsError = null,
  threadsLoading = false,
  activeThreadId,
  isOpen = false,
  onClose = () => {},
  onSelectThread,
  onNewChat,
  onRenameThread,
  onDeleteThread,
  onRetryThreads,
  onOpenSettings = null,
}) {
  const userRole = useStudioStore((state) => state.userRole);
  const initial = (username || "?").slice(0, 1).toUpperCase();
  const showEmptyState = !threadsLoading && !threadsError && threads.length === 0;

  function openSettings(event) {
    if (!onOpenSettings) {
      return;
    }
    event.preventDefault();
    onClose();
    onOpenSettings();
  }

  const accountAvatar = onOpenSettings ? (
    <button type="button" className="user-avatar" aria-label="Open settings" title="Open settings" onClick={openSettings} style={{ border: 0, cursor: "pointer" }}>{initial}</button>
  ) : (
    <Link href="/settings" className="user-avatar" aria-label="Open settings" title="Open settings" onClick={onClose} style={{ textDecoration: "none" }}>{initial}</Link>
  );

  const accountName = onOpenSettings ? (
    <button type="button" className="user-name" title="Open settings" onClick={openSettings} style={{ border: 0, background: "transparent", cursor: "pointer", textAlign: "left" }}>{username}</button>
  ) : (
    <Link href="/settings" className="user-name" title="Open settings" onClick={onClose} style={{ textDecoration: "none" }}>{username}</Link>
  );

  return (
    <>
      {isOpen ? (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={onClose}
        />
      ) : null}
      <aside className={`studio-sidebar${isOpen ? " studio-sidebar-open" : ""}`} aria-label="Conversations">
        <div className="sidebar-top">
          <Link href="/chat" className="wordmark" onClick={onClose}>
            Fugu Studio
          </Link>
          <button type="button" className="button-primary new-chat-button" onClick={onNewChat}>
            <PlusIcon />
            New chat
          </button>
        </div>

        <nav className="thread-list-wrapper" aria-label="Recent conversations">
          <div className="sidebar-section-header">
            <p className="sidebar-label">Recents</p>
            {onRetryThreads ? (
              <button type="button" className="sidebar-retry" onClick={onRetryThreads} disabled={threadsLoading}>
                {threadsLoading ? "Loading" : "Refresh"}
              </button>
            ) : null}
          </div>
          {threadsLoading ? <p className="sidebar-note">Loading conversations…</p> : null}
          {threadsError ? <p className="sidebar-note sidebar-note-error">{threadsError}</p> : null}
          {showEmptyState ? (
            <p className="sidebar-note">No conversations yet. Start a new chat to begin.</p>
          ) : null}
          <ul className="thread-list">
            {threads.map((thread) => (
              <ThreadListItem
                key={thread.id}
                thread={thread}
                isActive={thread.id === activeThreadId}
                onSelect={onSelectThread}
                onRename={onRenameThread}
                onDelete={onDeleteThread}
              />
            ))}
          </ul>
        </nav>

        <div className="sidebar-footer">
          {userRole === "admin" ? (
            <Link href="/runs" className="button-ghost" onClick={onClose} style={{ width: "100%", justifyContent: "center", marginBottom: "0.65rem" }}>
              Execution inspector
            </Link>
          ) : null}
          <div className="sidebar-user">
            {accountAvatar}
            {accountName}
            <span className="sidebar-user-actions">
              <ThemeCycleButton />
            </span>
          </div>
        </div>
      </aside>
    </>
  );
}
