import type { ReactNode } from "react";

export function PageHeader({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{children}</p>
    </div>
  );
}
