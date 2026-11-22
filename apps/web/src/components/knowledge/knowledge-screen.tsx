"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ConfirmButton } from "@/components/confirm-button";
import { PageHeader } from "@/components/page-header";
import { RequestError } from "@/components/request-error";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  deleteDocument,
  documentChunks,
  listDocuments,
  reindexDocument,
  searchDocuments,
  uploadDocument,
} from "@/lib/records-api";
import type { DocumentStatus, KnowledgeDocument } from "@/lib/records";
import { useWorkspace } from "@/lib/use-workspace";

function statusVariant(status: DocumentStatus): "default" | "secondary" {
  return status === "ready" ? "default" : "secondary";
}

function statusCopy(status: DocumentStatus): string {
  if (status === "pending") {
    return "Waiting to start indexing.";
  }
  if (status === "processing") {
    return "Indexing is in progress. This list refreshes until it finishes.";
  }
  if (status === "ready") {
    return "Indexed and searchable.";
  }
  return "Indexing failed. The stored error is shown on the row.";
}

export function KnowledgeScreen() {
  const { organizationId, organizationName } = useWorkspace();
  if (!organizationId) {
    return null;
  }
  return <KnowledgeWorkspace organizationId={organizationId} organizationName={organizationName ?? "this organization"} />;
}

function KnowledgeWorkspace({
  organizationId,
  organizationName,
}: {
  organizationId: string;
  organizationName: string;
}) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [submitted, setSubmitted] = useState("");
  const documents = useQuery({
    queryKey: ["documents", organizationId],
    queryFn: () => listDocuments(organizationId, { pageSize: 50 }),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      const working = items.some((item) => item.status === "pending" || item.status === "processing");
      return working ? 2000 : false;
    },
  });
  const upload = useMutation({
    mutationFn: (file: File) => uploadDocument(organizationId, file),
    onSuccess: (document) => {
      setSelectedId(document.id);
      void queryClient.invalidateQueries({ queryKey: ["documents", organizationId] });
    },
  });
  const hits = useQuery({
    queryKey: ["document-search", organizationId, submitted],
    queryFn: () => searchDocuments(organizationId, submitted),
    enabled: submitted.length >= 2,
  });

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <PageHeader title="Knowledge">
        PDF and text files for {organizationName}. Indexing runs in the background. Search uses this organization&apos;s ready documents only.
      </PageHeader>
      <section className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-sm font-medium">Upload</h2>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">PDF and TXT only. Other file types are rejected and nothing is stored.</p>
        <label className="mt-3 grid gap-2 text-sm">
          <span className="sr-only">Upload a PDF or TXT file</span>
          <input
            type="file"
            accept=".pdf,.txt,application/pdf,text/plain"
            className="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-sm file:font-medium file:text-primary-foreground"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) {
                upload.mutate(file);
              }
              event.target.value = "";
            }}
          />
        </label>
        {upload.isPending ? <p className="mt-3 text-sm text-muted-foreground">Uploading…</p> : null}
        {upload.isSuccess ? <p className="mt-3 text-sm text-muted-foreground">Uploaded. Indexing continues until the status is ready.</p> : null}
        {upload.isError ? <div className="mt-3"><RequestError error={upload.error} /></div> : null}
      </section>
      <section className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-sm font-medium">Search</h2>
        <form
          className="mt-3 flex flex-col gap-3 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            setSubmitted(search.trim());
          }}
        >
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search indexed text" aria-label="Search documents" />
          <Button type="submit">Search</Button>
        </form>
        {submitted.length > 0 && submitted.length < 2 ? (
          <p className="mt-3 text-sm text-muted-foreground">Enter at least two characters.</p>
        ) : null}
        {hits.isFetching ? <p className="mt-3 text-sm text-muted-foreground">Searching…</p> : null}
        {hits.isError ? <div className="mt-3"><RequestError error={hits.error} /></div> : null}
        {submitted.length >= 2 && hits.data ? (
          <p className="mt-3 text-sm text-muted-foreground">
            {hits.data.items.length === 0
              ? `No indexed excerpts matched “${submitted}”.`
              : `${hits.data.items.length} excerpt${hits.data.items.length === 1 ? "" : "s"} matched “${submitted}”. Order follows the stored search rank.`}
          </p>
        ) : null}
        <ul className="mt-3 space-y-3">
          {hits.data?.items.map((hit) => (
            <li key={hit.id} className="rounded-md border border-border bg-background p-3 text-sm">
              <p className="font-medium">
                {hit.document_title}
                {hit.page_number !== null ? ` · page ${hit.page_number}` : ""}
              </p>
              <p className="mt-2 whitespace-pre-wrap leading-6 text-muted-foreground">{hit.content}</p>
            </li>
          ))}
        </ul>
      </section>
      <section className="rounded-xl border border-border bg-card">
        {documents.isPending ? <div className="space-y-2 p-4"><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-full" /></div> : null}
        {documents.isError ? <div className="p-4"><RequestError error={documents.error} /></div> : null}
        {documents.data && documents.data.items.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">No documents uploaded yet.</p>
        ) : null}
        {documents.data && documents.data.items.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Size</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.data.items.map((document) => (
                <DocumentRow
                  key={document.id}
                  organizationId={organizationId}
                  document={document}
                  selected={document.id === selectedId}
                  onSelect={() => setSelectedId(document.id)}
                  onUpdated={() => void queryClient.invalidateQueries({ queryKey: ["documents", organizationId] })}
                  onDeleted={() => {
                    if (document.id === selectedId) {
                      setSelectedId(null);
                    }
                    void queryClient.invalidateQueries({ queryKey: ["documents", organizationId] });
                  }}
                />
              ))}
            </TableBody>
          </Table>
        ) : null}
      </section>
      {selectedId ? (
        <ChunkList
          organizationId={organizationId}
          documentId={selectedId}
          status={documents.data?.items.find((item) => item.id === selectedId)?.status ?? "pending"}
        />
      ) : null}
    </div>
  );
}

function DocumentRow({
  organizationId,
  document,
  selected,
  onSelect,
  onUpdated,
  onDeleted,
}: {
  organizationId: string;
  document: KnowledgeDocument;
  selected: boolean;
  onSelect: () => void;
  onUpdated: () => void;
  onDeleted: () => void;
}) {
  const reindex = useMutation({
    mutationFn: () => reindexDocument(organizationId, document.id),
    onSuccess: onUpdated,
  });
  const remove = useMutation({
    mutationFn: () => deleteDocument(organizationId, document.id),
    onSuccess: onDeleted,
  });
  return (
    <TableRow className={selected ? "bg-accent/40" : undefined}>
      <TableCell>
        <button type="button" className="text-left font-medium" onClick={onSelect}>{document.title}</button>
        {document.error_message ? <p className="mt-1 text-xs text-red-300">{document.error_message}</p> : null}
        {reindex.isError ? <RequestError error={reindex.error} /> : null}
        {remove.isError ? <RequestError error={remove.error} /> : null}
      </TableCell>
      <TableCell>
        <Badge variant={statusVariant(document.status)}>{document.status}</Badge>
        <p className="mt-1 max-w-48 text-xs leading-5 text-muted-foreground">{statusCopy(document.status)}</p>
      </TableCell>
      <TableCell>{Math.ceil(document.byte_size / 1024)} KB</TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" disabled={reindex.isPending} onClick={() => reindex.mutate()}>
            {reindex.isPending ? "Reindexing…" : "Reindex"}
          </Button>
          <ConfirmButton
            label="Delete"
            confirmLabel="Confirm delete"
            pendingLabel="Deleting…"
            pending={remove.isPending}
            size="sm"
            onConfirm={() => remove.mutate()}
          />
        </div>
      </TableCell>
    </TableRow>
  );
}

function ChunkList({
  organizationId,
  documentId,
  status,
}: {
  organizationId: string;
  documentId: string;
  status: DocumentStatus;
}) {
  const chunks = useQuery({
    queryKey: ["document-chunks", organizationId, documentId, status],
    queryFn: () => documentChunks(organizationId, documentId),
    refetchInterval: status === "pending" || status === "processing" ? 2000 : false,
  });
  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <h2 className="text-base font-semibold">Extracted text</h2>
      <p className="mt-1 text-sm text-muted-foreground">{statusCopy(status)}</p>
      {chunks.isPending ? <Skeleton className="mt-3 h-16 w-full" /> : null}
      {chunks.isError ? <div className="mt-3"><RequestError error={chunks.error} /></div> : null}
      {chunks.data && chunks.data.items.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">
          {status === "failed"
            ? "This document has no extracted text."
            : "Text appears after processing finishes."}
        </p>
      ) : null}
      <ul className="mt-3 space-y-3">
        {chunks.data?.items.map((chunk) => (
          <li key={chunk.id} className="rounded-md border border-border p-3 text-sm">
            <p className="text-xs text-muted-foreground">
              Chunk {chunk.chunk_index + 1}
              {chunk.page_number !== null ? ` · page ${chunk.page_number}` : ""}
            </p>
            <p className="mt-2 whitespace-pre-wrap">{chunk.content}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
