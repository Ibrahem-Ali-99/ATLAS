"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { ProviderNotice, getProviderStatus } from "@/components/provider-notice";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getAutomations } from "@/lib/automations";
import { listCompanies, listDocuments, listInquiries, listLeads } from "@/lib/records-api";
import { useWorkspace } from "@/lib/use-workspace";

type State = "ready" | "attention" | "not_configured" | "verified";

const stateCopy: Record<State, { label: string; className: string }> = {
  ready: { label: "Ready", className: "text-success" },
  attention: { label: "Needs attention", className: "text-warning" },
  not_configured: { label: "Not configured", className: "text-muted-foreground" },
  verified: { label: "Verified", className: "text-primary" },
};

export function SetupScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const provider = useQuery({
    queryKey: ["provider-status", organizationId],
    queryFn: () => getProviderStatus(organizationId ?? ""),
    enabled: Boolean(organizationId),
  });
  const documents = useQuery({
    queryKey: ["setup-documents", organizationId],
    queryFn: () => listDocuments(organizationId ?? "", { pageSize: 1 }),
    enabled: Boolean(organizationId),
  });
  const companies = useQuery({
    queryKey: ["setup-companies", organizationId],
    queryFn: () => listCompanies(organizationId ?? "", { pageSize: 1 }),
    enabled: Boolean(organizationId),
  });
  const leads = useQuery({
    queryKey: ["setup-leads", organizationId],
    queryFn: () => listLeads(organizationId ?? "", { pageSize: 1 }),
    enabled: Boolean(organizationId),
  });
  const inquiries = useQuery({
    queryKey: ["setup-inquiries", organizationId],
    queryFn: () => listInquiries(organizationId ?? "", { pageSize: 1 }),
    enabled: Boolean(organizationId),
  });
  const automations = useQuery({
    queryKey: ["setup-automations", organizationId],
    queryFn: () => getAutomations(organizationId ?? ""),
    enabled: Boolean(organizationId),
  });

  if (!organizationId) return null;

  const providerReady = Boolean(provider.data?.llm_ready && provider.data.embedding_ready);
  const knowledgeReady = Boolean(documents.data?.items.some((item) => item.status === "ready"));
  const crmReady = Boolean((companies.data?.total ?? 0) + (leads.data?.total ?? 0) + (inquiries.data?.total ?? 0));
  const n8nReady = Boolean(automations.data?.n8n_configured && automations.data.webhook_configured);
  const n8nInstalled = Boolean(automations.data?.n8n_configured);
  const items = [
    { title: "Organization details", detail: `${workspace.organizationName ?? "Organization"} is active for this workspace.`, state: "verified" as State, href: "/settings", action: "Review organization" },
    { title: "AI provider setup", detail: provider.data?.llm_detail ?? "Checking provider configuration.", state: providerReady ? "ready" as State : "attention" as State, href: "/settings", action: "Review provider status" },
    { title: "Embedding model readiness", detail: provider.data?.embedding_detail ?? "Checking embedding service.", state: provider.data?.embedding_ready ? "ready" as State : "attention" as State, href: "/knowledge", action: "Open knowledge" },
    { title: "Initial company knowledge", detail: knowledgeReady ? "Knowledge indexed and ready for search." : "Knowledge is empty. Upload a PDF or TXT document, then wait for Indexed and searchable.", state: knowledgeReady ? "ready" as State : "not_configured" as State, href: "/knowledge", action: knowledgeReady ? "Open knowledge" : "Upload knowledge" },
    { title: "CRM starting point", detail: crmReady ? "CRM records are available. Choose Operational or Demo scope deliberately." : "Operational CRM is empty. Create the first company when ready.", state: crmReady ? "ready" as State : "not_configured" as State, href: "/crm?tab=companies", action: "Open companies" },
    { title: "Email and calendar", detail: "Email remains sandboxed and calendar remains simulated; no external action is enabled.", state: "verified" as State, href: "/settings", action: "Review limitations" },
    { title: "n8n workflow setup", detail: n8nReady ? "Installed, active, and callback verified." : n8nInstalled ? "Installed but inactive: callback verification is not configured." : "Not configured in this environment.", state: n8nReady ? "ready" as State : n8nInstalled ? "attention" as State : "not_configured" as State, href: "/workflows", action: "Open workflows" },
    { title: "First grounded question", detail: providerReady && knowledgeReady ? "Ask a question in Assistant and inspect its citations." : "Requires a ready chat provider and indexed knowledge.", state: providerReady && knowledgeReady ? "ready" as State : "not_configured" as State, href: "/assistant", action: "Open Assistant" },
    { title: "Approval-controlled operation", detail: "Agent runs and approvals are real records; nothing is executed without an approval action.", state: "verified" as State, href: "/agent-runs", action: "Review approvals" },
  ];

  const attentionCount = items.filter((item) => item.state === "attention" || item.state === "not_configured").length;

  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <header>
        <p className="text-xs uppercase tracking-[0.14em] text-primary">First-run setup</p>
        <h1 className="mt-2 text-[31px] leading-none text-foreground">Make ATLAS useful for {workspace.organizationName ?? "your organization"}</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
          This checklist reports the real state of the current environment. It never treats a running local service as a successful external integration.
        </p>
      </header>
      <ProviderNotice organizationId={organizationId} detail />
      <section className="rounded-[10px] bg-muted p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg text-foreground">Readiness summary</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {attentionCount === 0 ? "The supported first-run path is ready to demonstrate." : `${attentionCount} steps need configuration or an explicit operator decision.`}
            </p>
          </div>
          <Link href="/overview"><Button variant="outline">Open workspace</Button></Link>
        </div>
      </section>
      <section className="rounded-[10px] bg-muted p-5">
        <h2 className="text-lg text-foreground">Follow these steps in order</h2>
        <p className="mt-1 text-sm text-muted-foreground">Each step reflects live backend state. “Verified” means ATLAS can report the state; it does not claim an external provider is live.</p>
      </section>
      <section className="grid gap-3 lg:grid-cols-2">
        {items.map((item, index) => {
          const state = stateCopy[item.state];
          return (
            <article key={item.title} className="rounded-[10px] bg-muted p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex gap-3">
                  <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-secondary text-xs text-muted-foreground">{index + 1}</span>
                  <div>
                    <h2 className="text-sm font-medium text-foreground">{item.title}</h2>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.detail}</p>
                  </div>
                </div>
                <span className={`whitespace-nowrap text-xs uppercase tracking-[0.1em] ${state.className}`}>{state.label}</span>
              </div>
              <Link className="mt-4 inline-block text-xs text-primary" href={item.href}>{item.action} →</Link>
            </article>
          );
        })}
      </section>
      {(provider.isPending || documents.isPending || automations.isPending) ? <Skeleton className="h-2 w-full" /> : null}
      <p className="text-xs leading-5 text-subtle">Provider credentials are operator-managed and restart-sensitive in this deployment. ATLAS does not offer a misleading in-browser save button for them.</p>
    </div>
  );
}
