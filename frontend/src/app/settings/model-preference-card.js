"use client";

import { useEffect, useState } from "react";

import {
  loadModelPreference,
  modelOptionsFor,
  normalizeProvider,
  saveModelPreference,
  supportedProviders,
} from "../../lib/model-options";
import { ProviderCredentialControls } from "./provider-credential-controls";
import styles from "./settings.module.css";

function providerInitial(provider) {
  return provider.label.slice(0, 1).toUpperCase();
}

function modelTitle(modelId) {
  const [, name = modelId] = modelId.split("/");
  return name
    .split("-")
    .filter(Boolean)
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
}

function modelFamily(modelId) {
  return modelId.includes("/") ? modelId.split("/")[0] : "model";
}

export function ModelPreferenceCard() {
  const [preference, setPreference] = useState(loadModelPreference);
  const [query, setQuery] = useState("");

  useEffect(() => {
    const handleChange = (event) => {
      setPreference(event.detail || loadModelPreference());
    };
    window.addEventListener("fugu:model-preference-change", handleChange);
    return () => window.removeEventListener("fugu:model-preference-change", handleChange);
  }, []);

  const providerType = normalizeProvider(preference.providerType);
  const models = modelOptionsFor(providerType);
  const selectedModel = models.find((model) => model.value === preference.modelIdentifier) || models[0];
  const normalizedQuery = query.trim().toLowerCase();
  const filteredModels = normalizedQuery
    ? models.filter((model) => `${model.value} ${model.label}`.toLowerCase().includes(normalizedQuery))
    : models;

  function updateProvider(nextProviderType) {
    setQuery("");
    setPreference(saveModelPreference({ providerType: nextProviderType }));
  }

  function updateModel(nextModelIdentifier) {
    setPreference(saveModelPreference({ providerType, modelIdentifier: nextModelIdentifier }));
  }

  return (
    <>
      <section className="settings-pane model-preference-card">
        <div className="settings-row settings-row-top">
          <div>
            <h3>Model</h3>
            <p className="muted">Choose the model used for your chat responses. This preference is saved on this device.</p>
          </div>
          <span className={styles.statusPill}>user preference</span>
        </div>

        <div className="model-provider-grid" role="radiogroup" aria-label="Model provider">
          {supportedProviders.map((provider) => {
            const selected = provider.value === providerType;
            return (
              <button
                key={provider.value}
                type="button"
                className={`model-provider-card ${selected ? "model-card-selected" : ""}`}
                onClick={() => updateProvider(provider.value)}
                role="radio"
                aria-checked={selected}
              >
                <span className="model-provider-mark" aria-hidden="true">{providerInitial(provider)}</span>
                <span>
                  <strong>{provider.label}</strong>
                  <small>{provider.value === "openrouter" ? "Free tier only" : "Free NVIDIA catalog"}</small>
                </span>
              </button>
            );
          })}
        </div>

        <div className="model-selected-summary">
          <div>
            <span className="model-selected-eyebrow">Selected model</span>
            <strong>{modelTitle(selectedModel.value)}</strong>
            <code>{selectedModel.value}</code>
          </div>
          <span className="model-family-pill">{modelFamily(selectedModel.value)}</span>
        </div>

        {models.length > 1 ? (
          <label className="model-search-box">
            Search models
            <input
              type="search"
              placeholder="Search NVIDIA models…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
        ) : null}

        <div className="model-option-list" role="radiogroup" aria-label="Available models">
          {filteredModels.map((model) => {
            const selected = model.value === selectedModel.value;
            return (
              <button
                key={model.value}
                type="button"
                className={`model-option-card ${selected ? "model-card-selected" : ""}`}
                onClick={() => updateModel(model.value)}
                role="radio"
                aria-checked={selected}
              >
                <span>
                  <strong>{modelTitle(model.value)}</strong>
                  <code>{model.value}</code>
                </span>
                <span className="model-family-pill">{modelFamily(model.value)}</span>
              </button>
            );
          })}
        </div>

        <p className="muted">
          Administrators manage each provider&apos;s single active key directly below the model catalogue.
        </p>
      </section>
      <ProviderCredentialControls />
    </>
  );
}
