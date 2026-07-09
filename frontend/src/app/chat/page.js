"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { SettingsDialog } from "../../components/settings-dialog";
import { StudioSidebar } from "../../components/sidebar";
import { useStudioStore } from "../../components/store";
import {
  SafeMarkdownRenderer,
  SafePlaintextRenderer,
} from "../../components/ui/message-renderer";
import { PromptTextArea } from "../../components/ui/text-area";
import { logout } from "../../lib/api-client";
import { loadModelPreference } from "../../lib/model-options";
import { executePipelineStream } from "../../lib/stream-client";
import {
  createThreadFromPrompt,
  deleteThreadEverywhere,
  openThread,
  refreshThreads,
  renameThreadEverywhere,
} from "../../lib/workspace";

function MenuIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <path d="M4 6h16M4 12h16M4 18h16" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true">
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

function ArrowDownIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 5v14M19 12l-7 7-7-7" />
    </svg>
  );
}

const GREETINGS = [
  "What are we running today?",
  "Ready when you are.",
  "Where should the pipeline start?",
];

const THREAD_LIST_ERROR_MESSAGE = "The conversation list could not be loaded. Refresh the list or check the backend connection.";

function isSessionExpired(error) {
  return error?.code === "session_expired" || error?.status === 401;
}

export default function ChatPage() {
  const router = useRouter();
  const controllerRef = useRef(null);
  const scrollRef = useRef(null);
  const pinnedRef = useRef(true);

  const isAuthenticated = useStudioStore((state) => state.isAuthenticated);
  const username = useStudioStore((state) => state.username);
  const threads = useStudioStore((state) => state.threads);
  const activeThreadId = useStudioStore((state) => state.activeThreadId);
  const messages = useStudioStore((state) => state.messages);
  const runStatus = useStudioStore((state) => state.currentRunStatus);
  const activeStep = useStudioStore((state) => state.activeProcessingStep);
  const streamError = useStudioStore((state) => state.streamError);
  const setActiveThread = useStudioStore((state) => state.setActiveThread);
  const appendMessage = useStudioStore((state) => state.appendMessage);
  const beginAssistantMessage = useStudioStore((state) => state.beginAssistantMessage);

  const [prompt, setPrompt] = useState("");
  const [lastPrompt, setLastPrompt] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [threadListError, setThreadListError] = useState("");
  const [isThreadListLoading, setIsThreadListLoading] = useState(false);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [greeting] = useState(() => GREETINGS[Math.floor(Math.random() * GREETINGS.length)]);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);

  const isRunning = runStatus === "connecting" || runStatus === "running";
  const isNewChat = activeThreadId === null && messages.length === 0;
  const activeThread = threads.find((thread) => thread.id === activeThreadId) ?? null;

  const expireSession = useCallback(() => {
    controllerRef.current?.abort();
    router.replace("/");
  }, [router]);

  const reloadThreads = useCallback(async () => {
    setIsThreadListLoading(true);
    setThreadListError("");
    try {
      await refreshThreads();
    } catch (error) {
      if (isSessionExpired(error)) {
        expireSession();
        return;
      }
      setThreadListError(THREAD_LIST_ERROR_MESSAGE);
      setWorkspaceError(THREAD_LIST_ERROR_MESSAGE);
    } finally {
      setIsThreadListLoading(false);
    }
  }, [expireSession]);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/");
    }
  }, [isAuthenticated, router]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  useEffect(() => {
    if (!isAuthenticated) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      reloadThreads();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [isAuthenticated, reloadThreads]);

  useEffect(() => {
    const container = scrollRef.current;
    if (container && pinnedRef.current) {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages, isRunning]);

  function handleScroll(event) {
    const container = event.currentTarget;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    pinnedRef.current = distanceFromBottom < 80;
    setShowJumpToLatest(!pinnedRef.current && messages.length > 0);
  }

  function jumpToLatest() {
    const container = scrollRef.current;
    if (container) {
      pinnedRef.current = true;
      setShowJumpToLatest(false);
      container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    }
  }

  async function selectThread(threadId) {
    if (isRunning || threadId === activeThreadId) {
      setIsSidebarOpen(false);
      return;
    }
    setWorkspaceError("");
    setIsSidebarOpen(false);
    setIsHistoryLoading(true);
    pinnedRef.current = true;
    try {
      await openThread(threadId);
    } catch (error) {
      if (isSessionExpired(error)) {
        expireSession();
        return;
      }
      setWorkspaceError("The conversation history could not be loaded.");
    } finally {
      setIsHistoryLoading(false);
    }
  }

  function startNewChat() {
    if (isRunning) {
      return;
    }
    setWorkspaceError("");
    setIsSidebarOpen(false);
    setActiveThread(null);
  }

  async function handleRenameThread(threadId, name) {
    try {
      await renameThreadEverywhere(threadId, name);
    } catch (error) {
      if (isSessionExpired(error)) {
        expireSession();
        return;
      }
      setWorkspaceError("The conversation could not be renamed.");
    }
  }

  async function handleDeleteThread(threadId, name) {
    const confirmed = window.confirm(`Delete "${name}"? Its messages and run history are removed permanently.`);
    if (!confirmed) {
      return;
    }
    if (threadId === activeThreadId) {
      controllerRef.current?.abort();
    }
    try {
      await deleteThreadEverywhere(threadId);
    } catch (error) {
      if (isSessionExpired(error)) {
        expireSession();
        return;
      }
      setWorkspaceError("The conversation could not be deleted.");
    }
  }

  async function runPrompt(content) {
    const normalized = content.trim();
    if (!normalized || isRunning) {
      return;
    }
    setWorkspaceError("");

    let threadId = activeThreadId;
    if (threadId === null) {
      try {
        const thread = await createThreadFromPrompt(normalized);
        threadId = thread.id;
        setThreadListError("");
      } catch (error) {
        if (isSessionExpired(error)) {
          expireSession();
          return;
        }
        setWorkspaceError("A new conversation could not be created. Check the backend connection and retry.");
        return;
      }
    }

    const requestId = crypto.randomUUID();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLastPrompt(normalized);
    appendMessage({ id: crypto.randomUUID(), role: "user", content: normalized });
    beginAssistantMessage(crypto.randomUUID());
    setPrompt("");
    pinnedRef.current = true;

    try {
      await executePipelineStream({
        threadId,
        prompt: normalized,
        modelPreference: loadModelPreference(),
        signal: controller.signal,
        requestId,
      });
    } catch (error) {
      if (error.code === "session_expired") {
        expireSession();
      }
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    }
  }

  function cancelStream() {
    controllerRef.current?.abort();
  }

  async function signOut() {
    controllerRef.current?.abort();
    await logout();
    router.replace("/");
  }

  if (!isAuthenticated) {
    return <main className="loading-shell">Restoring secure workspace…</main>;
  }

  const composer = (
    <div className="prompt-console">
      <PromptTextArea
        value={prompt}
        onChange={setPrompt}
        onSubmit={() => runPrompt(prompt)}
        disabled={isRunning || isHistoryLoading}
      />
      <div className="prompt-actions">
        <span className="prompt-hint">Enter to send · Shift+Enter for a new line</span>
        {isRunning ? (
          <button type="button" className="send-button send-button-stop" onClick={cancelStream} aria-label="Stop generating">
            <StopIcon />
          </button>
        ) : (
          <button
            type="button"
            className="send-button"
            onClick={() => runPrompt(prompt)}
            disabled={!prompt.trim() || isHistoryLoading}
            aria-label="Send message"
          >
            <SendIcon />
          </button>
        )}
      </div>
    </div>
  );

  return (
    <main className="studio-shell">
      <StudioSidebar
        username={username}
        threads={threads}
        threadsError={threadListError}
        threadsLoading={isThreadListLoading}
        activeThreadId={activeThreadId}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        onSelectThread={selectThread}
        onNewChat={startNewChat}
        onRenameThread={handleRenameThread}
        onDeleteThread={handleDeleteThread}
        onRetryThreads={reloadThreads}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />

      <section className="conversation-panel" aria-label="Conversation">
        <header className="workspace-header">
          <button
            type="button"
            className="icon-button sidebar-toggle"
            aria-label="Open navigation"
            onClick={() => setIsSidebarOpen(true)}
          >
            <MenuIcon />
          </button>
          <h1 className="workspace-title">{activeThread?.name || "New conversation"}</h1>
          {activeStep ? (
            <div className="run-indicator" title={activeStep}>
              <span className="run-indicator-dot" />
              <span>{activeStep}</span>
            </div>
          ) : null}
        </header>

        {isNewChat ? (
          <section className="hero">
            <div className="hero-inner">
              <p className="hero-mark">FUGU</p>
              <h2 className="hero-greeting">{greeting}</h2>
              <p className="hero-subtitle">Start a thread and Fugu will stream the terminal response while persisting the full execution trace.</p>
              {composer}
            </div>
            {workspaceError || streamError ? (
              <p className="form-error hero-error">{workspaceError || streamError}</p>
            ) : null}
          </section>
        ) : (
          <>
            <div className="message-scroll" ref={scrollRef} onScroll={handleScroll}>
              <div className="message-column">
                {workspaceError || streamError ? (
                  <p className="stream-error">{workspaceError || streamError}</p>
                ) : null}
                {isHistoryLoading ? <p className="history-loading">Loading conversation…</p> : null}
                {messages.map((message) => (
                  <article key={message.id} className={`message message-${message.role} ${isRunning && message === messages[messages.length - 1] ? "message-streaming" : ""}`}>
                    {message.role === "assistant" ? (
                      <SafeMarkdownRenderer content={message.content} />
                    ) : (
                      <SafePlaintextRenderer content={message.content} />
                    )}
                  </article>
                ))}
                {isRunning && !messages.at(-1)?.content ? (
                  <div className="message message-assistant">
                    <div className="thinking-dots" aria-label="Fugu is thinking">
                      <span />
                      <span />
                      <span />
                    </div>
                  </div>
                ) : null}
              </div>
              {showJumpToLatest ? (
                <button type="button" className="jump-to-latest" onClick={jumpToLatest} aria-label="Jump to latest message">
                  <ArrowDownIcon />
                </button>
              ) : null}
            </div>
            <div className="composer-dock">{composer}</div>
          </>
        )}
      </section>
      <SettingsDialog open={isSettingsOpen} username={username} onClose={() => setIsSettingsOpen(false)} onSignOut={signOut} />
    </main>
  );
}
