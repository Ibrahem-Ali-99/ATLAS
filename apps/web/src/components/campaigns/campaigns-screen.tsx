"use client";

import { useState } from "react";
import { Ban, Mail, Plus, Search, ShieldCheck, Users } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { createCampaign, createSegment, listCampaigns, listCampaignSuppressions, listSegments, previewCampaign, suppressCampaignAddress, updateCampaign, type Campaign, type CampaignDraft, type RecipientPreview, type Segment } from "@/lib/campaigns";
import { useWorkspace } from "@/lib/use-workspace";
import { CampaignDelivery } from "./campaign-delivery";

const selectClass = "h-10 w-full rounded-md border border-input bg-background px-3 text-sm";

export function CampaignsScreen() {
  const { organizationId } = useWorkspace();
  return organizationId ? <CampaignWorkspace key={organizationId} organizationId={organizationId} /> : null;
}

function CampaignWorkspace({ organizationId }: { organizationId: string }) {
  const client = useQueryClient();
  const segments = useQuery({ queryKey: ["segments", organizationId], queryFn: () => listSegments(organizationId) });
  const campaigns = useQuery({
    queryKey: ["campaigns", organizationId],
    queryFn: () => listCampaigns(organizationId),
    refetchInterval: (query) => query.state.data?.some(
      ({ status }) => status === "scheduled" || status === "dispatching",
    ) ? 4_000 : false,
  });
  const [segmentName, setSegmentName] = useState("");
  const [field, setField] = useState("lead_status");
  const [value, setValue] = useState("qualified");
  const [editor, setEditor] = useState<Campaign | "new" | null>(null);
  const [segmentId, setSegmentId] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [search, setSearch] = useState("");
  const segmentCreate = useMutation({
    mutationFn: () => createSegment(organizationId, { name: segmentName, logic: "and", conditions: [{ field, operator: "eq", value }] }),
    onSuccess: () => {
      setSegmentName("");
      void client.invalidateQueries({ queryKey: ["segments", organizationId] });
    },
  });
  const segmentLabel = segments.data?.find((segment) => segment.id === segmentId)?.name;
  const visibleCampaigns = campaigns.data?.filter((item) => [item.name, item.subject].some(
    (value) => value?.toLowerCase().includes(search.trim().toLowerCase()),
  )) ?? [];
  const selected = visibleCampaigns.find((item) => item.id === selectedId) ?? visibleCampaigns[0];

  return (
    <div className="min-w-0 space-y-6">
      <PageHeader title="Campaigns" eyebrow="Customer communications" actions={
        <>
          <CampaignSuppressionDialog organizationId={organizationId} />
          <Button onClick={() => setEditor("new")}><Plus size={16} /> New campaign</Button>
        </>
      }>
        Build audiences and prepare campaign drafts for review.
      </PageHeader>
      <div className="campaign-layout">
        <section aria-labelledby="campaign-drafts" className="panel campaign-library">
          <div className="border-b border-border p-5">
            <h2 id="campaign-drafts" className="font-semibold">Campaigns</h2>
            <div className="relative mt-3">
              <Search size={15} aria-hidden="true" className="pointer-events-none absolute top-3 left-3 text-muted-foreground" />
              <Input className="pl-9" aria-label="Search campaigns" placeholder="Search campaigns" value={search} onChange={(event) => setSearch(event.target.value)} />
            </div>
          </div>
          {campaigns.isPending ? <div className="p-5"><Skeleton className="h-16" /></div> : campaigns.isError ? (
            <div className="p-5"><RequestError error={campaigns.error} /></div>
          ) : visibleCampaigns.length ? (
            <ul className="campaign-list">
              {visibleCampaigns.map((campaign) => (
                <li key={campaign.id}>
                  <button aria-current={selected?.id === campaign.id || undefined} className={`campaign-card${selected?.id === campaign.id ? " active" : ""}`} type="button" onClick={() => setSelectedId(campaign.id)}>
                    <span className="flex min-w-0 items-center gap-3">
                      <Mail size={18} className="shrink-0 text-primary" />
                      <span className="min-w-0">
                        <strong className="block break-words text-sm font-medium">{campaign.name}</strong>
                        <span className="block truncate text-xs text-muted-foreground">{campaign.subject || "No subject"}</span>
                      </span>
                    </span>
                    <Badge variant="secondary" className="shrink-0 capitalize">{campaign.status.replaceAll("_", " ")}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="p-5 text-sm text-muted-foreground">{search.trim() ? "No campaigns match your search." : "No campaign drafts yet."}</p>}
        </section>
        {selected ? (
          <CampaignReview
            key={selected.id}
            organizationId={organizationId}
            campaign={selected}
            segment={segments.data?.find((segment) => segment.id === selected.segment_id)}
            edit={() => setEditor(selected)}
          />
        ) : null}
      </div>
        <section aria-labelledby="audience-segments" className="min-w-0 rounded-xl border border-border bg-card p-5">
          <h2 id="audience-segments" className="font-semibold">Audience segments</h2>
          <form className="mt-4 grid gap-3" onSubmit={(event) => { event.preventDefault(); segmentCreate.mutate(); }}>
            <label className="grid gap-1 text-sm">Segment name
              <Input required value={segmentName} onChange={(event) => setSegmentName(event.target.value)} />
            </label>
            <label className="grid gap-1 text-sm">Segment field
              <select className={selectClass} value={field} onChange={(event) => setField(event.target.value)}>
                <option value="lead_status">Lead status</option>
                <option value="owner_user_id">Lead owner ID</option>
                <option value="contact_email">Contact email</option>
              </select>
            </label>
            <label className="grid gap-1 text-sm">Segment value
              <Input required value={value} onChange={(event) => setValue(event.target.value)} />
            </label>
            <Button type="submit" variant="outline" className="justify-self-start" disabled={!segmentName.trim() || !value.trim() || segmentCreate.isPending}>Save segment</Button>
          </form>
          {segmentCreate.isError ? <div className="mt-3"><RequestError error={segmentCreate.error} /></div> : null}
          {segments.isPending ? <Skeleton className="mt-4 h-14" /> : segments.isError ? (
            <div className="mt-4"><RequestError error={segments.error} /></div>
          ) : segments.data.length ? (
            <ul className="mt-4 space-y-2">
              {segments.data.map((segment) => (
                <li key={segment.id}>
                  <button type="button" aria-pressed={segmentId === segment.id} onClick={() => setSegmentId(segment.id)}
                    className="w-full rounded-lg border border-border p-3 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-pressed:bg-accent">
                    <span className="block break-words text-sm font-medium">{segment.name}</span>
                    <span className="text-xs text-muted-foreground">{segment.preview.contacts} contacts · {segment.preview.leads} leads</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="mt-4 text-sm text-muted-foreground">No audience segments yet.</p>}
          {segmentLabel ? <p className="mt-3 text-xs text-muted-foreground" role="status">Selected for the next draft: {segmentLabel}</p> : null}
        </section>
      <Dialog open={editor !== null} onOpenChange={(open) => { if (!open) setEditor(null); }}>
        <DialogContent className="max-h-[90dvh] max-w-xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editor === "new" ? "New campaign" : editor?.name ?? "Campaign"}</DialogTitle>
            <DialogDescription>Save email content and preview the consented audience for the selected segment.</DialogDescription>
          </DialogHeader>
          {editor ? <CampaignEditor
            key={editor === "new" ? "new" : editor.id}
            organizationId={organizationId}
            campaign={editor === "new" ? null : editor}
            segments={segments.data ?? []}
            defaultSegment={segmentId}
            onSaved={(campaign) => {
              setEditor(campaign);
              setSearch("");
              setSelectedId(campaign.id);
              void client.invalidateQueries({ queryKey: ["campaigns", organizationId] });
              void client.invalidateQueries({ queryKey: ["campaign-preview", organizationId, campaign.id] });
            }}
          /> : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}


function CampaignReview({ organizationId, campaign, segment, edit }: {
  organizationId: string;
  campaign: Campaign;
  segment?: Segment;
  edit: () => void;
}) {
  const preview = useQuery({
    queryKey: ["campaign-preview", organizationId, campaign.id],
    queryFn: () => previewCampaign(organizationId, campaign.id),
    enabled: Boolean(campaign.segment_id) && campaign.status === "draft",
  });

  return (
    <section aria-label="Campaign review" className="panel campaign-detail">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border p-5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="break-words text-lg font-semibold">{campaign.name}</h2>
            <Badge variant="secondary" className="capitalize">{campaign.status.replaceAll("_", " ")}</Badge>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Email campaign · {new Date(campaign.updated_at).toLocaleDateString()}</p>
        </div>
        {campaign.status === "draft" ? <Button variant="outline" onClick={edit}>Edit draft</Button> : null}
      </div>
      <div className="grid gap-5 p-5">
        <section>
          <h3 className="flex items-center gap-2 text-sm font-semibold"><Users size={15} /> Audience</h3>
          <p className="mt-2 text-sm text-muted-foreground">{segment?.name ?? (campaign.segment_id ? "Campaign segment" : "Choose a segment in the draft to review its audience.")}</p>
        </section>
        {campaign.segment_id && campaign.status === "draft" ? (
          <section>
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold"><ShieldCheck size={15} /> Consent and suppression</h3>
            {preview.isPending ? <div role="status" aria-label="Checking audience"><Skeleton className="h-16" /></div> : null}
            {preview.error ? <RequestError error={preview.error} /> : null}
            {preview.data ? <AudiencePreview preview={preview.data} /> : null}
          </section>
        ) : null}
        <section>
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Mail size={15} /> Message content</h3>
          <div className="space-y-2 rounded-lg border border-border bg-muted p-4">
            <p className="break-words text-sm font-medium">{campaign.subject || "No subject yet"}</p>
            <p className="whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">{campaign.body || "No message body yet."}</p>
          </div>
        </section>
        <CampaignDelivery
          key={campaign.id}
          organizationId={organizationId}
          campaign={campaign}
          eligible={preview.data?.eligible ?? 0}
        />
      </div>
    </section>
  );
}

function AudiencePreview({ preview }: { preview: RecipientPreview }) {
  const metrics = [
    ["Eligible addresses", preview.eligible],
    ["Suppressed", preview.suppressed],
    ["Missing consent", preview.missing_consent],
    ["Matching contacts", preview.matching_contacts],
    ["Valid email", preview.valid_email],
    ["Consented", preview.consented],
  ] as const;
  return (
    <dl className="grid grid-cols-2 gap-3 rounded-lg border border-border bg-muted p-4 text-sm sm:grid-cols-3">
      {metrics.map(([label, value]) => (
        <div key={label}>
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="mt-1 font-semibold tabular-nums" data-testid={`campaign-audience-${label.toLowerCase().replaceAll(" ", "-")}`}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function CampaignSuppressionDialog({ organizationId }: { organizationId: string }) {
  const client = useQueryClient();
  const [email, setEmail] = useState("");
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const suppressions = useQuery({
    queryKey: ["campaign-suppressions", organizationId, offset],
    queryFn: () => listCampaignSuppressions(organizationId, offset),
    enabled: open,
    staleTime: 0,
  });
  const mutation = useMutation({
    mutationFn: () => suppressCampaignAddress(organizationId, email.trim()),
    onSuccess: () => {
      setEmail("");
      setOffset(0);
      void client.invalidateQueries({ queryKey: ["campaign-preview", organizationId] });
      void client.invalidateQueries({ queryKey: ["campaign-suppressions", organizationId] });
    },
  });
  return (
    <Dialog open={open} onOpenChange={(next) => { setOpen(next); if (!next) { setEmail(""); setOffset(0); mutation.reset(); } }}>
      <DialogTrigger asChild><Button variant="outline"><Ban size={15} /> Suppressions</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Campaign suppressions</DialogTitle>
          <DialogDescription>Exclude this address from campaign audiences across the workspace.</DialogDescription>
        </DialogHeader>
        <form className="mt-4 space-y-4" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
          <label className="grid gap-1 text-sm font-medium">Email address
            <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>
          {mutation.error ? <RequestError error={mutation.error} /> : null}
          {mutation.isSuccess ? <p role="status" className="text-sm text-muted-foreground">{mutation.data.email} was excluded from campaign audiences.</p> : null}
          <div className="flex justify-end gap-2">
            <DialogClose asChild><Button type="button" variant="outline">Close</Button></DialogClose>
            <Button type="submit" disabled={!email.trim() || mutation.isPending}>Suppress address</Button>
          </div>
        </form>
        <section aria-label="Suppressed addresses" className="border-t border-border pt-3">
          {suppressions.isPending ? <p role="status" className="text-sm">Loading suppressed addresses…</p> : null}
          {suppressions.error ? <RequestError error={suppressions.error} /> : null}
          {suppressions.data?.length === 0 ? <p className="text-sm text-muted-foreground">No suppressed addresses on this page.</p> : null}
          <ul className="max-h-48 divide-y divide-border overflow-y-auto">
            {suppressions.data?.map((row) => <li key={row.email} className="py-2 text-sm">
              <p className="break-all">{row.email}</p>
              <p className="capitalize text-muted-foreground">{row.reason.replaceAll("_", " ")} · <time dateTime={row.created_at}>{new Date(row.created_at).toLocaleDateString()}</time></p>
            </li>)}
          </ul>
          <div className="mt-2 flex gap-2">
            {offset > 0 ? <Button size="sm" variant="outline" onClick={() => setOffset(offset - 50)}>Previous</Button> : null}
            {suppressions.data?.length === 50 ? <Button size="sm" variant="outline" onClick={() => setOffset(offset + 50)}>Next</Button> : null}
          </div>
        </section>
      </DialogContent>
    </Dialog>
  );
}

function CampaignEditor({ organizationId, campaign, segments, defaultSegment, onSaved }: {
  organizationId: string;
  campaign: Campaign | null;
  segments: Segment[];
  defaultSegment: string;
  onSaved: (campaign: Campaign) => void;
}) {
  const [draft, setDraft] = useState<CampaignDraft>({
    name: campaign?.name ?? "", subject: campaign?.subject ?? "", body: campaign?.body ?? "",
    segment_id: campaign ? campaign.segment_id : defaultSegment || null,
  });
  const locked = Boolean(campaign && campaign.status !== "draft");
  const preview = useMutation({
    mutationFn: (campaignId: string) => previewCampaign(organizationId, campaignId),
  });
  const save = useMutation({
    mutationFn: () => {
      const payload = { ...draft, name: draft.name.trim(), subject: draft.subject?.trim() || null, body: draft.body?.trim() || null };
      return campaign ? updateCampaign(organizationId, campaign.id, payload) : createCampaign(organizationId, payload);
    },
    onSuccess: (saved) => { preview.reset(); onSaved(saved); },
  });
  const update = (field: keyof CampaignDraft, value: string | null) => {
    setDraft((current) => ({ ...current, [field]: value }));
    preview.reset();
  };
  return (
    <form className="grid gap-4" onSubmit={(event) => {
      event.preventDefault();
      if (!locked && !save.isPending && draft.name.trim()) save.mutate();
    }}>
      <fieldset disabled={locked || save.isPending || preview.isPending} className="grid gap-3">
        <label className="grid gap-1 text-sm">Campaign name
          <Input required maxLength={160} value={draft.name} onChange={(event) => update("name", event.target.value)} />
        </label>
        <label className="grid gap-1 text-sm">Campaign segment
          <select className={selectClass} value={draft.segment_id ?? ""} onChange={(event) => update("segment_id", event.target.value || null)}>
            <option value="">Choose a segment</option>
            {segments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-sm">Email subject
          <Input maxLength={200} value={draft.subject ?? ""} onChange={(event) => update("subject", event.target.value)} />
        </label>
        <label className="grid gap-1 text-sm">Email body
          <Textarea className="min-h-32" maxLength={20000} value={draft.body ?? ""} onChange={(event) => update("body", event.target.value)} />
        </label>
      </fieldset>
      {save.isError ? <RequestError error={save.error} /> : null}
      {preview.isError ? <RequestError error={preview.error} /> : null}
      {preview.data ? (
        <section aria-label="Recipient preview" className="rounded-lg border border-border bg-muted p-4">
          <h3 className="font-medium">Recipient preview</h3>
          <div className="mt-3"><AudiencePreview preview={preview.data} /></div>
        </section>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {!locked ? <Button type="submit" disabled={save.isPending || !draft.name.trim()}>{save.isPending ? "Saving…" : "Save draft"}</Button> : null}
        {campaign?.segment_id ? <Button type="button" variant="outline" disabled={preview.isPending || save.isPending || draft.segment_id !== campaign.segment_id} onClick={() => preview.mutate(campaign.id)}>
          {preview.isPending ? "Checking audience…" : "Preview recipients"}
        </Button> : null}
      </div>
    </form>
  );
}
