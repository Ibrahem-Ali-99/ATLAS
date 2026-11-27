"use client";

import { useState } from "react";

import { ApiError, apiFetch, setCsrfToken } from "@/data/client";
import type { Session } from "@/data/session";

export function LaunchDemo({ label = "Open the workspace" }: { label?: string }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function launch() {
    setPending(true);
    setError("");
    try {
      const started = await apiFetch<Session>("/api/v1/demo/sessions", { method: "POST" });
      setCsrfToken(started.csrf_token);
      window.location.assign("/login");
    } catch (caught) {
      setPending(false);
      setError(caught instanceof ApiError ? caught.message : "The demo could not be started.");
    }
  }

  return (
    <div>
      <button type="button" className="site-button" disabled={pending} onClick={() => void launch()}>
        {pending ? "Starting…" : label}
      </button>
      {error ? <p className="site-alert" role="alert">{error}</p> : null}
    </div>
  );
}
