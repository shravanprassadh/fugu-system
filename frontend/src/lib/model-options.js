export const defaultModelPreference = {
  providerType: "openrouter",
  modelIdentifier: "openrouter/free",
  temperature: null,
  maxOutputTokens: null,
  thinkingBudget: null,
};

const STORAGE_KEY = "fugu:selected-model";

function normalizedString(value) {
  return typeof value === "string" ? value.trim() : "";
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function positiveInteger(value) {
  const number = finiteNumber(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}

export function normalizeModelPreference(preference) {
  const providerType = normalizedString(preference?.providerType).toLowerCase();
  const modelIdentifier = normalizedString(preference?.modelIdentifier);
  if (!providerType || !modelIdentifier) {
    return { ...defaultModelPreference };
  }
  return {
    providerType,
    modelIdentifier,
    temperature: finiteNumber(preference?.temperature),
    maxOutputTokens: positiveInteger(preference?.maxOutputTokens),
    thinkingBudget: positiveInteger(preference?.thinkingBudget),
  };
}

function modelDefaults(provider, model) {
  return {
    providerType: provider.identifier,
    modelIdentifier: model.identifier,
    temperature: model.temperature?.default ?? null,
    maxOutputTokens: model.supported_parameters.includes("max_output_tokens") ? model.output_limit : null,
    thinkingBudget:
      model.supported_parameters.includes("thinking_budget") && model.thinking_budget_minimum !== null
        ? model.thinking_budget_minimum
        : null,
  };
}

export function normalizePreferenceAgainstCatalogue(preference, providers) {
  const normalized = normalizeModelPreference(preference);
  const provider = providers.find((item) => item.identifier === normalized.providerType);
  const selectedProvider = provider || providers[0];
  const model = selectedProvider?.models.find((item) => item.identifier === normalized.modelIdentifier);
  const selectedModel = model || selectedProvider?.models[0];
  if (!selectedProvider || !selectedModel) {
    return { ...defaultModelPreference };
  }

  const defaults = modelDefaults(selectedProvider, selectedModel);
  const temperature = selectedModel.temperature;
  const validTemperature =
    normalized.temperature !== null &&
    temperature !== null &&
    normalized.temperature >= temperature.minimum &&
    normalized.temperature <= temperature.maximum;
  const validOutput =
    normalized.maxOutputTokens !== null &&
    selectedModel.supported_parameters.includes("max_output_tokens") &&
    normalized.maxOutputTokens <= selectedModel.output_limit;
  const validThinking =
    normalized.thinkingBudget !== null &&
    selectedModel.supported_parameters.includes("thinking_budget") &&
    selectedModel.thinking_budget_minimum !== null &&
    selectedModel.thinking_budget_maximum !== null &&
    normalized.thinkingBudget >= selectedModel.thinking_budget_minimum &&
    normalized.thinkingBudget <= selectedModel.thinking_budget_maximum;

  return {
    ...defaults,
    temperature: validTemperature ? normalized.temperature : defaults.temperature,
    maxOutputTokens: validOutput ? normalized.maxOutputTokens : defaults.maxOutputTokens,
    thinkingBudget: validThinking ? normalized.thinkingBudget : defaults.thinkingBudget,
  };
}

export function loadModelPreference() {
  if (typeof window === "undefined") {
    return { ...defaultModelPreference };
  }
  try {
    return normalizeModelPreference(JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null"));
  } catch {
    return { ...defaultModelPreference };
  }
}

export function saveModelPreference(preference) {
  const normalized = normalizeModelPreference(preference);
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
    window.dispatchEvent(new CustomEvent("fugu:model-preference-change", { detail: normalized }));
  }
  return normalized;
}
