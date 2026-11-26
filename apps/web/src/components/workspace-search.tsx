"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useEffect, useState } from "react";

import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { navigation } from "@/lib/navigation";
import { listCompanies, listContacts, listLeads } from "@/lib/records-api";
import { useWorkspace } from "@/lib/use-workspace";

type Hit = { href: string; label: string; kind: string };

export function WorkspaceSearch() {
  const { organizationId } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const typed = search.trim();
  const deferred = useDeferredValue(typed);
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
  const pages = navigation.filter(({ label }) => label.toLowerCase().includes(typed.toLowerCase()));
  const records = useQuery({
    queryKey: ["workspace-search", organizationId, deferred],
    enabled: open && Boolean(organizationId) && deferred.length >= 2,
    queryFn: async (): Promise<Hit[]> => {
      const id = organizationId ?? "";
      const [companies, contacts, leads] = await Promise.all([
        listCompanies(id, { q: deferred, pageSize: 5 }),
        listContacts(id, { q: deferred, pageSize: 5 }),
        listLeads(id, { q: deferred, pageSize: 5 }),
      ]);
      return [
        ...companies.items.map((item) => ({ href: `/crm?tab=companies&id=${item.id}`, label: item.name, kind: "Company" })),
        ...contacts.items.map((item) => ({ href: `/crm?tab=contacts&id=${item.id}`, label: item.full_name, kind: "Contact" })),
        ...leads.items.map((item) => ({ href: `/crm?tab=leads&id=${item.id}`, label: item.title, kind: "Lead" })),
      ];
    },
  });
  const hits = deferred === typed ? records.data ?? [] : [];
  const waiting = deferred.length >= 2 && (deferred !== typed || records.isFetching) && hits.length === 0;

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogTrigger asChild>
        <button type="button" className="command-search" aria-label="Search workspace" aria-keyshortcuts="Control+K Meta+K">
          <Search size={15} aria-hidden="true" />
          <span>Search workspace</span>
          <kbd>Ctrl K</kbd>
        </button>
      </DialogTrigger>
      <DialogContent className="max-h-[75dvh] overflow-y-auto">
        <DialogTitle>Search workspace</DialogTitle>
        <DialogDescription className="mt-1">Find a page or a company, contact, or lead in this workspace.</DialogDescription>
        <Input aria-label="Find a page" placeholder="Search pages and records…" value={search} onChange={(event) => setSearch(event.target.value)} className="mt-4" />
        {pages.length ? (
          <ul className="mt-3 space-y-0.5">
            {pages.map(({ href, label, icon: Icon }) => (
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
        ) : null}
        {hits.length ? (
          <ul className="mt-3 space-y-0.5">
            {hits.map((hit) => (
              <li key={`${hit.kind}-${hit.href}`}>
                <DialogClose asChild>
                  <Link href={hit.href} className="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm hover:bg-accent focus-visible:bg-accent">
                    <span>{hit.label}</span>
                    <span className="text-xs text-muted-foreground">{hit.kind}</span>
                  </Link>
                </DialogClose>
              </li>
            ))}
          </ul>
        ) : null}
        {waiting ? <p className="mt-3 text-sm text-muted-foreground" role="status">Searching records…</p> : null}
        {!waiting && typed.length > 0 && pages.length === 0 && hits.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground" role="status">No matching records.</p>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
