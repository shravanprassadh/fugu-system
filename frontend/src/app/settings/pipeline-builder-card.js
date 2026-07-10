"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createPipelineDraft,
  deletePipelineDraft,
  getPipelineVersion,
  getProviderCatalogue,
  listPipelineVersions,
  publishPipelineDraft,
  rollbackPipelineVersion,
  savePipelineDraft,
  validatePipelineDraft,
} from "../../lib/api-client";
import {
  CAPABILITY_KEYS,
  addStage,
  applyModelToStage,
  applyProviderToStage,
  duplicateStage,
  hydratePipelineVersion,
  modelForStage,
  moveStage,
  removeStage,
  renameStageIdentifier,
  serializeStages,
  setTerminalStage,
} from "../../lib/pipeline-builder-model";
import styles from "./pipeline-builder.module.css";

const capabilityLabels = {
  text_generation: "Text generation",
  image_understanding: "Image understanding",
  document_input: "Document input",
  tool_support: "Tool support",
  reasoning_support: "Reasoning",
};

function displayState(value) {
  return String(value || "unknown").replaceAll("_", " ");
}

function formatDate(value) {
  if (!value) {
    return "Not yet";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function StatusBadge({ children }) {
  return <span className={styles.badge}>{children}</span>;
}

function numberValue(value) {
  return value === null || value === undefined ? "" : value;
}

function VersionHistory({ versions, selectedId, onSelect, disabled }) {
  return (
    <div className={styles.versionList}>
      {versions.map((version) => (
        <button
          key={version.id}
          type="button"
          className={`${styles.versionButton} ${version.id === selectedId ? styles.selected : ""}`}
          onClick={() => onSelect(version.id)}
          disabled={disabled}
          aria-pressed={version.id === selectedId}
        >
          <span className={styles.versionHeader}>
            <strong>Version {version.version_number}</strong>
            <StatusBadge>{displayState(version.state)}</StatusBadge>
          </span>
          <span>{version.change_description || "No change description"}</span>
          <span className={styles.badgeRow}>
            <StatusBadge>{displayState(version.validation_status)}</StatusBadge>
            <StatusBadge>{version.stage_count} stages</StatusBadge>
          </span>
        </button>
      ))}
    </div>
  );
}

function StageList({ pipeline, activeIdentifier, onSelect, onMove, onDuplicate, onRemove, onAdd, disabled }) {
  const editable = pipeline?.state === "draft";
  return (
    <div className={styles.stack}>
      <div className={styles.stageList}>
        {(pipeline?.stages || []).map((stage, index) => (
          <article key={stage.stable_identifier}>
            <button
              type="button"
              className={`${styles.stageButton} ${stage.stable_identifier === activeIdentifier ? styles.selected : ""}`}
              onClick={() => onSelect(stage.stable_identifier)}
              aria-pressed={stage.stable_identifier === activeIdentifier}
            >
              <span className={styles.versionHeader}>
                <strong>{stage.position}. {stage.name}</strong>
                {stage.is_terminal ? <StatusBadge>terminal</StatusBadge> : null}
              </span>
              <code>{stage.stable_identifier}</code>
              <span className={styles.badgeRow}>
                <StatusBadge>{stage.enabled ? "enabled" : "bypassed"}</StatusBadge>
                <StatusBadge>{stage.provider_type}</StatusBadge>
              </span>
            </button>
            {editable ? (
              <div className={styles.stageActions}>
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => onMove(stage.stable_identifier, -1)}
                  disabled={disabled || index === 0}
                  aria-label={`Move ${stage.name} up`}
                >
                  Up
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => onMove(stage.stable_identifier, 1)}
                  disabled={disabled || index === pipeline.stages.length - 1}
                  aria-label={`Move ${stage.name} down`}
                >
                  Down
                </button>
                <button
                  type="button"
                  className="button-ghost"
                  onClick={() => onDuplicate(stage.stable_identifier)}
                  disabled={disabled}
                  aria-label={`Duplicate ${stage.name}`}
                >
                  Copy
                </button>
                <button
                  type="button"
                  className={`button-ghost ${styles.dangerButton}`}
                  onClick={() => onRemove(stage.stable_identifier)}
                  disabled={disabled || pipeline.stages.length === 1}
                  aria-label={`Remove ${stage.name}`}
                >
                  Remove
                </button>
              </div>
            ) : null}
          </article>
        ))}
      </div>
      {editable ? (
        <button type="button" className="button-ghost" onClick={onAdd} disabled={disabled}>
          Add stage
        </button>
      ) : null}
    </div>
  );
}

function CheckboxCollection({ legend, options, selected, onToggle, disabled }) {
  return (
    <fieldset className={styles.dependencyFieldset} disabled={disabled}>
      <legend>{legend}</legend>
      <div className={styles.checkboxGrid}>
        {options.length === 0 ? <span className="muted">None available</span> : null}
        {options.map((option) => (
          <label className={styles.checkboxLabel} key={option.value}>
            <input
              type="checkbox"
              checked={selected.includes(option.value)}
              onChange={(event) => onToggle(option.value, event.target.checked)}
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function StageEditor({ pipeline, stage, providers, onChange, onRename, disabled }) {
  if (!stage) {
    return <div className={styles.emptyState}>Select a stage to inspect its configuration.</div>;
  }

  const editable = pipeline.state === "draft" && !disabled;
  const provider = providers.find((item) => item.identifier === stage.provider_type) || providers[0] || null;
  const models = provider?.models.filter((item) => item.availability_status === "available") || [];
  const model = modelForStage(stage, providers);
  const fallbackProvider = providers.find((item) => item.identifier === stage.fallback_provider_type) || null;
  const fallbackModels = fallbackProvider?.models.filter((item) => item.availability_status === "available") || [];
  const dependencyOptions = pipeline.stages
    .filter((item) => item.stable_identifier !== stage.stable_identifier && item.enabled)
    .map((item) => ({ value: item.stable_identifier, label: `${item.position}. ${item.name}` }));

  function updateNumber(field, rawValue) {
    onChange(field, rawValue === "" ? null : Number(rawValue));
  }

  function updateProvider(providerIdentifier) {
    onChange(null, applyProviderToStage(stage, providerIdentifier, providers));
  }

  function updateModel(modelIdentifier) {
    onChange(null, applyModelToStage(stage, modelIdentifier, providers));
  }

  function updateFallbackProvider(providerIdentifier) {
    const nextProvider = providers.find((item) => item.identifier === providerIdentifier);
    const nextModel = nextProvider?.models.find((item) => item.availability_status === "available");
    onChange(null, {
      ...stage,
      fallback_provider_type: providerIdentifier || null,
      fallback_model_string: nextModel?.identifier || null,
    });
  }

  return (
    <div className={styles.stack}>
      <div className={styles.stageHeader}>
        <div>
          <h3>{stage.name}</h3>
          <p className="muted">Stage {stage.position} · {stage.stable_identifier}</p>
        </div>
        <span className={styles.badgeRow}>
          {stage.is_terminal ? <StatusBadge>terminal</StatusBadge> : null}
          <StatusBadge>{stage.enabled ? "enabled" : "bypassed"}</StatusBadge>
        </span>
      </div>

      <div className={styles.formGrid}>
        <label>
          Stable identifier
          <input
            value={stage.stable_identifier}
            onChange={(event) => onRename(event.target.value)}
            disabled={!editable}
            pattern="[A-Za-z0-9][A-Za-z0-9_-]*"
            maxLength={100}
          />
        </label>
        <label>
          Display name
          <input
            value={stage.name}
            onChange={(event) => onChange("name", event.target.value)}
            disabled={!editable}
            maxLength={255}
          />
        </label>
        <label className={styles.fullWidth}>
          Description
          <input
            value={stage.description}
            onChange={(event) => onChange("description", event.target.value)}
            disabled={!editable}
            maxLength={4000}
          />
        </label>
        <label className={styles.checkboxLabel}>
          <input
            type="checkbox"
            checked={stage.enabled}
            onChange={(event) => onChange("enabled", event.target.checked)}
            disabled={!editable}
          />
          Enabled in published execution
        </label>
        <label className={styles.checkboxLabel}>
          <input
            type="checkbox"
            checked={stage.is_terminal}
            onChange={(event) => onChange("is_terminal", event.target.checked)}
            disabled={!editable || !stage.enabled}
          />
          Terminal response stage
        </label>

        <label>
          Provider
          <select value={stage.provider_type} onChange={(event) => updateProvider(event.target.value)} disabled={!editable}>
            {providers.map((item) => (
              <option key={item.identifier} value={item.identifier}>{item.display_name}</option>
            ))}
          </select>
        </label>
        <label>
          Model
          <select value={stage.model_string} onChange={(event) => updateModel(event.target.value)} disabled={!editable}>
            {models.map((item) => (
              <option key={item.identifier} value={item.identifier}>{item.display_name}</option>
            ))}
          </select>
        </label>

        {model?.temperature ? (
          <label>
            Temperature
            <input
              type="number"
              step="0.1"
              min={model.temperature.minimum}
              max={model.temperature.maximum}
              value={numberValue(stage.temperature)}
              onChange={(event) => updateNumber("temperature", event.target.value)}
              disabled={!editable}
            />
          </label>
        ) : null}
        {model?.supported_parameters.includes("max_output_tokens") ? (
          <label>
            Output token limit
            <input
              type="number"
              min={1}
              max={model.output_limit}
              value={numberValue(stage.token_limit)}
              onChange={(event) => updateNumber("token_limit", event.target.value)}
              disabled={!editable}
            />
          </label>
        ) : null}
        {model?.supported_parameters.includes("thinking_budget") ? (
          <label>
            Thinking budget
            <input
              type="number"
              min={model.thinking_budget_minimum}
              max={model.thinking_budget_maximum}
              value={numberValue(stage.thinking_budget)}
              onChange={(event) => updateNumber("thinking_budget", event.target.value)}
              disabled={!editable}
            />
          </label>
        ) : null}
        <label>
          Timeout in seconds
          <input
            type="number"
            min={1}
            max={3600}
            value={stage.timeout_seconds}
            onChange={(event) => updateNumber("timeout_seconds", event.target.value)}
            disabled={!editable}
          />
        </label>
        <label>
          Retry count
          <input
            type="number"
            min={0}
            max={10}
            value={stage.retry_count}
            onChange={(event) => updateNumber("retry_count", event.target.value)}
            disabled={!editable}
          />
        </label>

        <label>
          Fallback provider
          <select
            value={stage.fallback_provider_type || ""}
            onChange={(event) => updateFallbackProvider(event.target.value)}
            disabled={!editable}
          >
            <option value="">No fallback</option>
            {providers.map((item) => (
              <option key={item.identifier} value={item.identifier}>{item.display_name}</option>
            ))}
          </select>
        </label>
        <label>
          Fallback model
          <select
            value={stage.fallback_model_string || ""}
            onChange={(event) => onChange("fallback_model_string", event.target.value || null)}
            disabled={!editable || !stage.fallback_provider_type}
          >
            <option value="">No fallback</option>
            {fallbackModels.map((item) => (
              <option key={item.identifier} value={item.identifier}>{item.display_name}</option>
            ))}
          </select>
        </label>

        <div className={`${styles.fullWidth} ${styles.instructions}`}>
          <label>
            System instructions
            <textarea
              value={stage.system_prompt_directives}
              onChange={(event) => onChange("system_prompt_directives", event.target.value)}
              disabled={!editable}
              maxLength={24000}
            />
          </label>
        </div>

        <div className={styles.fullWidth}>
          <CheckboxCollection
            legend="Prerequisite stages"
            options={dependencyOptions}
            selected={stage.prerequisite_dependencies}
            disabled={!editable}
            onToggle={(identifier, checked) => {
              const dependencies = checked
                ? [...stage.prerequisite_dependencies, identifier]
                : stage.prerequisite_dependencies.filter((item) => item !== identifier);
              onChange("prerequisite_dependencies", dependencies);
            }}
          />
        </div>

        <fieldset className={`${styles.fullWidth} ${styles.capabilityFieldset}`} disabled={!editable}>
          <legend>Required model capabilities</legend>
          <div className={styles.checkboxGrid}>
            {CAPABILITY_KEYS.map((capability) => (
              <label className={styles.checkboxLabel} key={capability}>
                <input
                  type="checkbox"
                  checked={stage.required_capabilities.includes(capability)}
                  onChange={(event) => {
                    const capabilities = event.target.checked
                      ? [...stage.required_capabilities, capability]
                      : stage.required_capabilities.filter((item) => item !== capability);
                    onChange("required_capabilities", capabilities);
                  }}
                />
                {capabilityLabels[capability]}
              </label>
            ))}
          </div>
        </fieldset>

        <label className={`${styles.fullWidth} ${styles.policyFieldset}`}>
          Input policy JSON
          <textarea
            value={stage.input_policy_text}
            onChange={(event) => onChange("input_policy_text", event.target.value)}
            disabled={!editable}
            spellCheck={false}
          />
        </label>
        <label className={`${styles.fullWidth} ${styles.policyFieldset}`}>
          Output policy JSON
          <textarea
            value={stage.output_policy_text}
            onChange={(event) => onChange("output_policy_text", event.target.value)}
            disabled={!editable}
            spellCheck={false}
          />
        </label>
      </div>
    </div>
  );
}

export function PipelineBuilderCard({ onUnauthorized }) {
  const [open, setOpen] = useState(false);
  const [versions, setVersions] = useState([]);
  const [providers, setProviders] = useState([]);
  const [pipeline, setPipeline] = useState(null);
  const [selectedVersionId, setSelectedVersionId] = useState(null);
  const [activeStageIdentifier, setActiveStageIdentifier] = useState(null);
  const [draftDescription, setDraftDescription] = useState("");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const currentPublished = versions.find((version) => version.state === "published") || null;
  const activeStage = pipeline?.stages.find(
    (stage) => stage.stable_identifier === activeStageIdentifier,
  ) || pipeline?.stages[0] || null;
  const isBusy = status === "loading" || status === "saving" || status === "publishing";

  const handleError = useCallback((operationError, fallback) => {
    if (operationError?.status === 401) {
      onUnauthorized?.();
      return;
    }
    setError(operationError?.message || fallback);
    setStatus("failed");
  }, [onUnauthorized]);

  const refreshVersions = useCallback(async (preferredId = null) => {
    const loaded = await listPipelineVersions();
    setVersions(loaded);
    const nextId = preferredId || selectedVersionId || loaded.find((version) => version.state === "draft")?.id || loaded[0]?.id;
    if (nextId) {
      setSelectedVersionId(nextId);
    }
    return { loaded, nextId };
  }, [selectedVersionId]);

  const loadVersion = useCallback(async (versionId) => {
    if (!versionId) {
      setPipeline(null);
      setActiveStageIdentifier(null);
      return null;
    }
    const loaded = hydratePipelineVersion(await getPipelineVersion(versionId));
    setPipeline(loaded);
    setSelectedVersionId(loaded.id);
    setDraftDescription(loaded.change_description || "");
    setActiveStageIdentifier((current) =>
      loaded.stages.some((stage) => stage.stable_identifier === current)
        ? current
        : loaded.stages[0]?.stable_identifier || null,
    );
    return loaded;
  }, []);

  const loadBuilder = useCallback(async (preferredId = null) => {
    setStatus("loading");
    setError("");
    try {
      const [catalogue, history] = await Promise.all([
        getProviderCatalogue(),
        listPipelineVersions(),
      ]);
      const availableProviders = catalogue.providers.filter(
        (provider) => provider.adapter_available && provider.health_status === "available",
      );
      setProviders(availableProviders);
      setVersions(history);
      const nextId = preferredId || history.find((version) => version.state === "draft")?.id || history.find((version) => version.state === "published")?.id || history[0]?.id;
      if (nextId) {
        await loadVersion(nextId);
      }
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not load the pipeline control plane.");
    }
  }, [handleError, loadVersion]);

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      try {
        setVersions(await listPipelineVersions());
      } catch (operationError) {
        if (operationError?.status === 401) {
          onUnauthorized?.();
        }
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [onUnauthorized]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    function handleKeyDown(event) {
      if (event.key === "Escape" && !isBusy) {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, isBusy]);

  async function openBuilder() {
    setOpen(true);
    setNotice("");
    await loadBuilder();
  }

  async function selectVersion(versionId) {
    setStatus("loading");
    setError("");
    setNotice("");
    try {
      await loadVersion(versionId);
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not load that pipeline version.");
    }
  }

  function updateActiveStage(field, value) {
    if (!activeStage || pipeline?.state !== "draft") {
      return;
    }
    setPipeline((current) => ({
      ...current,
      stages: field === null
        ? current.stages.map((stage) =>
            stage.stable_identifier === activeStage.stable_identifier ? value : stage,
          )
        : field === "is_terminal"
          ? setTerminalStage(current.stages, activeStage.stable_identifier, value)
          : current.stages.map((stage) =>
              stage.stable_identifier === activeStage.stable_identifier
                ? { ...stage, [field]: value }
                : stage,
            ),
    }));
  }

  function renameActiveStage(value) {
    if (!activeStage || pipeline?.state !== "draft") {
      return;
    }
    const result = renameStageIdentifier(pipeline.stages, activeStage.stable_identifier, value);
    if (result.error) {
      setError(result.error);
      return;
    }
    setError("");
    setPipeline((current) => ({ ...current, stages: result.stages }));
    setActiveStageIdentifier(result.identifier);
  }

  function changeStageCollection(transform, nextIdentifier = null) {
    setPipeline((current) => {
      const stages = transform(current.stages);
      return { ...current, stages };
    });
    if (nextIdentifier) {
      setActiveStageIdentifier(nextIdentifier);
    }
  }

  function handleAddStage() {
    const next = addStage(pipeline.stages, providers);
    setPipeline((current) => ({ ...current, stages: next }));
    setActiveStageIdentifier(next[next.length - 1].stable_identifier);
  }

  function handleDuplicateStage(identifier) {
    const next = duplicateStage(pipeline.stages, identifier);
    const sourceIndex = pipeline.stages.findIndex((stage) => stage.stable_identifier === identifier);
    setPipeline((current) => ({ ...current, stages: next }));
    setActiveStageIdentifier(next[sourceIndex + 1].stable_identifier);
  }

  function handleRemoveStage(identifier) {
    const stage = pipeline.stages.find((item) => item.stable_identifier === identifier);
    if (!window.confirm(`Remove ${stage?.name || identifier} from this draft?`)) {
      return;
    }
    const next = removeStage(pipeline.stages, identifier);
    setPipeline((current) => ({ ...current, stages: next }));
    setActiveStageIdentifier(next[0]?.stable_identifier || null);
  }

  async function persistDraft({ announce = true } = {}) {
    if (!pipeline || pipeline.state !== "draft") {
      throw new Error("Select a draft before saving changes.");
    }
    if (!draftDescription.trim()) {
      throw new Error("Add a change description before saving this draft.");
    }
    const stages = serializeStages(pipeline.stages);
    const saved = hydratePipelineVersion(
      await savePipelineDraft(pipeline.id, {
        changeDescription: draftDescription.trim(),
        stages,
      }),
    );
    setPipeline(saved);
    setDraftDescription(saved.change_description);
    setActiveStageIdentifier((current) =>
      saved.stages.some((stage) => stage.stable_identifier === current)
        ? current
        : saved.stages[0]?.stable_identifier || null,
    );
    await refreshVersions(saved.id);
    if (announce) {
      setNotice(`Draft version ${saved.version_number} saved.`);
    }
    return saved;
  }

  async function handleSave() {
    setStatus("saving");
    setError("");
    setNotice("");
    try {
      await persistDraft();
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not save the pipeline draft.");
    }
  }

  async function handleValidate() {
    setStatus("saving");
    setError("");
    setNotice("");
    try {
      const saved = await persistDraft({ announce: false });
      const result = await validatePipelineDraft(saved.id);
      const validated = hydratePipelineVersion(result.version);
      setPipeline(validated);
      await refreshVersions(validated.id);
      setNotice(result.valid ? "Draft validation passed." : `Validation found ${result.issues.length} issue(s).`);
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not validate the pipeline draft.");
    }
  }

  async function handlePublish() {
    setStatus("publishing");
    setError("");
    setNotice("");
    try {
      const saved = await persistDraft({ announce: false });
      const result = await publishPipelineDraft(saved.id);
      const published = hydratePipelineVersion(result.version);
      setPipeline(published);
      await refreshVersions(published.id);
      if (!result.published) {
        setNotice(`Publication blocked by ${result.issues.length} validation issue(s).`);
        setStatus("ready");
        return;
      }
      setNotice(`Pipeline version ${published.version_number} is now published.`);
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not publish the pipeline draft.");
    }
  }

  async function handleCreateDraft() {
    const description = draftDescription.trim() || `Draft from pipeline version ${pipeline?.version_number || currentPublished?.version_number}`;
    setStatus("saving");
    setError("");
    setNotice("");
    try {
      const created = hydratePipelineVersion(
        await createPipelineDraft({
          sourceVersionId: pipeline?.id || currentPublished?.id || null,
          changeDescription: description,
        }),
      );
      setPipeline(created);
      setDraftDescription(created.change_description);
      setSelectedVersionId(created.id);
      setActiveStageIdentifier(created.stages[0]?.stable_identifier || null);
      await refreshVersions(created.id);
      setNotice(`Draft version ${created.version_number} created.`);
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not create a pipeline draft.");
    }
  }

  async function handleRollback() {
    if (!pipeline || pipeline.state === "draft") {
      return;
    }
    if (!window.confirm(`Publish a new version copied from pipeline version ${pipeline.version_number}?`)) {
      return;
    }
    setStatus("publishing");
    setError("");
    setNotice("");
    try {
      const result = await rollbackPipelineVersion(
        pipeline.id,
        draftDescription.trim() || `Rollback to pipeline version ${pipeline.version_number}`,
      );
      const restored = hydratePipelineVersion(result.version);
      setPipeline(restored);
      setDraftDescription(restored.change_description);
      setSelectedVersionId(restored.id);
      setActiveStageIdentifier(restored.stages[0]?.stable_identifier || null);
      await refreshVersions(restored.id);
      setNotice(
        result.published
          ? `Rollback published as version ${restored.version_number}.`
          : `Rollback blocked by ${result.issues.length} validation issue(s).`,
      );
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not roll back the selected pipeline version.");
    }
  }

  async function handleDeleteDraft() {
    if (!pipeline || pipeline.state !== "draft") {
      return;
    }
    if (!window.confirm(`Delete draft version ${pipeline.version_number}?`)) {
      return;
    }
    setStatus("saving");
    setError("");
    try {
      await deletePipelineDraft(pipeline.id);
      const history = await listPipelineVersions();
      setVersions(history);
      const nextId = history.find((version) => version.state === "published")?.id || history[0]?.id;
      if (nextId) {
        await loadVersion(nextId);
      } else {
        setPipeline(null);
      }
      setNotice("Draft deleted.");
      setStatus("ready");
    } catch (operationError) {
      handleError(operationError, "Could not delete the pipeline draft.");
    }
  }

  const validationIssues = useMemo(() => pipeline?.validation_issues || [], [pipeline]);

  return (
    <>
      <section className={`settings-pane ${styles.launcher}`}>
        <div className={styles.launcherHeader}>
          <div>
            <h3>Pipeline control</h3>
            <p className="muted">
              Build, validate, publish and roll back the complete reasoning pipeline without database or code access.
            </p>
          </div>
          <button type="button" className="button-primary" onClick={openBuilder}>
            Open pipeline builder
          </button>
        </div>
        {currentPublished ? (
          <div className={styles.metaRow}>
            <StatusBadge>version {currentPublished.version_number}</StatusBadge>
            <StatusBadge>{currentPublished.stage_count} stages</StatusBadge>
            <StatusBadge>{displayState(currentPublished.validation_status)}</StatusBadge>
            <span className="muted">Published {formatDate(currentPublished.published_at)}</span>
          </div>
        ) : (
          <p className="muted">No published pipeline summary loaded yet.</p>
        )}
      </section>

      {open ? (
        <div className={styles.overlay} role="presentation" onMouseDown={() => !isBusy && setOpen(false)}>
          <section
            className={styles.dialog}
            role="dialog"
            aria-modal="true"
            aria-labelledby="pipeline-builder-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className={styles.toolbar}>
              <div className={styles.toolbarTitle}>
                <p className="eyebrow">Administration</p>
                <h2 id="pipeline-builder-title">Pipeline builder</h2>
                <p className="muted">Published versions are immutable. All changes begin as a draft.</p>
              </div>
              <div className={styles.actionRow}>
                <button type="button" className="button-ghost" onClick={() => loadBuilder(selectedVersionId)} disabled={isBusy}>
                  Refresh
                </button>
                <button type="button" className="button-ghost" onClick={() => setOpen(false)} disabled={isBusy}>
                  Close
                </button>
              </div>
            </header>

            <div className={styles.workspace}>
              <aside className={styles.column} aria-label="Pipeline version history">
                <div className={styles.columnHeading}>
                  <h3>Versions</h3>
                  <p className="muted">Draft and published history</p>
                </div>
                <VersionHistory
                  versions={versions}
                  selectedId={selectedVersionId}
                  onSelect={selectVersion}
                  disabled={isBusy}
                />
              </aside>

              <aside className={styles.column} aria-label="Pipeline stages">
                <div className={styles.columnHeading}>
                  <h3>Stages</h3>
                  <p className="muted">Order, bypass and terminal routing</p>
                </div>
                {pipeline ? (
                  <StageList
                    pipeline={pipeline}
                    activeIdentifier={activeStage?.stable_identifier}
                    onSelect={setActiveStageIdentifier}
                    onMove={(identifier, direction) =>
                      changeStageCollection((stages) => moveStage(stages, identifier, direction))
                    }
                    onDuplicate={handleDuplicateStage}
                    onRemove={handleRemoveStage}
                    onAdd={handleAddStage}
                    disabled={isBusy}
                  />
                ) : (
                  <div className={styles.emptyState}>No pipeline version selected.</div>
                )}
              </aside>

              <main className={styles.column} aria-label="Pipeline stage editor">
                <div className={styles.columnHeading}>
                  <div className={styles.editorHeader}>
                    <div>
                      <h3>{pipeline ? `Version ${pipeline.version_number}` : "Configuration"}</h3>
                      <p className="muted">
                        {pipeline ? `${displayState(pipeline.state)} · ${displayState(pipeline.validation_status)}` : "Select a version"}
                      </p>
                    </div>
                    {pipeline ? (
                      <div className={styles.badgeRow}>
                        <StatusBadge>{pipeline.stages.length} stages</StatusBadge>
                        <StatusBadge>{displayState(pipeline.state)}</StatusBadge>
                      </div>
                    ) : null}
                  </div>
                </div>

                {error ? <p className={styles.error}>{error}</p> : null}
                {notice ? <p className={styles.notice}>{notice}</p> : null}

                {pipeline ? (
                  <div className={styles.stack}>
                    <label>
                      Change description
                      <input
                        value={draftDescription}
                        onChange={(event) => setDraftDescription(event.target.value)}
                        disabled={isBusy}
                        maxLength={4000}
                        placeholder="Explain what this version changes"
                      />
                    </label>

                    <div className={styles.actionRow}>
                      {pipeline.state === "draft" ? (
                        <>
                          <button type="button" className="button-ghost" onClick={handleSave} disabled={isBusy}>
                            Save draft
                          </button>
                          <button type="button" className="button-ghost" onClick={handleValidate} disabled={isBusy}>
                            Validate
                          </button>
                          <button type="button" className="button-primary" onClick={handlePublish} disabled={isBusy}>
                            Publish
                          </button>
                          <button type="button" className={`button-ghost ${styles.dangerButton}`} onClick={handleDeleteDraft} disabled={isBusy}>
                            Delete draft
                          </button>
                        </>
                      ) : (
                        <>
                          <button type="button" className="button-primary" onClick={handleCreateDraft} disabled={isBusy}>
                            Create draft from this version
                          </button>
                          {pipeline.state === "superseded" ? (
                            <button type="button" className="button-ghost" onClick={handleRollback} disabled={isBusy}>
                              Roll back to this version
                            </button>
                          ) : null}
                        </>
                      )}
                    </div>

                    {validationIssues.length > 0 ? (
                      <section className={styles.issueList} aria-label="Pipeline validation issues">
                        <h3>Validation issues</h3>
                        {validationIssues.map((issue, index) => (
                          <div className={styles.issue} key={`${issue.code}-${issue.stage_identifier || "pipeline"}-${index}`}>
                            <code>{issue.code}</code>
                            <strong>{issue.stage_identifier || "Pipeline"}</strong>
                            <p>{issue.message}</p>
                          </div>
                        ))}
                      </section>
                    ) : null}

                    <StageEditor
                      pipeline={pipeline}
                      stage={activeStage}
                      providers={providers}
                      onChange={updateActiveStage}
                      onRename={renameActiveStage}
                      disabled={isBusy}
                    />
                  </div>
                ) : (
                  <div className={styles.emptyState}>
                    {status === "loading" ? "Loading pipeline versions…" : "Select a pipeline version."}
                  </div>
                )}
              </main>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
