"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { CompaniesPanel } from "@/components/crm/companies-panel";
import { ContactsPanel } from "@/components/crm/contacts-panel";
import { InquiriesPanel } from "@/components/crm/inquiries-panel";
import { LeadsPanel } from "@/components/crm/leads-panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/use-workspace";

const tabs = [
  { id: "companies", label: "Companies" },
  { id: "contacts", label: "Contacts" },
  { id: "leads", label: "Leads" },
  { id: "inquiries", label: "Inquiries" },
] as const;

type TabId = (typeof tabs)[number]["id"];

export function CrmScreen() {
  const { organizationId, organizationName } = useWorkspace();
  const requested = useSearchParams().get("tab");
  const initial = tabs.some((item) => item.id === requested) ? (requested as TabId) : "companies";
  const [tab, setTab] = useState<TabId>(initial);
  if (!organizationId) {
    return null;
  }

  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <header>
        <h1 className="text-[31px] leading-none text-foreground">Customer records</h1>
        <p className="mt-3 max-w-3xl text-sm text-muted-foreground">
          Companies, contacts, leads, and inquiries for {organizationName ?? "this organization"}.
        </p>
        <p className="mt-2 max-w-3xl text-xs leading-5 text-subtle">
          Companies and contacts are alphabetical. Leads and inquiries are newest first. A lead score appears only after a stored prediction exists.
        </p>
      </header>
      <div className="flex max-w-full flex-wrap gap-2" role="tablist" aria-label="CRM records">
        {tabs.map((item) => (
          <Button
            key={item.id}
            className={cn(
              "h-10 shrink-0 rounded-[10px] px-4",
              tab === item.id ? "bg-accent text-foreground" : "text-muted-foreground",
            )}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            variant="ghost"
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </Button>
        ))}
      </div>
      {tab === "companies" ? <CompaniesPanel organizationId={organizationId} /> : null}
      {tab === "contacts" ? <ContactsPanel organizationId={organizationId} /> : null}
      {tab === "leads" ? <LeadsPanel organizationId={organizationId} /> : null}
      {tab === "inquiries" ? <InquiriesPanel organizationId={organizationId} /> : null}
    </div>
  );
}
