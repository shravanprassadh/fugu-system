export const defaultModelPreference = {
  providerType: "openrouter",
  modelIdentifier: "openrouter/free",
};

const STORAGE_KEY = "fugu:selected-model";

function normalizedString(value) {
  return typeof value === "string" ? value.trim() : "";
}

export function normalizeModelPreference(preference) {
  const providerType = normalizedString(preference?.providerType).toLowerCase();
  const modelIdentifier = normalizedString(preference?.modelIdentifier);
  if (!providerType || !modelIdentifier) {
    return { ...defaultModelPreference };
  }
  return { providerType, modelIdentifier };
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
  return {
    providerType: selectedProvider.identifier,
    modelIdentifier: selectedModel.identifier,
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
