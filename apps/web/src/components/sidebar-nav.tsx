"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { navigationGroups } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

export function SidebarNav({
  organizationName,
  onNavigate,
  collapsed = false,
  onToggleCollapse,
}: {
  organizationName?: string | null;
  onNavigate?: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}) {
  const pathname = usePathname();

  return (
    <div className={cn("flex h-full flex-col bg-sidebar text-foreground", collapsed ? "items-center" : "")}>
      <div className={cn("flex h-[60px] w-full shrink-0 items-center gap-2.5 border-b border-border", collapsed ? "justify-center" : "px-4")}>
        <span className="grid size-7 shrink-0 place-items-center rounded-md bg-primary text-xs font-bold text-primary-foreground" aria-label="ATLAS">A</span>
        {!collapsed ? <span className="text-sm font-bold tracking-[0.16em]">ATLAS</span> : null}
      </div>
      <div className={cn("mx-2.5 mt-3 flex min-h-11 shrink-0 items-center rounded-md px-2", collapsed ? "justify-center" : "gap-2.5")}>
        <span className="grid size-7 shrink-0 place-items-center rounded-md bg-foreground text-[10px] font-bold text-background">{(organizationName ?? "AT").slice(0, 2).toUpperCase()}</span>
        {!collapsed ? <div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold">{organizationName ?? "ATLAS"}</p><p className="mt-0.5 truncate text-[10px] text-muted-foreground">Workspace</p></div> : null}
      </div>
      <nav className="mt-3 flex w-full flex-1 flex-col gap-4 overflow-y-auto px-2.5 pb-3" aria-label="Workspace">
        {navigationGroups.map((group) => (
          <div key={group.label} className="flex flex-col gap-1">
            {!collapsed ? <p className="px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{group.label}</p> : null}
            <div className="flex flex-col gap-1">
              {group.items.map((item) => {
                const active = pathname === item.href || (item.href !== "/overview" && pathname.startsWith(`${item.href}/`));
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    onClick={onNavigate}
                    title={collapsed ? item.label : undefined}
                    className={cn(
                      "flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
                      collapsed && "justify-center px-0",
                      active && "bg-accent font-medium text-accent-foreground hover:bg-accent",
                    )}
                  >
                    <Icon className="size-4 shrink-0" aria-hidden="true" />
                    {!collapsed ? <span className="truncate">{item.label}</span> : null}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
      <div className={cn("w-full border-t border-border px-2.5 py-2", collapsed ? "flex justify-center" : "")}>
        {onToggleCollapse ? <button type="button" onClick={onToggleCollapse} className="flex h-8 w-full items-center gap-2 rounded-md px-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? <PanelLeftOpen className="size-4" /> : <><PanelLeftClose className="size-4" /><span>Collapse sidebar</span></>}
        </button> : null}
      </div>
    </div>
  );
}
