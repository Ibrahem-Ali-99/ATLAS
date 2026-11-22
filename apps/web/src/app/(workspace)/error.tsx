"use client";

import { Button } from "@/components/ui/button";

export default function WorkspaceError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-lg rounded-xl border border-border bg-card p-6">
      <h1 className="text-lg font-semibold">This page failed to render</h1>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        {error.message || "An unexpected rendering error occurred."}
      </p>
      <Button className="mt-4" onClick={() => reset()}>
        Try again
      </Button>
    </div>
  );
}
