export function StatusTag({ status = "idle", stepName = null }) {
  const label = stepName ? `${status}: ${stepName}` : status;
  return (
    <span className={`status-tag status-${status}`} aria-live="polite">
      <span className="status-dot" aria-hidden="true" />
      {label}
    </span>
  );
}
