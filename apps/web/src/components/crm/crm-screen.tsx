"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { BriefcaseBusiness, Building2, Contact, Inbox } from "lucide-react";

import { CompaniesPanel } from "@/components/crm/companies-panel";
import { ContactsPanel } from "@/components/crm/contacts-panel";
import { InquiriesPanel } from "@/components/crm/inquiries-panel";
import { LeadsPanel } from "@/components/crm/leads-panel";
import { OpportunityPipeline } from "@/components/crm/opportunity-pipeline";
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
    <div className="mx-auto flex w-full max-w-[1180px] min-w-0 flex-col gap-6" data-testid="crm-workspace">
      <header className="flex flex-col gap-4 border-b border-border/80 pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-primary">Workspace / CRM</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">Customer records</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Manage the companies, people, opportunities, and requests behind your customer work.</p>
        </div>
        <div className="hidden items-center gap-2 text-xs text-subtle sm:flex"><span className="size-2 rounded-full bg-success" /> {organizationName ?? "Current workspace"}</div>
      </header>
      <div className="-mx-1 flex max-w-full gap-1 overflow-x-auto px-1 pb-1" role="tablist" aria-label="CRM records" data-testid="crm-tabs">
        {tabs.map((item) => (
          <Button
            key={item.id}
            className={cn(
              "h-10 shrink-0 gap-2 rounded-lg border border-transparent px-3.5 text-sm",
              activeTab === item.id ? "border-primary/30 bg-accent font-semibold text-accent-foreground shadow-sm" : "text-muted-foreground hover:border-border hover:bg-card hover:text-foreground",
            )}
            type="button"
            role="tab"
            aria-selected={activeTab === item.id}
            variant="ghost"
            onClick={() => { setTarget(null); setTab(item.id); router.replace(`/crm?tab=${item.id}`); }}
          >
            {item.id === "companies" ? <Building2 className="size-4" aria-hidden="true" /> : item.id === "contacts" ? <Contact className="size-4" aria-hidden="true" /> : item.id === "leads" ? <BriefcaseBusiness className="size-4" aria-hidden="true" /> : <Inbox className="size-4" aria-hidden="true" />}
            {item.label}
          </Button>
        ))}
      </div>
      <OpportunityPipeline />
      {activeTab === "companies" ? <CompaniesPanel key={`companies-${target?.id ?? "none"}`} organizationId={organizationId} selectedId={target?.tab === "companies" ? target.id : null} onNavigate={navigateTo} /> : null}
      {activeTab === "contacts" ? <ContactsPanel key={`contacts-${target?.id ?? "none"}`} organizationId={organizationId} selectedId={target?.tab === "contacts" ? target.id : null} onNavigate={navigateTo} /> : null}
      {activeTab === "leads" ? <LeadsPanel key={`leads-${target?.id ?? "none"}-${initialStatus}`} organizationId={organizationId} selectedId={target?.tab === "leads" ? target.id : null} initialStatus={initialStatus} onNavigate={navigateTo} /> : null}
      {activeTab === "inquiries" ? <InquiriesPanel key={`inquiries-${target?.id ?? "none"}`} organizationId={organizationId} selectedId={target?.tab === "inquiries" ? target.id : null} onNavigate={navigateTo} /> : null}
    </div>
  );
}
