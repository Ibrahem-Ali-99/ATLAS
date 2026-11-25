"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ProviderNotice, getProviderStatus } from "@/components/provider-notice";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getAutomations } from "@/lib/automations";
import { getDocumentJob, listCompanies, listDocuments, listInquiries, listLeads, uploadDocument } from "@/lib/records-api";
import { useWorkspace } from "@/lib/use-workspace";
import { getOnboarding, saveAgentConfiguration, saveOnboarding, testOnboardingAssistant } from "@/lib/onboarding";

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
  const queryClient = useQueryClient();
  const onboarding = useQuery({ queryKey: ["onboarding", organizationId], queryFn: () => getOnboarding(organizationId ?? ""), enabled: Boolean(organizationId) });
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
  const setup = onboarding.data?.setup;
  const agent = onboarding.data?.agent;

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
      <OnboardingForms organizationId={organizationId} initialName={workspace.organizationName ?? "Organization"} setup={setup} agent={agent} onSaved={() => void queryClient.invalidateQueries({ queryKey: ["onboarding", organizationId] })} />
      <KnowledgeOnboarding organizationId={organizationId} />
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

function OnboardingForms({ organizationId, initialName, setup, agent, onSaved }: { organizationId: string; initialName: string; setup?: { business_description: string | null; industry: string | null; timezone: string; language: string; completed: boolean }; agent?: { assistant_name: string; purpose: string; tone: string; response_language: string; business_instructions: string }; onSaved: () => void }) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState("");
  const [assistantName, setAssistantName] = useState("");
  const [instructions, setInstructions] = useState("");
  const [industry, setIndustry] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [language, setLanguage] = useState("en");
  const [question, setQuestion] = useState("What should I know about our customer workspace?");
  const [testResult, setTestResult] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => { if (setup && agent) { setDescription(setup.business_description ?? ""); setIndustry(setup.industry ?? ""); setTimezone(setup.timezone); setLanguage(setup.language); setAssistantName(agent.assistant_name); setInstructions(agent.business_instructions); } }, [setup, agent]);
  const save = useMutation({ mutationFn: async () => { await saveOnboarding(organizationId, { name: name || "Organization", business_description: description, industry, timezone, language, completed: true }); return saveAgentConfiguration(organizationId, { assistant_name: assistantName || "ATLAS Assistant", purpose: agent?.purpose ?? "Help the team understand and act on customer information.", tone: agent?.tone ?? "professional", response_language: agent?.response_language ?? language, business_instructions: instructions }); }, onSuccess: () => { setMessage("Setup saved."); onSaved(); }, onError: (error) => setMessage(error instanceof Error ? error.message : "Setup could not be saved.") });
  const assistantTest = useMutation({ mutationFn: () => testOnboardingAssistant(organizationId, question), onSuccess: (result) => setTestResult(`${result.message}${result.sources.length ? ` Sources: ${result.sources.map((source) => source.title ?? source.document_title ?? "workspace evidence").join(", ")}` : " No knowledge sources were used."}`), onError: (error) => setTestResult(error instanceof Error ? error.message : "Assistant test failed.") });
  return <section className="rounded-[10px] bg-muted p-5" aria-label="Organization onboarding"><div className="grid gap-4 lg:grid-cols-2"><div><h2 className="text-lg text-foreground">Organization profile</h2><label className="mt-3 grid gap-2 text-sm"><span>Business description</span><textarea className="min-h-24 rounded-md border border-input bg-background p-3" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What does your team help customers with?" /></label><label className="mt-3 grid gap-2 text-sm"><span>Industry</span><input className="h-10 rounded-md border border-input bg-background px-3" value={industry} onChange={(e) => setIndustry(e.target.value)} /></label><label className="mt-3 grid gap-2 text-sm"><span>Timezone</span><input className="h-10 rounded-md border border-input bg-background px-3" value={timezone} onChange={(e) => setTimezone(e.target.value)} placeholder="Africa/Cairo" /></label><label className="mt-3 grid gap-2 text-sm"><span>Preferred language</span><select className="h-10 rounded-md border border-input bg-background px-3" value={language} onChange={(e) => setLanguage(e.target.value)}><option value="en">English</option><option value="ar">Arabic</option><option value="fr">French</option></select></label></div><div><h2 className="text-lg text-foreground">Assistant configuration</h2><label className="mt-3 grid gap-2 text-sm"><span>Assistant name</span><input className="h-10 rounded-md border border-input bg-background px-3" value={assistantName} onChange={(e) => setAssistantName(e.target.value)} /></label><label className="mt-3 grid gap-2 text-sm"><span>Business instructions</span><textarea className="min-h-24 rounded-md border border-input bg-background p-3" value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Useful context and preferences; safety rules remain enforced." /></label><h3 className="mt-5 text-base text-foreground">Test your assistant</h3><input className="mt-3 h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={question} onChange={(e) => setQuestion(e.target.value)} /><Button className="mt-3" variant="outline" onClick={() => assistantTest.mutate()} disabled={assistantTest.isPending}>Run assistant test</Button>{testResult ? <p className="mt-3 whitespace-pre-wrap text-sm text-muted-foreground" role="status">{testResult}</p> : null}</div></div><div className="mt-4 flex items-center gap-3"><Button onClick={() => save.mutate()} disabled={save.isPending}>Save setup</Button>{message ? <span className="text-sm text-muted-foreground" role="status">{message}</span> : null}</div></section>;
}

function KnowledgeOnboarding({ organizationId }: { organizationId: string }) {
  const [job, setJob] = useState<{ document_id: string; status: string; error_message?: string | null } | null>(null);
  const [message, setMessage] = useState("");
  const upload = useMutation({ mutationFn: (file: File) => uploadDocument(organizationId, file), onSuccess: (document) => { setMessage("Document uploaded. Processing has started."); setJob({ document_id: document.id, status: document.status }); }, onError: (error) => setMessage(error instanceof Error ? error.message : "Document upload failed.") });
  useEffect(() => { if (!job || !["queued", "running", "retrying"].includes(job.status)) return; const timer = window.setInterval(() => { void getDocumentJob(organizationId, job.document_id).then(setJob).catch(() => undefined); }, 2000); return () => window.clearInterval(timer); }, [job, organizationId]);
  return <section className="rounded-[10px] bg-muted p-5" aria-label="Knowledge setup"><h2 className="text-lg text-foreground">Add optional knowledge</h2><p className="mt-1 text-sm text-muted-foreground">Upload a PDF or TXT file to ground the Assistant. You can finish setup without a document.</p><label className="mt-4 block text-sm"><span className="sr-only">Choose knowledge document</span><input type="file" accept="application/pdf,text/plain" onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); }} disabled={upload.isPending} /></label>{message ? <p className="mt-3 text-sm text-muted-foreground" role="status">{message}</p> : null}{job ? <div className="mt-3 rounded-md border border-border p-3 text-sm"><p>Ingestion status: <strong>{job.status}</strong></p>{job.error_message ? <p className="mt-1 text-destructive">{job.error_message}</p> : null}{job.status === "failed" ? <Link className="mt-2 inline-block text-primary" href="/knowledge">Open Knowledge to recover →</Link> : null}</div> : null}</section>;
}
