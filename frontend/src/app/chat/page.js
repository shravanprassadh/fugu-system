"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { StudioSidebar } from "../../components/sidebar";
import { useStudioStore } from "../../components/store";
import { SafePlaintextRenderer } from "../../components/ui/message-renderer";
import { StatusTag } from "../../components/ui/status-tag";
import { PromptTextArea } from "../../components/ui/text-area";
import { logout } from "../../lib/api-client";
import { executePipelineStream } from "../../lib/stream-client";

export default function ChatPage() {
  const router = useRouter();
  const controllerRef = useRef(null);
  const isAuthenticated = useStudioStore((state) => state.isAuthenticated);
  const username = useStudioStore((state) => state.username);
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

  const isRunning = runStatus === "connecting" || runStatus === "running";

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/");
    }
  }, [isAuthenticated, router]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  async function runPrompt(content) {
    const normalized = content.trim();
    if (!normalized || !activeThreadId || isRunning) {
      return;
    }

    const requestId = crypto.randomUUID();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLastPrompt(normalized);
    appendMessage({ id: crypto.randomUUID(), role: "user", content: normalized });
    beginAssistantMessage(crypto.randomUUID());
    setPrompt("");

    try {
      await executePipelineStream({
        threadId: activeThreadId,
        prompt: normalized,
        signal: controller.signal,
        requestId,
      });
    } catch (error) {
      if (error.code === "session_expired") {
        router.replace("/");
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

  return (
    <main className="studio-shell">
      <StudioSidebar
        username={username}
        activeThreadId={activeThreadId}
        onSelectThread={setActiveThread}
        onSignOut={signOut}
      />

      <section className="conversation-panel" aria-label="Conversation workspace">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">Thread {activeThreadId ?? "not selected"}</p>
            <h2>Execution canvas</h2>
          </div>
          <StatusTag status={runStatus} stepName={activeStep} />
        </header>

        <div className="message-list" aria-live="polite">
          {messages.length === 0 ? (
            <div className="empty-state">
              <p className="eyebrow">No messages</p>
              <h3>Submit a prompt to start the deterministic pipeline.</h3>
              <p>Intermediate model output remains in diagnostic traces; only the terminal stage appears here.</p>
            </div>
          ) : (
            messages.map((message) => (
              <article className={`message message-${message.role}`} key={message.id}>
                <p className="message-role">{message.role}</p>
                <SafePlaintextRenderer rawContentText={message.content} />
              </article>
            ))
          )}
        </div>

        {streamError ? (
          <div className="stream-error" role="alert">
            <span>{streamError}</span>
            {lastPrompt && !isRunning ? (
              <button type="button" onClick={() => runPrompt(lastPrompt)}>
                Reconnect with a new run
              </button>
            ) : null}
          </div>
        ) : null}

        <div className="prompt-console">
          <PromptTextArea
            value={prompt}
            onChange={setPrompt}
            onSubmit={() => runPrompt(prompt)}
            disabled={isRunning || !activeThreadId}
          />
          <div className="prompt-actions">
            <span>Enter to run · Shift+Enter for newline</span>
            {isRunning ? (
              <button className="button-secondary" type="button" onClick={cancelStream}>
                Cancel
              </button>
            ) : (
              <button type="button" onClick={() => runPrompt(prompt)} disabled={!prompt.trim()}>
                Execute
              </button>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
