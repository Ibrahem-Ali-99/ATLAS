"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ConfirmButton } from "@/components/confirm-button";
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
import { getLeadPrediction, scoreLead } from "@/lib/intelligence";
import {
  addInteraction,
  createLead,
  deleteLead,
  listCompanies,
  listInteractions,
  listLeads,
  updateLead,
} from "@/lib/records-api";
import { blankToNull, interactionKinds, leadStatuses, type InteractionKind, type Lead, type LeadStatus } from "@/lib/records";

const schema = z.object({
  title: z.string().trim().min(1, "Title is required").max(200),
  status: z.enum(leadStatuses),
  company_id: z.string(),
  source: z.string().max(120),
  notes: z.string().max(4000),
});

type FormValues = z.infer<typeof schema>;

const noteSchema = z.object({
  kind: z.enum(interactionKinds),
  body: z.string().trim().min(1, "Write a note").max(4000),
});

type NoteValues = z.infer<typeof noteSchema>;

export function LeadsPanel({ organizationId }: { organizationId: string }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<LeadStatus | "">("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const leads = useQuery({
    queryKey: ["leads", organizationId, query, status, page],
    queryFn: () => listLeads(organizationId, { q: query, status, page }),
  });
  const companies = useQuery({
    queryKey: ["companies", organizationId, "options"],
    queryFn: () => listCompanies(organizationId, { pageSize: 100 }),
  });

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const selected = leads.data?.items.find((item) => item.id === selectedId) ?? null;

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(20rem,0.9fr)]">
      <section className="rounded-[10px] bg-muted">
        <div className="grid gap-3 p-4 sm:grid-cols-[1fr_10rem_auto]">
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search leads" aria-label="Search leads" />
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
                    <button type="button" className="text-left font-medium" onClick={() => setSelectedId(lead.id)}>{lead.title}</button>
                  </TableCell>
                  <TableCell><Badge variant="secondary">{lead.status}</Badge></TableCell>
                  <TableCell>{lead.source ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
        {leads.data ? <Pager page={leads.data.page} pageSize={leads.data.page_size} total={leads.data.total} onPage={setPage} /> : null}
      </section>
      {selected ? (
        <LeadDetail
          key={selected.id}
          organizationId={organizationId}
          lead={selected}
          companies={companies.data?.items ?? []}
          onChanged={() => void queryClient.invalidateQueries({ queryKey: ["leads", organizationId] })}
          onDeleted={() => {
            setSelectedId(null);
            void queryClient.invalidateQueries({ queryKey: ["leads", organizationId] });
          }}
        />
      ) : (
        <aside className="rounded-[10px] bg-muted p-6 text-sm text-muted-foreground">
          Select a lead to update its status and interaction history.
        </aside>
      )}
      <LeadDialog
        organizationId={organizationId}
        companies={companies.data?.items ?? []}
        open={open}
        onOpenChange={setOpen}
        onCreated={(lead) => {
          setSelectedId(lead.id);
          void queryClient.invalidateQueries({ queryKey: ["leads", organizationId] });
        }}
      />
    </div>
  );
}

function LeadDialog({
  organizationId,
  companies,
  open,
  onOpenChange,
  onCreated,
}: {
  organizationId: string;
  companies: { id: string; name: string }[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (lead: Lead) => void;
}) {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { title: "", status: "new", company_id: "", source: "", notes: "" },
  });
  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      createLead(organizationId, {
        title: values.title.trim(),
        status: values.status,
        company_id: blankToNull(values.company_id),
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
        <LeadFields form={form} companies={companies} onSubmit={(values) => mutation.mutate(values)} />
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
  onChanged,
  onDeleted,
}: {
  organizationId: string;
  lead: Lead;
  companies: { id: string; name: string }[];
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: lead.title,
      status: lead.status,
      company_id: lead.company_id ?? "",
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
        source: blankToNull(values.source),
        notes: blankToNull(values.notes),
      }),
    onSuccess: onChanged,
  });
  const remove = useMutation({ mutationFn: () => deleteLead(organizationId, lead.id), onSuccess: onDeleted });
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

  return (
    <aside className="space-y-4 rounded-[10px] bg-muted p-6">
      <div>
        <h2 className="text-base font-semibold">{lead.title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">Owned by the member who created it unless reassigned by the API.</p>
      </div>
      <LeadFields form={form} formId="lead-edit" companies={companies} onSubmit={(values) => save.mutate(values)} />
      {save.isSuccess ? <p className="text-sm text-muted-foreground">Saved.</p> : null}
      {save.isError ? <RequestError error={save.error} /> : null}
      {remove.isError ? <RequestError error={remove.error} /> : null}
      <div className="flex gap-2">
        <Button type="submit" form="lead-edit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save"}</Button>
        <ConfirmButton label="Delete" confirmLabel="Confirm delete" pendingLabel="Deleting…" pending={remove.isPending} onConfirm={() => remove.mutate()} />
      </div>
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
          {noteForm.formState.errors.body ? <p className="text-sm text-red-300">{noteForm.formState.errors.body.message}</p> : null}
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
  formId = "lead-create",
  onSubmit,
}: {
  form: ReturnType<typeof useForm<FormValues>>;
  companies: { id: string; name: string }[];
  formId?: string;
  onSubmit: (values: FormValues) => void;
}) {
  return (
    <form id={formId} className="grid gap-3" onSubmit={form.handleSubmit(onSubmit)}>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-title`}>Title</Label>
        <Input id={`${formId}-title`} {...form.register("title")} />
        {form.formState.errors.title ? <p className="text-sm text-red-300">{form.formState.errors.title.message}</p> : null}
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
        <Label htmlFor={`${formId}-notes`}>Notes</Label>
        <Textarea id={`${formId}-notes`} {...form.register("notes")} />
      </div>
    </form>
  );
}
