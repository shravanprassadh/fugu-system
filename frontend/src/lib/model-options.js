export const supportedProviders = [
  { value: "openrouter", label: "OpenRouter" },
  { value: "nvidia", label: "NVIDIA" },
];

export const nvidiaChatModelIds = [
  "01-ai/yi-large",
  "abacusai/dracarys-llama-3.1-70b-instruct",
  "ai21labs/jamba-1.5-large-instruct",
  "aisingapore/sea-lion-7b-instruct",
  "bytedance/seed-oss-36b-instruct",
  "databricks/dbrx-instruct",
  "deepseek-ai/deepseek-coder-6.7b-instruct",
  "deepseek-ai/deepseek-v4-flash",
  "deepseek-ai/deepseek-v4-pro",
  "google/codegemma-1.1-7b",
  "google/codegemma-7b",
  "google/gemma-2-2b-it",
  "google/gemma-3-12b-it",
  "google/gemma-3-4b-it",
  "google/gemma-3n-e2b-it",
  "google/gemma-3n-e4b-it",
  "google/gemma-4-31b-it",
  "ibm/granite-3.0-3b-a800m-instruct",
  "ibm/granite-3.0-8b-instruct",
  "ibm/granite-34b-code-instruct",
  "ibm/granite-8b-code-instruct",
  "meta/codellama-70b",
  "meta/llama-3.1-70b-instruct",
  "meta/llama-3.1-8b-instruct",
  "meta/llama-3.2-1b-instruct",
  "meta/llama-3.2-3b-instruct",
  "meta/llama-3.2-11b-vision-instruct",
  "meta/llama-3.2-90b-vision-instruct",
  "meta/llama-3.3-70b-instruct",
  "meta/llama-4-maverick-17b-128e-instruct",
  "meta/llama2-70b",
  "microsoft/phi-3-vision-128k-instruct",
  "microsoft/phi-3.5-moe-instruct",
  "microsoft/phi-4-mini-instruct",
  "microsoft/phi-4-multimodal-instruct",
  "minimaxai/minimax-m2.7",
  "minimaxai/minimax-m3",
  "mistralai/codestral-22b-instruct-v0.1",
  "mistralai/ministral-14b-instruct-2512",
  "mistralai/mistral-7b-instruct-v0.3",
  "mistralai/mistral-large",
  "mistralai/mistral-large-2-instruct",
  "mistralai/mistral-large-3-675b-instruct-2512",
  "mistralai/mistral-medium-3.5-128b",
  "mistralai/mistral-nemotron",
  "mistralai/mistral-small-4-119b-2603",
  "mistralai/mixtral-8x22b-v0.1",
  "mistralai/mixtral-8x7b-instruct-v0.1",
  "moonshotai/kimi-k2.6",
  "nv-mistralai/mistral-nemo-12b-instruct",
  "nvidia/cosmos-reason2-8b",
  "nvidia/llama-3.1-nemotron-51b-instruct",
  "nvidia/llama-3.1-nemotron-70b-instruct",
  "nvidia/llama-3.1-nemotron-nano-8b-v1",
  "nvidia/llama-3.1-nemotron-ultra-253b-v1",
  "nvidia/llama-3.3-nemotron-super-49b-v1",
  "nvidia/llama-3.3-nemotron-super-49b-v1.5",
  "nvidia/llama3-chatqa-1.5-70b",
  "nvidia/mistral-nemo-minitron-8b-8k-instruct",
  "nvidia/nemotron-3-nano-30b-a3b",
  "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
  "nvidia/nemotron-3-super-120b-a12b",
  "nvidia/nemotron-3-ultra-550b-a55b",
  "nvidia/nemotron-4-340b-instruct",
  "nvidia/nemotron-mini-4b-instruct",
  "nvidia/nvidia-nemotron-nano-9b-v2",
  "openai/gpt-oss-120b",
  "openai/gpt-oss-20b",
  "qwen/qwen3-next-80b-a3b-instruct",
  "qwen/qwen3.5-122b-a10b",
  "qwen/qwen3.5-397b-a17b",
  "sarvamai/sarvam-m",
  "stepfun-ai/step-3.5-flash",
  "stepfun-ai/step-3.7-flash",
  "stockmark/stockmark-2-100b-instruct",
  "upstage/solar-10.7b-instruct",
  "writer/palmyra-creative-122b",
  "writer/palmyra-fin-70b-32k",
  "writer/palmyra-med-70b",
  "writer/palmyra-med-70b-32k",
  "z-ai/glm-5.2",
  "zyphra/zamba2-7b-instruct",
];

export const supportedModelsByProvider = {
  openrouter: [{ value: "openrouter/free", label: "OpenRouter free tier" }],
  nvidia: nvidiaChatModelIds.map((modelId) => ({ value: modelId, label: modelId })),
};

export const defaultModelPreference = {
  providerType: "openrouter",
  modelIdentifier: "openrouter/free",
};

const STORAGE_KEY = "fugu:selected-model";

export function normalizeProvider(providerType) {
  return supportedModelsByProvider[providerType] ? providerType : defaultModelPreference.providerType;
}

export function modelOptionsFor(providerType) {
  return supportedModelsByProvider[normalizeProvider(providerType)];
}

export function normalizeModel(providerType, modelIdentifier) {
  const options = modelOptionsFor(providerType);
  return options.some((option) => option.value === modelIdentifier)
    ? modelIdentifier
    : options[0].value;
}

export function normalizeModelPreference(preference) {
  const providerType = normalizeProvider(preference?.providerType);
  return {
    providerType,
    modelIdentifier: normalizeModel(providerType, preference?.modelIdentifier),
  };
}

export function loadModelPreference() {
  if (typeof window === "undefined") {
    return defaultModelPreference;
  }
  try {
    return normalizeModelPreference(JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null"));
  } catch {
    return defaultModelPreference;
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
