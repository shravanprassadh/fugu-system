"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

import {
  deleteAttachment,
  downloadAttachment,
  getAttachmentCapabilities,
  listThreadAttachments,
  reprocessAttachment,
  uploadAttachment,
} from "../lib/attachment-api";
import styles from "./attachment-composer.module.css";

const MAX_ATTACHMENTS_PER_REQUEST = 10;

function PaperclipIcon() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

function formatBytes(value) {
  if (!Number.isFinite(value) || value < 0) {
    return "Unknown size";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function extensionOf(filename) {
  const pieces = String(filename || "").toLowerCase().split(".");
  return pieces.length > 1 ? pieces.at(-1) : "";
}

function localIdentity(file) {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

function statusLabel(item) {
  if (item.status === "uploading") {
    return `Uploading ${item.progress}%`;
  }
  if (item.status === "failed") {
    return item.error || "Upload failed";
  }
  return "Ready to upload";
}

export const AttachmentComposer = forwardRef(function AttachmentComposer(
  {
    activeThreadId,
    disabled = false,
    onBusyChange = () => {},
    onUnauthorized = () => {},
  },
  ref,
) {
  const inputRef = useRef(null);
  const pendingRef = useRef([]);
  const selectedHistoryRef = useRef(new Set());
  const [capabilities, setCapabilities] = useState(null);
  const [pending, setPending] = useState([]);
  const [history, setHistory] = useState([]);
  const [selectedHistoryIds, setSelectedHistoryIds] = useState(new Set());
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    pendingRef.current = pending;
  }, [pending]);

  useEffect(() => {
    selectedHistoryRef.current = selectedHistoryIds;
  }, [selectedHistoryIds]);

  const reportError = useCallback(
    (caught, fallback) => {
      if (caught?.status === 401) {
        onUnauthorized();
        return;
      }
      setError(caught?.message || fallback);
    },
    [onUnauthorized],
  );

  useEffect(() => {
    let cancelled = false;
    getAttachmentCapabilities()
      .then((payload) => {
        if (!cancelled) {
          setCapabilities(payload);
        }
      })
      .catch((caught) => {
        if (!cancelled) {
          reportError(caught, "Attachment capabilities could not be loaded.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reportError]);

  const refreshHistory = useCallback(async () => {
    if (!activeThreadId) {
      setHistory([]);
      setSelectedHistoryIds(new Set());
      return [];
    }
    setHistoryLoading(true);
    try {
      const payload = await listThreadAttachments(activeThreadId);
      setHistory(payload);
      setSelectedHistoryIds((current) => {
        const available = new Set(payload.filter((item) => item.processing_status === "ready").map((item) => item.id));
        return new Set([...current].filter((id) => available.has(id)));
      });
      return payload;
    } catch (caught) {
      reportError(caught, "Attachment history could not be loaded.");
      return [];
    } finally {
      setHistoryLoading(false);
    }
  }, [activeThreadId, reportError]);

  useEffect(() => {
    refreshHistory();
  }, [refreshHistory]);

  useEffect(
    () => () => {
      pendingRef.current.forEach((item) => {
        if (item.previewUrl) {
          URL.revokeObjectURL(item.previewUrl);
        }
      });
    },
    [],
  );

  const setBusyState = useCallback(
    (value) => {
      setBusy(value);
      onBusyChange(value);
    },
    [onBusyChange],
  );

  const clearPending = useCallback(() => {
    setPending((current) => {
      current.forEach((item) => {
        if (item.previewUrl) {
          URL.revokeObjectURL(item.previewUrl);
        }
      });
      return [];
    });
  }, []);

  const resetSelection = useCallback(() => {
    clearPending();
    setSelectedHistoryIds(new Set());
    setError("");
  }, [clearPending]);

  const addFiles = useCallback(
    (fileList) => {
      if (disabled || busy) {
        return;
      }
      setError("");
      const incoming = Array.from(fileList || []);
      if (!incoming.length) {
        return;
      }
      const supported = new Set(capabilities?.supported_extensions || []);
      const maxSize = capabilities?.max_file_size_bytes || 25 * 1024 * 1024;
      const existing = new Set(pendingRef.current.map((item) => localIdentity(item.file)));
      const next = [];
      const problems = [];
      for (const file of incoming) {
        const extension = extensionOf(file.name);
        if (supported.size && !supported.has(extension)) {
          problems.push(`${file.name}: unsupported file type`);
          continue;
        }
        if (file.size > maxSize) {
          problems.push(`${file.name}: exceeds ${formatBytes(maxSize)}`);
          continue;
        }
        if (existing.has(localIdentity(file))) {
          continue;
        }
        if (pendingRef.current.length + selectedHistoryRef.current.size + next.length >= MAX_ATTACHMENTS_PER_REQUEST) {
          problems.push(`Only ${MAX_ATTACHMENTS_PER_REQUEST} attachments can be used in one request.`);
          break;
        }
        existing.add(localIdentity(file));
        next.push({
          localId: crypto.randomUUID(),
          file,
          previewUrl: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
          status: "pending",
          progress: 0,
          error: "",
        });
      }
      if (next.length) {
        setPending((current) => [...current, ...next]);
      }
      if (problems.length) {
        setError(problems.join(" · "));
      }
    },
    [busy, capabilities, disabled],
  );

  const removePending = useCallback((localId) => {
    setPending((current) => {
      const target = current.find((item) => item.localId === localId);
      if (target?.previewUrl) {
        URL.revokeObjectURL(target.previewUrl);
      }
      return current.filter((item) => item.localId !== localId);
    });
  }, []);

  const toggleHistory = useCallback((attachment) => {
    if (attachment.processing_status !== "ready") {
      return;
    }
    setSelectedHistoryIds((current) => {
      const next = new Set(current);
      if (next.has(attachment.id)) {
        next.delete(attachment.id);
      } else if (next.size + pendingRef.current.length < MAX_ATTACHMENTS_PER_REQUEST) {
        next.add(attachment.id);
      }
      return next;
    });
  }, []);

  const prepareForSend = useCallback(
    async (threadId) => {
      const selected = [...selectedHistoryRef.current];
      const files = pendingRef.current;
      if (!selected.length && !files.length) {
        return [];
      }
      if (!threadId) {
        throw new Error("A conversation must exist before attachments can be uploaded.");
      }
      setBusyState(true);
      setError("");
      const uploadedIds = [];
      try {
        for (const item of files) {
          setPending((current) =>
            current.map((candidate) =>
              candidate.localId === item.localId
                ? { ...candidate, status: "uploading", progress: 0, error: "" }
                : candidate,
            ),
          );
          try {
            const uploaded = await uploadAttachment(threadId, item.file, {
              onProgress: (progress) => {
                setPending((current) =>
                  current.map((candidate) =>
                    candidate.localId === item.localId ? { ...candidate, progress } : candidate,
                  ),
                );
              },
            });
            if (uploaded.processing_status !== "ready") {
              throw new Error(uploaded.processing_error_message || `${uploaded.filename} could not be processed.`);
            }
            uploadedIds.push(uploaded.id);
          } catch (caught) {
            setPending((current) =>
              current.map((candidate) =>
                candidate.localId === item.localId
                  ? { ...candidate, status: "failed", error: caught?.message || "Upload failed" }
                  : candidate,
              ),
            );
            throw caught;
          }
        }
        clearPending();
        setSelectedHistoryIds(new Set());
        await refreshHistory();
        return [...selected, ...uploadedIds];
      } catch (caught) {
        reportError(caught, "One or more attachments could not be prepared.");
        throw caught;
      } finally {
        setBusyState(false);
      }
    },
    [clearPending, refreshHistory, reportError, setBusyState],
  );

  useImperativeHandle(
    ref,
    () => ({
      prepareForSend,
      resetSelection,
      refreshHistory,
      hasSelection: () => pendingRef.current.length > 0 || selectedHistoryRef.current.size > 0,
    }),
    [prepareForSend, refreshHistory, resetSelection],
  );

  async function handleDownload(attachment) {
    try {
      const blob = await downloadAttachment(attachment.id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = attachment.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (caught) {
      reportError(caught, "The attachment could not be downloaded.");
    }
  }

  async function handleReprocess(attachment) {
    setBusyState(true);
    try {
      await reprocessAttachment(attachment.id);
      await refreshHistory();
    } catch (caught) {
      reportError(caught, "The attachment could not be reprocessed.");
    } finally {
      setBusyState(false);
    }
  }

  async function handleDelete(attachment) {
    if (!window.confirm(`Delete ${attachment.filename}?`)) {
      return;
    }
    setBusyState(true);
    try {
      await deleteAttachment(attachment.id);
      await refreshHistory();
    } catch (caught) {
      reportError(caught, "The attachment could not be deleted.");
    } finally {
      setBusyState(false);
    }
  }

  function handlePaste(event) {
    const files = Array.from(event.clipboardData?.files || []);
    if (files.length) {
      event.preventDefault();
      addFiles(files);
    }
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragActive(false);
    addFiles(event.dataTransfer.files);
  }

  const selectedCount = pending.length + selectedHistoryIds.size;
  const storageEnabled = capabilities?.enabled !== false;

  return (
    <section
      className={`${styles.workspace} ${styles.dropzone} ${dragActive ? styles.dropzoneActive : ""}`}
      onPaste={handlePaste}
      onDragEnter={(event) => {
        event.preventDefault();
        setDragActive(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setDragActive(false);
        }
      }}
      onDrop={handleDrop}
      aria-label="Attachments"
    >
      <div className={styles.toolbar}>
        <div className={styles.toolbarActions}>
          <button
            type="button"
            className={styles.attachButton}
            onClick={() => inputRef.current?.click()}
            disabled={disabled || busy || !storageEnabled || selectedCount >= MAX_ATTACHMENTS_PER_REQUEST}
          >
            <PaperclipIcon />
            Attach files
          </button>
          {activeThreadId ? (
            <button
              type="button"
              className={styles.historyButton}
              onClick={() => setHistoryOpen((value) => !value)}
              disabled={disabled}
              aria-expanded={historyOpen}
            >
              Thread files ({history.length})
            </button>
          ) : null}
        </div>
        <span className={styles.helper}>
          {selectedCount}/{MAX_ATTACHMENTS_PER_REQUEST} selected · Drop files or paste an image
        </span>
      </div>
      <input
        ref={inputRef}
        className={styles.hiddenInput}
        type="file"
        multiple
        accept={(capabilities?.supported_extensions || []).map((extension) => `.${extension}`).join(",")}
        onChange={(event) => {
          addFiles(event.target.files);
          event.target.value = "";
        }}
      />
      {!storageEnabled ? (
        <p className={styles.warning}>Attachment storage is not configured on the backend.</p>
      ) : null}
      {error ? <p className={styles.error}>{error}</p> : null}

      {pending.length ? (
        <div className={styles.pendingGrid} aria-label="Files selected for upload">
          {pending.map((item) => (
            <div key={item.localId} className={styles.fileCard}>
              <div
                className={styles.preview}
                style={item.previewUrl ? { backgroundImage: `url(${item.previewUrl})` } : undefined}
                aria-hidden="true"
              >
                {item.previewUrl ? "" : extensionOf(item.file.name) || "file"}
              </div>
              <div className={styles.fileInfo}>
                <div className={styles.fileName} title={item.file.name}>{item.file.name}</div>
                <div className={styles.fileMeta}>{formatBytes(item.file.size)}</div>
                <div className={styles.fileStatus}>{statusLabel(item)}</div>
              </div>
              <button
                type="button"
                className={styles.removeButton}
                onClick={() => removePending(item.localId)}
                disabled={item.status === "uploading"}
                aria-label={`Remove ${item.file.name}`}
              >
                ×
              </button>
              {item.status === "uploading" ? (
                <div className={styles.progressTrack} aria-label={`${item.progress}% uploaded`}>
                  <div className={styles.progressBar} style={{ width: `${item.progress}%` }} />
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {historyOpen ? (
        <div className={styles.historyPanel}>
          <div className={styles.historyHeader}>
            <h3>Thread attachment history</h3>
            <button type="button" className={styles.smallButton} onClick={refreshHistory} disabled={historyLoading || busy}>
              {historyLoading ? "Loading…" : "Refresh"}
            </button>
          </div>
          {history.length ? (
            <div className={styles.historyList}>
              {history.map((attachment) => {
                const selected = selectedHistoryIds.has(attachment.id);
                return (
                  <div
                    key={attachment.id}
                    className={`${styles.historyItem} ${selected ? styles.historyItemSelected : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={selected}
                      disabled={attachment.processing_status !== "ready" || disabled || busy}
                      onChange={() => toggleHistory(attachment)}
                      aria-label={`Use ${attachment.filename} in the next request`}
                    />
                    <div className={styles.fileInfo}>
                      <div className={styles.fileName} title={attachment.filename}>{attachment.filename}</div>
                      <div className={styles.fileMeta}>
                        {formatBytes(attachment.size_bytes)} · {attachment.processing_status}
                      </div>
                      {attachment.processing_warnings?.length ? (
                        <div className={styles.fileStatus}>{attachment.processing_warnings.join(" · ")}</div>
                      ) : null}
                      {attachment.processing_error_message ? (
                        <div className={styles.fileStatus}>{attachment.processing_error_message}</div>
                      ) : null}
                    </div>
                    <div className={styles.historyActions}>
                      <button type="button" className={styles.smallButton} onClick={() => handleDownload(attachment)} disabled={busy}>
                        Open
                      </button>
                      {attachment.processing_status === "failed" ? (
                        <button type="button" className={styles.smallButton} onClick={() => handleReprocess(attachment)} disabled={busy}>
                          Reprocess
                        </button>
                      ) : null}
                      <button type="button" className={styles.smallButton} onClick={() => handleDelete(attachment)} disabled={busy}>
                        Delete
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className={styles.empty}>{historyLoading ? "Loading attachment history…" : "No files have been attached to this thread."}</p>
          )}
        </div>
      ) : null}
    </section>
  );
});

AttachmentComposer.displayName = "AttachmentComposer";
