"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { navigationGroups } from "@/lib/navigation";
import { cn } from "@/lib/utils";

export function SidebarNav({
  organizationName,
  onNavigate,
}: {
  organizationName?: string | null;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col">
      <div className="px-2 py-1">
        <div className="flex items-center gap-3">
          <div className="flex size-8 items-center justify-center rounded-md bg-primary text-xs font-semibold text-primary-foreground">
            A
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold tracking-tight">ATLAS</p>
            <p className="truncate text-xs text-muted-foreground">{organizationName ?? "Operations"}</p>
          </div>
        </div>
      </div>
      <nav className="mt-6 flex flex-1 flex-col gap-6" aria-label="Workspace">
        {navigationGroups.map((group) => (
          <div key={group.label}>
            <p className="px-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
              {group.label}
            </p>
            <div className="mt-2 flex flex-col gap-0.5">
              {group.items.map((item) => {
                const active = pathname === item.href;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    onClick={onNavigate}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
                      active && "bg-accent text-foreground",
                    )}
                  >
                    <Icon className="size-4 shrink-0" aria-hidden="true" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </div>
  );
}
