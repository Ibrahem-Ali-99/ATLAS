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
import { createContact, getContact, deleteContact, listCompanies, listContacts, listInquiries, listLeads, restoreContact, updateContact } from "@/lib/records-api";
import { blankToNull, type Contact } from "@/lib/records";
import { getMarketingConsent, recordMarketingConsent, type ConsentStatus } from "@/lib/campaigns";

const schema = z.object({
  full_name: z.string().trim().min(1, "Name is required").max(200),
  email: z.string().max(320),
  phone: z.string().max(40),
  title: z.string().max(120),
  company_id: z.string(),
});

type FormValues = z.infer<typeof schema>;

function payload(values: FormValues) {
  return {
    full_name: values.full_name.trim(),
    email: blankToNull(values.email),
    phone: blankToNull(values.phone),
    title: blankToNull(values.title),
    company_id: blankToNull(values.company_id),
  };
}

type Navigate = (target: { tab: "companies" | "contacts" | "leads" | "inquiries"; id: string | null }) => void;

export function ContactsPanel({ organizationId, selectedId: requestedId, onNavigate }: { organizationId: string; selectedId?: string | null; onNavigate: Navigate }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [open, setOpen] = useState(false);
  const selectedId = requestedId ?? null;
  const contacts = useQuery({
    queryKey: ["contacts", organizationId, query, page, includeArchived],
    queryFn: () => listContacts(organizationId, { q: query, page, includeArchived }),
  });
  const companies = useQuery({
    queryKey: ["companies", organizationId, "options"],
    queryFn: () => listCompanies(organizationId, { pageSize: 100 }),
  });
  const related = useQuery({
    queryKey: ["contact-relations", organizationId, selectedId],
    queryFn: async () => Promise.all([listLeads(organizationId, { pageSize: 100 }), listInquiries(organizationId, { pageSize: 100 })]),
    enabled: Boolean(selectedId),
  });

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const selectedInList = contacts.data?.items.find((item) => item.id === selectedId);
  const record = useQuery({
    queryKey: ["contacts", organizationId, "record", selectedId],
    queryFn: () => getContact(organizationId, selectedId ?? ""),
    enabled: Boolean(selectedId && !selectedInList),
  });
  const selected = selectedInList ?? record.data ?? null;
  const companyName = (companyId: string | null) =>
    companies.data?.items.find((company) => company.id === companyId)?.name ?? "—";

  return (
    <div className={selected ? "grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(20rem,0.8fr)]" : "min-w-0"}>
      <section className="overflow-hidden rounded-xl border border-border bg-card shadow-[0_18px_60px_rgba(0,0,0,0.16)]">
        <div className="flex flex-col gap-3 border-b border-border/80 bg-card/80 p-4 sm:flex-row">
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search contacts" aria-label="Search contacts" />
          <label className="flex items-center gap-2 text-sm text-muted-foreground"><input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} /> Show archived</label>
          <Button type="button" onClick={() => setOpen(true)}>New contact</Button>
        </div>
        {contacts.isPending ? <div className="space-y-2 px-4 pb-4"><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-full" /></div> : null}
        {contacts.isError ? <div className="px-4 pb-4"><RequestError error={contacts.error} /></div> : null}
        {contacts.data && contacts.data.items.length === 0 ? (
          <p className="px-4 pb-6 text-sm text-muted-foreground">No contacts match this search.</p>
        ) : null}
        {contacts.data && contacts.data.items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Company</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {contacts.data.items.map((contact) => (
                <TableRow key={contact.id} className={contact.id === selectedId ? "bg-accent/40" : undefined}>
                  <TableCell>
                    <button type="button" className="text-left font-medium" onClick={() => onNavigate({ tab: "contacts", id: contact.id })}>
                      {contact.full_name}
                    </button>
                  </TableCell>
                  <TableCell>{contact.email ?? "—"}</TableCell>
                  <TableCell>{companyName(contact.company_id)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
        {contacts.data ? <Pager page={contacts.data.page} pageSize={contacts.data.page_size} total={contacts.data.total} onPage={setPage} /> : null}
      </section>
      {selected ? (
        <ContactEditor
          key={selected.id}
          organizationId={organizationId}
          contact={selected}
          companies={companies.data?.items ?? []}
          related={related.data}
          onNavigate={onNavigate}
          onSaved={() => void queryClient.invalidateQueries({ queryKey: ["contacts", organizationId] })}
          onDeleted={() => {
            onNavigate({ tab: "contacts", id: null });
            void queryClient.invalidateQueries({ queryKey: ["contacts", organizationId] });
          }}
        />
      ) : record.isError ? <RequestError error={record.error} /> : (
        <aside className="rounded-[10px] bg-muted p-6 text-sm text-muted-foreground">
          Select a contact to view and edit it.
        </aside>
      )}
      <ContactDialog
        organizationId={organizationId}
        companies={companies.data?.items ?? []}
        open={open}
        onOpenChange={setOpen}
        onCreated={(contact) => {
          onNavigate({ tab: "contacts", id: contact.id });
          void queryClient.invalidateQueries({ queryKey: ["contacts", organizationId] });
        }}
      />
    </div>
  );
}

function ContactDialog({
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
  onCreated: (contact: Contact) => void;
}) {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: "", email: "", phone: "", title: "", company_id: "" },
  });
  const mutation = useMutation({
    mutationFn: (values: FormValues) => createContact(organizationId, payload(values)),
    onSuccess: (contact) => {
      form.reset();
      onOpenChange(false);
      onCreated(contact);
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New contact</DialogTitle>
          <DialogDescription>Contacts belong to the signed-in organization.</DialogDescription>
        </DialogHeader>
        <ContactFields form={form} companies={companies} onSubmit={(values) => mutation.mutate(values)} />
        {mutation.isError ? <RequestError error={mutation.error} /> : null}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" form="contact-create" disabled={mutation.isPending}>{mutation.isPending ? "Saving…" : "Create"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ContactEditor({
  organizationId,
  contact,
  companies,
  related,
  onNavigate,
  onSaved,
  onDeleted,
}: {
  organizationId: string;
  contact: Contact;
  companies: { id: string; name: string }[];
  related?: [{ items: import("@/lib/records").Lead[] }, { items: import("@/lib/records").Inquiry[] }];
  onNavigate: Navigate;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      full_name: contact.full_name,
      email: contact.email ?? "",
      phone: contact.phone ?? "",
      title: contact.title ?? "",
      company_id: contact.company_id ?? "",
    },
  });
  const save = useMutation({
    mutationFn: (values: FormValues) => updateContact(organizationId, contact.id, payload(values)),
    onSuccess: onSaved,
  });
  const remove = useMutation({ mutationFn: () => deleteContact(organizationId, contact.id), onSuccess: onDeleted });
  const restore = useMutation({ mutationFn: () => restoreContact(organizationId, contact.id), onSuccess: onDeleted });
  return (
    <aside className="rounded-[10px] bg-muted p-6" data-testid="crm-detail-contacts" data-record-id={contact.id} data-archived={contact.archived_at ? "true" : "false"}>
      <h2 className="text-base font-semibold">{contact.full_name}</h2>
      <div className="mt-3 border-t border-border pt-3 text-sm"><h3 className="font-medium">Related records</h3><div className="mt-2 grid gap-1">
        {contact.company_id ? <button className="text-left text-accent underline" onClick={() => onNavigate({ tab: "companies", id: contact.company_id! })}>{companies.find((item) => item.id === contact.company_id)?.name ?? "Company"}</button> : null}
        {related?.[0].items.filter((item) => item.contact_id === contact.id).map((item) => <button key={item.id} className="text-left text-accent underline" onClick={() => onNavigate({ tab: "leads", id: item.id })}>{item.title}</button>)}
        {related?.[1].items.filter((item) => item.lead_id && related[0].items.some((lead) => lead.id === item.lead_id && lead.contact_id === contact.id)).map((item) => <button key={item.id} className="text-left text-accent underline" onClick={() => onNavigate({ tab: "inquiries", id: item.id })}>{item.subject}</button>)}
      </div></div>
      <div className="mt-4">
        <ContactFields form={form} formId="contact-edit" companies={companies} onSubmit={(values) => save.mutate(values)} />
      </div>
      {save.isSuccess ? <p className="mt-3 text-sm text-muted-foreground">Saved.</p> : null}
      {save.isError ? <div className="mt-3"><RequestError error={save.error} /></div> : null}
      {remove.isError ? <div className="mt-3"><RequestError error={remove.error} /></div> : null}
      <div className="mt-4 flex gap-2">
        <Button type="submit" form="contact-edit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save"}</Button>
        {contact.archived_at ? <Button type="button" variant="outline" disabled={restore.isPending} onClick={() => restore.mutate()}>{restore.isPending ? "Restoring…" : "Restore"}</Button> : <ConfirmButton label="Archive" confirmLabel="Confirm archive" pendingLabel="Archiving…" pending={remove.isPending} onConfirm={() => remove.mutate()} />}
      </div>
      {!contact.archived_at && contact.email ? (
        <ContactConsent key={contact.email} organizationId={organizationId} contactId={contact.id} />
      ) : null}
    </aside>
  );
}

function ContactConsent({ organizationId, contactId }: { organizationId: string; contactId: string }) {
  const client = useQueryClient();
  const key = ["marketing-consent", organizationId, contactId] as const;
  const [status, setStatus] = useState<ConsentStatus | "">("");
  const [source, setSource] = useState("");
  const consent = useQuery({ queryKey: key, queryFn: () => getMarketingConsent(organizationId, contactId) });
  const save = useMutation({
    mutationFn: (decision: ConsentStatus) => recordMarketingConsent(organizationId, contactId, decision, source.trim()),
    onSuccess: (record) => {
      client.setQueryData(key, record);
      void client.invalidateQueries({ queryKey: ["campaign-preview", organizationId] });
      setStatus("");
      setSource("");
    },
  });
  return (
    <section aria-label="Marketing consent" className="mt-5 space-y-3 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Marketing consent</h3>
      {consent.isPending ? <Skeleton className="h-5" /> : null}
      {consent.error ? <RequestError error={consent.error} /> : null}
      {consent.data ? (
        <p className="break-words text-sm text-muted-foreground">
          {consent.data.status === "granted" ? "Granted" : consent.data.status === "revoked" ? "Revoked" : "No consent recorded"}
          {consent.data.source ? ` · ${consent.data.source === "email_changed" ? "Email address changed" : consent.data.source}` : ""}
        </p>
      ) : null}
      <form className="grid gap-2" onSubmit={(event) => { event.preventDefault(); if (status && source.trim()) save.mutate(status); }}>
        <label className="grid gap-1 text-sm">Consent decision
          <select className="h-9 rounded-md border border-input bg-background px-2" value={status} onChange={(event) => setStatus(event.target.value as ConsentStatus | "")} required>
            <option value="">Choose a decision</option>
            <option value="granted">Record consent</option>
            <option value="revoked">Record withdrawal</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm">Consent source
          <Input value={source} onChange={(event) => setSource(event.target.value)} placeholder="Where the decision was recorded" required maxLength={80} />
        </label>
        <Button type="submit" variant="outline" className="justify-self-start" disabled={!status || !source.trim() || save.isPending}>Save consent</Button>
      </form>
      {save.error ? <RequestError error={save.error} /> : null}
      {save.isSuccess ? <p role="status" className="text-sm text-muted-foreground">Marketing consent updated.</p> : null}
    </section>
  );
}

function ContactFields({
  form,
  companies,
  formId = "contact-create",
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
        <Label htmlFor={`${formId}-name`}>Name</Label>
        <Input id={`${formId}-name`} {...form.register("full_name")} />
        {form.formState.errors.full_name ? <p className="text-sm text-destructive">{form.formState.errors.full_name.message}</p> : null}
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-email`}>Email</Label>
        <Input id={`${formId}-email`} {...form.register("email")} />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-phone`}>Phone</Label>
        <Input id={`${formId}-phone`} {...form.register("phone")} />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-title`}>Title</Label>
        <Input id={`${formId}-title`} {...form.register("title")} />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-company`}>Company</Label>
        <select id={`${formId}-company`} className="h-10 rounded-md border border-input bg-background px-3 text-sm" {...form.register("company_id")}>
          <option value="">No company</option>
          {companies.map((company) => (
            <option key={company.id} value={company.id}>{company.name}</option>
          ))}
        </select>
      </div>
    </form>
  );
}
