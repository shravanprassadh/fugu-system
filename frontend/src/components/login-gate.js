"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";

import { getApiConfigurationProblem, loadProfile, login } from "../lib/api-client";
import { useStudioStore } from "./store";

const emptySubscribe = () => () => {};
const serverConfigurationProblem = () => null;

export function LoginGate() {
  const router = useRouter();
  // Evaluated after hydration so the server-rendered HTML stays consistent.
  const configurationProblem = useSyncExternalStore(
    emptySubscribe,
    getApiConfigurationProblem,
    serverConfigurationProblem,
  );
  const isAuthenticated = useStudioStore((state) => state.isAuthenticated);
  const setSession = useStudioStore((state) => state.setSession);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      router.replace("/chat");
    }
  }, [isAuthenticated, router]);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const sessionCredential = await login(username.trim(), password);
      const profile = await loadProfile(sessionCredential);
      setSession({
        sessionCredential,
        username: profile.username,
        userRole: profile.role,
        userId: profile.id,
      });
      router.push("/chat");
    } catch (requestError) {
      setError(requestError.message || "Authentication failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel" aria-labelledby="auth-title">
        <p className="auth-mark" aria-hidden="true">河豚</p>
        <h1 id="auth-title" className="auth-title">Fugu Studio</h1>
        <p className="auth-copy">
          Sign in to your workspace. This browser stays signed in until you sign out or remain inactive for 48 hours.
        </p>
        {configurationProblem ? (
          <p className="form-error config-error" role="alert">{configurationProblem}</p>
        ) : null}
        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="username">Username</label>
          <input
            id="username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button type="submit" className="button-primary" disabled={isSubmitting || Boolean(configurationProblem)}>
            {isSubmitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
