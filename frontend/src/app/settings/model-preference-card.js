"use client";

import { useEffect, useState } from "react";

import {
  loadModelPreference,
  modelOptionsFor,
  normalizeProvider,
  saveModelPreference,
  supportedProviders,
} from "../../lib/model-options";
import styles from "./settings.module.css";

export function ModelPreferenceCard() {
  const [preference, setPreference] = useState(loadModelPreference);

  useEffect(() => {
    const handleChange = (event) => {
      setPreference(event.detail || loadModelPreference());
    };
    window.addEventListener("fugu:model-preference-change", handleChange);
    return () => window.removeEventListener("fugu:model-preference-change", handleChange);
  }, []);

  const providerType = normalizeProvider(preference.providerType);
  const models = modelOptionsFor(providerType);

  function updateProvider(nextProviderType) {
    setPreference(saveModelPreference({ providerType: nextProviderType }));
  }

  function updateModel(nextModelIdentifier) {
    setPreference(saveModelPreference({ providerType, modelIdentifier: nextModelIdentifier }));
  }

  return (
    <section className="settings-pane">
      <div className="settings-row settings-row-top">
        <div>
          <h3>Model</h3>
          <p className="muted">Choose the model used for your chat responses. This preference is saved on this device.</p>
        </div>
        <span className={styles.statusPill}>user preference</span>
      </div>
      <div className={styles.preferenceForm}>
        <label>
          Provider
          <select value={providerType} onChange={(event) => updateProvider(event.target.value)}>
            {supportedProviders.map((provider) => (
              <option key={provider.value} value={provider.value}>{provider.label}</option>
            ))}
          </select>
        </label>
        <label>
          Model
          <select value={preference.modelIdentifier} onChange={(event) => updateModel(event.target.value)}>
            {models.map((model) => (
              <option key={model.value} value={model.value}>{model.label}</option>
            ))}
          </select>
        </label>
      </div>
      <p className="muted">
        Admins still manage provider API keys in AI & operations. If a provider key is missing, runs using that provider will fail clearly.
      </p>
    </section>
  );
}
