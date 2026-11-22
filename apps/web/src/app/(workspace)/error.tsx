"use client";

import { useEffect, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { isStaleChunkError } from "@/lib/chunk-error";

const RELOAD_KEY = "atlas-chunk-reload";

function chunkReloadExhausted(): boolean {
  return window.sessionStorage.getItem(RELOAD_KEY) === "1";
}

export default function WorkspaceError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const staleChunk = isStaleChunkError(error);
  const exhausted = useSyncExternalStore(() => () => undefined, chunkReloadExhausted, () => false);

  useEffect(() => {
    if (!staleChunk || exhausted) {
      return;
    }
    window.sessionStorage.setItem(RELOAD_KEY, "1");
    window.location.reload();
  }, [exhausted, staleChunk]);

  return (
    <div className="mx-auto max-w-lg rounded-xl border border-border bg-card p-6">
      <h1 className="text-lg font-semibold">This page failed to render</h1>
      {staleChunk ? (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {exhausted
            ? "The page asked for a JavaScript file this web server does not have. Rebuilds do not update a running next start process. Restart the web server, then reload."
            : "Loading the current page bundle."}
        </p>
      ) : (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {error.message || "An unexpected rendering error occurred."}
        </p>
      )}
      <Button
        className="mt-4"
        onClick={() => {
          window.sessionStorage.removeItem(RELOAD_KEY);
          reset();
        }}
      >
        Try again
      </Button>
    </div>
  );
}
