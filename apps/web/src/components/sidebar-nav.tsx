"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown, ChevronRight, X } from "lucide-react";

import { navigationGroups } from "@/lib/navigation";
import { cn } from "@/lib/utils";

const demoHidden = new Set(["/billing", "/settings", "/setup"]);

function mark(name: string): string {
  const letters = name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("");
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
  const groups = demo
    ? navigationGroups
        .map((group) => ({ ...group, items: group.items.filter((item) => !demoHidden.has(item.href)) }))
        .filter((group) => group.items.length > 0)
    : navigationGroups;
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
              <small>{demo ? "Demonstration" : "Workspace"}</small>
            </span>
          ) : null}
          {!collapsed ? <ChevronDown size={15} aria-hidden="true" /> : null}
        </label>
      </div>
      <nav className="sidebar-nav" aria-label="Workspace">
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
