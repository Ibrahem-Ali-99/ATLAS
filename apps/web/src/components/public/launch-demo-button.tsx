"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, apiFetch, sessionQueryOptions, setCsrfToken } from "@/lib/api";
import { isDemoSession } from "@/lib/demo-session";
import type { AuthSession } from "@/lib/types";
import { cn } from "@/lib/utils";

export function LaunchDemoButton({
  size = "default",
  className,
  label = "Launch interactive demo",
}: {
  size?: "default" | "sm" | "lg";
  className?: string;
  label?: string;
}) {
  const session = useQuery(sessionQueryOptions);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const demo = isDemoSession(session.data);
  let text = label;
  if (pending) {
    text = "Starting the demo…";
  } else if (demo) {
    text = "Open interactive demo";
  }

  async function launch() {
    if (demo) {
      window.location.assign("/overview");
      return;
    }
    if (session.isSuccess) {
      const confirmed = window.confirm(
        "Starting the interactive demo signs this browser out of the current workspace. Continue?",
      );
      if (!confirmed) {
        return;
      }
    }
    setPending(true);
    setError(null);
    try {
      const started = await apiFetch<AuthSession>("/api/v1/demo/sessions", { method: "POST" });
      setCsrfToken(started.csrf_token);
      window.location.assign("/overview");
    } catch (caught) {
      setPending(false);
      setError(caught instanceof ApiError ? caught.message : "The demo could not be started.");
    }
  }

  return (
    <span className={cn("inline-flex flex-col items-start gap-1", className)}>
      <Button
        type="button"
        size={size}
        className="w-full"
        disabled={pending || session.isPending}
        onClick={() => void launch()}
      >
        {text}
      </Button>
      {error ? (
        <span role="alert" className="max-w-xs text-xs text-destructive">
          {error}
        </span>
      ) : null}
    </span>
  );
}
