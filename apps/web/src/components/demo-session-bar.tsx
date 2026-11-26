"use client";

import { useState } from "react";

import { ApiError, apiFetch, setCsrfToken } from "@/lib/api";
import { isDemoSession } from "@/lib/demo-session";
import type { AuthSession } from "@/lib/types";

export function useDemoRestart() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function restart() {
    setPending(true);
    setError(null);
    try {
      const started = await apiFetch<AuthSession>("/api/v1/demo/sessions/restart", {
        method: "POST",
      });
      setCsrfToken(started.csrf_token);
      window.location.assign("/overview");
    } catch (caught) {
      setPending(false);
      setError(caught instanceof ApiError ? caught.message : "The demonstration could not be restarted.");
    }
  }

  return { pending, error, restart };
}

export function DemoSessionBadge({ session }: { session: AuthSession }) {
  if (!isDemoSession(session)) {
    return null;
  }
  const expiry = session.demo_expires_at ? new Date(session.demo_expires_at) : null;
  const when =
    expiry && !Number.isNaN(expiry.getTime())
      ? expiry.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
      : null;
  return (
    <p className="hidden items-center gap-2 rounded-full border border-border bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground sm:flex">
      <span className="size-1.5 rounded-full bg-primary" aria-hidden="true" />
      Demonstration{when ? ` · until ${when}` : ""}
    </p>
  );
}
