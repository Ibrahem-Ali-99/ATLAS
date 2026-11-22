"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";

export function ConfirmButton({
  label,
  confirmLabel,
  pendingLabel,
  pending,
  onConfirm,
  size = "default",
}: {
  label: string;
  confirmLabel: string;
  pendingLabel: string;
  pending: boolean;
  onConfirm: () => void;
  size?: "default" | "sm";
}) {
  const [armed, setArmed] = useState(false);
  if (!armed) {
    return (
      <Button type="button" size={size} variant="outline" onClick={() => setArmed(true)}>
        {label}
      </Button>
    );
  }
  return (
    <span className="inline-flex flex-wrap gap-2">
      <Button type="button" size={size} variant="outline" disabled={pending} onClick={onConfirm}>
        {pending ? pendingLabel : confirmLabel}
      </Button>
      <Button type="button" size={size} variant="ghost" disabled={pending} onClick={() => setArmed(false)}>
        Cancel
      </Button>
    </span>
  );
}
