"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ProviderNotice } from "@/components/provider-notice";
import { MembershipTable } from "@/components/membership-table";
import { RequestError } from "@/components/request-error";
import { SignOutDialog } from "@/components/sign-out-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { sessionQueryOptions } from "@/lib/api";
import { getAutomations } from "@/lib/automations";
import { useWorkspace } from "@/lib/use-workspace";
import {
  getIntegrations,
  integrationAction,
  saveIntegration,
  verifyIntegration,
  type IntegrationMetadata,
  type IntegrationType,
} from "@/lib/integrations";

export function SettingsScreen() {
  const session = useQuery(sessionQueryOptions);
  const { organizationId } = useWorkspace();
  const { role } = useWorkspace();
  const isAdmin = role === "admin";
  const queryClient = useQueryClient();
  const integrations = useQuery({
    queryKey: ["integrations", organizationId],
    queryFn: () => getIntegrations(organizationId ?? ""),
    enabled: Boolean(organizationId),
    retry: false,
  });
  const automations = useQuery({
    queryKey: ["automations", organizationId],
    queryFn: () => getAutomations(organizationId ?? ""),
    enabled: Boolean(organizationId),
  });
  const [signOutOpen, setSignOutOpen] = useState(false);
  const user = session.data?.user;

  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <div>
        <h1 className="text-[31px] leading-none text-foreground">Settings</h1>
        <p className="mt-3 max-w-3xl text-sm text-muted-foreground">
          Account, organization, and integration readiness. Secrets are never shown after they are saved.
        </p>
      </div>
      <div className="grid items-start gap-4 xl:grid-cols-2">
      {organizationId ? (
        <IntegrationSettings
          organizationId={organizationId}
          isAdmin={isAdmin}
          integrations={integrations.data ?? []}
          isLoading={integrations.isPending}
          error={integrations.error}
          onChanged={() => {
            void queryClient.invalidateQueries({ queryKey: ["integrations", organizationId] });
            void queryClient.invalidateQueries({ queryKey: ["provider-status", organizationId] });
          }}
        />
      ) : null}
      <section className="rounded-[10px] bg-muted p-4">
        <h2 className="text-base text-foreground">Account</h2>
        <p className="mt-1 text-sm text-muted-foreground">Read-only fields returned by the session.</p>
        <div className="mt-4">
          {session.isPending || !user ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <div className="grid gap-4">
              <label className="grid gap-2 text-sm">
                <span className="font-medium">Name</span>
                <input
                  readOnly
                  aria-readonly="true"
                  value={user.full_name}
                  className="h-10 cursor-default rounded-[10px] border-0 bg-secondary px-3 text-sm text-foreground"
                />
                <span className="text-xs text-muted-foreground">Read only</span>
              </label>
              <label className="grid gap-2 text-sm">
                <span className="font-medium">Email</span>
                <input
                  readOnly
                  aria-readonly="true"
                  value={user.email}
                  className="h-10 cursor-default rounded-[10px] border-0 bg-secondary px-3 text-sm text-foreground"
                />
                <span className="text-xs text-muted-foreground">Read only</span>
              </label>
            </div>
          )}
        </div>
      </section>
      {organizationId ? <ProviderNotice organizationId={organizationId} detail /> : null}
      <section className="rounded-[10px] bg-muted p-4">
        <h2 className="text-base text-foreground">Organization</h2>
        <p className="mt-1 text-sm text-muted-foreground">Roles are stored on the membership, not chosen in the browser.</p>
        <div className="mt-4">
          {session.isPending || !session.data ? (
            <Skeleton className="h-16 w-full" />
          ) : (
            <MembershipTable memberships={session.data.memberships} />
          )}
        </div>
      </section>
      <section className="rounded-[10px] bg-muted p-4">
        <h2 className="text-base text-foreground">Delivery</h2>
        <p className="mt-1 text-sm text-muted-foreground">Read only. Webhook keys and model keys are not shown.</p>
        {automations.isPending ? <Skeleton className="mt-4 h-16 w-full" /> : null}
        {automations.isError ? <div className="mt-4"><RequestError error={automations.error} /></div> : null}
        {automations.data ? (
          <dl className="mt-4 space-y-2 text-sm text-muted-foreground">
            <div>Email mode: {automations.data.email_mode}</div>
            <div>Calendar: {automations.data.calendar_provider}</div>
            <div>n8n: {automations.data.n8n_configured ? "configured" : "not configured"}</div>
            <div>Webhook key: {automations.data.webhook_configured ? "configured" : "not configured"}</div>
          </dl>
        ) : null}
      </section>
      <section className="rounded-[10px] bg-muted p-4">
        <h2 className="text-base text-foreground">Session</h2>
        <p className="mt-1 text-sm text-muted-foreground">Signing out revokes the server session for this browser.</p>
        <Button className="mt-4" variant="outline" onClick={() => setSignOutOpen(true)}>
          Sign out
        </Button>
      </section>
      <SignOutDialog open={signOutOpen} onOpenChange={setSignOutOpen} />
      </div>
    </div>
  );
}

function IntegrationSettings({
  organizationId,
  isAdmin,
  integrations,
  isLoading,
  error,
  onChanged,
}: {
  organizationId: string;
  isAdmin: boolean;
  integrations: IntegrationMetadata[];
  isLoading: boolean;
  error: unknown;
  onChanged: () => void;
}) {
  const byType = useMemo(() => new Map(integrations.map((item) => [item.integration_type, item])), [integrations]);
  return (
    <section className="rounded-[10px] bg-muted p-4 xl:col-span-2" aria-labelledby="integrations-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="integrations-heading" className="text-base text-foreground">Integrations</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Organization-scoped provider settings. Environment defaults remain active when no override is configured.
          </p>
        </div>
        <Badge variant="secondary">{isAdmin ? "Administrator access" : "Read only"}</Badge>
      </div>
      {error ? <div className="mt-4"><RequestError error={error} /></div> : null}
      {isLoading ? <Skeleton className="mt-4 h-32 w-full" /> : (
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <ProviderCard key={`chat-${byType.get("chat")?.id ?? "fallback"}`} organizationId={organizationId} type="chat" title="Language model" record={byType.get("chat")} isAdmin={isAdmin} onChanged={onChanged} />
          <ProviderCard key={`embedding-${byType.get("embedding")?.id ?? "fallback"}`} organizationId={organizationId} type="embedding" title="Embeddings" record={byType.get("embedding")} isAdmin={isAdmin} onChanged={onChanged} />
          <N8nCard record={byType.get("n8n")} />
        </div>
      )}
    </section>
  );
}

function ProviderCard({
  organizationId, type, title, record, isAdmin, onChanged,
}: { organizationId: string; type: Exclude<IntegrationType, "n8n">; title: string; record?: IntegrationMetadata; isAdmin: boolean; onChanged: () => void }) {
  const [provider, setProvider] = useState(record?.provider ?? (type === "chat" ? "groq" : "ollama"));
  const [model, setModel] = useState(String(record?.config.model ?? (type === "chat" ? "openai/gpt-oss-20b" : "nomic-embed-text:v1.5")));
  const [baseUrl, setBaseUrl] = useState(String(record?.config.base_url ?? (type === "chat" ? "https://api.groq.com/openai/v1" : "http://ollama:11434/v1")));
  const [dimensions, setDimensions] = useState(String(record?.config.dimensions ?? (type === "embedding" ? "768" : "")));
  const [secret, setSecret] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const save = useMutation({ mutationFn: () => saveIntegration(organizationId, type, { provider, config: { base_url: baseUrl, model, ...(type === "embedding" ? { dimensions: Number(dimensions) } : {}) }, ...(secret ? { credentials: secret } : {}), ...(record ? { expected_version: record.credential_version } : {}) }), onSuccess: () => { setSecret(""); setMessage("Configuration saved. Run a connection test before relying on it."); onChanged(); }, onError: (err) => setMessage(err instanceof Error ? err.message : "Could not save configuration.") });
  const verify = useMutation({ mutationFn: () => verifyIntegration(organizationId, type), onSuccess: (result) => { setMessage(result.verified ? result.detail : `Verification failed: ${result.detail}`); onChanged(); }, onError: (err) => setMessage(err instanceof Error ? err.message : "Verification failed.") });
  const action = useMutation({ mutationFn: (kind: "enable" | "disable" | "revoke") => integrationAction(organizationId, type, kind, record?.credential_version ?? 0), onSuccess: (_, kind) => { setMessage(kind === "revoke" ? "Credential revoked. The integration is disabled." : `Integration ${kind}d.`); onChanged(); }, onError: (err) => setMessage(err instanceof Error ? err.message : "Could not update integration.") });
  const fallback = !record;
  return (
    <div className="rounded-[10px] border border-border bg-background p-4">
      <div className="flex items-start justify-between gap-2"><div><h3 className="font-medium">{title}</h3><p className="mt-1 text-xs text-muted-foreground">{fallback ? "Using environment default" : `${record.status.replace("_", " ")} · version ${record.credential_version}`}</p></div><Badge variant="secondary">{fallback ? "Fallback" : record.has_credentials ? "Key installed" : "No key"}</Badge></div>
      <div className="mt-4 grid gap-3">
        <label className="grid gap-1 text-sm"><span>Provider</span><select disabled={!isAdmin} value={provider} onChange={(event) => setProvider(event.target.value)} className="h-10 rounded-md border border-input bg-background px-3"><option value={type === "chat" ? "groq" : "ollama"}>{type === "chat" ? "Groq" : "Ollama"}</option><option value="openai">OpenAI</option></select></label>
        <label className="grid gap-1 text-sm"><span>Model</span><Input disabled={!isAdmin} value={model} onChange={(event) => setModel(event.target.value)} /></label>
        <label className="grid gap-1 text-sm"><span>Base URL</span><Input disabled={!isAdmin} value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} /></label>
        {type === "embedding" ? <label className="grid gap-1 text-sm"><span>Vector dimensions</span><select disabled={!isAdmin} value={dimensions} onChange={(event) => setDimensions(event.target.value)} className="h-10 rounded-md border border-input bg-background px-3"><option value="768">768 · Ollama</option><option value="1536">1536 · OpenAI-compatible</option></select></label> : null}
        {isAdmin ? <label className="grid gap-1 text-sm"><span>{record?.has_credentials ? "Replace API key" : "API key"}</span><Input type="password" autoComplete="new-password" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder={record?.has_credentials ? "Leave blank to keep current key" : "Enter key"} /></label> : null}
      </div>
      {type === "embedding" && record && Number(record.config.dimensions ?? dimensions) !== Number(dimensions) ? <p className="mt-3 rounded-md border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-xs leading-5 text-amber-100">Changing model or dimensions can require a full reindex. Existing indexed knowledge will not be silently mixed.</p> : null}
      {message ? <p className="mt-3 text-xs leading-5 text-muted-foreground" role="status">{message}</p> : null}
      {isAdmin ? <div className="mt-4 flex flex-wrap gap-2"><Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save"}</Button>{record ? <Button size="sm" variant="outline" onClick={() => verify.mutate()} disabled={verify.isPending || record.status === "disabled"}>{verify.isPending ? "Testing…" : "Test connection"}</Button> : null}{record ? <Button size="sm" variant="ghost" onClick={() => action.mutate(record.status === "disabled" ? "enable" : "disable")} disabled={action.isPending}>{record.status === "disabled" ? "Enable" : "Disable"}</Button> : null}{record?.has_credentials ? <Button size="sm" variant="ghost" onClick={() => action.mutate("revoke")} disabled={action.isPending}>Revoke key</Button> : null}</div> : null}
    </div>
  );
}

function N8nCard({ record }: { record?: IntegrationMetadata }) {
  return <div className="rounded-[10px] border border-border bg-background p-4"><div className="flex items-start justify-between gap-2"><div><h3 className="font-medium">n8n automation</h3><p className="mt-1 text-xs text-muted-foreground">Read-only integration status</p></div><Badge variant="secondary">{record?.status ?? "Environment"}</Badge></div><p className="mt-4 text-sm leading-6 text-muted-foreground">Workflow availability and callback verification remain managed by the existing provisioning and webhook safeguards. No unsupported activation or secret controls are exposed here.</p></div>;
}
