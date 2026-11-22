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
    <div className="flex h-full flex-col px-3 py-7">
      <p className="px-2 text-[22px] leading-none text-foreground">ATLAS</p>
      <p className="mt-3 px-2 text-[10px] uppercase tracking-[0.16em] text-subtle">
        {organizationName ?? "Business operations"}
      </p>
      <nav className="mt-8 flex flex-1 flex-col gap-7" aria-label="Workspace">
        {navigationGroups.map((group) => (
          <div key={group.label} className="flex flex-col gap-1">
            <div className="flex flex-col">
              {group.items.map((item) => {
                const active = pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    onClick={onNavigate}
                    className={cn(
                      "flex h-10 items-center rounded-[10px] px-4 text-sm text-muted-foreground transition-colors hover:bg-accent/70 hover:text-foreground",
                      active && "bg-accent text-foreground hover:bg-accent",
                    )}
                  >
                    {item.label}
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
