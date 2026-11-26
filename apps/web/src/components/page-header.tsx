import type { ReactNode } from "react";

export function PageHeader({
  title,
  eyebrow,
  actions,
  children,
}: {
  title: string;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-5 border-b border-border pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-3xl">
        {eyebrow ? (
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.07em] text-muted-foreground">{eyebrow}</p>
        ) : null}
        <h1 className="text-2xl font-semibold tracking-[-0.03em] text-foreground sm:text-[1.75rem]">{title}</h1>
        <p className="mt-1.5 max-w-2xl text-[13px] leading-5 text-muted-foreground">{children}</p>
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}
