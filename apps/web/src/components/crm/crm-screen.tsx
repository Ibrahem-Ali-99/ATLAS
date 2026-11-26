"use client";

import { useSearchParams } from "next/navigation";
import { BriefcaseBusiness, Building2, Contact, Inbox, Kanban } from "lucide-react";

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
  { id: "opportunities", label: "Opportunities" },
] as const;

type TabId = (typeof tabs)[number]["id"];
type RecordTarget = { tab: TabId; id: string | null };

export function CrmScreen() {
  const { organizationId, organizationName } = useWorkspace();
  const searchParams = useSearchParams();
  const requested = searchParams.get("tab");
  const requestedId = searchParams.get("id");
  const requestedStatus = searchParams.get("status");
  const activeTab = tabs.some((item) => item.id === requested) ? (requested as TabId) : "companies";
  const initialStatus = leadStatuses.includes(requestedStatus as LeadStatus) ? (requestedStatus as LeadStatus) : "";
  const target = requestedId ? { tab: activeTab, id: requestedId } : null;
  const selectTab = (next: TabId) => {
    window.history.replaceState(null, "", `/crm?tab=${next}`);
  };
  const navigateTo = (next: RecordTarget) => {
    const params = new URLSearchParams({ tab: next.tab });
    if (next.id) params.set("id", next.id);
    if (next.tab === "leads" && initialStatus) params.set("status", initialStatus);
    window.history.replaceState(null, "", `/crm?${params}`);
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
        {tabs.map((item, index) => (
          <Button
            key={item.id}
            className={cn(
              "h-10 shrink-0 gap-2 rounded-lg border border-transparent px-3.5 text-sm",
              activeTab === item.id ? "border-primary/30 bg-accent font-semibold text-accent-foreground shadow-sm" : "text-muted-foreground hover:border-border hover:bg-card hover:text-foreground",
            )}
            type="button"
            role="tab"
            id={`crm-tab-${item.id}`}
            tabIndex={activeTab === item.id ? 0 : -1}
            aria-controls="crm-records-panel"
            aria-selected={activeTab === item.id}
            variant="ghost"
            onClick={() => selectTab(item.id)}
            onKeyDown={(event) => {
              const last = tabs.length - 1;
              const directions: Partial<Record<string, number>> = {
                ArrowRight: (index + 1) % tabs.length,
                ArrowLeft: (index + last) % tabs.length,
                Home: 0,
                End: last,
              };
              const nextIndex = directions[event.key];
              if (nextIndex === undefined) return;
              event.preventDefault();
              const next = tabs[nextIndex].id;
              const nextButton = document.getElementById(`crm-tab-${next}`);
              nextButton?.focus();
              selectTab(next);
            }}
          >
            {item.id === "companies" ? <Building2 className="size-4" aria-hidden="true" /> : item.id === "contacts" ? <Contact className="size-4" aria-hidden="true" /> : item.id === "leads" ? <BriefcaseBusiness className="size-4" aria-hidden="true" /> : item.id === "opportunities" ? <Kanban className="size-4" aria-hidden="true" /> : <Inbox className="size-4" aria-hidden="true" />}
            {item.label}
          </Button>
        ))}
      </div>
      <div id="crm-records-panel" role="tabpanel" aria-labelledby={`crm-tab-${activeTab}`} className="min-w-0" tabIndex={0}>
      {activeTab === "opportunities" ? <OpportunityPipeline key={organizationId} selectedId={target?.id ?? null} onSelect={(id) => navigateTo({ tab: "opportunities", id })} /> : null}
      {activeTab === "companies" ? <CompaniesPanel key={`companies-${organizationId}`} organizationId={organizationId} selectedId={target?.tab === "companies" ? target.id : null} onNavigate={navigateTo} /> : null}
      {activeTab === "contacts" ? <ContactsPanel key={`contacts-${organizationId}`} organizationId={organizationId} selectedId={target?.tab === "contacts" ? target.id : null} onNavigate={navigateTo} /> : null}
      {activeTab === "leads" ? <LeadsPanel key={`leads-${organizationId}-${initialStatus}`} organizationId={organizationId} selectedId={target?.tab === "leads" ? target.id : null} initialStatus={initialStatus} onNavigate={navigateTo} /> : null}
      {activeTab === "inquiries" ? <InquiriesPanel key={`inquiries-${organizationId}`} organizationId={organizationId} selectedId={target?.tab === "inquiries" ? target.id : null} onNavigate={navigateTo} /> : null}
      </div>
    </div>
  );
}
