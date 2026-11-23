"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ConfirmButton } from "@/components/confirm-button";
import { ProviderNotice } from "@/components/provider-notice";
import { RequestError } from "@/components/request-error";
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
import { documentOriginLabel, documentOrigins, type DocumentOrigin, type DocumentStatus, type KnowledgeDocument } from "@/lib/records";
import { useWorkspace } from "@/lib/use-workspace";

function statusClass(status: DocumentStatus): string {
  if (status === "ready") {
    return "text-success";
  }
  if (status === "failed") {
    return "text-destructive";
  }
  return "text-warning";
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
  const [origin, setOrigin] = useState<DocumentOrigin>("operational");
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
    mutationFn: (file: File) => uploadDocument(organizationId, file, origin),
    onSuccess: (document) => {
      setSelectedId(document.id);
      void queryClient.invalidateQueries({ queryKey: ["documents", organizationId] });
    },
  });
  const selected = documents.data?.items.find((item) => item.id === selectedId) ?? null;
  const hits = useQuery({
    queryKey: ["document-search", organizationId, submitted],
    queryFn: () => searchDocuments(organizationId, submitted),
    enabled: submitted.length >= 2,
  });

  return (
    <div className="flex w-full min-w-0 flex-col gap-6">
      <header>
        <h1 className="text-[31px] leading-none text-foreground">Company knowledge</h1>
        <p className="mt-3 max-w-3xl text-sm text-muted-foreground">
          Uploaded documents, indexing status, and retrieved evidence for {organizationName}.
        </p>
      </header>
      <ProviderNotice organizationId={organizationId} detail />
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(20rem,0.8fr)]">
      <div className="flex flex-col gap-4">
      <section className="rounded-[10px] bg-muted p-4">
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
        <label className="mt-3 grid max-w-xs gap-2 text-sm">
          <span className="text-muted-foreground">Record origin</span>
          <select aria-label="Document origin" value={origin} onChange={(event) => setOrigin(event.target.value as DocumentOrigin)} className="h-10 rounded-[10px] border-0 bg-secondary px-3 text-sm text-foreground">
            {documentOrigins.map((value) => <option key={value} value={value}>{value === "operational" ? "Operational" : "Demo"}</option>)}
          </select>
          <span className="text-xs text-muted-foreground">Stored with the upload; it cannot be changed here.</span>
        </label>
        {upload.isSuccess ? <p className="mt-3 text-sm text-success">Uploaded as {upload.data.origin}. Indexing continues until the status is ready.</p> : null}
        {upload.isError ? <div className="mt-3"><RequestError error={upload.error} /></div> : null}
      </section>
      <section className="min-w-0 overflow-x-auto rounded-[10px] bg-muted">
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
                <TableHead>Origin</TableHead>
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
      </div>
      <div className="flex flex-col gap-4">
      <section className="rounded-[10px] bg-muted p-4">
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
              <li key={hit.id} className="rounded-[10px] bg-secondary p-3 text-sm">
              <p className="font-medium">
                {hit.document_title}
                {hit.page_number !== null ? ` · page ${hit.page_number}` : ""}
              </p>
              <p className="mt-2 whitespace-pre-wrap leading-6 text-muted-foreground">{hit.content}</p>
            </li>
          ))}
        </ul>
      </section>
      {selected ? (
        <ChunkList organizationId={organizationId} document={selected} />
      ) : (
        <p className="rounded-[10px] bg-muted p-4 text-sm text-muted-foreground">
          Select a document to inspect its extracted passages, source metadata, and any processing error.
        </p>
      )}
      </div>
      </div>
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
        <p className={`text-xs uppercase tracking-[0.12em] ${statusClass(document.status)}`}>{document.status}</p>
        <p className="mt-1 max-w-48 text-xs leading-5 text-muted-foreground">{statusCopy(document.status)}</p>
      </TableCell>
      <TableCell className={document.origin === "demo" ? "text-primary" : "text-muted-foreground"}>
        {documentOriginLabel(document.origin)}
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
  document,
}: {
  organizationId: string;
  document: KnowledgeDocument;
}) {
  const status = document.status;
  const chunks = useQuery({
    queryKey: ["document-chunks", organizationId, document.id, status],
    queryFn: () => documentChunks(organizationId, document.id),
    refetchInterval: status === "pending" || status === "processing" ? 2000 : false,
  });
  return (
    <section className="rounded-[10px] bg-muted p-4">
      <h2 className="text-base text-foreground">{document.title}</h2>
      <p className={`mt-2 text-xs uppercase tracking-[0.12em] ${statusClass(status)}`}>{statusCopy(status)}</p>
      <dl className="mt-4 space-y-2 text-xs text-muted-foreground">
        <div><dt className="text-subtle">File</dt><dd>{document.filename}</dd></div>
        <div><dt className="text-subtle">Type</dt><dd>{document.media_type}</dd></div>
        <div><dt className="text-subtle">Size</dt><dd>{Math.ceil(document.byte_size / 1024)} KB</dd></div>
        <div><dt className="text-subtle">Origin</dt><dd>{documentOriginLabel(document.origin)}</dd></div>
        <div><dt className="text-subtle">Updated</dt><dd>{new Date(document.updated_at).toLocaleString()}</dd></div>
      </dl>
      {document.error_message ? <p className="mt-4 text-sm leading-6 text-destructive">{document.error_message}</p> : null}
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
          <li key={chunk.id} className="rounded-[10px] bg-secondary p-3 text-sm">
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
