"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ConfirmButton } from "@/components/confirm-button";
import { AppointmentDialog } from "@/components/calendar/appointment-dialog";
import { Pager } from "@/components/pager";
import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import { startAgentRun } from "@/lib/agent-api";
import { getLeadPrediction, scoreLead } from "@/lib/intelligence";
import {
  addInteraction,
  createLead, getLead,
  deleteLead,
  listCompanies,
  listContacts,
  listInquiries,
  listInteractions,
  listLeads,
  restoreLead,
  updateLead,
} from "@/lib/records-api";
import { blankToNull, interactionKinds, leadStatuses, type InteractionKind, type Lead, type LeadStatus } from "@/lib/records";

const schema = z.object({
  title: z.string().trim().min(1, "Title is required").max(200),
  status: z.enum(leadStatuses),
  company_id: z.string(),
  contact_id: z.string(),
  source: z.string().max(120),
  notes: z.string().max(4000),
});

type FormValues = z.infer<typeof schema>;

const noteSchema = z.object({
  kind: z.enum(interactionKinds),
  body: z.string().trim().min(1, "Write a note").max(4000),
});

type NoteValues = z.infer<typeof noteSchema>;

type Navigate = (target: { tab: "companies" | "contacts" | "leads" | "inquiries"; id: string | null }) => void;

export function LeadsPanel({ organizationId, selectedId: requestedId, initialStatus = "", onNavigate }: { organizationId: string; selectedId?: string | null; initialStatus?: LeadStatus | ""; onNavigate: Navigate }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<LeadStatus | "">(initialStatus);
  const [page, setPage] = useState(1);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [open, setOpen] = useState(false);
  const selectedId = requestedId ?? null;
  const leads = useQuery({
    queryKey: ["leads", organizationId, query, status, page, includeArchived],
    queryFn: () => listLeads(organizationId, { q: query, status, page, includeArchived }),
  });
  const companies = useQuery({
    queryKey: ["companies", organizationId, "options"],
    queryFn: () => listCompanies(organizationId, { pageSize: 100 }),
  });
  const contacts = useQuery({
    queryKey: ["contacts", organizationId, "options"],
    queryFn: () => listContacts(organizationId, { pageSize: 100 }),
  });
  const inquiries = useQuery({
    queryKey: ["lead-relations", organizationId, selectedId],
    queryFn: () => listInquiries(organizationId, { pageSize: 100 }),
    enabled: Boolean(selectedId),
  });

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const selectedInList = leads.data?.items.find((item) => item.id === selectedId);
  const record = useQuery({
    queryKey: ["leads", organizationId, "record", selectedId],
    queryFn: () => getLead(organizationId, selectedId ?? ""),
    enabled: Boolean(selectedId && !selectedInList),
  });
  const selected = selectedInList ?? record.data ?? null;

  return (
    <div className={selected ? "grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(20rem,0.9fr)]" : "w-full"}>
      <section className="min-w-0 rounded-lg border border-border bg-card shadow-sm">
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search leads" aria-label="Search leads" />
          <label className="flex items-center gap-2 text-sm text-muted-foreground"><input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} /> Show archived</label>
          <select
            className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            value={status}
            aria-label="Filter by status"
            onChange={(event) => {
              setStatus(event.target.value as LeadStatus | "");
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            {leadStatuses.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <Button type="button" onClick={() => setOpen(true)}>New lead</Button>
        </div>
        {leads.isPending ? <div className="space-y-2 px-4 pb-4"><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-full" /></div> : null}
        {leads.isError ? <div className="px-4 pb-4"><RequestError error={leads.error} /></div> : null}
        {leads.data && leads.data.items.length === 0 ? (
          <p className="px-4 pb-6 text-sm text-muted-foreground">No leads match this search.</p>
        ) : null}
        {leads.data && leads.data.items.length > 0 ? (
          <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Source</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {leads.data.items.map((lead) => (
                <TableRow key={lead.id} className={lead.id === selectedId ? "bg-accent/40" : undefined}>
                  <TableCell>
                    <button type="button" className="text-left font-medium" onClick={() => onNavigate({ tab: "leads", id: lead.id })}>{lead.title}</button>
                  </TableCell>
                  <TableCell><Badge variant="secondary">{lead.status}</Badge></TableCell>
                  <TableCell>{lead.source ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          </div>
        ) : null}
        {leads.data ? <Pager page={leads.data.page} pageSize={leads.data.page_size} total={leads.data.total} onPage={setPage} /> : null}
      </section>
      {selected ? (
        <LeadDetail
          key={selected.id}
          organizationId={organizationId}
          lead={selected}
          companies={companies.data?.items ?? []}
          contacts={contacts.data?.items ?? []}
          inquiries={inquiries.data?.items ?? []}
          onNavigate={onNavigate}
          onChanged={() => void queryClient.invalidateQueries({ queryKey: ["leads", organizationId] })}
          onDeleted={() => {
            onNavigate({ tab: "leads", id: null });
            void queryClient.invalidateQueries({ queryKey: ["leads", organizationId] });
          }}
        />
      ) : record.isError ? <RequestError error={record.error} /> : (
        <aside className="rounded-lg border border-dashed border-border bg-card p-6 text-sm text-muted-foreground lg:min-h-32">
          Select a lead to update its status and interaction history.
        </aside>
      )}
      <LeadDialog
        organizationId={organizationId}
        companies={companies.data?.items ?? []}
        contacts={contacts.data?.items ?? []}
        open={open}
        onOpenChange={setOpen}
        onCreated={(lead) => {
          onNavigate({ tab: "leads", id: lead.id });
          void queryClient.invalidateQueries({ queryKey: ["leads", organizationId] });
        }}
      />
    </div>
  );
}

function LeadDialog({
  organizationId,
  companies,
  contacts,
  open,
  onOpenChange,
  onCreated,
}: {
  organizationId: string;
  companies: { id: string; name: string }[];
  contacts: { id: string; full_name: string }[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (lead: Lead) => void;
}) {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { title: "", status: "new", company_id: "", contact_id: "", source: "", notes: "" },
  });
  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      createLead(organizationId, {
        title: values.title.trim(),
        status: values.status,
        company_id: blankToNull(values.company_id),
        contact_id: blankToNull(values.contact_id),
        source: blankToNull(values.source),
        notes: blankToNull(values.notes),
      }),
    onSuccess: (lead) => {
      form.reset();
      onOpenChange(false);
      onCreated(lead);
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New lead</DialogTitle>
          <DialogDescription>You become the owner. The assistant can read this lead and cannot change it.</DialogDescription>
        </DialogHeader>
        <LeadFields form={form} companies={companies} contacts={contacts} onSubmit={(values) => mutation.mutate(values)} />
        {mutation.isError ? <RequestError error={mutation.error} /> : null}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" form="lead-create" disabled={mutation.isPending}>{mutation.isPending ? "Saving…" : "Create"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function LeadDetail({
  organizationId,
  lead,
  companies,
  contacts,
  inquiries,
  onNavigate,
  onChanged,
  onDeleted,
}: {
  organizationId: string;
  lead: Lead;
  companies: { id: string; name: string }[];
  contacts: { id: string; full_name: string }[];
  inquiries: import("@/lib/records").Inquiry[];
  onNavigate: Navigate;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const router = useRouter();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: lead.title,
      status: lead.status,
      company_id: lead.company_id ?? "",
      contact_id: lead.contact_id ?? "",
      source: lead.source ?? "",
      notes: lead.notes ?? "",
    },
  });
  const save = useMutation({
    mutationFn: (values: FormValues) =>
      updateLead(organizationId, lead.id, {
        title: values.title.trim(),
        status: values.status,
        company_id: blankToNull(values.company_id),
        contact_id: blankToNull(values.contact_id),
        source: blankToNull(values.source),
        notes: blankToNull(values.notes),
      }),
    onSuccess: onChanged,
  });
  const remove = useMutation({ mutationFn: () => deleteLead(organizationId, lead.id), onSuccess: onDeleted });
  const restore = useMutation({ mutationFn: () => restoreLead(organizationId, lead.id), onSuccess: onDeleted });
  const history = useQuery({
    queryKey: ["interactions", organizationId, lead.id],
    queryFn: () => listInteractions(organizationId, lead.id),
  });
  const noteForm = useForm<NoteValues>({ resolver: zodResolver(noteSchema), defaultValues: { kind: "note", body: "" } });
  const note = useMutation({
    mutationFn: (values: NoteValues) =>
      addInteraction(organizationId, lead.id, { kind: values.kind as InteractionKind, body: values.body.trim() }),
    onSuccess: () => {
      noteForm.reset({ kind: "note", body: "" });
      void history.refetch();
    },
  });
  const linkedInquiry = inquiries.find((item) => item.lead_id === lead.id);
  const followUp = useMutation({
    mutationFn: () => startAgentRun(organizationId, linkedInquiry?.id ?? ""),
    onSuccess: (result) => router.push(`/agent-runs?run=${result.run.id}`),
  });

  return (
    <aside className="min-w-0 space-y-5 rounded-lg border border-border bg-card p-5 shadow-sm" data-testid="crm-detail-leads" data-record-id={lead.id} data-archived={lead.archived_at ? "true" : "false"}>
      <div>
        <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs uppercase tracking-[0.12em] text-muted-foreground">Lead detail</p><h2 className="mt-1 break-words text-lg font-semibold">{lead.title}</h2></div><Badge variant="secondary">{lead.status}</Badge></div>
      </div>
      <div className="border-t border-border pt-4 text-sm"><h3 className="font-medium">Related records</h3><div className="mt-2 grid min-w-0 gap-1">
        {lead.company_id ? <button className="text-left text-accent underline" onClick={() => onNavigate({ tab: "companies", id: lead.company_id! })}>{companies.find((item) => item.id === lead.company_id)?.name ?? "Company"}</button> : null}
        {lead.contact_id ? <button className="text-left text-accent underline" onClick={() => onNavigate({ tab: "contacts", id: lead.contact_id! })}>{contacts.find((item) => item.id === lead.contact_id)?.full_name ?? "Contact"}</button> : null}
        {inquiries.filter((item) => item.lead_id === lead.id).map((item) => <button key={item.id} className="text-left text-accent underline" onClick={() => onNavigate({ tab: "inquiries", id: item.id })}>{item.subject}</button>)}
      </div></div>
      <LeadFields form={form} formId="lead-edit" companies={companies} contacts={contacts} onSubmit={(values) => save.mutate(values)} />
      {save.isSuccess ? <p className="text-sm text-muted-foreground">Saved.</p> : null}
      {save.isError ? <RequestError error={save.error} /> : null}
      {remove.isError ? <RequestError error={remove.error} /> : null}
      <div className="flex gap-2">
        <Button type="submit" form="lead-edit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save"}</Button>
        <Button type="button" variant="outline" disabled={!linkedInquiry || !lead.contact_id || followUp.isPending} onClick={() => followUp.mutate()} title={!linkedInquiry ? "Add an inquiry to this lead before drafting a follow-up" : undefined}>
          {followUp.isPending ? "Drafting…" : "Draft follow-up"}
        </Button>
        {lead.archived_at ? <Button type="button" variant="outline" disabled={restore.isPending} onClick={() => restore.mutate()}>{restore.isPending ? "Restoring…" : "Restore"}</Button> : <ConfirmButton label="Archive" confirmLabel="Confirm archive" pendingLabel="Archiving…" pending={remove.isPending} onConfirm={() => remove.mutate()} />}
      </div>
      {linkedInquiry && !lead.archived_at ? <AppointmentDialog key={lead.id} leadId={lead.id} organizationId={organizationId} /> : null}
      {followUp.isError ? <RequestError error={followUp.error} /> : null}
      <LeadScore organizationId={organizationId} leadId={lead.id} />
      <div className="border-t border-border pt-4">
        <h3 className="text-sm font-medium">Interaction history</h3>
        {history.isPending ? <Skeleton className="mt-3 h-16 w-full" /> : null}
        {history.isError ? <div className="mt-3"><RequestError error={history.error} /></div> : null}
        {history.data && history.data.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">No interactions yet.</p>
        ) : null}
        <ul className="mt-3 space-y-3">
          {history.data?.map((item) => (
            <li key={item.id} className="rounded-md border border-border p-3 text-sm">
              <div className="flex items-center justify-between gap-2">
                <Badge variant="secondary">{item.kind}</Badge>
                <time className="text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString()}</time>
              </div>
              <p className="mt-2 whitespace-pre-wrap">{item.body}</p>
            </li>
          ))}
        </ul>
        <form className="mt-3 grid gap-2" onSubmit={noteForm.handleSubmit((values) => note.mutate(values))}>
          <select className="h-10 rounded-md border border-input bg-background px-3 text-sm" {...noteForm.register("kind")}>
            {interactionKinds.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
          </select>
          <Textarea placeholder="What happened?" {...noteForm.register("body")} />
          {noteForm.formState.errors.body ? <p className="text-sm text-destructive">{noteForm.formState.errors.body.message}</p> : null}
          {note.isError ? <RequestError error={note.error} /> : null}
          <Button type="submit" disabled={note.isPending}>{note.isPending ? "Saving…" : "Add interaction"}</Button>
        </form>
      </div>
    </aside>
  );
}

function LeadScore({ organizationId, leadId }: { organizationId: string; leadId: string }) {
  const queryClient = useQueryClient();
  const prediction = useQuery({
    queryKey: ["lead-prediction", organizationId, leadId],
    queryFn: () => getLeadPrediction(organizationId, leadId),
    retry: false,
  });
  const score = useMutation({
    mutationFn: () => scoreLead(organizationId, leadId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["lead-prediction", organizationId, leadId] });
    },
  });
  const missing = prediction.error instanceof ApiError && prediction.error.status === 404;
  return (
    <div className="border-t border-border pt-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium">Lead score</h3>
        <Button type="button" variant="outline" disabled={score.isPending} onClick={() => score.mutate()}>
          {score.isPending ? "Scoring" : "Score lead"}
        </Button>
      </div>
      {prediction.isPending ? <Skeleton className="mt-3 h-16 w-full" /> : null}
      {missing ? <p className="mt-3 text-sm text-muted-foreground">No prediction is stored for this lead.</p> : null}
      {prediction.isError && !missing ? <div className="mt-3"><RequestError error={prediction.error} /></div> : null}
      {score.isError ? <div className="mt-3"><RequestError error={score.error} /></div> : null}
      {prediction.data ? (
        <div className="mt-3 space-y-2 text-sm">
          <p>{prediction.data.label}. Confidence: {prediction.data.confidence ?? "unavailable"}</p>
          <p className="text-muted-foreground">{prediction.data.notice}</p>
          <p className="text-muted-foreground">{prediction.data.explanation}</p>
          {prediction.data.contributions.length === 0 ? (
            <p className="text-muted-foreground">Feature influence is unavailable for this model.</p>
          ) : (
            <ul className="space-y-1 text-muted-foreground">
              {prediction.data.contributions.map((item) => (
                <li key={`${item.feature}-${item.relation ?? "weight"}`}>
                  {item.feature}: {item.contribution}
                  {item.relation ? ` (${item.relation} ${item.threshold})` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}

function LeadFields({
  form,
  companies,
  contacts,
  formId = "lead-create",
  onSubmit,
}: {
  form: ReturnType<typeof useForm<FormValues>>;
  companies: { id: string; name: string }[];
  contacts: { id: string; full_name: string }[];
  formId?: string;
  onSubmit: (values: FormValues) => void;
}) {
  return (
    <form id={formId} className="grid gap-3" onSubmit={form.handleSubmit(onSubmit)}>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-title`}>Title</Label>
        <Input id={`${formId}-title`} {...form.register("title")} />
        {form.formState.errors.title ? <p className="text-sm text-destructive">{form.formState.errors.title.message}</p> : null}
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-status`}>Status</Label>
        <select id={`${formId}-status`} className="h-10 rounded-md border border-input bg-background px-3 text-sm" {...form.register("status")}>
          {leadStatuses.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-company`}>Company</Label>
        <select id={`${formId}-company`} className="h-10 rounded-md border border-input bg-background px-3 text-sm" {...form.register("company_id")}>
          <option value="">No company</option>
          {companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}
        </select>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-source`}>Source</Label>
        <Input id={`${formId}-source`} {...form.register("source")} />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-contact`}>Contact</Label>
        <select id={`${formId}-contact`} className="h-10 rounded-md border border-input bg-background px-3 text-sm" {...form.register("contact_id")}>
          <option value="">No contact</option>
          {contacts.map((contact) => <option key={contact.id} value={contact.id}>{contact.full_name}</option>)}
        </select>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-notes`}>Notes</Label>
        <Textarea id={`${formId}-notes`} {...form.register("notes")} />
      </div>
    </form>
  );
}
