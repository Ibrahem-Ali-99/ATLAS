"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ConfirmButton } from "@/components/confirm-button";
import { Pager } from "@/components/pager";
import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { createInquiry, getInquiry, deleteInquiry, listCompanies, listInquiries, listLeads, restoreInquiry, updateInquiry } from "@/lib/records-api";
import { blankToNull, type Inquiry } from "@/lib/records";

const schema = z.object({
  subject: z.string().trim().min(1, "Subject is required").max(200),
  body: z.string().trim().min(1, "Body is required").max(8000),
  company_id: z.string(),
  lead_id: z.string(),
});

type FormValues = z.infer<typeof schema>;

function payload(values: FormValues) {
  return {
    subject: values.subject.trim(),
    body: values.body.trim(),
    company_id: blankToNull(values.company_id),
    lead_id: blankToNull(values.lead_id),
  };
}

type Navigate = (target: { tab: "companies" | "contacts" | "leads" | "inquiries"; id: string | null }) => void;

export function InquiriesPanel({ organizationId, selectedId: requestedId, onNavigate }: { organizationId: string; selectedId?: string | null; onNavigate: Navigate }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [open, setOpen] = useState(false);
  const selectedId = requestedId ?? null;
  const inquiries = useQuery({
    queryKey: ["inquiries", organizationId, query, page, includeArchived],
    queryFn: () => listInquiries(organizationId, { q: query, page, includeArchived }),
  });
  const companies = useQuery({
    queryKey: ["companies", organizationId, "options"],
    queryFn: () => listCompanies(organizationId, { pageSize: 100 }),
  });
  const leads = useQuery({
    queryKey: ["leads", organizationId, "options"],
    queryFn: () => listLeads(organizationId, { pageSize: 100 }),
  });

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const selectedInList = inquiries.data?.items.find((item) => item.id === selectedId);
  const record = useQuery({
    queryKey: ["inquiries", organizationId, "record", selectedId],
    queryFn: () => getInquiry(organizationId, selectedId ?? ""),
    enabled: Boolean(selectedId && !selectedInList),
  });
  const selected = selectedInList ?? record.data ?? null;

  return (
    <div className={selected ? "grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(20rem,0.8fr)]" : "min-w-0"}>
      <section className="overflow-hidden rounded-xl border border-border bg-card shadow-[0_18px_60px_rgba(0,0,0,0.16)]">
        <div className="flex flex-col gap-3 border-b border-border/80 bg-card/80 p-4 sm:flex-row">
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search inquiries" aria-label="Search inquiries" />
          <label className="flex items-center gap-2 text-sm text-muted-foreground"><input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} /> Show archived</label>
          <Button type="button" onClick={() => setOpen(true)}>New inquiry</Button>
        </div>
        {inquiries.isPending ? <div className="space-y-2 px-4 pb-4"><Skeleton className="h-8 w-full" /></div> : null}
        {inquiries.isError ? <div className="px-4 pb-4"><RequestError error={inquiries.error} /></div> : null}
        {inquiries.data && inquiries.data.items.length === 0 ? (
          <p className="px-4 pb-6 text-sm text-muted-foreground">No inquiries match this search.</p>
        ) : null}
        {inquiries.data && inquiries.data.items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Subject</TableHead>
                <TableHead>Received</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {inquiries.data.items.map((inquiry) => (
                <TableRow key={inquiry.id} className={inquiry.id === selectedId ? "bg-accent/40" : undefined}>
                  <TableCell>
                    <button type="button" className="text-left font-medium" onClick={() => onNavigate({ tab: "inquiries", id: inquiry.id })}>{inquiry.subject}</button>
                  </TableCell>
                  <TableCell>{new Date(inquiry.created_at).toLocaleDateString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
        {inquiries.data ? <Pager page={inquiries.data.page} pageSize={inquiries.data.page_size} total={inquiries.data.total} onPage={setPage} /> : null}
      </section>
      {selected ? (
        <InquiryEditor
          key={selected.id}
          organizationId={organizationId}
          inquiry={selected}
          companies={companies.data?.items ?? []}
          leads={leads.data?.items ?? []}
          onNavigate={onNavigate}
          onSaved={() => void queryClient.invalidateQueries({ queryKey: ["inquiries", organizationId] })}
          onDeleted={() => {
            onNavigate({ tab: "inquiries", id: null });
            void queryClient.invalidateQueries({ queryKey: ["inquiries", organizationId] });
          }}
        />
      ) : record.isError ? <RequestError error={record.error} /> : (
        <aside className="rounded-[10px] bg-muted p-6 text-sm text-muted-foreground">
          Select an inquiry to read and update it.
        </aside>
      )}
      <InquiryDialog
        organizationId={organizationId}
        companies={companies.data?.items ?? []}
        leads={leads.data?.items ?? []}
        open={open}
        onOpenChange={setOpen}
        onCreated={(inquiry) => {
          onNavigate({ tab: "inquiries", id: inquiry.id });
          void queryClient.invalidateQueries({ queryKey: ["inquiries", organizationId] });
        }}
      />
    </div>
  );
}

function InquiryDialog({
  organizationId,
  companies,
  leads,
  open,
  onOpenChange,
  onCreated,
}: {
  organizationId: string;
  companies: { id: string; name: string }[];
  leads: { id: string; title: string }[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (inquiry: Inquiry) => void;
}) {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { subject: "", body: "", company_id: "", lead_id: "" },
  });
  const mutation = useMutation({
    mutationFn: (values: FormValues) => createInquiry(organizationId, payload(values)),
    onSuccess: (inquiry) => {
      form.reset();
      onOpenChange(false);
      onCreated(inquiry);
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New inquiry</DialogTitle>
          <DialogDescription>Inquiries stay inside this organization.</DialogDescription>
        </DialogHeader>
        <InquiryFields form={form} companies={companies} leads={leads} onSubmit={(values) => mutation.mutate(values)} />
        {mutation.isError ? <RequestError error={mutation.error} /> : null}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" form="inquiry-create" disabled={mutation.isPending}>{mutation.isPending ? "Saving…" : "Create"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InquiryEditor({
  organizationId,
  inquiry,
  companies,
  leads,
  onNavigate,
  onSaved,
  onDeleted,
}: {
  organizationId: string;
  inquiry: Inquiry;
  companies: { id: string; name: string }[];
  leads: { id: string; title: string }[];
  onNavigate: Navigate;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { subject: inquiry.subject, body: inquiry.body, company_id: inquiry.company_id ?? "", lead_id: inquiry.lead_id ?? "" },
  });
  const save = useMutation({
    mutationFn: (values: FormValues) => updateInquiry(organizationId, inquiry.id, payload(values)),
    onSuccess: onSaved,
  });
  const remove = useMutation({ mutationFn: () => deleteInquiry(organizationId, inquiry.id), onSuccess: onDeleted });
  const restore = useMutation({ mutationFn: () => restoreInquiry(organizationId, inquiry.id), onSuccess: onDeleted });
  return (
    <aside className="rounded-[10px] bg-muted p-6" data-testid="crm-detail-inquiries" data-record-id={inquiry.id} data-archived={inquiry.archived_at ? "true" : "false"}>
      <h2 className="text-base font-semibold">{inquiry.subject}</h2>
      <div className="mt-3 border-t border-border pt-3 text-sm"><h3 className="font-medium">Related records</h3><div className="mt-2 grid gap-1">
        {inquiry.company_id ? <button className="text-left text-primary underline" onClick={() => onNavigate({ tab: "companies", id: inquiry.company_id! })}>{companies.find((item) => item.id === inquiry.company_id)?.name ?? "Company"}</button> : null}
        {inquiry.lead_id ? <button className="text-left text-primary underline" onClick={() => onNavigate({ tab: "leads", id: inquiry.lead_id! })}>{leads.find((item) => item.id === inquiry.lead_id)?.title ?? "Lead"}</button> : null}
      </div></div>
      <div className="mt-4">
        <InquiryFields form={form} formId="inquiry-edit" companies={companies} leads={leads} onSubmit={(values) => save.mutate(values)} />
      </div>
      {save.isSuccess ? <p className="mt-3 text-sm text-muted-foreground">Saved.</p> : null}
      {save.isError ? <div className="mt-3"><RequestError error={save.error} /></div> : null}
      {remove.isError ? <div className="mt-3"><RequestError error={remove.error} /></div> : null}
      <div className="mt-4 flex gap-2">
        <Button type="submit" form="inquiry-edit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save"}</Button>
        {inquiry.archived_at ? <Button type="button" variant="outline" disabled={restore.isPending} onClick={() => restore.mutate()}>{restore.isPending ? "Restoring…" : "Restore"}</Button> : <ConfirmButton label="Archive" confirmLabel="Confirm archive" pendingLabel="Archiving…" pending={remove.isPending} onConfirm={() => remove.mutate()} />}
      </div>
    </aside>
  );
}

function InquiryFields({
  form,
  companies,
  leads,
  formId = "inquiry-create",
  onSubmit,
}: {
  form: ReturnType<typeof useForm<FormValues>>;
  companies: { id: string; name: string }[];
  leads: { id: string; title: string }[];
  formId?: string;
  onSubmit: (values: FormValues) => void;
}) {
  return (
    <form id={formId} className="grid gap-3" onSubmit={form.handleSubmit(onSubmit)}>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-subject`}>Subject</Label>
        <Input id={`${formId}-subject`} {...form.register("subject")} />
        {form.formState.errors.subject ? <p className="text-sm text-destructive">{form.formState.errors.subject.message}</p> : null}
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-body`}>Body</Label>
        <Textarea id={`${formId}-body`} {...form.register("body")} />
        {form.formState.errors.body ? <p className="text-sm text-destructive">{form.formState.errors.body.message}</p> : null}
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-company`}>Company</Label>
        <select id={`${formId}-company`} className="h-10 rounded-md border border-input bg-background px-3 text-sm" {...form.register("company_id")}>
          <option value="">No company</option>
          {companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}
        </select>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-lead`}>Lead</Label>
        <select id={`${formId}-lead`} className="h-10 rounded-md border border-input bg-background px-3 text-sm" {...form.register("lead_id")}>
          <option value="">No lead</option>
          {leads.map((lead) => <option key={lead.id} value={lead.id}>{lead.title}</option>)}
        </select>
      </div>
    </form>
  );
}
