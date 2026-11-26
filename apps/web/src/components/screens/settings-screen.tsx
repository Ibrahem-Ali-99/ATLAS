"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Bot, Building2, ChevronRight, Fingerprint, Mail, MessageCircle, Search, UserRound, Users, Workflow } from "lucide-react";

import { ConfirmButton } from "@/components/confirm-button";
import { CalendarConnectionCard } from "@/components/calendar/calendar-connection";
import { WidgetSettingsDialog } from "@/components/inbox/inbox-screen";
import { PageHeader } from "@/components/page-header";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { getProviderStatus, ProviderNotice } from "@/components/provider-notice";
import { MembershipTable } from "@/components/membership-table";
import { RequestError } from "@/components/request-error";
import { SignOutDialog } from "@/components/sign-out-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { sessionQueryOptions } from "@/lib/api";
import { getAutomations } from "@/lib/automations";
import { getCalendarConnection } from "@/lib/calendar";
import { cancelEmbeddingReindex, getEmbeddingReindex, startEmbeddingReindex } from "@/lib/embedding-reindex";
import { getInboxWidget } from "@/lib/inbox";
import { useWorkspace } from "@/lib/use-workspace";
import { createInvitation, listInvitations, type InvitationStatus } from "@/lib/invitations";
import { listTeam, removeMember, updateMemberRole, updateOrganization, type TeamMember } from "@/lib/organization";
import {
  getIntegrations,
  getWebhookKeyStatus,
  issueWebhookKey,
  disconnectWebhookKey,
  integrationConnection,
  modelConnection,
  getEmailDomains,
  registerEmailDomain,
  checkEmailDomain,
  revokeEmailDomain,
  getResendTestStatus,
  approveResendTestRecipient,
  sendResendTest,
  getWhatsAppTestStatus,
  approveWhatsAppTestRecipient,
  integrationAction,
  saveIntegration,
  verifyIntegration,
  type IntegrationMetadata,
  type IntegrationType,
} from "@/lib/integrations";

const settingsSections = [
  { id: "organization", label: "Organization", icon: Building2 },
  { id: "account", label: "Account", icon: UserRound },
  { id: "members", label: "Members", icon: Users },
  { id: "sessions", label: "Sessions", icon: Fingerprint },
  { id: "connections", label: "Integrations", icon: Workflow },
];
export function SettingsScreen({ integrationsOnly = false }: { integrationsOnly?: boolean }) {
  const session = useQuery(sessionQueryOptions);
  const queryClient = useQueryClient();
  const { organizationId, role } = useWorkspace();
  const isAdmin = role === "admin";
  const integrations = useQuery({
    queryKey: ["integrations", organizationId],
    queryFn: () => getIntegrations(organizationId ?? ""),
    enabled: Boolean(organizationId && isAdmin),
    retry: false,
  });
  const automations = useQuery({
    queryKey: ["automations", organizationId],
    queryFn: () => getAutomations(organizationId ?? ""),
    enabled: Boolean(organizationId && !integrationsOnly),
  });
  const [signOutOpen, setSignOutOpen] = useState(false);
  const user = session.data?.user;
  const team = useQuery({ queryKey: ["team", organizationId], queryFn: () => listTeam(organizationId ?? ""), enabled: Boolean(organizationId && !integrationsOnly) });
  const integrationProps = {
    organizationId: organizationId ?? "",
    isAdmin,
    integrations: isAdmin ? integrations.data ?? [] : [],
    isLoading: isAdmin && integrations.isPending,
    error: isAdmin ? integrations.error : null,
    onChanged: () => {
      void queryClient.invalidateQueries({ queryKey: ["integrations", organizationId] });
      void queryClient.invalidateQueries({ queryKey: ["provider-status", organizationId] });
    },
  };

  if (integrationsOnly) {
    return (
      <div className="min-w-0 space-y-6">
        <PageHeader title="Integrations">Connect the services your organization uses for messaging, automation, and knowledge.</PageHeader>
        {organizationId ? <IntegrationMarketplace key={organizationId} {...integrationProps} /> : null}
      </div>
    );
  }

  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <PageHeader title="Settings" eyebrow="Workspace administration">Manage your account, workspace, and connections.</PageHeader>
      <div className="grid min-w-0 items-start gap-4 lg:grid-cols-[11rem_minmax(0,1fr)]">
      <nav aria-label="Settings sections" className="min-w-0 overflow-x-auto rounded-xl border border-border bg-card p-1.5 lg:sticky lg:top-[76px]">
        <ul className="flex w-max gap-1 lg:w-full lg:flex-col">
          {settingsSections.map(({ id, label, icon: Icon }) => (
            <li key={id}>
              <a href={`#settings-${id}`} className="flex h-9 items-center gap-2 rounded-md px-2.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground">
                <Icon className="size-4 shrink-0" aria-hidden="true" />{label}
              </a>
            </li>
          ))}
        </ul>
      </nav>
      <div className="grid min-w-0 gap-4" key={organizationId}>
      <div id="settings-organization" className="grid scroll-mt-20 gap-4">
      {organizationId && isAdmin ? <OrganizationCard organizationId={organizationId} initialName={session.data?.memberships.find((m) => m.organization_id === organizationId)?.organization_name ?? ""} onSaved={() => void queryClient.invalidateQueries({ queryKey: ["session"] })} /> : null}
      <section className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-base font-semibold">Workspace access</h2>
        <div className="mt-4">
          {session.isPending || !session.data ? <Skeleton className="h-16 w-full" /> : <MembershipTable memberships={session.data.memberships} />}
        </div>
      </section>
      {organizationId ? <section className="rounded-xl border border-border bg-card p-4">
        <h2 className="font-semibold">Billing</h2>
        <p className="mt-1 text-sm text-muted-foreground">View the subscription and workspace usage.</p>
        <Button asChild variant="outline" className="mt-3"><Link href="/billing">Open billing</Link></Button>
      </section> : null}
      </div>
      <section id="settings-account" className="scroll-mt-20 rounded-xl border border-border bg-card p-4">
        <h2 className="text-base font-semibold">Account</h2>
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
                  aria-label="Name"
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
                  aria-label="Email"
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
      <div id="settings-members" className="grid scroll-mt-20 gap-4">
        {organizationId && isAdmin ? <InviteMemberCard organizationId={organizationId} /> : null}
        {organizationId ? <TeamCard organizationId={organizationId} isAdmin={isAdmin} members={team.data ?? []} onChanged={() => void queryClient.invalidateQueries({ queryKey: ["team", organizationId] })} /> : null}
      </div>
      <section id="settings-sessions" className="scroll-mt-20 rounded-xl border border-border bg-card p-4">
        <h2 className="text-base font-semibold">Session</h2>
        <p className="mt-1 text-sm text-muted-foreground">Signing out revokes the server session for this browser.</p>
        <Button className="mt-4" variant="outline" onClick={() => setSignOutOpen(true)}>
          Sign out
        </Button>
      </section>
      <div id="settings-connections" className="grid scroll-mt-20 gap-4">
      {organizationId ? <ProviderNotice organizationId={organizationId} detail /> : null}
      <section className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-base font-semibold text-foreground">Delivery</h2>
        <p className="mt-1 text-sm text-muted-foreground">How this workspace sends mail and runs automations. Secrets stay hidden.</p>
        {automations.isPending ? <Skeleton className="mt-4 h-16 w-full" /> : null}
        {automations.isError ? <div className="mt-4"><RequestError error={automations.error} /></div> : null}
        {automations.data ? (
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <div><dt className="text-xs text-muted-foreground">Email</dt><dd className="mt-1 capitalize">{automations.data.email_mode}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Calendar</dt><dd className="mt-1 capitalize">{automations.data.calendar_provider}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Automations</dt><dd className="mt-1">{automations.data.n8n_configured ? "Connected" : "Not connected"}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Callback key</dt><dd className="mt-1">{automations.data.webhook_configured ? "Ready" : "Not created"}</dd></div>
          </dl>
        ) : null}
      </section>
      {organizationId && isAdmin ? (
        <IntegrationSettings key={organizationId} {...integrationProps} />
      ) : organizationId ? (
        <section className="rounded-xl border border-border bg-card p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Integrations</h2><Badge variant="secondary">Read only</Badge>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">An administrator connects email, messaging, and calendar for this workspace.</p>
          <Button asChild variant="outline" className="mt-3"><Link href="/integrations">Browse integrations</Link></Button>
        </section>
      ) : null}
      </div>
      <SignOutDialog open={signOutOpen} onOpenChange={setSignOutOpen} />
      </div>
      </div>
    </div>
  );
}


function OrganizationCard({ organizationId, initialName, onSaved }: { organizationId: string; initialName: string; onSaved: () => void }) {
  const [name, setName] = useState(initialName);
  const [message, setMessage] = useState("");
  const save = useMutation({ mutationFn: () => updateOrganization(organizationId, name), onSuccess: () => { setMessage("Organization details saved."); onSaved(); }, onError: (e) => setMessage(e instanceof Error ? e.message : "Could not save organization.") });
  return <section className="rounded-[10px] bg-muted p-4"><h2 className="text-base text-foreground">Organization</h2><label className="mt-4 grid gap-2 text-sm"><span className="font-medium">Workspace name</span><Input value={name} onChange={(e) => setName(e.target.value)} disabled={save.isPending} /></label><Button className="mt-3" size="sm" onClick={() => save.mutate()} disabled={!name.trim() || save.isPending}>Save organization</Button>{message ? <p className="mt-2 text-xs text-muted-foreground" role="status">{message}</p> : null}</section>;
}

function TeamCard({ organizationId, isAdmin, members, onChanged }: { organizationId: string; isAdmin: boolean; members: TeamMember[]; onChanged: () => void }) {
  const [message, setMessage] = useState("");
  return <section className="rounded-[10px] bg-muted p-4"><h2 className="text-base text-foreground">Team</h2><div className="mt-4 space-y-2">{members.map((member) => <div key={member.membership_id} className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-secondary p-3 text-sm"><div><p className="font-medium">{member.full_name}</p><p className="text-muted-foreground">{member.email} · joined {new Date(member.joined_at).toLocaleDateString()}</p></div><div className="flex items-center gap-2"><select aria-label={`Role for ${member.email}`} value={member.role} disabled={!isAdmin} onChange={async (e) => { try { await updateMemberRole(organizationId, member.membership_id, e.target.value as TeamMember["role"]); onChanged(); } catch (err) { setMessage(err instanceof Error ? err.message : "Could not update role."); } }}><option value="admin">Admin</option><option value="staff">Staff</option></select>{isAdmin ? <Button size="sm" variant="ghost" onClick={async () => { if (!window.confirm("Remove this member?")) return; try { await removeMember(organizationId, member.membership_id); onChanged(); } catch (err) { setMessage(err instanceof Error ? err.message : "Could not remove member."); } }}>Remove</Button> : null}</div></div>)}</div>{message ? <p className="mt-2 text-xs text-destructive" role="alert">{message}</p> : null}</section>;
}

function InviteMemberCard({ organizationId }: { organizationId: string }) {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [pending, setPending] = useState(false);
  const invitations = useQuery({ queryKey: ["invitations", organizationId], queryFn: () => listInvitations(organizationId) });
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setToken(null);
    try {
      const invitation = await createInvitation(organizationId, email.trim());
      setToken(invitation.token);
      setEmail("");
      void invitations.refetch();
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error("Invitation could not be created."));
    } finally {
      setPending(false);
    }
  }
  return <section className="rounded-[10px] bg-muted p-4" aria-labelledby="invite-member-title">
    <h2 id="invite-member-title" className="text-base text-foreground">Invite a teammate</h2>
    <p className="mt-1 text-sm text-muted-foreground">Creates a staff invitation. The secure token is shown once because outbound email is not enabled.</p>
    <form className="mt-4 flex flex-col gap-2 sm:flex-row" onSubmit={submit}>
      <Input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="teammate@company.com" aria-label="Teammate email" />
      <Button type="submit" disabled={pending}>{pending ? "Creating…" : "Create invitation"}</Button>
    </form>
    {error ? <div className="mt-3"><RequestError error={error} /></div> : null}
    {token ? (
      <label className="mt-3 grid gap-2 rounded-md border border-warning/40 bg-background p-3 text-sm">
        Invitation link
        <Input readOnly value={new URL(`/invite/accept#token=${encodeURIComponent(token)}`, window.location.origin).href} onFocus={(event) => event.currentTarget.select()} />
        <span className="text-xs text-muted-foreground">Copy and send this link to your teammate. It is shown once.</span>
      </label>
    ) : null}
    {invitations.data?.length ? <div className="mt-4 space-y-2 text-sm"><h3 className="font-medium">Invitation status</h3>{invitations.data.map((item: InvitationStatus) => <div key={item.id} className="flex justify-between gap-3 text-muted-foreground"><span>{item.email}</span><span>{item.accepted_at ? "Accepted" : new Date(item.expires_at) <= new Date() ? "Expired" : "Pending"}</span></div>)}</div> : null}
  </section>;
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
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const matches = (name: string, group: string) =>
    (category === "all" || category === group) && name.toLowerCase().includes(query.trim().toLowerCase());
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
      <ExternalActivationChecklist />
      <div className="mt-4 flex flex-wrap gap-3">
        <Input aria-label="Search integrations" className="max-w-sm" placeholder="Search providers" value={query} onChange={(event) => setQuery(event.target.value)} />
        <select aria-label="Filter integrations by category" className="h-10 rounded-md border border-input bg-background px-3 text-sm" value={category} onChange={(event) => setCategory(event.target.value)}>
          <option value="all">All categories</option>
          <option value="ai">AI models</option>
          <option value="email">Email</option>
          <option value="messaging">Messaging</option>
          <option value="automation">Automation</option>
          <option value="infrastructure">Infrastructure</option>
        </select>
      </div>
      {error ? <div className="mt-4"><RequestError error={error} /></div> : null}
      {isLoading ? <Skeleton className="mt-4 h-32 w-full" /> : (
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          {matches("Language model Groq OpenAI", "ai") ? <ProviderCard key="chat" organizationId={organizationId} type="chat" title="Language model" record={byType.get("chat")} isAdmin={isAdmin} onChanged={onChanged} /> : null}
          {matches("Embeddings Ollama OpenAI", "ai") ? <ProviderCard key="embedding" organizationId={organizationId} type="embedding" title="Embeddings" record={byType.get("embedding")} isAdmin={isAdmin} onChanged={onChanged} /> : null}
          {matches("n8n automation", "automation") ? <N8nCard organizationId={organizationId} isAdmin={isAdmin} record={byType.get("n8n")} /> : null}
          {matches("MCP retrieval", "infrastructure") ? <McpCard /> : null}
          {matches("Email SMTP Resend", "email") ? <EmailSettingsCard organizationId={organizationId} isAdmin={isAdmin} record={byType.get("email")} onChanged={onChanged} /> : null}
          {matches("WhatsApp Meta Cloud", "messaging") ? <WhatsAppSettingsCard organizationId={organizationId} isAdmin={isAdmin} record={byType.get("whatsapp")} onChanged={onChanged} /> : null}
          {!matches("Language model Groq OpenAI", "ai") && !matches("Embeddings Ollama OpenAI", "ai") && !matches("n8n automation", "automation") && !matches("MCP retrieval", "infrastructure") && !matches("Email SMTP Resend", "email") && !matches("WhatsApp Meta Cloud", "messaging") ? <p className="rounded-md border border-dashed border-border p-5 text-sm text-muted-foreground lg:col-span-3">No integrations match this filter.</p> : null}
        </div>
      )}
    </section>
  );
}

const externalActivation = [
  {
    name: "WhatsApp",
    customer: "In WhatsApp Business, enter the Business Account ID, phone number ID, and access token. Save, then test the connection.",
    operator: "Publish an HTTPS address for this API, set the verification token and app secret on the server, and leave live messaging off until a reply is approved.",
  },
  {
    name: "Resend",
    customer: "In Email, add the Resend key, register the sending domain, publish the DNS records, and run verification.",
    operator: "Set the public campaign address, link secret, and Resend webhook secret. Live campaigns also require live email, which stays off until separately approved.",
  },
  {
    name: "Google Calendar",
    customer: "After Google sign-in is available, choose Connect Google, grant Calendar access, and run Test connection.",
    operator: "Enable the Calendar API, create a web OAuth client, and set the client id, secret, web origin, and callback ending in /api/v1/calendar/google/callback.",
  },
  {
    name: "Stripe",
    customer: "On Billing, choose a plan after test mode is on. Checkout updates the subscription when Stripe confirms it.",
    operator: "Provide a test secret key, an approved test price, and a signed webhook. Test mode does not create a live charge.",
  },
] as const;

function ExternalActivationChecklist() {
  return (
    <section className="rounded-xl border border-border bg-card p-4" aria-label="External activation checklist">
      <h2 className="text-base font-semibold">External accounts</h2>
      <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
        WhatsApp, Resend, Google Calendar, and Stripe stay off until you have the provider account and an operator has prepared this deployment. Saving a key here does not send a message or charge a card.
      </p>
      <ol className="mt-4 grid gap-3">
        {externalActivation.map((item) => (
          <li key={item.name} className="rounded-md border border-border p-3">
            <h3 className="text-sm font-medium">{item.name}</h3>
            <p className="mt-2 text-sm leading-6"><span className="font-medium">You </span>{item.customer}</p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground"><span className="font-medium text-foreground">Operator </span>{item.operator}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

const marketplace = [
  { type: "email", name: "Email", providers: "SMTP · Resend", category: "Messaging", benefit: "Test SMTP, manage sending domains, and review sandbox delivery settings.", activation: "Local Mailpit accepts sandbox mail. An administrator can test the Resend sending key without enabling live replies or campaigns.", icon: Mail },
  { type: "whatsapp", name: "WhatsApp Business", providers: "Meta Cloud API", category: "Messaging", benefit: "Receive customer messages in Inbox once your Meta webhook is verified.", activation: "Requires a Meta Business account. Saving settings does not send customer messages.", icon: MessageCircle },
  { type: "n8n", name: "n8n", providers: "n8n", category: "Automation", benefit: "Run workflows and track callbacks from ATLAS.", activation: "Requires your own n8n instance. Issue a callback key here, then confirm the first signed callback.", icon: Workflow },
  { type: "chat", name: "Language model", providers: "OpenAI · Groq", category: "Knowledge", benefit: "Power grounded answers and draft follow-ups.", activation: "The deployment model is used until this workspace saves its own provider.", icon: Bot },
  { type: "embedding", name: "Embeddings", providers: "OpenAI · Ollama", category: "Knowledge", benefit: "Find relevant passages across your organization's documents.", activation: "Ollama on this machine keeps passages local. OpenAI sends passages to an external account and needs approval.", icon: Search },
] satisfies { type: IntegrationType; name: string; providers: string; category: string; benefit: string; activation: string; icon: typeof Mail }[];

function IntegrationMarketplace({
  organizationId, isAdmin, integrations, isLoading, error, onChanged,
}: Parameters<typeof IntegrationSettings>[0]) {
  const calendarCallback = useSearchParams().get("calendar");
  const [view, setView] = useState<"Connected" | "Discover">("Discover");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All categories");
  const calendar = useQuery({
    queryKey: ["calendar-connection", organizationId],
    queryFn: () => getCalendarConnection(organizationId),
    enabled: Boolean(organizationId),
  });
  const showCalendar = (category === "All categories" || category === "Automation") &&
    "google calendar scheduling appointment availability".includes(search.trim().toLowerCase()) &&
    (view === "Discover" || Boolean(calendar.data?.connected || calendar.data?.connection_error));
  const widget = useQuery({
    queryKey: ["inbox-widget", organizationId],
    queryFn: () => getInboxWidget(organizationId),
    enabled: Boolean(organizationId && isAdmin),
  });
  const providers = useQuery({
    queryKey: ["provider-status", organizationId],
    queryFn: () => getProviderStatus(organizationId),
    enabled: Boolean(organizationId),
  });
  const n8n = useQuery({
    queryKey: ["webhook-key-status", organizationId],
    queryFn: () => getWebhookKeyStatus(organizationId),
    enabled: Boolean(organizationId && isAdmin),
  });
  const showWidget = (category === "All categories" || category === "Messaging") &&
    "website chat embed inbox".includes(search.trim().toLowerCase()) &&
    (view === "Discover" || Boolean(widget.data));
  const cards = marketplace.filter((item) => {
    const record = integrations.find((entry) => entry.integration_type === item.type);
    const deploymentReady = item.type === "chat" ? providers.data?.llm_ready : item.type === "embedding" ? providers.data?.embedding_ready : false;
    const connected = item.type === "n8n" ? Boolean(n8n.data) : Boolean(record) || Boolean(deploymentReady);
    return (view === "Discover" || connected) &&
      (category === "All categories" || category === item.category) &&
      `${item.name} ${item.providers} ${item.benefit}`.toLowerCase().includes(search.trim().toLowerCase());
  });

  return (
    <section className="space-y-5" aria-label="Integration marketplace">
      <ExternalActivationChecklist />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Marketplace view" className="flex gap-1 rounded-lg border border-border bg-muted p-1">
          {(["Connected", "Discover"] as const).map((name) => (
            <Button key={name} size="sm" variant={view === name ? "outline" : "ghost"}
              aria-pressed={view === name} onClick={() => setView(name)}>{name}</Button>
          ))}
        </div>
        {!isAdmin ? <Badge variant="secondary">Read only</Badge> : null}
      </div>
      <div className="flex flex-wrap gap-3">
        <Input aria-label="Search integrations" placeholder="Search integrations" className="sm:max-w-xs"
          value={search} onChange={(event) => setSearch(event.target.value)} />
        <select aria-label="Filter integrations by category" className="h-10 max-w-full rounded-md border border-input bg-background px-3 text-sm"
          value={category} onChange={(event) => setCategory(event.target.value)}>
          {["All categories", "Messaging", "Automation", "Knowledge"].map((name) => <option key={name}>{name}</option>)}
        </select>
      </div>
      {error ? <RequestError error={error} /> : isLoading ? (
        <div role="status" aria-label="Loading integrations"><Skeleton className="h-40 w-full" /></div>
      ) : cards.length || showWidget || showCalendar ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {showCalendar ? (
            calendar.error ? <RequestError error={calendar.error} /> :
              <CalendarConnectionCard organizationId={organizationId} isAdmin={isAdmin}
                connection={calendar.data} callback={calendarCallback} />
          ) : null}
          {cards.map((item) => {
            const record = integrations.find((entry) => entry.integration_type === item.type);
            const status = !isAdmin ? "Admin managed" : item.type === "n8n"
              ? (n8n.data?.revoked_at ? "Disconnected" : n8n.data?.last_accepted_at ? "Callback verified" : n8n.data ? "Awaiting callback" : "Managed by deployment")
              : item.type === "chat" || item.type === "embedding"
                ? modelConnection(record, item.type === "chat" ? providers.data?.llm_ready : providers.data?.embedding_ready)
                : integrationConnection(record);
            const props = { organizationId, isAdmin, record, onChanged };
            return (
              <Dialog key={item.type}>
                <article className="flex min-w-0 flex-col rounded-xl border border-border bg-card p-5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <span className="rounded-lg bg-accent p-2.5 text-accent-foreground"><item.icon size={20} aria-hidden /></span>
                    <Badge variant="secondary">{status}</Badge>
                  </div>
                  <h2 className="mt-4 font-semibold">{item.name}</h2>
                  <p className="mt-1 text-xs text-muted-foreground">{item.providers}</p>
                  <p className="mt-3 flex-1 text-sm leading-6 text-muted-foreground">{item.benefit}</p>
                  <p className="mb-5 mt-2 text-xs leading-5 text-muted-foreground">{item.activation}</p>
                  <DialogTrigger asChild>
                    <Button variant="outline" size="sm" className="self-start" aria-label={`${item.name} settings`}>
                      {isAdmin && (record?.status === "disabled" || record?.status === "verification_failed") ? "Recover connection" : isAdmin && item.type !== "n8n" ? "Configure" : "View details"}
                      <ChevronRight size={15} aria-hidden />
                    </Button>
                  </DialogTrigger>
                </article>
                <DialogContent className="max-h-[90dvh] w-[calc(100%-2rem)] max-w-2xl overflow-y-auto">
                  <DialogTitle>{item.name}</DialogTitle>
                  <DialogDescription>{item.benefit} {isAdmin ? "Enter your provider settings below and test the connection where available." : "An organization administrator manages this connection."}</DialogDescription>
                  {!isAdmin ? null : item.type === "email" ? <EmailSettingsCard {...props} /> :
                    item.type === "whatsapp" ? <WhatsAppSettingsCard {...props} /> :
                    item.type === "n8n" ? <N8nCard organizationId={organizationId} isAdmin={isAdmin} record={record} /> :
                    <ProviderCard {...props} type={item.type} title={item.name} />}
                  <div className="mt-4 flex justify-end">
                    <DialogClose asChild><Button variant="outline">Close</Button></DialogClose>
                  </div>
                </DialogContent>
              </Dialog>
            );
          })}
          {showWidget ? <article className="flex min-w-0 flex-col rounded-xl border border-border bg-card p-5">
            <div className="flex items-center justify-between gap-2">
              <span className="rounded-lg bg-accent p-2.5 text-accent-foreground"><MessageCircle size={20} aria-hidden /></span>
              <Badge variant="secondary">{!isAdmin ? "Admin managed" : widget.isError ? "Unavailable" : widget.isPending ? "Checking" : widget.data?.enabled && widget.data.allowed_domains.length ? "Enabled" : widget.data ? "Paused" : "Not configured"}</Badge>
            </div>
            <h2 className="mt-4 font-semibold">Website chat</h2>
            <p className="mt-1 text-xs text-muted-foreground">ATLAS embed</p>
            <p className="mb-5 mt-3 flex-1 text-sm leading-6 text-muted-foreground">Open a chat from your website and handle customer messages in Inbox.</p>
            {isAdmin ? <div className="self-start"><WidgetSettingsDialog organizationId={organizationId} /></div> : <Button asChild size="sm" variant="outline" className="self-start"><Link href="/inbox">Open Inbox</Link></Button>}
          </article> : null}
        </div>
      ) : (
        <p className="rounded-xl border border-dashed border-border p-8 text-sm text-muted-foreground">
          {search || category !== "All categories" ? "No integrations match your filters." : "No organization connections yet. Open Discover to browse available integrations."}
        </p>
      )}
    </section>
  );
}

function MessagingConnectionControls({ organizationId, record, type, onChanged, onVersion }: {
  organizationId: string; record: IntegrationMetadata; type: "email" | "whatsapp";
  onChanged: () => void; onVersion: (version: number) => void;
}) {
  const [notice, setNotice] = useState("");
  const verify = useMutation({
    mutationFn: () => verifyIntegration(organizationId, type),
    onSuccess: (result) => { setNotice(result.detail); onChanged(); },
  });
  const change = useMutation({
    mutationFn: (action: "enable" | "disable" | "revoke") => integrationAction(organizationId, type, action, record.credential_version),
    onSuccess: (result) => {
      onVersion(result.credential_version);
      setNotice(result.status === "disabled" ? "Integration disconnected." : "Integration enabled. Test the connection to verify it.");
      onChanged();
    },
  });
  const busy = verify.isPending || change.isPending;
  return (
    <div className="mt-4 grid gap-2 border-t border-border pt-3">
      <div className="flex flex-wrap items-center gap-2">
        {record.status === "disabled" ? <Button size="sm" variant="outline" disabled={busy} onClick={() => change.mutate("enable")}>Enable connection</Button> : <>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => verify.mutate()}>{verify.isPending ? "Testing…" : type === "email" ? "Test SMTP connection" : "Test connection"}</Button>
          <ConfirmButton size="sm" label="Disconnect" confirmLabel="Confirm disconnect" pendingLabel="Disconnecting…" pending={busy} onConfirm={() => change.mutate("disable")} />
        </>}
        {record.has_credentials ? <ConfirmButton size="sm" label="Remove credentials" confirmLabel="Confirm removal" pendingLabel="Removing…" pending={busy} onConfirm={() => change.mutate("revoke")} /> : null}
      </div>
      {record.verified_at ? <p className="text-xs text-muted-foreground">Last checked {new Date(record.verified_at).toLocaleString()}</p> : null}
      {notice ? <p className="text-xs text-muted-foreground" role="status">{notice}</p> : null}
      {verify.error || change.error ? <RequestError error={verify.error ?? change.error} /> : null}
    </div>
  );
}

function WhatsAppTestReply({ organizationId, expectedVersion }: { organizationId: string; expectedVersion: number }) {
  const queryClient = useQueryClient();
  const [phone, setPhone] = useState("");
  const status = useQuery({
    queryKey: ["whatsapp-test-reply", organizationId],
    queryFn: () => getWhatsAppTestStatus(organizationId),
  });
  const approve = useMutation({
    mutationFn: (next: string | null) => approveWhatsAppTestRecipient(organizationId, next, expectedVersion),
    onSuccess: () => {
      setPhone("");
      void queryClient.invalidateQueries({ queryKey: ["whatsapp-test-reply", organizationId] });
    },
  });
  const current = status.data;
  const locked = current?.test_reply_sent || current?.test_reply_pending;
  return (
    <section className="mt-4 grid gap-3 border-t border-border pt-3" aria-label="Restricted test reply">
      <h4 className="text-sm font-medium">Restricted test reply</h4>
      <div className="flex flex-wrap gap-2">
        <Badge variant="secondary">Production messaging {current?.production_messaging_enabled ? "Enabled" : "Disabled"}</Badge>
        <Badge variant="secondary">Test number {current?.test_number_confirmed ? "Confirmed" : "Not confirmed"}</Badge>
        <Badge variant="secondary">{current?.recipient_approved ? `Recipient ····${current.recipient_suffix}` : "Recipient not approved"}</Badge>
        <Badge variant="secondary">{current?.test_reply_sent ? "Test reply sent" : current?.test_reply_pending ? "Test reply in progress" : "Test reply not sent"}</Badge>
      </div>
      <p className="text-xs text-muted-foreground">One session message can be approved from Inbox for a number that already messaged this workspace. This does not enable customer messaging.</p>
      {locked ? null : (
        <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); approve.mutate(phone.trim()); }}>
          <label className="grid gap-1 text-sm">Approved test recipient
            <Input required inputMode="tel" autoComplete="off" placeholder="Number with country code" value={phone} disabled={approve.isPending} onChange={(event) => setPhone(event.target.value)} />
          </label>
          <Button size="sm" type="submit" disabled={approve.isPending || !phone.trim()}>Approve recipient</Button>
          {current?.recipient_approved ? <Button size="sm" type="button" variant="outline" disabled={approve.isPending} onClick={() => approve.mutate(null)}>Clear recipient</Button> : null}
        </form>
      )}
      {approve.error ? <RequestError error={approve.error} /> : null}
    </section>
  );
}

function WhatsAppSettingsCard({ organizationId, isAdmin, record, onChanged }: { organizationId: string; isAdmin: boolean; record?: IntegrationMetadata; onChanged: () => void }) {
  const [version, setVersion] = useState(record?.credential_version);
  const [account, setAccount] = useState(String(record?.config.business_account_id ?? ""));
  const [phone, setPhone] = useState(String(record?.config.phone_number_id ?? ""));
  const [token, setToken] = useState("");
  const save = useMutation({
    mutationFn: () => saveIntegration(organizationId, "whatsapp", {
      provider: "meta", config: { business_account_id: account.trim(), phone_number_id: phone.trim() },
      ...(token ? { credentials: JSON.stringify({ access_token: token.trim() }) } : {}), expected_version: version,
    }),
    onSuccess: (result) => { setVersion(result.credential_version); setToken(""); onChanged(); },
  });
  const callback = `/api/v1/organizations/${organizationId}/inbox/webhooks/whatsapp`;
  return (
    <section className="mt-4 rounded-xl border border-border bg-background p-4" aria-label="WhatsApp connection">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="font-medium">Meta Cloud API connection</h3>
        <Badge variant="secondary">{integrationConnection(record)}</Badge>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">Verified inbound text messages appear in Inbox. Customer messaging stays off until an operator enables it. A restricted test reply can send one session message to a number that already wrote in.</p>
      {record && isAdmin ? <WhatsAppTestReply organizationId={organizationId} expectedVersion={version ?? record.credential_version} /> : null}
      <form className="mt-4 grid gap-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1 text-sm">Business Account ID<Input required inputMode="numeric" pattern="[0-9]{1,32}" value={account} disabled={!isAdmin || save.isPending} onChange={(e) => setAccount(e.target.value)} /></label>
          <label className="grid gap-1 text-sm">Phone number ID<Input required inputMode="numeric" pattern="[0-9]{1,32}" value={phone} disabled={!isAdmin || save.isPending} onChange={(e) => setPhone(e.target.value)} /></label>
        </div>
        {isAdmin ? <>
          <label className="grid gap-1 text-sm">{record?.has_credentials ? "Replace access token" : "Access token"}
            <Input type="password" autoComplete="new-password" required={!record?.has_credentials} disabled={save.isPending} value={token} onChange={(e) => setToken(e.target.value)} />
          </label>
          <Button size="sm" type="submit" className="justify-self-start" disabled={save.isPending}>Save WhatsApp settings</Button>
        </> : null}
      </form>
      {save.error ? <div className="mt-3"><RequestError error={save.error} /></div> : null}
      {record?.last_inbound_at ? <p className="mt-3 text-xs text-muted-foreground">Last customer message {new Date(record.last_inbound_at).toLocaleString()}</p> : null}
      {record && isAdmin ? <MessagingConnectionControls organizationId={organizationId} type="whatsapp" record={record} onChanged={onChanged} onVersion={setVersion} /> : null}
      <details className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">
        <summary className="cursor-pointer font-medium text-foreground">Connection steps</summary>
        <ol className="mt-2 list-decimal space-y-1 pl-4">
          <li>Enter the Business Account ID, phone number ID, and access token from Meta, then save and test the connection.</li>
          <li>Give Meta this callback path on the public HTTPS address your operator provides.</li>
          <li>The verification token and app secret stay on the server. They are not entered here.</li>
          <li>Approve one test recipient to send a single session reply. That does not enable customer messaging or paid templates.</li>
        </ol>
        <code className="mt-2 block break-all rounded-md bg-muted p-2">{callback}</code>
      </details>
    </section>
  );
}

function EmailSettingsCard({
  organizationId, isAdmin, record, onChanged,
}: { organizationId: string; isAdmin: boolean; record?: IntegrationMetadata; onChanged: () => void }) {
  const queryClient = useQueryClient();
  const domains = useQuery({ queryKey: ["email-domains", organizationId], queryFn: () => getEmailDomains(organizationId), enabled: isAdmin });
  const delivery = useQuery({ queryKey: ["automations", organizationId], queryFn: () => getAutomations(organizationId) });
  const live = delivery.data?.email_mode === "live";
  const [version, setVersion] = useState(record?.credential_version);
  const [host, setHost] = useState(String(record?.config.host ?? "127.0.0.1"));
  const [port, setPort] = useState(String(record?.config.port ?? "1025"));
  const [from, setFrom] = useState(String(record?.config.from_address ?? "atlas@localhost"));
  const [security, setSecurity] = useState(record?.config.use_tls ? "tls" : record?.config.starttls ? "starttls" : "local");
  const [allowLiveReplies, setAllowLiveReplies] = useState(record?.config.live_delivery_enabled === true);
  const [smtpUser, setSmtpUser] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [resendKey, setResendKey] = useState("");
  const [domain, setDomain] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const editingAuthentication = Boolean(smtpUser.trim() || smtpPassword);
  const authenticationValid = !editingAuthentication || Boolean(smtpUser.trim() && smtpPassword && security !== "local");
  const credentialUpdate = {
    ...(resendKey.trim() ? { resend_api_key: resendKey.trim() } : {}),
    ...(editingAuthentication ? { username: smtpUser.trim(), password: smtpPassword } : {}),
  };
  const save = useMutation({
    mutationFn: () => saveIntegration(organizationId, "email", {
      provider: "smtp", config: { ...record?.config, host: host.trim(), port: Number(port), from_address: from.trim(), use_tls: security === "tls", starttls: security === "starttls", ...(live ? { live_delivery_enabled: allowLiveReplies } : {}) },
      ...(Object.keys(credentialUpdate).length ? { credentials: JSON.stringify(credentialUpdate), merge_email_credentials: true } : {}),
      expected_version: version,
    }),
    onSuccess: (saved) => { setVersion(saved.credential_version); setResendKey(""); setSmtpUser(""); setSmtpPassword(""); setMessage("Saved. Test the connection and check the sending domain."); onChanged(); void queryClient.invalidateQueries({ queryKey: ["email-domains", organizationId] }); },
    onError: (error) => setMessage(error instanceof Error ? error.message : "Could not save email settings."),
  });
  const register = useMutation({ mutationFn: () => registerEmailDomain(organizationId, domain), onSuccess: () => { setDomain(""); setMessage("Domain registered. Publish the DNS records shown below."); void queryClient.invalidateQueries({ queryKey: ["email-domains", organizationId] }); }, onError: (error) => setMessage(error instanceof Error ? error.message : "Could not register domain.") });
  const check = useMutation({ mutationFn: (id: string) => checkEmailDomain(organizationId, id), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["email-domains", organizationId] }), onError: (error) => setMessage(error instanceof Error ? error.message : "Verification check failed.") });
  const revoke = useMutation({ mutationFn: (id: string) => revokeEmailDomain(organizationId, id), onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["email-domains", organizationId] }), onError: (error) => setMessage(error instanceof Error ? error.message : "Could not revoke domain.") });
  const emailRelayFields = <>
    <div className="grid gap-3 md:grid-cols-3">
      <label className="grid gap-1 text-sm"><span>SMTP host</span><Input value={host} onChange={(e) => setHost(e.target.value)} /></label>
      <label className="grid gap-1 text-sm"><span>SMTP port</span><Input value={port} onChange={(e) => setPort(e.target.value)} /></label>
      <label className="grid gap-1 text-sm"><span>Sender address</span><Input value={from} onChange={(e) => setFrom(e.target.value)} /></label>
    </div>
    <label className="grid gap-1 text-sm">SMTP security
      <select className="h-10 rounded-md border border-input bg-background px-2 text-sm" value={security} onChange={(e) => setSecurity(e.target.value)}>
        <option value="local">Local SMTP without authentication</option><option value="starttls">STARTTLS</option><option value="tls">TLS</option>
      </select>
    </label>
    {security !== "local" ? <div className="grid gap-3 sm:grid-cols-2">
      <label className="grid gap-1 text-sm">SMTP username<Input value={smtpUser} onChange={(e) => setSmtpUser(e.target.value)} autoComplete="off" /></label>
      <label className="grid gap-1 text-sm">SMTP password<Input type="password" value={smtpPassword} onChange={(e) => setSmtpPassword(e.target.value)} autoComplete="new-password" /></label>
    </div> : null}
    <label className="grid min-w-0 gap-1 text-sm">Resend API key
      <Input type="password" autoComplete="new-password" value={resendKey} onChange={(e) => setResendKey(e.target.value)} placeholder="Leave blank to keep the current key" />
    </label>
    {live ? <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={allowLiveReplies} onChange={(event) => setAllowLiveReplies(event.target.checked)} /> Enable approved live replies for this workspace</label> : null}
    {!authenticationValid ? <p className="text-xs text-warning">Enter the SMTP username and password together and select TLS or STARTTLS.</p> : null}
    <Button size="sm" className="justify-self-start" onClick={() => save.mutate()} disabled={!authenticationValid || save.isPending}>{save.isPending ? "Saving…" : "Save email settings"}</Button>
  </>;
  return <div className="rounded-[10px] border border-border bg-background p-4 lg:col-span-3">
    <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-medium">Email delivery</h3><p className="mt-1 text-xs text-muted-foreground">SMTP for approved replies and Resend for campaign delivery.</p></div><Badge variant="secondary">{live ? "LIVE ENVIRONMENT" : delivery.data ? "MAILPIT SANDBOX" : "DELIVERY STATUS UNAVAILABLE"}</Badge></div>
    <p className="mt-3 rounded-md border border-border bg-accent px-3 py-2 text-sm leading-6 text-foreground">{live ? "Live replies require a verified domain, a verified SMTP connection and workspace approval." : "Approved sandbox replies already go to the mailbox on this machine. No SMTP change is required."}</p>
    {live ? null : <p className="mt-3 text-sm leading-6 text-muted-foreground">Open the section below only when you are preparing Resend or a live relay. Those fields do not send customer mail while this workspace stays in sandbox.</p>}
    {isAdmin ? <ResendAdministratorTest organizationId={organizationId} credentialVersion={version} /> : null}
    {isAdmin ? (live ? <div className="mt-4 grid gap-3">{emailRelayFields}</div> : (
      <details className="mt-4 border-t border-border pt-3">
        <summary className="cursor-pointer text-sm font-medium">Prepare live SMTP and Resend</summary>
        <div className="mt-3 grid gap-3">{emailRelayFields}</div>
      </details>
    )) : null}
    {record && isAdmin ? <MessagingConnectionControls organizationId={organizationId} type="email" record={record} onChanged={onChanged} onVersion={setVersion} /> : null}
    <details className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">
      <summary className="cursor-pointer font-medium text-foreground">Inbound email gateway</summary>
      <p className="mt-2">Ask your deployment operator to forward signed email events to this workspace callback.</p>
      <code className="mt-2 block break-all rounded-md bg-muted p-2">{`/api/v1/organizations/${organizationId}/inbox/webhooks/inbound`}</code>
      {record?.last_inbound_at ? <p className="mt-2">Last inbound email {new Date(record.last_inbound_at).toLocaleString()}</p> : null}
    </details>
    <div className="mt-5 border-t border-border pt-4"><h4 className="text-sm font-medium">Sending domains</h4><p className="mt-1 text-xs text-muted-foreground">Register a domain, publish the provider DNS records, then refresh verification. Domain administration needs a full-access Resend key. A sending key is enough for the administrator test.</p>{isAdmin ? <div className="mt-3 flex gap-2"><Input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="mail.example.com" /><Button size="sm" onClick={() => register.mutate()} disabled={!domain || register.isPending}>Register domain</Button></div> : null}
      <div className="mt-3 space-y-3">{!isAdmin ? <p className="text-sm text-muted-foreground">Workspace administrators manage sending domains.</p> : domains.isPending ? <Skeleton className="h-12 w-full" /> : domains.error ? <RequestError error={domains.error} /> : domains.data?.length ? domains.data.map((item) => <div key={item.id} className="rounded-md border border-border p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium">{item.domain}</span><Badge variant="secondary">{item.status === "verified" && item.credential_version !== version ? "Recheck required" : item.status}</Badge></div>{item.dns_records.length ? <div className="mt-2 overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr className="text-muted-foreground"><th className="pr-3">Type</th><th className="pr-3">Host</th><th>Value</th></tr></thead><tbody>{item.dns_records.map((dns) => <tr key={`${dns.record_type}-${dns.name}`}><td className="pr-3">{dns.record_type}</td><td className="max-w-[220px] truncate pr-3">{dns.name}</td><td className="max-w-[320px] truncate">{dns.value}</td></tr>)}</tbody></table></div> : null}{isAdmin && item.status !== "revoked" ? <div className="mt-3 flex gap-2"><Button size="sm" variant="outline" disabled={check.isPending || revoke.isPending} onClick={() => check.mutate(item.id)}>Verify domain</Button><Button size="sm" variant="ghost" onClick={() => { if (window.confirm(`Revoke ${item.domain}?`)) revoke.mutate(item.id); }}>Revoke</Button></div> : null}</div>) : <p className="text-sm text-muted-foreground">No sending domains registered.</p>}</div>
    </div>{message ? <p className="mt-3 text-xs text-muted-foreground" role="status">{message}</p> : null}
  </div>;
}

function ResendAdministratorTest({ organizationId, credentialVersion }: { organizationId: string; credentialVersion?: number }) {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["resend-test", organizationId], queryFn: () => getResendTestStatus(organizationId) });
  const [owner, setOwner] = useState("");
  const [recipient, setRecipient] = useState("delivered@resend.dev");
  const [notice, setNotice] = useState<string | null>(null);
  const approved = status.data?.approved_recipient;
  useEffect(() => {
    if (approved) setOwner((current) => current || approved);
  }, [approved]);
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["resend-test", organizationId] });
  const approve = useMutation({
    mutationFn: () => approveResendTestRecipient(organizationId, owner.trim() || null, credentialVersion ?? 0),
    onSuccess: (saved) => {
      setNotice(saved.approved_recipient ? `Approved ${saved.approved_recipient} for the administrator test.` : "Cleared the approved test recipient.");
      refresh();
    },
  });
  const send = useMutation({
    mutationFn: () => sendResendTest(organizationId, recipient),
    onSuccess: (result) => {
      setNotice(`Resend accepted the test for ${result.recipient}. Message ${result.message_id}.`);
      refresh();
    },
  });
  const recipients = [
    ...(approved ? [approved] : []),
    ...(status.data?.official_recipients ?? []),
  ];
  const states = status.data ? [
    ["Sending key", status.data.credential_configured ? "Configured" : "Not configured"],
    ["Test delivery", status.data.test_delivery_verified ? "Verified" : "Not verified"],
    ["Sending domain", status.data.sending_domain_verified ? "Verified" : "Not verified"],
    ["Production delivery", status.data.production_delivery_enabled ? "Enabled" : "Disabled"],
  ] : [];
  return <section aria-label="Resend administrator test" className="mt-4 rounded-md border border-border p-3">
    <h4 className="text-sm font-medium">Administrator test</h4>
    <p className="mt-1 text-xs leading-5 text-muted-foreground">Sends one message from {status.data?.test_sender ?? "onboarding@resend.dev"} with the stored sending key. This does not send customer mail or start a campaign.</p>
    {status.isPending ? <Skeleton className="mt-3 h-16 w-full" /> : status.error ? <div className="mt-3"><RequestError error={status.error} /></div> : <dl className="mt-3 grid gap-2 sm:grid-cols-2">
      {states.map(([label, value]) => <div key={label} className="flex items-center justify-between gap-2 rounded-md bg-accent px-3 py-2"><dt className="text-xs text-muted-foreground">{label}</dt><dd><Badge variant="secondary">{value}</Badge></dd></div>)}
    </dl>}
    <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
      <label className="grid gap-1 text-sm">Account-owner address
        <Input value={owner} onChange={(event) => setOwner(event.target.value)} autoComplete="off" placeholder="The address registered on the Resend account" />
      </label>
      <Button size="sm" className="self-end" variant="outline" disabled={!credentialVersion || approve.isPending} onClick={() => approve.mutate()}>{owner.trim() ? "Approve address" : "Clear address"}</Button>
    </div>
    <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
      <label className="grid gap-1 text-sm">Test recipient
        <select className="h-10 rounded-md border border-input bg-background px-2 text-sm" value={recipient} onChange={(event) => setRecipient(event.target.value)}>
          {recipients.map((item) => <option key={item} value={item}>{item === approved ? `Account owner · ${item}` : item}</option>)}
        </select>
      </label>
      <Button size="sm" className="self-end" disabled={!status.data?.credential_configured || send.isPending} onClick={() => {
        if (window.confirm(`Send one Resend test to ${recipient}?`)) send.mutate();
      }}>{send.isPending ? "Sending…" : "Send test email"}</Button>
    </div>
    {approve.error || send.error ? <div className="mt-3"><RequestError error={approve.error ?? send.error} /></div> : null}
    {notice ? <p className="mt-3 text-xs text-muted-foreground" role="status">{notice}</p> : null}
    {status.data?.last_test_message_id ? <p className="mt-2 text-xs text-muted-foreground">Last accepted test to {status.data.last_test_recipient} · {status.data.provider_confirmation === "retrieved" ? "Resend returned the message" : "Resend accepted the message"} · {status.data.last_test_message_id}</p> : null}
  </section>;
}

function reindexFailure(code: string) {
  if (code === "embedding_configuration_changed") return "Provider settings changed during the build. Reload and try again.";
  if (code === "embedding_unavailable") return "Ollama or the embedding endpoint could not be reached. The previous index is unchanged.";
  if (code === "embedding_dimension_mismatch") return "The model returned a different vector width. Choose 768 or 1536 to match the model.";
  if (code === "reindex_provider_invalid") return "Use Ollama on this machine, OpenAI, or this deployment's embedding endpoint.";
  return "Check the target credentials, endpoint, and vector dimensions before retrying.";
}

function ProviderCard({
  organizationId, type, title, record, isAdmin, onChanged,
}: { organizationId: string; type: Exclude<IntegrationType, "n8n">; title: string; record?: IntegrationMetadata; isAdmin: boolean; onChanged: () => void }) {
  const cache = useQueryClient();
  const [version, setVersion] = useState(record?.credential_version);
  const [provider, setProvider] = useState(record?.provider ?? (type === "chat" ? "groq" : "ollama"));
  const [model, setModel] = useState(String(record?.config.model ?? (type === "chat" ? "openai/gpt-oss-20b" : "nomic-embed-text:v1.5")));
  const [baseUrl, setBaseUrl] = useState(String(record?.config.base_url ?? (type === "chat" ? "https://api.groq.com/openai/v1" : "http://127.0.0.1:11434/v1")));
  const [dimensions, setDimensions] = useState(String(record?.config.dimensions ?? (type === "embedding" ? "768" : "")));
  const [secret, setSecret] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const reindexKey = ["embedding-reindex", organizationId];
  const reindex = useQuery({
    queryKey: reindexKey,
    queryFn: () => getEmbeddingReindex(organizationId),
    enabled: type === "embedding" && isAdmin,
    refetchInterval: (query) => query.state.data?.status === "building" ? 1_500 : false,
  });
  const reindexStatus = reindex.data?.status;
  useEffect(() => {
    if (reindexStatus === "completed") {
      void cache.invalidateQueries({ queryKey: ["integrations", organizationId] });
      void cache.invalidateQueries({ queryKey: ["provider-status", organizationId] });
    }
  }, [cache, organizationId, reindexStatus]);
  const rebuild = useMutation({
    mutationFn: () => startEmbeddingReindex(organizationId, {
      provider, base_url: baseUrl.trim(), model: model.trim(), dimensions: Number(dimensions),
      credentials: secret || undefined, expected_version: record?.credential_version ?? version,
    }),
    onSuccess: (job) => {
      cache.setQueryData(reindexKey, job);
      setSecret("");
      setMessage(null);
    },
  });
  const cancelBuild = useMutation({
    mutationFn: () => cancelEmbeddingReindex(organizationId),
    onSuccess: () => void cache.invalidateQueries({ queryKey: reindexKey }),
  });
  const save = useMutation({ mutationFn: () => saveIntegration(organizationId, type, { provider, config: { base_url: baseUrl, model, ...(type === "embedding" ? { dimensions: Number(dimensions) } : {}) }, ...(secret ? { credentials: secret } : {}), expected_version: record?.credential_version ?? version }), onSuccess: (saved) => { setVersion(saved.credential_version); setSecret(""); setMessage("Configuration saved. Run a connection test before relying on it."); onChanged(); }, onError: (err) => setMessage(err instanceof Error ? err.message : "Could not save configuration.") });
  const verify = useMutation({ mutationFn: () => verifyIntegration(organizationId, type), onSuccess: (result) => { setMessage(result.verified ? result.detail : `Verification failed: ${result.detail}`); onChanged(); }, onError: (err) => setMessage(err instanceof Error ? err.message : "Verification failed.") });
  const action = useMutation({ mutationFn: (kind: "enable" | "disable" | "revoke") => integrationAction(organizationId, type, kind, version ?? 0), onSuccess: (saved, kind) => { setVersion(saved.credential_version); setMessage(kind === "revoke" ? "Credential revoked. The integration is disabled." : `Integration ${kind}d.`); onChanged(); }, onError: (err) => setMessage(err instanceof Error ? err.message : "Could not update integration.") });
  const fallback = !record;
  return (
    <section aria-label={title} className="min-w-0 rounded-[10px] border border-border bg-background p-4">
      <div className="flex items-start justify-between gap-2"><div><h3 className="font-medium">{title}</h3><p className="mt-1 text-xs text-muted-foreground">{fallback ? "Using the server default. Saving here creates a workspace override." : `Workspace configuration · version ${record.credential_version}`}</p>{record?.has_credentials ? <p className="mt-2 text-xs font-medium text-success">Key installed</p> : null}{record?.status === "disabled" ? <p className="mt-2 text-xs font-medium text-warning">This connection is disabled.</p> : null}</div><Badge variant="secondary">{fallback ? "Managed by deployment" : "Workspace"}</Badge></div>
      {type === "embedding" ? <ol className="mt-3 list-decimal space-y-1 pl-4 text-xs leading-5 text-muted-foreground"><li>Choose Ollama on this machine, or OpenAI when an external account is approved.</li><li>Save, then test the connection. Local Ollama does not need an API key.</li><li>When documents already exist, build a replacement index before switching models. Cancel leaves the current index in place.</li></ol> : null}
      <div className="mt-4 grid gap-3">
        <label className="grid gap-1 text-sm"><span>Provider</span><select disabled={!isAdmin} value={provider} onChange={(event) => {
          const next = event.target.value;
          setProvider(next);
          if (type !== "embedding") return;
          if (next === "ollama") {
            setBaseUrl("http://127.0.0.1:11434/v1");
            setDimensions("768");
            setModel((current) => current.trim() && current !== "text-embedding-3-small" ? current : "nomic-embed-text:v1.5");
          } else {
            setBaseUrl("https://api.openai.com/v1");
            setDimensions("1536");
            setModel((current) => current === "nomic-embed-text:v1.5" ? "text-embedding-3-small" : current);
          }
        }} className="h-10 rounded-md border border-input bg-background px-3"><option value={type === "chat" ? "groq" : "ollama"}>{type === "chat" ? "Groq" : "Ollama on this machine"}</option><option value="openai">OpenAI</option></select></label>
        <label className="grid gap-1 text-sm"><span>Model</span><Input disabled={!isAdmin} value={model} onChange={(event) => setModel(event.target.value)} /></label>
        <label className="grid gap-1 text-sm"><span>Base URL</span><Input disabled={!isAdmin} value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} /></label>
        {type === "embedding" ? <label className="grid gap-1 text-sm"><span>Vector dimensions</span><select disabled={!isAdmin} value={dimensions} onChange={(event) => setDimensions(event.target.value)} className="h-10 rounded-md border border-input bg-background px-3"><option value="768">768 · Ollama</option><option value="1536">1536 · OpenAI-compatible</option></select></label> : null}
        {type === "embedding" && record && dimensions !== String(record.config.dimensions ?? "768") ? <p className="text-xs leading-5 text-warning">Changing these settings requires a full reindex. Build a replacement index before saving, or the current index stays in place.</p> : null}
        {isAdmin && !(type === "embedding" && provider === "ollama") ? <label className="grid gap-1 text-sm"><span>{record?.has_credentials ? "Replace API key" : "API key"}</span><Input type="password" autoComplete="new-password" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder={record?.has_credentials ? "Leave blank to keep current key" : "Enter key"} /></label> : null}
        {type === "embedding" && provider === "ollama" ? <p className="text-xs leading-5 text-muted-foreground">Local Ollama does not need an API key. Use port 11434 on this machine when the API runs here. A containerized API should use its Ollama service address instead.</p> : null}
      </div>
      {type === "embedding" && isAdmin ? <section aria-label="Embedding index migration" className="mt-4 space-y-2 rounded-lg border border-border p-3">
        <h4 className="text-sm font-semibold">Replace the knowledge index</h4>
        <p className="text-xs leading-5 text-muted-foreground">Build a replacement with the target settings above. Search keeps using the active index until the full build succeeds. Source files and citations are preserved.</p>
        {reindex.data ? <p role="status" className="text-sm">
          {reindexStatus === "building" ? `Building ${reindex.data.model} · ${reindex.data.staged_chunks} of ${reindex.data.total_chunks} passages` :
            reindexStatus === "completed" ? `${reindex.data.model} is active.` :
            reindexStatus === "failed" ? "Build failed. The previous index is still active." : "Build cancelled. The previous index is still active."}
        </p> : null}
        {reindex.data?.error_code ? <p className="text-xs text-muted-foreground">{reindexFailure(reindex.data.error_code)}</p> : null}
        {reindex.error || rebuild.error || cancelBuild.error ? <RequestError error={reindex.error ?? rebuild.error ?? cancelBuild.error} /> : null}
        {reindexStatus === "building" ?
          <Button size="sm" variant="outline" disabled={cancelBuild.isPending} onClick={() => cancelBuild.mutate()}>Cancel build</Button> :
          <Button size="sm" variant="outline" disabled={reindex.isPending || rebuild.isPending || !model.trim() || !baseUrl.trim()} onClick={() => {
            let host = "";
            try { host = new URL(baseUrl.trim()).hostname; } catch { setMessage("Enter a valid embedding address before building an index."); return; }
            const local = host === "127.0.0.1" || host === "localhost" || host === "::1";
            if (!local && !window.confirm(`This build sends document passages to ${host}. Continue only when that provider is approved.`)) return;
            rebuild.mutate();
          }}>Build replacement index</Button>}
      </section> : null}
      {message ? <p className="mt-3 text-xs leading-5 text-muted-foreground" role="status">{message}</p> : null}
  {isAdmin ? <div className="mt-4 flex flex-wrap gap-2"><Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save"}</Button>{record || type === "chat" || type === "embedding" ? <Button size="sm" variant="outline" onClick={() => verify.mutate()} disabled={verify.isPending || record?.status === "disabled"}>{verify.isPending ? "Testing…" : record ? "Test connection" : "Test current connection"}</Button> : null}{record ? <Button size="sm" variant="ghost" onClick={() => { const kind = record.status === "disabled" ? "enable" : "disable"; if (kind === "enable" || window.confirm("Change this integration state?")) action.mutate(kind); }} disabled={action.isPending}>{record.status === "disabled" ? "Enable" : "Disable"}</Button> : null}{record?.has_credentials ? <Button size="sm" variant="ghost" onClick={() => { if (window.confirm("Revoke this integration credential?")) action.mutate("revoke"); }} disabled={action.isPending}>Revoke key</Button> : null}</div> : null}
    </section>
  );
}

function N8nCard({ organizationId, isAdmin, record }: {
  organizationId: string;
  isAdmin: boolean;
  record?: IntegrationMetadata;
}) {
  const client = useQueryClient();
  const [issued, setIssued] = useState<{ id: string; secret: string } | null>(null);
  const [pending, setPending] = useState(false);
  const [operationError, setOperationError] = useState<unknown>(null);
  const key = useQuery({
    queryKey: ["webhook-key-status", organizationId],
    queryFn: () => getWebhookKeyStatus(organizationId),
    enabled: Boolean(organizationId && isAdmin),
  });
  const acceptedAt = key.data?.last_accepted_at;
  const state = !isAdmin ? "Operator managed" : key.isPending ? "Checking" : key.error ? "Unavailable" :
    key.data?.revoked_at ? "Disconnected" : acceptedAt ? "Callback verified" : key.data ? "Awaiting callback" : "Key required";
  async function change(action: "issue" | "rotate" | "disconnect") {
    if (pending) return;
    setPending(true);
    setOperationError(null);
    try {
      if (action === "disconnect") {
        await disconnectWebhookKey(organizationId);
        setIssued(null);
      } else {
        setIssued(await issueWebhookKey(organizationId, action === "rotate"));
      }
      await client.invalidateQueries({ queryKey: ["webhook-key-status", organizationId] });
      void client.invalidateQueries({ queryKey: ["automations", organizationId] });
    } catch (error) {
      setOperationError(error);
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="rounded-xl border border-border bg-background p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-medium">n8n automation</h3>
          <p className="mt-1 text-xs text-muted-foreground">Signed workflow callbacks</p>
        </div>
        <Badge variant="secondary">{record?.status === "disabled" ? "Disabled" : state}</Badge>
      </div>
      {key.error ? <div className="mt-3"><RequestError error={key.error} /></div> : null}
      {acceptedAt && !key.data?.revoked_at ? <p className="mt-3 text-sm text-muted-foreground">
        Last accepted <time dateTime={acceptedAt}>{new Date(acceptedAt).toLocaleString()}</time>
      </p> : null}
      <p className="mt-3 text-sm text-muted-foreground">Configure the signing key in your n8n deployment, then check this page after the first signed callback.</p>
      {key.data ? <p className="mt-2 break-all text-xs text-muted-foreground">Key ID {key.data.id}</p> : null}
      {isAdmin && key.isSuccess ? <div className="mt-4 flex flex-wrap gap-2">
        {key.data ? <>
          <ConfirmButton size="sm" label={key.data.revoked_at ? "Reconnect with a new key" : "Rotate key"} confirmLabel="Issue new key" pendingLabel="Issuing…" pending={pending} onConfirm={() => void change("rotate")} />
          {!key.data.revoked_at ? <ConfirmButton size="sm" label="Disconnect n8n" confirmLabel="Confirm disconnect" pendingLabel="Disconnecting…" pending={pending} onConfirm={() => void change("disconnect")} /> : null}
        </> : <Button size="sm" disabled={pending} onClick={() => void change("issue")}>Create signing key</Button>}
        <Button size="sm" variant="ghost" disabled={pending || key.isFetching} onClick={() => void key.refetch()}>Refresh callback status</Button>
      </div> : null}
      {operationError ? <div className="mt-3"><RequestError error={operationError} /></div> : null}
      {issued ? <div className="mt-3 grid gap-2 rounded-lg border border-border bg-card p-3">
        <p className="text-xs text-muted-foreground">Copy this secret into your n8n credential store. This is the only time it is shown.</p>
        <label className="grid gap-1 text-sm">Signing secret
          <Input readOnly value={issued.secret} className="font-mono text-xs" onFocus={(event) => event.currentTarget.select()} />
        </label>
        <Button size="sm" variant="outline" className="justify-self-start" onClick={() => setIssued(null)}>Hide secret</Button>
      </div> : null}
    </div>
  );
}

function McpCard() {
  return <div className="rounded-[10px] border border-border bg-background p-4"><div className="flex items-start justify-between gap-2"><div><h3 className="font-medium">MCP retrieval</h3><p className="mt-1 text-xs text-muted-foreground">Infrastructure capability</p></div><Badge variant="secondary">Available</Badge></div><p className="mt-4 text-sm leading-6 text-muted-foreground">MCP is provisioned by the server and receives only the organization-scoped embedding settings required for retrieval. There is no separate user-managed connection or credential form.</p></div>;
}
