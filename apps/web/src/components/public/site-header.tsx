"use client";

import { Menu, Moon, Sun, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { LaunchDemoButton } from "@/components/public/launch-demo-button";
import { Button } from "@/components/ui/button";
import { sessionQueryOptions } from "@/lib/api";
import { publicNav } from "@/lib/public-site";
import { useTheme } from "@/components/theme-provider";

export function SiteHeader() {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();
  const session = useQuery(sessionQueryOptions);
  const [open, setOpen] = useState(false);
  const signedIn = session.isSuccess;

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur-md">
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-40 focus:rounded-md focus:bg-card focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight" onClick={() => setOpen(false)}>
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-sm text-primary-foreground">A</span>
          ATLAS
        </Link>
        <nav className="ml-4 hidden items-center gap-1 lg:flex" aria-label="Primary">
          {publicNav.map((item) => {
            const active = item.href.startsWith("/") && !item.href.includes("#") && pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-md px-3 py-2 text-sm ${active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground"}`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-2">
          <Button type="button" variant="ghost" size="icon" aria-label={theme === "dark" ? "Use light theme" : "Use dark theme"} onClick={toggleTheme}>
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </Button>
          <Button asChild variant="outline" className="hidden sm:inline-flex">
            <Link href={signedIn ? "/overview" : "/login"}>{signedIn ? "Open workspace" : "Sign in"}</Link>
          </Button>
          <LaunchDemoButton className="hidden sm:inline-flex" />
          <Button type="button" variant="outline" size="icon" className="lg:hidden" aria-expanded={open} aria-controls="public-menu" onClick={() => setOpen((value) => !value)}>
            {open ? <X size={16} /> : <Menu size={16} />}
            <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
          </Button>
        </div>
      </div>
      {open ? (
        <nav id="public-menu" className="border-t border-border px-4 py-3 lg:hidden" aria-label="Mobile">
          <ul className="grid gap-1">
            {publicNav.map((item) => (
              <li key={item.href}>
                <Link href={item.href} className="block rounded-md px-3 py-3 text-base hover:bg-accent" onClick={() => setOpen(false)}>
                  {item.label}
                </Link>
              </li>
            ))}
            <li>
              <Link href={signedIn ? "/overview" : "/login"} className="block rounded-md px-3 py-3 text-base hover:bg-accent" onClick={() => setOpen(false)}>
                {signedIn ? "Open workspace" : "Sign in"}
              </Link>
            </li>
            <li className="px-3 py-2">
              <LaunchDemoButton className="w-full" />
            </li>
          </ul>
        </nav>
      ) : null}
    </header>
  );
}
