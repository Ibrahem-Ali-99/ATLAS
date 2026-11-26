"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, apiFetch, setCsrfToken } from "@/lib/api";
import { isDemoSession } from "@/lib/demo-session";
import type { AuthSession } from "@/lib/types";

export function DemoSessionBar({ session }: { session: AuthSession }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!isDemoSession(session)) {
    return null;
  }
  const expiry = session.demo_expires_at ? new Date(session.demo_expires_at) : null;
  const when =
    expiry && !Number.isNaN(expiry.getTime())
      ? expiry.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
      : null;

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
      setError(caught instanceof ApiError ? caught.message : "The demo could not be restarted.");
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-primary/10 px-4 py-2 text-sm md:px-7">
      <p className="max-w-3xl leading-6">
        Harbor & Co. is a fictional demonstration. Messages, payments, and credentials stay inside
        this session, and integrations are simulated.
        {when ? ` This session ends at ${when}.` : " This session is short-lived."}
      </p>
      <div className="flex items-center gap-3">
        {error ? (
          <span role="alert" className="text-xs text-destructive">
            {error}
          </span>
        ) : null}
        <Button type="button" size="sm" variant="outline" disabled={pending} onClick={() => void restart()}>
          {pending ? "Restarting…" : "Restart demonstration"}
        </Button>
      </div>
    </div>
  );
}
