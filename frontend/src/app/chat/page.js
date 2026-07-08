"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { StudioSidebar } from "../../components/sidebar";
import { useStudioStore } from "../../components/store";
import {
  SafeMarkdownRenderer,
  SafePlaintextRenderer,
} from "../../components/ui/message-renderer";
import { PromptTextArea } from "../../components/ui/text-area";
import { logout } from "../../lib/api-client";
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
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [greeting] = useState(() => GREETINGS[Math.floor(Math.random() * GREETINGS.length)]);
  const [showJumpToLatest, setShowJumpToLatest] = useState(false);

  const isRunning = runStatus === "connecting" || runStatus === "running";
  const isNewChat = activeThreadId === null && messages.length === 0;
  const activeThread = threads.find((thread) => thread.id === activeThreadId) ?? null;

  const expireSession = useCallback(() => {
    controllerRef.current?.abort();
    router.replace("/");
  }, [router]);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/");
    }
  }, [isAuthenticated, router]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }
    refreshThreads().catch((error) => {
      if (isSessionExpired(error)) {
        expireSession();
        return;
      }
      setWorkspaceError("The conversation list could not be loaded. Check the backend connection and retry.");
    });
  }, [isAuthenticated, expireSession]);

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
        activeThreadId={activeThreadId}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        onSelectThread={selectThread}
        onNewChat={startNewChat}
        onRenameThread={handleRenameThread}
        onDeleteThread={handleDeleteThread}
        onSignOut={signOut}
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
          <h1 className="workspace-title" title={activeThread?.name ?? "New chat"}>
            {activeThread?.name ?? "New chat"}
          </h1>
          {isRunning ? (
            <span className="run-indicator" aria-live="polite">
              <span className="run-indicator-dot" aria-hidden="true" />
              {activeStep ? `Running · ${activeStep}` : "Running"}
            </span>
          ) : null}
        </header>

        {isNewChat && !isHistoryLoading ? (
          <div className="hero">
            <div className="hero-inner">
              <p className="hero-mark" aria-hidden="true">河豚</p>
              <h2 className="hero-greeting">{greeting}</h2>
              <p className="hero-subtitle">
                Your prompt starts a new conversation and streams the pipeline&apos;s final stage back here.
              </p>
              {composer}
            </div>
          </div>
        ) : (
          <>
            <div className="message-scroll" ref={scrollRef} onScroll={handleScroll} aria-live="polite">
              <div className="message-column">
                {isHistoryLoading ? (
                  <p className="history-loading">Loading conversation…</p>
                ) : (
                  messages.map((message, index) => {
                    const isLast = index === messages.length - 1;
                    const isStreamingMessage = isLast && isRunning && message.role === "assistant";
                    if (message.role === "user") {
                      return (
                        <article className="message message-user" key={message.id}>
                          <SafePlaintextRenderer rawContentText={message.content} />
                        </article>
                      );
                    }
                    return (
                      <article
                        className={`message message-assistant${isStreamingMessage ? " message-streaming" : ""}`}
                        key={message.id}
                      >
                        {message.content ? (
                          <SafeMarkdownRenderer rawContentText={message.content} />
                        ) : (
                          <span className="thinking-dots" aria-label="Waiting for the first token">
                            <span /><span /><span />
                          </span>
                        )}
                      </article>
                    );
                  })
                )}
              </div>
              {showJumpToLatest ? (
                <button type="button" className="jump-to-latest" onClick={jumpToLatest} aria-label="Jump to latest message">
                  <ArrowDownIcon />
                </button>
              ) : null}
            </div>

            <div className="composer-dock">
              {streamError ? (
                <div className="stream-error" role="alert">
                  <span>{streamError}</span>
                  {lastPrompt && !isRunning ? (
                    <button type="button" className="button-ghost" onClick={() => runPrompt(lastPrompt)}>
                      Retry
                    </button>
                  ) : null}
                </div>
              ) : null}
              {workspaceError ? (
                <div className="stream-error" role="alert">
                  <span>{workspaceError}</span>
                </div>
              ) : null}
              {composer}
            </div>
          </>
        )}

        {isNewChat && workspaceError ? (
          <div className="stream-error hero-error" role="alert">
            <span>{workspaceError}</span>
          </div>
        ) : null}
      </section>
    </main>
  );
}
