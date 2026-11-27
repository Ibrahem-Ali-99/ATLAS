"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown, ChevronRight, X } from "lucide-react";

import { listAgentRuns, listApprovals } from "@/lib/agent-api";
import { listInbox } from "@/lib/inbox";
import { navigationGroups } from "@/lib/navigation";
import { cn } from "@/lib/utils";

function mark(name: string): string {
  const letters = name.trim().split(/\s+/).filter((part) => /[A-Za-z0-9]/.test(part[0] ?? "")).slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("");
  return letters || "AT";
}

export function SidebarNav({
  organizationName,
  memberships,
  organizationId,
  onOrganizationChange,
  onNavigate,
  collapsed = false,
  onToggleCollapse,
  onClose,
  demo = false,
}: {
  organizationName?: string | null;
  memberships?: { organization_id: string; organization_name: string }[];
  organizationId?: string | null;
  onOrganizationChange?: (organizationId: string) => void;
  onNavigate?: () => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  onClose?: () => void;
  demo?: boolean;
}) {
  const pathname = usePathname();
  const groups = navigationGroups;
  const inbox = useQuery({ queryKey: ["nav-inbox-count", organizationId], queryFn: () => listInbox(organizationId ?? ""), enabled: Boolean(organizationId) });
  const pendingApprovals = useQuery({ queryKey: ["nav-approvals-count", organizationId], queryFn: () => listApprovals(organizationId ?? "", { status: "pending" }), enabled: Boolean(organizationId) });
  const running = useQuery({ queryKey: ["nav-runs-count", organizationId], queryFn: () => listAgentRuns(organizationId ?? "", { status: "running" }), enabled: Boolean(organizationId) });
  const counts: Record<string, number> = {
    "/inbox": (inbox.data ?? []).reduce((sum, item) => sum + item.unread_count, 0),
    "/approvals": pendingApprovals.data?.total ?? 0,
    "/agent-runs": running.data?.total ?? 0,
  };
  const orgs = memberships ?? [];
  const current = organizationName ?? "ATLAS";

  return (
    <>
      <div className="brand-row">
        <div className="brand-mark" aria-hidden="true">A</div>
        {!collapsed ? <span className="brand-name">ATLAS</span> : null}
        {onClose ? (
          <button type="button" className="button button-ghost button-icon sidebar-close" aria-label="Close navigation" onClick={onClose}>
            <X size={18} />
          </button>
        ) : null}
      </div>
      <div className="org-wrap">
        <label className={cn("org-switcher", collapsed && "justify-center")}>
          <span className="org-logo" aria-hidden="true">{mark(current)}</span>
          {!collapsed ? (
            <span className="org-copy">
              <select
                aria-label="Organization"
                value={organizationId ?? ""}
                onChange={(event) => onOrganizationChange?.(event.target.value)}
                disabled={orgs.length < 2}
              >
                {orgs.length === 0 ? <option value={organizationId ?? ""}>{current}</option> : null}
                {orgs.map((membership) => (
                  <option key={membership.organization_id} value={membership.organization_id}>{membership.organization_name}</option>
                ))}
              </select>
              <small>Primary organization</small>
            </span>
          ) : null}
          {!collapsed ? <ChevronDown size={15} aria-hidden="true" /> : null}
        </label>
      </div>
      <nav className="sidebar-nav" aria-label="Primary navigation">
        {groups.map((group) => (
          <div key={group.label}>
            {!collapsed ? <p className="nav-section">{group.label}</p> : null}
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
                  className={cn("nav-item", active && "nav-item-active")}
                >
                  <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
                  {!collapsed ? <span>{item.label}</span> : null}
                  {!collapsed && counts[item.href] !== undefined ? <span className="nav-count">{counts[item.href]}</span> : null}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="sidebar-footer">
        {onToggleCollapse ? (
          <button type="button" className="collapse-button" onClick={onToggleCollapse} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            <ChevronRight size={16} className={collapsed ? "" : "rotate-180"} />
            {!collapsed ? <span>Collapse sidebar</span> : null}
          </button>
        ) : null}
      </div>
    </>
  );
}
