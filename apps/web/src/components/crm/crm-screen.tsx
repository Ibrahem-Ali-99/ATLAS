"use client";

import { useState } from "react";

import { CompaniesPanel } from "@/components/crm/companies-panel";
import { ContactsPanel } from "@/components/crm/contacts-panel";
import { InquiriesPanel } from "@/components/crm/inquiries-panel";
import { LeadsPanel } from "@/components/crm/leads-panel";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
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
  const [tab, setTab] = useState<TabId>("companies");
  if (!organizationId) {
    return null;
  }

  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <PageHeader title="CRM" eyebrow={organizationName ?? undefined}>
        Browse companies and contacts, then work a lead without leaving the record. Every row belongs to this organization.
      </PageHeader>
      <div className="flex max-w-full gap-1 overflow-x-auto rounded-lg border border-border bg-card p-1" role="tablist" aria-label="CRM records">
        {tabs.map((item) => (
          <Button
            key={item.id}
            className="shrink-0"
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            variant={tab === item.id ? "default" : "ghost"}
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
