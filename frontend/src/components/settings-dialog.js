"use client";

import { useEffect, useState } from "react";

import { ModelPreferenceCard } from "../app/settings/model-preference-card";
import settingsStyles from "../app/settings/settings.module.css";
import { ThemeModePicker } from "./theme-toggle";

const sections = [
  {
    id: "general",
    label: "General",
    description: "Theme, model and client behavior",
  },
  {
    id: "account",
    label: "Account",
    description: "Session and sign out",
  },
];

const overlayStyle = {
  position: "fixed",
  inset: 0,
  zIndex: 70,
  display: "grid",
  placeItems: "center",
  background: "rgba(7, 10, 18, 0.52)",
  padding: "clamp(0.75rem, 2vw, 1.5rem)",
};

const dialogStyle = {
  width: "min(100%, 920px)",
  maxHeight: "min(760px, calc(100dvh - 2rem))",
  display: "grid",
  gridTemplateColumns: "220px minmax(0, 1fr)",
  border: "1px solid color-mix(in srgb, var(--line) 82%, transparent)",
  borderRadius: "24px",
  background: "color-mix(in srgb, var(--surface) 96%, var(--bg))",
  boxShadow: "0 28px 90px rgba(0, 0, 0, 0.32)",
  overflow: "hidden",
};

const navStyle = {
  display: "grid",
  alignContent: "start",
  gap: "0.18rem",
  minHeight: "28rem",
  borderRight: "1px solid color-mix(in srgb, var(--line) 78%, transparent)",
  background: "color-mix(in srgb, var(--bg) 38%, var(--surface))",
  padding: "0.75rem",
};

const contentStyle = {
  display: "grid",
  alignContent: "start",
  gap: "0.8rem",
  minWidth: 0,
  overflowY: "auto",
  padding: "clamp(1rem, 2.2vw, 1.35rem)",
};

const titleRowStyle = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  gap: "1rem",
};

export function SettingsDialog({ open, username, onClose, onSignOut }) {
  const [activeSection, setActiveSection] = useState("general");

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  const currentSection = sections.find((section) => section.id === activeSection) || sections[0];

  return (
    <div style={overlayStyle} role="presentation" onMouseDown={onClose}>
      <section
        style={dialogStyle}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <aside className="settings-nav" style={navStyle} aria-label="Settings sections">
          {sections.map((section) => (
            <button
              key={section.id}
              type="button"
              className={`settings-nav-item ${currentSection.id === section.id ? "settings-nav-item-active" : ""}`}
              onClick={() => setActiveSection(section.id)}
            >
              <span className="settings-nav-label">{section.label}</span>
              <span className="settings-nav-description">{section.description}</span>
            </button>
          ))}
          <div style={{ marginTop: "auto", paddingTop: "0.75rem" }}>
            <button
              type="button"
              className="settings-nav-item"
              onClick={onSignOut}
              style={{ width: "100%", color: "var(--danger)" }}
            >
              <span className="settings-nav-label">Log out</span>
              <span className="settings-nav-description">End current session</span>
            </button>
          </div>
        </aside>

        <div className="settings-content" style={contentStyle}>
          <div className="settings-section-heading" style={titleRowStyle}>
            <div>
              <p className="eyebrow">{currentSection.label}</p>
              <h2 id="settings-dialog-title">{currentSection.description}</h2>
            </div>
            <button type="button" className="button-ghost" onClick={onClose}>Close</button>
          </div>

          {currentSection.id === "general" ? (
            <div className="settings-stack">
              <section className="settings-pane">
                <div className="settings-row">
                  <div>
                    <h3>Theme</h3>
                    <p className="muted">Choose a fixed theme or follow your device preference.</p>
                  </div>
                  <ThemeModePicker />
                </div>
              </section>

              <ModelPreferenceCard />

              <section className="settings-pane">
                <div className="settings-row settings-row-top">
                  <div>
                    <h3>Client safety</h3>
                    <p className="muted">Browser-side safeguards for rendering, sessions, cancellation, and stream errors.</p>
                  </div>
                </div>
                <ul className="check-list settings-check-list">
                  <li>Session state resets after expiry</li>
                  <li>Messages render through an element-only markdown renderer; raw HTML is never interpreted</li>
                  <li>Cancellation terminates the active request</li>
                  <li>Malformed stream frames surface controlled errors</li>
                </ul>
              </section>
            </div>
          ) : null}

          {currentSection.id === "account" ? (
            <div className="settings-stack">
              <section className="settings-pane">
                <div className="settings-row settings-row-top">
                  <div>
                    <h3>{username || "Current user"}</h3>
                    <p className="muted">Manage the active browser session.</p>
                  </div>
                  <button type="button" className="button-ghost" onClick={onSignOut}>Log out</button>
                </div>
              </section>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
