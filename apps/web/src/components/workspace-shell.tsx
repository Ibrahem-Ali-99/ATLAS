"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Menu, Moon, Settings, Sun, Users } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { DemoSessionBadge, useDemoRestart } from "@/components/demo-session-bar";
import { SidebarNav } from "@/components/sidebar-nav";
import { WorkspaceSearch } from "@/components/workspace-search";
import { SignOutDialog } from "@/components/sign-out-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, sessionQueryOptions } from "@/lib/api";
import { isDemoSession } from "@/lib/demo-session";
import { titleForPath } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { WorkspaceProvider, useWorkspace } from "@/lib/use-workspace";
import { useTheme } from "@/components/theme-provider";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() ?? "").join("") || "A";
}

function mainClass(pathname: string): string {
  if (pathname.startsWith("/assistant")) return "assistant-main";
  if (pathname.startsWith("/inbox")) return "inbox-main";
  if (pathname.startsWith("/crm")) return "crm-main";
  if (pathname.startsWith("/knowledge")) return "knowledge-main";
  if (pathname.startsWith("/approvals") || pathname.startsWith("/agent-runs")) return "operations-main";
  if (pathname.startsWith("/workflows")) return "workflows-main";
  if (pathname.startsWith("/analytics")) return "analytics-main";
  if (pathname.startsWith("/campaigns")) return "campaigns-main";
  if (pathname.startsWith("/monitoring")) return "monitoring-main";
  if (pathname.startsWith("/integrations")) return "integrations-main";
  if (pathname.startsWith("/billing")) return "billing-main";
  if (pathname.startsWith("/settings") || pathname.startsWith("/setup")) return "settings-main";
  return "";
}

export function WorkspaceShell({ children }: { children: ReactNode }) {
  return <WorkspaceProvider><WorkspaceShellContent>{children}</WorkspaceShellContent></WorkspaceProvider>;
}

function WorkspaceShellContent({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const session = useQuery(sessionQueryOptions);
  const [navOpen, setNavOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [signOutOpen, setSignOutOpen] = useState(false);
  const demoRestart = useDemoRestart();
  const [collapsed, setCollapsed] = useState(false);
  const workspace = useWorkspace();
  const theme = useTheme();
  const unauthenticated = session.error instanceof ApiError && session.error.status === 401;

  useEffect(() => {
    if (unauthenticated) {
      router.replace("/login");
    }
  }, [router, unauthenticated]);

  if (session.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6" role="status">
        <div className="w-full max-w-sm space-y-3">
          <p className="text-sm font-medium text-foreground">Loading your workspace</p>
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      </div>
    );
  }

  if (unauthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <p className="text-sm text-muted-foreground">Redirecting to sign in…</p>
      </div>
    );
  }

  if (session.isError || !session.data) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="max-w-md space-y-4 rounded-xl border border-border bg-card p-6">
          <h1 className="text-lg font-semibold">Workspace unavailable</h1>
          <p className="text-sm leading-6 text-muted-foreground">
            {session.error instanceof Error
              ? session.error.message
              : "The session request failed."}
          </p>
          <Button onClick={() => session.refetch()}>Try again</Button>
        </div>
      </div>
    );
  }

  const user = session.data.user;
  const organizationName = workspace.organizationName;
  const demo = isDemoSession(session.data);
  const accountName = user.full_name;
  const accountDetail = demo ? "Demonstration" : user.email;
  const crumb = titleForPath(pathname);

  return (
    <div className={cn("app-shell", collapsed && "sidebar-collapsed")}>
      <a href="#main" className="sr-only">Skip to content</a>
      {navOpen ? <button type="button" className="mobile-backdrop" aria-label="Close navigation" onClick={() => setNavOpen(false)} /> : null}
      <aside className={cn("sidebar", collapsed && "sidebar-collapsed", navOpen && "sidebar-mobile-open")}>
        <SidebarNav
          organizationName={organizationName}
          memberships={workspace.memberships}
          organizationId={workspace.organizationId}
          onOrganizationChange={workspace.setOrganizationId}
          collapsed={collapsed}
          demo={demo}
          onToggleCollapse={() => setCollapsed((value) => !value)}
          onClose={() => setNavOpen(false)}
          onNavigate={() => setNavOpen(false)}
        />
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div className="topbar-left">
            <button type="button" className="button button-ghost button-icon mobile-menu" aria-label="Open navigation" onClick={() => { setCollapsed(false); setNavOpen(true); }}>
              <Menu size={19} />
            </button>
            <div className="breadcrumbs" aria-label="Breadcrumb">
              <span>{organizationName ?? "ATLAS"}</span>
              <ChevronRight size={13} aria-hidden="true" />
              <strong>{crumb}</strong>
            </div>
            <DemoSessionBadge session={session.data} />
          </div>
          <div className="topbar-actions">
            <WorkspaceSearch />
            <button type="button" className="button button-ghost button-icon" onClick={theme.toggleTheme} aria-label={`Switch to ${theme.theme === "dark" ? "light" : "dark"} theme`}>
              {theme.theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <div className="profile-wrap">
              <button type="button" className="profile-button" aria-label="Open profile menu" aria-expanded={profileOpen} onClick={() => setProfileOpen((value) => !value)}>
                <span className="avatar avatar-blue avatar-sm">{initials(accountName)}</span>
                <ChevronDown size={13} />
              </button>
              {profileOpen ? (
                <div className="menu profile-menu">
                  <div className="profile-summary">
                    <span className="avatar avatar-blue avatar-sm">{initials(accountName)}</span>
                    <span><strong>{accountName}</strong><small>{accountDetail}</small></span>
                  </div>
                  <div className="menu-separator" />
                  {demo ? (
                    <button type="button" disabled={demoRestart.pending} onClick={() => void demoRestart.restart()}>
                      <span>{demoRestart.pending ? "Restarting…" : "Restart demonstration"}</span>
                    </button>
                  ) : (
                    <>
                      <Link href="/settings#settings-account" onClick={() => setProfileOpen(false)}><Users size={16} /><span>Profile and preferences</span></Link>
                      <Link href="/settings" onClick={() => setProfileOpen(false)}><Settings size={16} /><span>Workspace settings</span></Link>
                    </>
                  )}
                  {demo && demoRestart.error ? <p role="alert" className="px-2 py-1 text-xs text-destructive">{demoRestart.error}</p> : null}
                  <div className="menu-separator" />
                  <button type="button" onClick={() => { setProfileOpen(false); setSignOutOpen(true); }}><span>Sign out</span></button>
                </div>
              ) : null}
            </div>
          </div>
        </header>
        <main id="main" className={mainClass(pathname)}>{children}</main>
      </div>
      <SignOutDialog open={signOutOpen} onOpenChange={setSignOutOpen} />
    </div>
  );
}
