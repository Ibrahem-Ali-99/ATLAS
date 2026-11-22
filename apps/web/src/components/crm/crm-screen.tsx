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
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <PageHeader title="CRM">
        Companies, contacts, leads, and inquiries for {organizationName}. Records are loaded from this organization only.
      </PageHeader>
      <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1" role="tablist" aria-label="CRM records">
        {tabs.map((item) => (
          <Button
            key={item.id}
            className="shrink-0"
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            variant={tab === item.id ? "default" : "outline"}
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
