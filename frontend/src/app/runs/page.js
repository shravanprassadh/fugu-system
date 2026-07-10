"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useStudioStore } from "@/components/store";
import {
  cancelExecutionRun,
  exportExecutionDiagnostics,
  getExecutionRun,
  listExecutionRuns,
  retryExecutionRun,
  retryExecutionStage,
} from "@/lib/execution-api";

import styles from "./runs.module.css";

const emptyFilters = {
  status: "",
  userId: "",
  provider: "",
  model: "",
  threadId: "",
  dateFrom: "",
  dateTo: "",
};

function formatTimestamp(value) {
  if (!value) {
    return "Not available";
  }
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function formatDuration(value) {
  if (value === null || value === undefined) {
    return "In progress";
  }
  if (value < 1000) {
    return `${value} ms`;
  }
  return `${(value / 1000).toFixed(2)} s`;
}

function StatusBadge({ status }) {
  const normalized = String(status || "unknown").toLowerCase();
  const styleName = `status${normalized[0]?.toUpperCase() || ""}${normalized.slice(1)}`;
  return <span className={`${styles.status} ${styles[styleName] || ""}`}>{normalized}</span>;
}

function summaryItems(run) {
  return [
    ["Run", `#${run.id}`],
    ["Thread", `${run.thread_name} (#${run.thread_id})`],
    ["User", `${run.username} (#${run.user_id})`],
    ["Pipeline", run.pipeline_version_number ? `Version ${run.pipeline_version_number}` : "Legacy run"],
    ["Started", formatTimestamp(run.started_at)],
    ["Duration", formatDuration(run.latency_ms)],
    ["Failed stage", run.failed_stage || "None"],
    ["Retry lineage", run.source_run_id ? `${run.retry_kind} retry of #${run.source_run_id}` : "Original run"],
    ["Retryable", run.retryable === null || run.retryable === undefined ? "Not classified" : run.retryable ? "Yes" : "No"],
  ];
}

export default function ExecutionRunsPage() {
  const router = useRouter();
  const isAuthenticated = useStudioStore((state) => state.isAuthenticated);
  const userRole = useStudioStore((state) => state.userRole);
  const [filters, setFilters] = useState(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState(emptyFilters);
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [operation, setOperation] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const handleUnauthorized = useCallback(() => {
    router.replace("/");
  }, [router]);

  const loadRuns = useCallback(async () => {
    if (!isAuthenticated || userRole !== "admin") {
      return;
    }
    setLoadingRuns(true);
    setError("");
    try {
      const payload = await listExecutionRuns(appliedFilters);
      setRuns(payload);
      setSelectedRunId((current) => {
        if (current && payload.some((run) => run.id === current)) {
          return current;
        }
        return payload[0]?.id ?? null;
      });
      if (payload.length === 0) {
        setDetail(null);
      }
    } catch (operationError) {
      if (operationError?.status === 401) {
        handleUnauthorized();
        return;
      }
      setError(operationError.message || "Could not load execution history.");
    } finally {
      setLoadingRuns(false);
    }
  }, [appliedFilters, handleUnauthorized, isAuthenticated, userRole]);

  const loadDetail = useCallback(async () => {
    if (!selectedRunId || !isAuthenticated || userRole !== "admin") {
      return;
    }
    setLoadingDetail(true);
    setError("");
    try {
      setDetail(await getExecutionRun(selectedRunId));
    } catch (operationError) {
      if (operationError?.status === 401) {
        handleUnauthorized();
        return;
      }
      setError(operationError.message || "Could not load execution details.");
    } finally {
      setLoadingDetail(false);
    }
  }, [handleUnauthorized, isAuthenticated, selectedRunId, userRole]);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/");
      return;
    }
    if (userRole && userRole !== "admin") {
      router.replace("/chat");
    }
  }, [isAuthenticated, router, userRole]);

  useEffect(() => {
    const timer = window.setTimeout(loadRuns, 0);
    return () => window.clearTimeout(timer);
  }, [loadRuns]);

  useEffect(() => {
    const timer = window.setTimeout(loadDetail, 0);
    return () => window.clearTimeout(timer);
  }, [loadDetail]);

  const selectedSummary = useMemo(
    () => runs.find((run) => run.id === selectedRunId) || null,
    [runs, selectedRunId],
  );

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function applyFilters(event) {
    event.preventDefault();
    setNotice("");
    setAppliedFilters(filters);
  }

  function clearFilters() {
    setFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
    setNotice("");
  }

  async function runControl(label, action) {
    setOperation(label);
    setNotice("");
    setError("");
    try {
      const result = await action();
      setNotice(
        result.source_run_id
          ? `Created ${result.retry_kind} retry run #${result.run_id} from run #${result.source_run_id}.`
          : `Run #${result.run_id} is ${result.status}.`,
      );
      await loadRuns();
      if (result.run_id !== selectedRunId) {
        setSelectedRunId(result.run_id);
      } else {
        await loadDetail();
      }
    } catch (operationError) {
      if (operationError?.status === 401) {
        handleUnauthorized();
        return;
      }
      setError(operationError.message || `Could not ${label}.`);
    } finally {
      setOperation("");
    }
  }

  async function copyDiagnostics() {
    if (!detail) {
      return;
    }
    setOperation("copy diagnostics");
    setNotice("");
    setError("");
    try {
      const payload = await exportExecutionDiagnostics(detail.id);
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      setNotice(`Copied sanitised diagnostics for run #${detail.id}.`);
    } catch (operationError) {
      if (operationError?.status === 401) {
        handleUnauthorized();
        return;
      }
      setError(operationError.message || "Could not copy diagnostics.");
    } finally {
      setOperation("");
    }
  }

  if (!isAuthenticated || userRole !== "admin") {
    return <main className={styles.shell}>Checking administrator access…</main>;
  }

  const activeRun = detail || selectedSummary;
  const canCancel = ["pending", "running", "cancelling"].includes(activeRun?.status);
  const canRetry = ["completed", "failed", "cancelled"].includes(activeRun?.status);

  return (
    <main className={styles.shell}>
      <div className={styles.frame}>
        <header className={styles.header}>
          <div>
            <p className="eyebrow">Administrator operations</p>
            <h1>Execution inspector</h1>
            <p className={styles.muted}>
              Inspect sanitised stage diagnostics, trace immutable retry lineage, and recover failed runs safely.
            </p>
          </div>
          <div className={styles.headerActions}>
            <Link href="/chat" className="button-ghost">Back to chat</Link>
            <button type="button" className="button-primary" onClick={loadRuns} disabled={loadingRuns || Boolean(operation)}>
              {loadingRuns ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </header>

        {error ? <p className={styles.error} role="alert">{error}</p> : null}
        {notice ? <p className={styles.notice} role="status">{notice}</p> : null}

        <div className={styles.grid}>
          <section className={`${styles.panel} ${styles.listPanel}`} aria-label="Execution history">
            <div className={styles.runTitle}>
              <div>
                <h2>Run history</h2>
                <p className={styles.muted}>{runs.length} run{runs.length === 1 ? "" : "s"} loaded</p>
              </div>
              {loadingRuns ? <StatusBadge status="pending" /> : null}
            </div>

            <form className={styles.filters} onSubmit={applyFilters}>
              <label>
                Status
                <select aria-label="Run status" value={filters.status} onChange={(event) => updateFilter("status", event.target.value)}>
                  <option value="">All statuses</option>
                  <option value="pending">Pending</option>
                  <option value="running">Running</option>
                  <option value="cancelling">Cancelling</option>
                  <option value="cancelled">Cancelled</option>
                  <option value="completed">Completed</option>
                  <option value="failed">Failed</option>
                </select>
              </label>
              <label>
                User ID
                <input aria-label="User ID" inputMode="numeric" value={filters.userId} onChange={(event) => updateFilter("userId", event.target.value)} />
              </label>
              <label>
                Provider
                <input aria-label="Provider" value={filters.provider} onChange={(event) => updateFilter("provider", event.target.value)} placeholder="openrouter" />
              </label>
              <label>
                Model
                <input aria-label="Model" value={filters.model} onChange={(event) => updateFilter("model", event.target.value)} placeholder="provider/model" />
              </label>
              <label>
                Thread ID
                <input aria-label="Thread ID" inputMode="numeric" value={filters.threadId} onChange={(event) => updateFilter("threadId", event.target.value)} />
              </label>
              <label>
                From
                <input aria-label="Date from" type="datetime-local" value={filters.dateFrom} onChange={(event) => updateFilter("dateFrom", event.target.value ? new Date(event.target.value).toISOString() : "")} />
              </label>
              <label>
                To
                <input aria-label="Date to" type="datetime-local" value={filters.dateTo ? filters.dateTo.slice(0, 16) : ""} onChange={(event) => updateFilter("dateTo", event.target.value ? new Date(event.target.value).toISOString() : "")} />
              </label>
              <div className={styles.filterActions}>
                <button type="button" className="button-ghost" onClick={clearFilters}>Clear</button>
                <button type="submit" className="button-primary">Apply filters</button>
              </div>
            </form>

            <ul className={styles.runList}>
              {!loadingRuns && runs.length === 0 ? <li className={styles.empty}>No runs match the current filters.</li> : null}
              {runs.map((run) => (
                <li key={run.id}>
                  <button
                    type="button"
                    className={`${styles.runButton} ${run.id === selectedRunId ? styles.runButtonActive : ""}`}
                    onClick={() => setSelectedRunId(run.id)}
                    aria-label={`Inspect run ${run.id}`}
                  >
                    <span className={styles.runTitle}>
                      <strong>#{run.id} · {run.thread_name}</strong>
                      <StatusBadge status={run.status} />
                    </span>
                    <span className={styles.metaRow}>
                      <span>{run.username}</span>
                      <span>v{run.pipeline_version_number || "legacy"}</span>
                      <span>{formatDuration(run.latency_ms)}</span>
                    </span>
                    {run.failed_stage ? <span className={styles.error}>Failed at {run.failed_stage}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <section className={`${styles.panel} ${styles.detailPanel}`} aria-label="Execution details">
            {loadingDetail ? <p className={styles.empty}>Loading run details…</p> : null}
            {!loadingDetail && !detail ? <p className={styles.empty}>Select a run to inspect its stage diagnostics.</p> : null}
            {detail ? (
              <div className={styles.summary}>
                <div className={styles.stageHeader}>
                  <div>
                    <p className="eyebrow">Run #{detail.id}</p>
                    <h2>{detail.thread_name}</h2>
                    <div className={styles.metaRow}>
                      <StatusBadge status={detail.status} />
                      {detail.error_category ? <span>{detail.error_category}</span> : null}
                    </div>
                  </div>
                  <div className={styles.actions}>
                    <button type="button" className="button-ghost" onClick={copyDiagnostics} disabled={Boolean(operation)}>
                      {operation === "copy diagnostics" ? "Copying…" : "Copy diagnostics"}
                    </button>
                    {canCancel ? (
                      <button type="button" className="button-ghost" onClick={() => runControl("cancel run", () => cancelExecutionRun(detail.id))} disabled={Boolean(operation)}>
                        Cancel run
                      </button>
                    ) : null}
                    {canRetry ? (
                      <button type="button" className="button-primary" onClick={() => runControl("retry run", () => retryExecutionRun(detail.id))} disabled={Boolean(operation)}>
                        Retry full run
                      </button>
                    ) : null}
                  </div>
                </div>

                <dl className={styles.summaryGrid}>
                  {summaryItems(detail).map(([label, value]) => (
                    <div className={styles.summaryItem} key={label}>
                      <dt>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>

                {detail.error_message ? <p className={styles.error}>{detail.error_message}</p> : null}

                <section>
                  <h3>Final result</h3>
                  <pre className={styles.result}>{detail.final_result || "No final result was persisted."}</pre>
                </section>

                <section className={styles.stages}>
                  <h3>Stage diagnostics</h3>
                  {detail.stages.map((stage) => {
                    const canRetryStage = stage.status === "failed" && stage.side_effect_free;
                    return (
                      <article className={styles.stage} key={stage.id}>
                        <div className={styles.stageHeader}>
                          <div>
                            <h3>{stage.display_name}</h3>
                            <p className={styles.muted}>{stage.step_name}</p>
                          </div>
                          <div className={styles.actions}>
                            <StatusBadge status={stage.status} />
                            {canRetryStage ? (
                              <button
                                type="button"
                                className="button-primary"
                                onClick={() => runControl(`retry ${stage.step_name}`, () => retryExecutionStage(detail.id, stage.step_name))}
                                disabled={Boolean(operation)}
                              >
                                Retry failed stage
                              </button>
                            ) : null}
                          </div>
                        </div>
                        <div className={styles.stageMeta}>
                          <div><strong>Provider</strong><span>{stage.provider || "Unknown"}</span></div>
                          <div><strong>Model</strong><span>{stage.model || "Unknown"}</span></div>
                          <div><strong>Latency</strong><span>{formatDuration(stage.latency_ms)}</span></div>
                          <div><strong>Retries</strong><span>{stage.actual_retry_count}/{stage.configured_retry_count}</span></div>
                          <div><strong>Input tokens</strong><span>{stage.input_token_usage ?? "Unknown"}</span></div>
                          <div><strong>Output tokens</strong><span>{stage.output_token_usage ?? "Unknown"}</span></div>
                          <div><strong>Side-effect safe</strong><span>{stage.side_effect_free ? "Yes" : "No"}</span></div>
                          <div><strong>Completed</strong><span>{formatTimestamp(stage.completed_at)}</span></div>
                        </div>
                        {stage.error_message ? <p className={styles.error}>{stage.error_message}</p> : null}
                        <details className={styles.stageDetails}>
                          <summary>Sanitised input and output</summary>
                          <div className={styles.diagnosticGrid}>
                            <div>
                              <p className={styles.muted}>Input</p>
                              <pre className={styles.diagnostic}>{stage.sanitised_input || "No input snapshot."}</pre>
                            </div>
                            <div>
                              <p className={styles.muted}>Output</p>
                              <pre className={styles.diagnostic}>{stage.sanitised_output || "No output snapshot."}</pre>
                            </div>
                          </div>
                        </details>
                      </article>
                    );
                  })}
                </section>
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </main>
  );
}
