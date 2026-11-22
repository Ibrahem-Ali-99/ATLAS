"use client";

import { Button } from "@/components/ui/button";
import { DATA_SCOPES, type DataScope } from "@/lib/provenance";

export function DataScopeControl({
  value,
  onChange,
}: {
  value: DataScope;
  onChange: (scope: DataScope) => void;
}) {
  return (
    <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Data scope">
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
}
