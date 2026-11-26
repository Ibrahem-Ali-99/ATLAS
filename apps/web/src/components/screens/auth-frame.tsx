"use client";

import { Moon, Sun } from "lucide-react";
import type { ReactNode } from "react";

import { useTheme } from "@/components/theme-provider";
import { Button } from "@/components/ui/button";

export function AuthFrame({ title, description, icon, children }: {
  title: string;
  description: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  const { theme, toggleTheme } = useTheme();

  return (
    <main className="grid min-h-dvh grid-rows-[auto_1fr] bg-background">
      <header className="flex items-center justify-between border-b border-border bg-card px-5 py-4 sm:px-8">
        <div className="flex items-center gap-2.5 font-semibold tracking-[0.12em]">
          <span aria-hidden className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground">A</span>
          ATLAS
        </div>
        <Button size="icon" variant="ghost" aria-label="Toggle light and dark theme" onClick={toggleTheme}>
          {theme === "dark" ? <Sun size={16} aria-hidden /> : <Moon size={16} aria-hidden />}
        </Button>
      </header>
      <div className="grid place-items-center px-4 py-10">
        <section aria-labelledby="auth-title" className="w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-sm sm:p-8">
          <div aria-hidden className="mb-4 grid size-11 place-items-center rounded-lg bg-accent text-accent-foreground">{icon}</div>
          <h1 id="auth-title" className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
          {children}
        </section>
      </div>
    </main>
  );
}
