"use client";

import { DATA_SCOPES, type DataScope } from "@/lib/provenance";

export function DataScopeControl({
  value,
  onChange,
}: {
  value: DataScope;
  onChange: (scope: DataScope) => void;
  advanced?: boolean;
}) {
  return (
    <label className="grid gap-1 text-sm">
      Records
      <select
        aria-label="Records"
        className="h-9 rounded-md border border-border bg-background px-2"
        value={value}
        onChange={(event) => onChange(event.target.value as DataScope)}
      >
        {DATA_SCOPES.map((item) => (
          <option key={item.id} value={item.id}>{item.label}</option>
        ))}
      </select>
    </label>
  );
}
