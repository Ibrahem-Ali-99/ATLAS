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
import { createCompany, getCompany, deleteCompany, listCompanies, listContacts, listInquiries, listLeads, restoreCompany, updateCompany } from "@/lib/records-api";
import { blankToNull, type Company } from "@/lib/records";

const schema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
  website: z.string().max(300),
  industry: z.string().max(120),
  notes: z.string().max(4000),
});

type FormValues = z.infer<typeof schema>;

function valuesOf(company?: Company): FormValues {
  return {
    name: company?.name ?? "",
    website: company?.website ?? "",
    industry: company?.industry ?? "",
    notes: company?.notes ?? "",
  };
}

function payload(values: FormValues) {
  return {
    name: values.name.trim(),
    website: blankToNull(values.website),
    industry: blankToNull(values.industry),
    notes: blankToNull(values.notes),
  };
}

type Navigate = (target: { tab: "companies" | "contacts" | "leads" | "inquiries"; id: string | null }) => void;

export function CompaniesPanel({ organizationId, selectedId: requestedId, onNavigate }: { organizationId: string; selectedId?: string | null; onNavigate: Navigate }) {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [open, setOpen] = useState(false);
  const selectedId = requestedId ?? null;
  const companies = useQuery({
    queryKey: ["companies", organizationId, query, page, includeArchived],
    queryFn: () => listCompanies(organizationId, { q: query, page, includeArchived }),
  });
  const related = useQuery({
    queryKey: ["company-relations", organizationId, selectedId],
    queryFn: async () => Promise.all([listContacts(organizationId, { pageSize: 100 }), listLeads(organizationId, { pageSize: 100 }), listInquiries(organizationId, { pageSize: 100 })]),
    enabled: Boolean(selectedId),
  });

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const selectedInList = companies.data?.items.find((item) => item.id === selectedId);
  const record = useQuery({
    queryKey: ["companies", organizationId, "record", selectedId],
    queryFn: () => getCompany(organizationId, selectedId ?? ""),
    enabled: Boolean(selectedId && !selectedInList),
  });
  const selected = selectedInList ?? record.data ?? null;

  return (
    <div className={selected ? "grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(20rem,0.8fr)]" : "min-w-0"}>
      <section className="overflow-hidden rounded-xl border border-border bg-card shadow-[0_18px_60px_rgba(0,0,0,0.16)]">
        <div className="flex flex-col gap-3 border-b border-border/80 bg-card/80 p-4 sm:flex-row sm:items-center">
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search companies"
            aria-label="Search companies"
          />
          <label className="flex items-center gap-2 text-sm text-muted-foreground"><input type="checkbox" checked={includeArchived} onChange={(event) => setIncludeArchived(event.target.checked)} /> Show archived</label>
          <Button type="button" onClick={() => setOpen(true)}>
            New company
          </Button>
        </div>
        {companies.isPending ? (
          <div className="space-y-2 px-4 pb-4">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : null}
        {companies.isError ? (
          <div className="px-4 pb-4">
            <RequestError error={companies.error} />
          </div>
        ) : null}
        {companies.data && companies.data.items.length === 0 ? (
          <p className="px-4 pb-6 text-sm text-muted-foreground">No companies match this search.</p>
        ) : null}
        {companies.data && companies.data.items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Industry</TableHead>
                <TableHead>Website</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {companies.data.items.map((company) => (
                <TableRow
                  key={company.id}
                  className={company.id === selectedId ? "bg-accent/40" : undefined}
                  onClick={() => onNavigate({ tab: "companies", id: company.id })}
                >
                  <TableCell>
                    <button type="button" className="text-left font-medium" onClick={() => onNavigate({ tab: "companies", id: company.id })}>
                      {company.name}
                    </button>
                  </TableCell>
                  <TableCell>{company.industry ?? "—"}</TableCell>
                  <TableCell>{company.website ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
        {companies.data ? (
          <Pager page={companies.data.page} pageSize={companies.data.page_size} total={companies.data.total} onPage={setPage} />
        ) : null}
      </section>
      {record.isError && !selectedInList ? <RequestError error={record.error} /> : null}
      <CompanyEditor
        organizationId={organizationId}
        company={selected}
        related={related.data}
        onNavigate={onNavigate}
        onDeleted={() => {
          onNavigate({ tab: "companies", id: null });
          void queryClient.invalidateQueries({ queryKey: ["companies", organizationId] });
        }}
        onSaved={() => void queryClient.invalidateQueries({ queryKey: ["companies", organizationId] })}
      />
      <CompanyDialog
        organizationId={organizationId}
        open={open}
        onOpenChange={setOpen}
        onCreated={(company) => {
          onNavigate({ tab: "companies", id: company.id });
          void queryClient.invalidateQueries({ queryKey: ["companies", organizationId] });
        }}
      />
    </div>
  );
}

function CompanyDialog({
  organizationId,
  open,
  onOpenChange,
  onCreated,
}: {
  organizationId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (company: Company) => void;
}) {
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: valuesOf() });
  const mutation = useMutation({
    mutationFn: (values: FormValues) => createCompany(organizationId, payload(values)),
    onSuccess: (company) => {
      form.reset(valuesOf());
      onOpenChange(false);
      onCreated(company);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New company</DialogTitle>
          <DialogDescription>The company is saved in this organization only.</DialogDescription>
        </DialogHeader>
        <CompanyFields form={form} onSubmit={(values) => mutation.mutate(values)} />
        {mutation.isError ? <RequestError error={mutation.error} /> : null}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" form="company-create" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CompanyEditor({
  organizationId,
  company,
  related,
  onNavigate,
  onSaved,
  onDeleted,
}: {
  organizationId: string;
  company: Company | null;
  related?: [{ items: import("@/lib/records").Contact[] }, { items: import("@/lib/records").Lead[] }, { items: import("@/lib/records").Inquiry[] }];
  onNavigate: Navigate;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  if (!company) {
    return (
      <aside className="rounded-[10px] bg-muted p-6 text-sm text-muted-foreground">
        Select a company to view and edit it.
      </aside>
    );
  }
  return (
    <CompanyEditorForm
      key={company.id}
      organizationId={organizationId}
      company={company}
      related={related}
      onNavigate={onNavigate}
      onSaved={onSaved}
      onDeleted={onDeleted}
    />
  );
}

function CompanyEditorForm({
  organizationId,
  company,
  related,
  onNavigate,
  onSaved,
  onDeleted,
}: {
  organizationId: string;
  company: Company;
  related?: [{ items: import("@/lib/records").Contact[] }, { items: import("@/lib/records").Lead[] }, { items: import("@/lib/records").Inquiry[] }];
  onNavigate: Navigate;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: valuesOf(company) });
  const save = useMutation({
    mutationFn: (values: FormValues) => updateCompany(organizationId, company.id, payload(values)),
    onSuccess: onSaved,
  });
  const remove = useMutation({ mutationFn: () => deleteCompany(organizationId, company.id), onSuccess: onDeleted });
  const restore = useMutation({ mutationFn: () => restoreCompany(organizationId, company.id), onSuccess: onDeleted });

  return (
    <aside className="rounded-[10px] bg-muted p-6" data-testid="crm-detail-companies" data-record-id={company.id} data-archived={company.archived_at ? "true" : "false"}>
      <h2 className="text-base font-semibold">{company.name}</h2>
      <p className="mt-1 text-sm text-muted-foreground">Updated {new Date(company.updated_at).toLocaleString()}</p>
      <div className="mt-4 border-t border-border pt-4">
        <h3 className="text-sm font-medium">Related records</h3>
        <div className="mt-2 grid gap-1 text-sm">
          {related?.[0].items.filter((item) => item.company_id === company.id).map((item) => <button key={item.id} className="text-left text-primary underline" onClick={() => onNavigate({ tab: "contacts", id: item.id })}>{item.full_name}</button>)}
          {related?.[1].items.filter((item) => item.company_id === company.id).map((item) => <button key={item.id} className="text-left text-primary underline" onClick={() => onNavigate({ tab: "leads", id: item.id })}>{item.title}</button>)}
          {related?.[2].items.filter((item) => item.company_id === company.id).map((item) => <button key={item.id} className="text-left text-primary underline" onClick={() => onNavigate({ tab: "inquiries", id: item.id })}>{item.subject}</button>)}
          {related && related.every((page) => page.items.every((item) => item.company_id !== company.id)) ? <p className="text-muted-foreground">No linked records yet.</p> : null}
        </div>
      </div>
      <div className="mt-4">
        <CompanyFields form={form} formId="company-edit" onSubmit={(values) => save.mutate(values)} />
      </div>
      {save.isSuccess ? <p className="mt-3 text-sm text-muted-foreground">Saved.</p> : null}
      {save.isError ? <div className="mt-3"><RequestError error={save.error} /></div> : null}
      {remove.isError ? <div className="mt-3"><RequestError error={remove.error} /></div> : null}
      <div className="mt-4 flex gap-2">
        <Button type="submit" form="company-edit" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save"}
        </Button>
        {company.archived_at ? (
          <Button type="button" variant="outline" disabled={restore.isPending} onClick={() => restore.mutate()}>{restore.isPending ? "Restoring…" : "Restore"}</Button>
        ) : (
          <ConfirmButton label="Archive" confirmLabel="Confirm archive" pendingLabel="Archiving…" pending={remove.isPending} onConfirm={() => remove.mutate()} />
        )}
      </div>
    </aside>
  );
}

function CompanyFields({
  form,
  formId = "company-create",
  onSubmit,
}: {
  form: ReturnType<typeof useForm<FormValues>>;
  formId?: string;
  onSubmit: (values: FormValues) => void;
}) {
  return (
    <form id={formId} className="grid gap-3" onSubmit={form.handleSubmit(onSubmit)}>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-name`}>Name</Label>
        <Input id={`${formId}-name`} {...form.register("name")} />
        {form.formState.errors.name ? <RequestError error={new Error(form.formState.errors.name.message)} /> : null}
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-industry`}>Industry</Label>
        <Input id={`${formId}-industry`} {...form.register("industry")} />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-website`}>Website</Label>
        <Input id={`${formId}-website`} {...form.register("website")} />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${formId}-notes`}>Notes</Label>
        <Textarea id={`${formId}-notes`} {...form.register("notes")} />
      </div>
    </form>
  );
}
