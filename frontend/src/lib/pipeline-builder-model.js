const CAPABILITY_KEYS = [
  "text_generation",
  "image_understanding",
  "document_input",
  "tool_support",
  "reasoning_support",
];

export { CAPABILITY_KEYS };

function slugify(value) {
  return String(value || "stage")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "") || "stage";
}

export function uniqueStageIdentifier(stages, preferred = "stage") {
  const base = slugify(preferred);
  const used = new Set(stages.map((stage) => stage.stable_identifier));
  if (!used.has(base)) {
    return base;
  }
  let suffix = 2;
  while (used.has(`${base}-${suffix}`)) {
    suffix += 1;
  }
  return `${base}-${suffix}`;
}

export function normalizeStagePositions(stages) {
  return stages.map((stage, index) => ({ ...stage, position: index + 1 }));
}

export function hydrateStage(stage) {
  return {
    ...stage,
    description: stage.description || "",
    system_prompt_directives: stage.system_prompt_directives || "",
    prerequisite_dependencies: [...(stage.prerequisite_dependencies || [])],
    required_capabilities: [...(stage.required_capabilities || ["text_generation"])],
    input_policy_text: JSON.stringify(stage.input_policy || {}, null, 2),
    output_policy_text: JSON.stringify(stage.output_policy || {}, null, 2),
  };
}

export function hydratePipelineVersion(version) {
  return {
    ...version,
    stages: normalizeStagePositions(
      [...(version.stages || [])]
        .sort((left, right) => left.position - right.position)
        .map(hydrateStage),
    ),
  };
}

export function createStage(stages, providers, preferredName = "New stage") {
  const provider = providers.find((item) => item.adapter_available && item.health_status === "available") || providers[0];
  const model = provider?.models.find((item) => item.availability_status === "available") || provider?.models[0];
  const stableIdentifier = uniqueStageIdentifier(stages, preferredName);
  return {
    id: null,
    stable_identifier: stableIdentifier,
    name: preferredName,
    description: "",
    enabled: true,
    position: stages.length + 1,
    provider_type: provider?.identifier || "openrouter",
    model_string: model?.identifier || "openrouter/free",
    system_prompt_directives: "",
    prerequisite_dependencies: [],
    is_terminal: stages.length === 0,
    temperature: model?.temperature?.default ?? null,
    thinking_budget: model?.thinking_budget_minimum ?? null,
    token_limit: model?.supported_parameters?.includes("max_output_tokens")
      ? Math.min(model.output_limit || 4096, 4096)
      : null,
    timeout_seconds: 45,
    retry_count: 0,
    fallback_provider_type: null,
    fallback_model_string: null,
    input_policy: {},
    output_policy: {},
    required_capabilities: ["text_generation"],
    input_policy_text: "{}",
    output_policy_text: "{}",
  };
}

export function addStage(stages, providers) {
  return normalizeStagePositions([...stages, createStage(stages, providers)]);
}

export function duplicateStage(stages, stageIdentifier) {
  const index = stages.findIndex((stage) => stage.stable_identifier === stageIdentifier);
  if (index < 0) {
    return stages;
  }
  const source = stages[index];
  const duplicateIdentifier = uniqueStageIdentifier(stages, `${source.stable_identifier}-copy`);
  const duplicate = {
    ...source,
    id: null,
    stable_identifier: duplicateIdentifier,
    name: `${source.name} copy`,
    is_terminal: false,
    prerequisite_dependencies: [...source.prerequisite_dependencies],
    required_capabilities: [...source.required_capabilities],
  };
  const next = [...stages];
  next.splice(index + 1, 0, duplicate);
  return normalizeStagePositions(next);
}

export function removeStage(stages, stageIdentifier) {
  const remaining = stages
    .filter((stage) => stage.stable_identifier !== stageIdentifier)
    .map((stage) => ({
      ...stage,
      prerequisite_dependencies: stage.prerequisite_dependencies.filter(
        (dependency) => dependency !== stageIdentifier,
      ),
    }));
  if (remaining.length > 0 && !remaining.some((stage) => stage.enabled && stage.is_terminal)) {
    const terminalIndex = [...remaining].reverse().findIndex((stage) => stage.enabled);
    if (terminalIndex >= 0) {
      const actualIndex = remaining.length - 1 - terminalIndex;
      remaining[actualIndex] = { ...remaining[actualIndex], is_terminal: true };
    }
  }
  return normalizeStagePositions(remaining);
}

export function moveStage(stages, stageIdentifier, direction) {
  const index = stages.findIndex((stage) => stage.stable_identifier === stageIdentifier);
  const targetIndex = index + direction;
  if (index < 0 || targetIndex < 0 || targetIndex >= stages.length) {
    return stages;
  }
  const next = [...stages];
  [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
  return normalizeStagePositions(next);
}

export function renameStageIdentifier(stages, previousIdentifier, nextValue) {
  const nextIdentifier = slugify(nextValue);
  if (
    !nextIdentifier ||
    stages.some(
      (stage) => stage.stable_identifier === nextIdentifier && stage.stable_identifier !== previousIdentifier,
    )
  ) {
    return { stages, identifier: previousIdentifier, error: "Stage identifiers must be unique." };
  }
  const nextStages = stages.map((stage) => ({
    ...stage,
    stable_identifier:
      stage.stable_identifier === previousIdentifier ? nextIdentifier : stage.stable_identifier,
    prerequisite_dependencies: stage.prerequisite_dependencies.map((dependency) =>
      dependency === previousIdentifier ? nextIdentifier : dependency,
    ),
  }));
  return { stages: nextStages, identifier: nextIdentifier, error: "" };
}

export function setTerminalStage(stages, stageIdentifier, terminal) {
  return stages.map((stage) => ({
    ...stage,
    is_terminal: terminal ? stage.stable_identifier === stageIdentifier : stage.is_terminal && stage.stable_identifier !== stageIdentifier,
  }));
}

export function modelForStage(stage, providers) {
  const provider = providers.find((item) => item.identifier === stage.provider_type);
  return provider?.models.find((item) => item.identifier === stage.model_string) || null;
}

export function applyProviderToStage(stage, providerIdentifier, providers) {
  const provider = providers.find((item) => item.identifier === providerIdentifier);
  const model = provider?.models.find((item) => item.availability_status === "available") || provider?.models[0];
  return applyModelToStage(
    { ...stage, provider_type: provider?.identifier || providerIdentifier },
    model?.identifier || "",
    providers,
  );
}

export function applyModelToStage(stage, modelIdentifier, providers) {
  const provider = providers.find((item) => item.identifier === stage.provider_type);
  const model = provider?.models.find((item) => item.identifier === modelIdentifier);
  if (!model) {
    return { ...stage, model_string: modelIdentifier };
  }
  return {
    ...stage,
    model_string: model.identifier,
    temperature: model.temperature ? model.temperature.default : null,
    thinking_budget: model.supported_parameters.includes("thinking_budget")
      ? model.thinking_budget_minimum
      : null,
    token_limit: model.supported_parameters.includes("max_output_tokens")
      ? Math.min(model.output_limit, stage.token_limit || model.output_limit)
      : null,
  };
}

function parsePolicy(value, label, stageIdentifier) {
  try {
    const parsed = JSON.parse(value || "{}");
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("must be a JSON object");
    }
    return parsed;
  } catch (error) {
    throw new Error(`${label} for ${stageIdentifier} is invalid: ${error.message}`);
  }
}

export function serializeStages(stages) {
  return normalizeStagePositions(stages).map((stage) => ({
    stable_identifier: stage.stable_identifier,
    name: stage.name.trim(),
    description: stage.description.trim(),
    enabled: Boolean(stage.enabled),
    position: stage.position,
    provider_type: stage.provider_type,
    model_string: stage.model_string,
    system_prompt_directives: stage.system_prompt_directives.trim(),
    prerequisite_dependencies: [...stage.prerequisite_dependencies],
    is_terminal: Boolean(stage.is_terminal),
    temperature: stage.temperature === "" ? null : stage.temperature,
    thinking_budget: stage.thinking_budget === "" ? null : stage.thinking_budget,
    token_limit: stage.token_limit === "" ? null : stage.token_limit,
    timeout_seconds: Number(stage.timeout_seconds),
    retry_count: Number(stage.retry_count),
    fallback_provider_type: stage.fallback_provider_type || null,
    fallback_model_string: stage.fallback_model_string || null,
    input_policy: parsePolicy(stage.input_policy_text, "Input policy", stage.stable_identifier),
    output_policy: parsePolicy(stage.output_policy_text, "Output policy", stage.stable_identifier),
    required_capabilities: [...stage.required_capabilities],
  }));
}
