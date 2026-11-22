"use client";

import { useQuery } from "@tanstack/react-query";
import { Menu } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { SidebarNav } from "@/components/sidebar-nav";
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

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() ?? "").join("") || "A";
}

export function WorkspaceShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const session = useQuery(sessionQueryOptions);
  const [navOpen, setNavOpen] = useState(false);
  const [signOutOpen, setSignOutOpen] = useState(false);
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

  return (
    <div className="min-h-screen md:grid md:grid-cols-[240px_minmax(0,1fr)]">
      <aside className="hidden border-r border-border bg-background/80 md:block">
        <div className="sticky top-0 h-screen p-4">
          <SidebarNav />
        </div>
      </aside>
      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur md:px-6">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              aria-label="Open navigation"
              onClick={() => setNavOpen(true)}
            >
              <Menu className="size-4" />
            </Button>
            <p className="text-sm font-medium">{titleForPath(pathname)}</p>
          </div>
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
        </header>
        <main id="main" className="flex-1 px-4 py-6 md:px-8 md:py-8">
          {children}
        </main>
      </div>
      <Sheet open={navOpen} onOpenChange={setNavOpen}>
        <SheetContent aria-describedby={undefined}>
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <SidebarNav onNavigate={() => setNavOpen(false)} />
        </SheetContent>
      </Sheet>
      <SignOutDialog open={signOutOpen} onOpenChange={setSignOutOpen} />
    </div>
  );
}
