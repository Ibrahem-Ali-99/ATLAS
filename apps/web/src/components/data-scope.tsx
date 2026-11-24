"use client";

import { Button } from "@/components/ui/button";
import { DATA_SCOPES, type DataScope } from "@/lib/provenance";

export function DataScopeControl({
  value,
  onChange,
  advanced = false,
}: {
  value: DataScope;
  onChange: (scope: DataScope) => void;
  advanced?: boolean;
}) {
  const controls = (
    <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Advanced data scope">
      {DATA_SCOPES.map((item) => (
        <Button
          key={item.id}
          type="button"
          size="sm"
          variant={value === item.id ? "default" : "outline"}
          aria-pressed={value === item.id}
          onClick={() => onChange(item.id)}
        >
          {item.label}
        </Button>
      ))}
    </div>
  );
  if (!advanced) return controls;
  return (
    <details className="mt-4 max-w-xl rounded-md border border-border/70 px-3 py-2">
      <summary className="cursor-pointer text-xs text-muted-foreground">Advanced data filters</summary>
      {controls}
    </details>
  );
}
