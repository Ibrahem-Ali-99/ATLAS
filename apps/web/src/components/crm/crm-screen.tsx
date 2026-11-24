"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { CompaniesPanel } from "@/components/crm/companies-panel";
import { ContactsPanel } from "@/components/crm/contacts-panel";
import { InquiriesPanel } from "@/components/crm/inquiries-panel";
import { LeadsPanel } from "@/components/crm/leads-panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { leadStatuses, type LeadStatus } from "@/lib/records";
import { useWorkspace } from "@/lib/use-workspace";

const tabs = [
  { id: "companies", label: "Companies" },
  { id: "contacts", label: "Contacts" },
  { id: "leads", label: "Leads" },
  { id: "inquiries", label: "Inquiries" },
] as const;

type TabId = (typeof tabs)[number]["id"];
type RecordTarget = { tab: TabId; id: string };

export function CrmScreen() {
  const router = useRouter();
  const { organizationId, organizationName } = useWorkspace();
  const requested = useSearchParams().get("tab");
  const requestedId = useSearchParams().get("id");
  const requestedStatus = useSearchParams().get("status");
  const initial = tabs.some((item) => item.id === requested) ? (requested as TabId) : "companies";
  const initialStatus = leadStatuses.includes(requestedStatus as LeadStatus) ? (requestedStatus as LeadStatus) : "";
  const [tab, setTab] = useState<TabId>(initial);
  const [target, setTarget] = useState<RecordTarget | null>(requestedId ? { tab: initial, id: requestedId } : null);
  const activeTab = requested ? initial : tab;
  const navigateTo = (next: RecordTarget) => {
    setTarget(next);
    setTab(next.tab);
    router.replace(`/crm?tab=${next.tab}&id=${next.id}`);
  };
  if (!organizationId) {
    return null;
  }

  return (
    <div className="mx-auto flex w-full max-w-[1118px] min-w-0 flex-col gap-5">
      <header>
        <h1 className="text-3xl font-semibold leading-tight text-foreground">Customer records</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">Companies, contacts, leads, and inquiries for {organizationName ?? "this organization"}.</p>
      </header>
      <div className="flex max-w-full gap-2 overflow-x-auto border-b border-border pb-3" role="tablist" aria-label="CRM records">
        {tabs.map((item) => (
          <Button
            key={item.id}
            className={cn(
              "h-9 shrink-0 rounded-md px-4",
              activeTab === item.id ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
            type="button"
            role="tab"
            aria-selected={activeTab === item.id}
            variant="ghost"
          onClick={() => { setTarget(null); setTab(item.id); router.replace(`/crm?tab=${item.id}`); }}
          >
            {item.label}
          </Button>
        ))}
      </div>
      {activeTab === "companies" ? <CompaniesPanel key={`companies-${target?.id ?? "none"}`} organizationId={organizationId} selectedId={target?.tab === "companies" ? target.id : null} onNavigate={navigateTo} /> : null}
      {activeTab === "contacts" ? <ContactsPanel key={`contacts-${target?.id ?? "none"}`} organizationId={organizationId} selectedId={target?.tab === "contacts" ? target.id : null} onNavigate={navigateTo} /> : null}
      {activeTab === "leads" ? <LeadsPanel key={`leads-${target?.id ?? "none"}-${initialStatus}`} organizationId={organizationId} selectedId={target?.tab === "leads" ? target.id : null} initialStatus={initialStatus} onNavigate={navigateTo} /> : null}
      {activeTab === "inquiries" ? <InquiriesPanel key={`inquiries-${target?.id ?? "none"}`} organizationId={organizationId} selectedId={target?.tab === "inquiries" ? target.id : null} onNavigate={navigateTo} /> : null}
    </div>
  );
}
