"use client";

import { useCallback, useEffect, useState } from "react";

import { getProviderCatalogue } from "../../lib/api-client";
import {
  loadModelPreference,
  normalizePreferenceAgainstCatalogue,
  saveModelPreference,
} from "../../lib/model-options";
import { ProviderCredentialControls } from "./provider-credential-controls";
import styles from "./settings.module.css";

function providerInitial(provider) {
  return provider.display_name.slice(0, 1).toUpperCase();
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(value);
}

function capabilityLabels(model) {
  const labels = ["Text"];
  if (model.capabilities.image_understanding) {
    labels.push("Vision");
  }
  if (model.capabilities.document_input) {
    labels.push("Documents");
  }
  if (model.capabilities.tool_support) {
    labels.push("Tools");
  }
  if (model.capabilities.reasoning_support) {
    labels.push("Reasoning");
  }
  return labels;
}

export function ModelPreferenceCard() {
  const [preference, setPreference] = useState(loadModelPreference);
  const [providers, setProviders] = useState([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState("");

  const loadCatalogue = useCallback(async () => {
    setStatus("loading");
    setError("");
    try {
      const payload = await getProviderCatalogue();
      const availableProviders = payload.providers.filter(
        (provider) => provider.adapter_available && provider.health_status === "available",
      );
      setProviders(availableProviders);
      setPreference((current) => {
        const normalized = normalizePreferenceAgainstCatalogue(current, availableProviders);
        return saveModelPreference(normalized);
      });
      setStatus("ready");
    } catch (operationError) {
      setError(operationError.message || "Could not load the provider catalogue.");
      setStatus("failed");
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadCatalogue();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadCatalogue]);

  useEffect(() => {
    const handleChange = (event) => {
      setPreference(event.detail || loadModelPreference());
    };
    window.addEventListener("fugu:model-preference-change", handleChange);
    return () => window.removeEventListener("fugu:model-preference-change", handleChange);
  }, []);

  const selectedProvider =
    providers.find((provider) => provider.identifier === preference.providerType) || providers[0] || null;
  const models = selectedProvider?.models.filter((model) => model.availability_status === "available") || [];
  const selectedModel =
    models.find((model) => model.identifier === preference.modelIdentifier) || models[0] || null;
  const normalizedQuery = query.trim().toLowerCase();
  const filteredModels = normalizedQuery
    ? models.filter((model) =>
        `${model.identifier} ${model.display_name}`.toLowerCase().includes(normalizedQuery),
      )
    : models;

  function updateProvider(providerIdentifier) {
    const provider = providers.find((item) => item.identifier === providerIdentifier);
    const model = provider?.models.find((item) => item.availability_status === "available");
    if (!provider || !model) {
      return;
    }
    setQuery("");
    setPreference(
      saveModelPreference({
        providerType: provider.identifier,
        modelIdentifier: model.identifier,
      }),
    );
  }

  function updateModel(modelIdentifier) {
    if (!selectedProvider) {
      return;
    }
    setPreference(
      saveModelPreference({
        providerType: selectedProvider.identifier,
        modelIdentifier,
      }),
    );
  }

  return (
    <>
      <section className="settings-pane model-preference-card">
        <div className="settings-row settings-row-top">
          <div>
            <h3>Model</h3>
            <p className="muted">
              Provider and model capabilities come from the backend catalogue. Unsupported combinations are never offered.
            </p>
          </div>
          <button type="button" className="button-ghost" onClick={loadCatalogue} disabled={status === "loading"}>
            Refresh catalogue
          </button>
        </div>

        {error ? <p className={styles.diagnosticError}>{error}</p> : null}
        {status === "loading" && providers.length === 0 ? <p className="muted">Loading provider catalogue…</p> : null}

        {providers.length > 0 ? (
          <div className="model-provider-grid" role="radiogroup" aria-label="Model provider">
            {providers.map((provider) => {
              const selected = provider.identifier === selectedProvider?.identifier;
              return (
                <button
                  key={provider.identifier}
                  type="button"
                  className={`model-provider-card ${selected ? "model-card-selected" : ""}`}
                  onClick={() => updateProvider(provider.identifier)}
                  role="radio"
                  aria-checked={selected}
                >
                  <span className="model-provider-mark" aria-hidden="true">{providerInitial(provider)}</span>
                  <span>
                    <strong>{provider.display_name}</strong>
                    <small>{provider.models.length} backend-approved models</small>
                  </span>
                </button>
              );
            })}
          </div>
        ) : null}

        {selectedModel ? (
          <>
            <div className="model-selected-summary">
              <div>
                <span className="model-selected-eyebrow">Selected model</span>
                <strong>{selectedModel.display_name}</strong>
                <code>{selectedModel.identifier}</code>
              </div>
              <span className="model-family-pill">{selectedProvider.display_name}</span>
            </div>

            <div className="model-provider-grid" aria-label="Selected model capabilities">
              {capabilityLabels(selectedModel).map((capability) => (
                <span className="model-family-pill" key={capability}>{capability}</span>
              ))}
              <span className="model-family-pill">{formatNumber(selectedModel.context_size)} context</span>
              <span className="model-family-pill">{formatNumber(selectedModel.output_limit)} output</span>
            </div>

            {models.length > 1 ? (
              <label className="model-search-box">
                Search models
                <input
                  type="search"
                  placeholder={`Search ${selectedProvider.display_name} models…`}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
            ) : null}

            <div className="model-option-list" role="radiogroup" aria-label="Available models">
              {filteredModels.map((model) => {
                const selected = model.identifier === selectedModel.identifier;
                return (
                  <button
                    key={model.identifier}
                    type="button"
                    className={`model-option-card ${selected ? "model-card-selected" : ""}`}
                    onClick={() => updateModel(model.identifier)}
                    role="radio"
                    aria-checked={selected}
                  >
                    <span>
                      <strong>{model.display_name}</strong>
                      <code>{model.identifier}</code>
                    </span>
                    <span className="model-family-pill">
                      {capabilityLabels(model).join(" · ")}
                    </span>
                  </button>
                );
              })}
            </div>
          </>
        ) : null}
      </section>
      <ProviderCredentialControls providers={providers} />
    </>
  );
}
