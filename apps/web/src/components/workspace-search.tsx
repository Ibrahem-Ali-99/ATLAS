"use client";

import { Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { navigation } from "@/lib/navigation";

export function WorkspaceSearch() {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  function changeOpen(next: boolean) {
    setOpen(next);
    if (!next) setSearch("");
  }
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== "k" || !(event.metaKey || event.ctrlKey) || event.altKey) return;
      event.preventDefault();
      setOpen(true);
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  const items = navigation.filter(({ label }) => label.toLowerCase().includes(search.trim().toLowerCase()));

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" className="h-8 gap-2 px-2 text-xs text-muted-foreground lg:min-w-44 lg:justify-start" aria-label="Search workspace" aria-keyshortcuts="Control+K Meta+K">
          <Search className="size-4" aria-hidden="true" />
          <span className="hidden lg:block">Search workspace</span>
          <kbd className="ml-auto hidden rounded border border-border px-1 text-[10px] xl:block">Ctrl K</kbd>
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[75dvh] overflow-y-auto">
        <DialogTitle>Search workspace</DialogTitle>
        <DialogDescription className="mt-1">Find a workspace page.</DialogDescription>
        <Input aria-label="Find a page" placeholder="Search pages…" value={search} onChange={(event) => setSearch(event.target.value)} className="mt-4" />
        {items.length ? (
          <ul className="mt-3 space-y-0.5">
            {items.map(({ href, label, icon: Icon }) => (
              <li key={href}>
                <DialogClose asChild>
                  <Link href={href} className="flex items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-accent focus-visible:bg-accent">
                    <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
                    {label}
                  </Link>
                </DialogClose>
              </li>
            ))}
          </ul>
        ) : <p className="mt-3 text-sm text-muted-foreground" role="status">No matching pages.</p>}
      </DialogContent>
    </Dialog>
  );
}
