"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ProviderNotice, getProviderStatus } from "@/components/provider-notice";
import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { getDocumentJob, uploadDocument } from "@/lib/records-api";
import { sessionQueryOptions } from "@/lib/api";
import { useWorkspace } from "@/lib/use-workspace";
import { getOnboarding, getOnboardingProgress, saveOnboarding, testOnboardingAssistant } from "@/lib/onboarding";

export function SetupScreen() {
  const workspace = useWorkspace();
  const organizationId = workspace.organizationId;
  const isAdmin = workspace.role === "admin";
  const queryClient = useQueryClient();
  const onboarding = useQuery({ queryKey: ["onboarding", organizationId], queryFn: () => getOnboarding(organizationId ?? ""), enabled: Boolean(organizationId && isAdmin) });
  const provider = useQuery({
    queryKey: ["provider-status", organizationId],
    queryFn: () => getProviderStatus(organizationId ?? ""),
    enabled: Boolean(organizationId),
  });
  const progress = useQuery({
    queryKey: ["onboarding-progress", organizationId],
    queryFn: () => getOnboardingProgress(organizationId ?? ""),
    enabled: Boolean(organizationId),
    staleTime: 0,
  });

  if (!organizationId) return null;
  const setup = onboarding.data?.setup;
  const agent = onboarding.data?.agent;
  const readiness = progress.data;
  const providerReady = Boolean(provider.data?.llm_ready && provider.data.embedding_ready);
  const checklist = [
    { key: "profile", title: "Save the organization profile", detail: "Set your team’s name, timezone and assistant preferences.", href: "#organization-profile", action: "Edit profile" },
    { key: "company", title: "Add the first company", detail: "Create a company in your workspace CRM.", href: "/crm?tab=companies", action: "Open companies" },
    { key: "contact", title: "Add the first contact", detail: "Add a contact and link them to their company.", href: "/crm?tab=contacts", action: "Open contacts" },
    { key: "lead", title: "Create the first lead", detail: "Create a lead for the contact so your team can track their request.", href: "/crm?tab=leads", action: "Open leads" },
    { key: "inquiry", title: "Record the first customer inquiry", detail: "Capture the customer request and link it to the lead for follow-up.", href: "/crm?tab=inquiries", action: "Open inquiries" },
    { key: "workflow", title: "Complete a workflow run", detail: "Create a workflow that adds a CRM task, then run it against an operational record and inspect the result.", href: "/workflows", action: "Open workflows" },
    { key: "knowledge", title: "Index the first document", detail: "Upload a PDF or TXT file and wait for indexing to finish.", href: "#knowledge-setup", action: "Upload knowledge" },
    { key: "assistant", title: "Verify an answer with citations", detail: providerReady ? "Run an assistant test and check that its answer cites your workspace data." : "Configure chat and embeddings, then run a test with your workspace data.", href: providerReady ? "#organization-profile" : "/integrations", action: providerReady ? "Test assistant" : "Open integrations" },
  ] as const;
  const completed = checklist.filter(({ key }) => readiness?.[key]).length;
  const next = readiness ? checklist.find(({ key }) => !readiness[key] && (isAdmin || !["profile", "assistant", "workflow"].includes(key))) : undefined;
  function refreshProgress() {
    void queryClient.invalidateQueries({ queryKey: ["onboarding-progress", organizationId] });
  }
  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <PageHeader title="Workspace setup" actions={<Button asChild variant="outline"><Link href="/overview">Open workspace</Link></Button>}>
        Prepare {workspace.organizationName ?? "your organization"} to use CRM, company knowledge, and approved workflows.
      </PageHeader>
      <ProviderNotice organizationId={organizationId} detail />
      <section className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="min-w-0 space-y-4">
      {!isAdmin ? <p className="rounded-xl border border-border bg-card p-5 text-sm text-muted-foreground">Workspace administrators manage the organization profile and assistant configuration.</p> : onboarding.isPending ? <Skeleton className="h-56 w-full" /> : onboarding.isError ? (
        <RequestError error={onboarding.error} />
      ) : (
        <OnboardingForms key={`profile-${organizationId}`} organizationId={organizationId} initialName={onboarding.data?.organization.name ?? workspace.organizationName ?? "Organization"} setup={setup} agent={agent} onProgress={refreshProgress} onSaved={() => { refreshProgress(); void queryClient.invalidateQueries({ queryKey: ["onboarding", organizationId] }); void queryClient.invalidateQueries({ queryKey: sessionQueryOptions.queryKey }); }} />
      )}
      <KnowledgeOnboarding key={`knowledge-${organizationId}`} organizationId={organizationId} />
      </div>
      <section aria-labelledby="setup-checklist" className="min-w-0 self-start rounded-xl border border-border bg-card">
        <div className="border-b border-border p-5">
          <h2 id="setup-checklist" className="font-semibold">Setup checklist</h2>
          {readiness ? <p role="status" className="mt-1 text-sm text-muted-foreground">{completed} of {checklist.length} steps completed</p> : null}
          {next ? <Button asChild size="sm" className="mt-3"><Link href={next.href}>Continue setup</Link></Button> : null}
          {progress.isPending ? <Skeleton className="mt-2 h-4 w-36" /> : null}
          {progress.error ? <RequestError error={progress.error} /> : null}
        </div>
        <ol className="divide-y divide-border">
          {checklist.map(({ key, title, detail, href, action }) => (
            <li key={key} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="text-sm font-medium">{title}</h3>
                {readiness ? <span className={readiness[key] ? "text-xs font-medium text-success" : "text-xs text-muted-foreground"}>{readiness[key] ? "Complete" : "To do"}</span> : null}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{detail}</p>
              {isAdmin || (key !== "profile" && key !== "assistant") ? <Link className="mt-3 inline-block text-sm font-medium text-primary hover:underline" href={href}>{action}</Link> : null}
            </li>
          ))}
        </ol>
        <div className="border-t border-border p-4">
          <div className="flex flex-wrap gap-3">
            <Link href="/integrations" className="text-sm font-medium text-primary hover:underline">Connect providers</Link>
            {isAdmin ? <Link href="/settings#settings-members" className="text-sm font-medium text-primary hover:underline">Invite teammates</Link> : null}
          </div>
        </div>
      </section>
      </section>
    </div>
  );
}

function OnboardingForms({ organizationId, initialName, setup, agent, onSaved, onProgress }: { organizationId: string; initialName: string; setup?: { business_description: string | null; industry: string | null; timezone: string; language: string; completed: boolean }; agent?: { assistant_name: string; purpose: string; tone: string; response_language: string; business_instructions: string }; onSaved: () => void; onProgress: () => void }) {
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(setup?.business_description ?? "");
  const [assistantName, setAssistantName] = useState(agent?.assistant_name ?? "");
  const [instructions, setInstructions] = useState(agent?.business_instructions ?? "");
  const [industry, setIndustry] = useState(setup?.industry ?? "");
  const [timezone, setTimezone] = useState(setup?.timezone ?? "UTC");
  const [language, setLanguage] = useState(setup?.language ?? "en");
  const [question, setQuestion] = useState("What should I know about our customer workspace?");
  const [testResult, setTestResult] = useState("");
  const [message, setMessage] = useState("");
  const save = useMutation({
    mutationFn: () => saveOnboarding(organizationId, {
      name: name.trim(),
      business_description: description.trim(),
      industry: industry.trim(),
      timezone: timezone.trim(),
      language,
      completed: true,
      agent: {
        assistant_name: assistantName.trim() || "ATLAS Assistant",
        purpose: agent?.purpose ?? "Help the team understand and act on customer information.",
        tone: agent?.tone ?? "professional",
        response_language: agent?.response_language ?? language,
        business_instructions: instructions.trim(),
      },
    }),
    onSuccess: () => { setMessage("Setup saved."); onSaved(); },
    onError: (error) => setMessage(error instanceof Error ? error.message : "Setup could not be saved."),
  });
  const assistantTest = useMutation({ mutationFn: () => testOnboardingAssistant(organizationId, question), onSuccess: (result) => { if (result.sources.length) onProgress(); setTestResult(`${result.message}${result.sources.length ? ` Sources: ${result.sources.map((source) => source.title ?? source.document_title ?? "workspace evidence").join(", ")}` : " No knowledge sources were used."}`); }, onError: (error) => setTestResult(error instanceof Error ? error.message : "Assistant test failed.") });
  return <section id="organization-profile" className="scroll-mt-24 rounded-xl border border-border bg-card p-5" aria-label="Organization onboarding"><div className="grid gap-4 lg:grid-cols-2"><div><h2 className="text-lg text-foreground">Organization profile</h2><label className="mt-3 grid gap-2 text-sm">Organization name<input className="h-10 rounded-md border border-input bg-background px-3" value={name} maxLength={200} onChange={(event) => setName(event.target.value)} /></label><label className="mt-3 grid gap-2 text-sm"><span>Business description</span><textarea className="min-h-24 rounded-md border border-input bg-background p-3" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What does your team help customers with?" /></label><label className="mt-3 grid gap-2 text-sm"><span>Industry</span><input className="h-10 rounded-md border border-input bg-background px-3" value={industry} onChange={(e) => setIndustry(e.target.value)} /></label><label className="mt-3 grid gap-2 text-sm"><span>Timezone</span><input className="h-10 rounded-md border border-input bg-background px-3" value={timezone} onChange={(e) => setTimezone(e.target.value)} placeholder="Africa/Cairo" /></label><label className="mt-3 grid gap-2 text-sm"><span>Preferred language</span><select className="h-10 rounded-md border border-input bg-background px-3" value={language} onChange={(e) => setLanguage(e.target.value)}><option value="en">English</option><option value="ar">Arabic</option><option value="fr">French</option></select></label></div><div><h2 className="text-lg text-foreground">Assistant configuration</h2><label className="mt-3 grid gap-2 text-sm"><span>Assistant name</span><input className="h-10 rounded-md border border-input bg-background px-3" value={assistantName} onChange={(e) => setAssistantName(e.target.value)} /></label><label className="mt-3 grid gap-2 text-sm"><span>Business instructions</span><textarea className="min-h-24 rounded-md border border-input bg-background p-3" value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Useful context and preferences; safety rules remain enforced." /></label><h3 className="mt-5 text-base text-foreground">Test your assistant</h3><input aria-label="Assistant test question" className="mt-3 h-10 w-full rounded-md border border-input bg-background px-3 text-sm" value={question} onChange={(e) => setQuestion(e.target.value)} /><Button className="mt-3" variant="outline" onClick={() => assistantTest.mutate()} disabled={assistantTest.isPending}>Run assistant test</Button>{testResult ? <p className="mt-3 whitespace-pre-wrap text-sm text-muted-foreground" role="status">{testResult}</p> : null}</div></div><div className="mt-4 flex items-center gap-3"><Button onClick={() => save.mutate()} disabled={save.isPending || !name.trim()}>Save setup</Button>{message ? <span className="text-sm text-muted-foreground" role="status">{message}</span> : null}</div></section>;
}

function KnowledgeOnboarding({ organizationId }: { organizationId: string }) {
  const client = useQueryClient();
  const [documentId, setDocumentId] = useState<string | null>(null);
  const upload = useMutation({
    mutationFn: (file: File) => uploadDocument(organizationId, file),
    onSuccess: (document) => setDocumentId(document.id),
  });
  const job = useQuery({
    queryKey: ["setup-ingestion", organizationId, documentId],
    queryFn: () => getDocumentJob(organizationId, documentId ?? ""),
    enabled: Boolean(documentId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "succeeded" || status === "failed" ? false : 2000;
    },
  });
  const indexed = job.data?.status === "succeeded";
  useEffect(() => {
    if (indexed) void client.invalidateQueries({ queryKey: ["onboarding-progress", organizationId] });
  }, [client, indexed, organizationId]);

  return (
    <section id="knowledge-setup" className="scroll-mt-24 rounded-xl border border-border bg-card p-5" aria-label="Knowledge setup">
      <h2 className="font-semibold">Add company knowledge</h2>
      <p className="mt-1 text-sm text-muted-foreground">Upload a PDF or TXT file so Assistant can cite it in answers.</p>
      <label className="mt-4 block text-sm">
        <span className="sr-only">Choose knowledge document</span>
        <input type="file" accept="application/pdf,text/plain,.pdf,.txt" disabled={upload.isPending} onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          if (file) {
            setDocumentId(null);
            upload.mutate(file);
            event.currentTarget.value = "";
          }
        }} />
      </label>
      {upload.isPending ? <p className="mt-3 text-sm text-muted-foreground" role="status">Uploading document…</p> : null}
      {upload.error || job.error ? <div className="mt-3"><RequestError error={upload.error ?? job.error} /></div> : null}
      {documentId && job.isPending ? <p className="mt-3 text-sm text-muted-foreground" role="status">Waiting for the ingestion job…</p> : null}
      {job.data ? (
        <div className="mt-3 rounded-lg border border-border p-3 text-sm">
          <p role="status">{indexed ? "Indexed and searchable." : `Ingestion status: ${job.data.status}.`}</p>
          {job.data.error_message ? <p className="mt-1 text-destructive">{job.data.error_message}</p> : null}
          {job.data.status === "failed" ? <Link className="mt-2 inline-block text-primary" href="/knowledge">Open Knowledge to retry</Link> : null}
          {indexed ? <Link className="mt-2 inline-block text-primary" href="/assistant">Ask a question about this document</Link> : null}
        </div>
      ) : null}
    </section>
  );
}
