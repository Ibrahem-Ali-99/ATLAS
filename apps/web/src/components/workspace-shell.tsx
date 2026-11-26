"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Menu, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { SidebarNav } from "@/components/sidebar-nav";
import { WorkspaceSearch } from "@/components/workspace-search";
import { SignOutDialog } from "@/components/sign-out-dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, sessionQueryOptions } from "@/lib/api";
import { titleForPath } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { WorkspaceProvider, useWorkspace } from "@/lib/use-workspace";
import { useTheme } from "@/components/theme-provider";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() ?? "").join("") || "A";
}

export function WorkspaceShell({ children }: { children: ReactNode }) {
  return <WorkspaceProvider><WorkspaceShellContent>{children}</WorkspaceShellContent></WorkspaceProvider>;
}

function WorkspaceShellContent({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const session = useQuery(sessionQueryOptions);
  const [navOpen, setNavOpen] = useState(false);
  const [signOutOpen, setSignOutOpen] = useState(false);
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
      <div className="flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-sm space-y-3">
          <Skeleton className="h-8 w-32" />
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
  const immersive = pathname === "/assistant";

  return (
    <div className={cn("min-h-screen bg-background md:grid", collapsed ? "md:grid-cols-[68px_minmax(0,1fr)]" : "md:grid-cols-[240px_minmax(0,1fr)]")}>
      <aside className="hidden border-r border-border bg-sidebar md:block">
        <div className="sticky top-0 flex h-screen flex-col">
          <SidebarNav organizationName={organizationName} collapsed={collapsed} onToggleCollapse={() => setCollapsed((value) => !value)} />
        </div>
      </aside>
      <div className="flex min-h-screen min-w-0 flex-col">
        <header className="sticky top-0 z-20 flex h-[60px] shrink-0 items-center justify-between gap-2 border-b border-border bg-card/95 px-3 backdrop-blur md:px-7">
          <div className="flex min-w-0 items-center gap-1.5">
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              aria-label="Open navigation"
              onClick={() => setNavOpen(true)}
            >
              <Menu className="size-4" />
            </Button>
            <p aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
              <span className="hidden max-w-44 truncate md:inline">{organizationName ?? "ATLAS"}</span>
              <ChevronRight className="hidden size-3 shrink-0 md:block" aria-hidden="true" />
              <span className="truncate font-medium text-foreground">{titleForPath(pathname)}</span>
            </p>
          </div>
          {workspace.memberships.length > 1 ? (
            <label className="sr-only" htmlFor="organization-selector">Organization</label>
          ) : null}
          {workspace.memberships.length > 1 ? (
            <select
              id="organization-selector"
              aria-label="Organization"
              value={workspace.organizationId ?? ""}
              onChange={(event) => workspace.setOrganizationId(event.target.value)}
              className="min-w-0 max-w-24 rounded-md border border-border bg-background px-1.5 py-1 text-xs sm:max-w-48 sm:px-2"
            >
              {workspace.memberships.map((membership) => <option key={membership.organization_id} value={membership.organization_id}>{membership.organization_name}</option>)}
            </select>
          ) : null}
          <div className="flex shrink-0 items-center gap-1">
            <WorkspaceSearch />
            <Button variant="ghost" size="icon" onClick={theme.toggleTheme} aria-label={`Switch to ${theme.theme === "dark" ? "light" : "dark"} theme`} title={`Switch to ${theme.theme === "dark" ? "light" : "dark"} theme`}>
              {theme.theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                className="flex items-center gap-3 rounded-md px-2 py-1 text-left hover:bg-accent"
              >
                <span className="flex size-8 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
                  {initials(user.full_name)}
                </span>
                <span className="hidden max-w-48 sm:block">
                  <span className="block truncate text-sm font-medium">{user.full_name}</span>
                  <span className="block truncate text-xs text-muted-foreground">{user.email}</span>
                </span>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>{user.email}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild><Link href="/settings#settings-account">Profile and preferences</Link></DropdownMenuItem>
              <DropdownMenuItem asChild><Link href="/settings">Workspace settings</Link></DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={(event) => {
                  event.preventDefault();
                  setSignOutOpen(true);
                }}
              >
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          </div>
        </header>
        <main
          id="main"
          className={
            immersive
              ? "h-[calc(100dvh-60px)] min-w-0 overflow-hidden"
              : "min-w-0 flex-1 overflow-x-hidden px-4 py-6 md:px-8 md:py-8"
          }
        >
          {children}
        </main>
      </div>
      <Sheet open={navOpen} onOpenChange={setNavOpen}>
        <SheetContent aria-describedby={undefined}>
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <SidebarNav organizationName={organizationName} onNavigate={() => setNavOpen(false)} />
        </SheetContent>
      </Sheet>
      <SignOutDialog open={signOutOpen} onOpenChange={setSignOutOpen} />
    </div>
  );
}
