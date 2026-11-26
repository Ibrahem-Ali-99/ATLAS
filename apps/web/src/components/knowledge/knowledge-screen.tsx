"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, FileText, FolderOpen, Search, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useRef, useState } from "react";

import { ConfirmButton } from "@/components/confirm-button";
import { getProviderStatus } from "@/components/provider-notice";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { RequestError } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  archiveDocument,
  deleteDocument,
  createKnowledgeEvaluation,
  compareKnowledgeEvaluations,
  documentChunks,
  getDocument,
  listDocuments,
  previewDocument,
  reindexDocument,
  replaceDocument,
  restoreDocument,
  retryDocumentJob,
  searchDocuments,
  runKnowledgeEvaluation,
  uploadDocument,
} from "@/lib/records-api";
import { documentOriginLabel, documentOrigins, type DocumentOrigin, type DocumentStatus, type KnowledgeDocument, type PageResult } from "@/lib/records";
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
  const { organizationId, organizationName, role } = useWorkspace();
  if (!organizationId) {
    return null;
  }
  return <KnowledgeWorkspace key={organizationId} organizationId={organizationId} organizationName={organizationName ?? "this organization"} isAdmin={role === "admin"} />;
}

function KnowledgeWorkspace({
  organizationId,
  organizationName,
  isAdmin,
}: {
  organizationId: string;
  organizationName: string;
  isAdmin: boolean;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<"library" | "search" | "evaluation">("library");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [documentName, setDocumentName] = useState("");
  const deferredName = useDeferredValue(documentName);
  const [statusFilter, setStatusFilter] = useState<DocumentStatus | "">("");
  const [typeFilter, setTypeFilter] = useState<"pdf" | "txt" | "">("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [page, setPage] = useState(1);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const clearFilters = () => {
    setDocumentName("");
    setStatusFilter("");
    setTypeFilter("");
    setPage(1);
  };
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [origin, setOrigin] = useState<DocumentOrigin>("operational");
  const [evaluationQuestion, setEvaluationQuestion] = useState("");
  const [evaluationEvidence, setEvaluationEvidence] = useState("");
  const [evaluationMode, setEvaluationMode] = useState("grounded");
  const [evaluation, setEvaluation] = useState<{ evidence_match: boolean; answer_grounded: boolean | null; case_result: Record<string, unknown>; retrieved_sources: { document_title: string; score: number }[]; failure_reason: string | null } | null>(null);
  const documents = useQuery({
    queryKey: ["documents", organizationId, deferredName, statusFilter, typeFilter, includeArchived, page],
    queryFn: () => listDocuments(organizationId, {
      q: deferredName.trim(), status: statusFilter || undefined, fileType: typeFilter || undefined,
      includeArchived, page,
    }),
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
      setUploadOpen(false);
      setFile(null);
      clearFilters();
      setIncludeArchived(false);
      setView("library");
      void queryClient.invalidateQueries({ queryKey: ["documents", organizationId] });
    },
  });
  const listed = documents.data?.items.find((item) => item.id === selectedId) ?? null;
  const detail = useQuery({
    queryKey: ["document", organizationId, selectedId],
    queryFn: () => getDocument(organizationId, selectedId ?? ""),
    enabled: Boolean(selectedId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "processing" ? 2000 : false;
    },
  });
  const selected = listed ?? detail.data ?? null;
  const embeddings = useQuery({
    queryKey: ["provider-status", organizationId],
    queryFn: () => getProviderStatus(organizationId),
    retry: false,
  });
  const hits = useQuery({
    queryKey: ["document-search", organizationId, submitted],
    queryFn: () => searchDocuments(organizationId, submitted),
    enabled: view === "search" && submitted.length >= 2,
  });
  const runEvaluation = useMutation({ mutationFn: async () => { const question = await createKnowledgeEvaluation(organizationId, evaluationQuestion, evaluationEvidence.split(",").map((item) => item.trim()).filter(Boolean), evaluationMode); return runKnowledgeEvaluation(organizationId, question.id); }, onSuccess: setEvaluation });
  const comparison = useQuery({ queryKey: ["knowledge-evaluation-comparison", organizationId], queryFn: () => compareKnowledgeEvaluations(organizationId), enabled: view === "evaluation" });

  return (
    <div className="flex w-full min-w-0 max-w-full flex-col gap-6 overflow-x-hidden">
      <PageHeader title="Company knowledge" actions={
        <Button onClick={() => { upload.reset(); setUploadOpen(true); }}><UploadCloud size={16} /> Upload document</Button>
      }>
        Documents ATLAS can search when answering questions for {organizationName}.
      </PageHeader>
      <div role="group" aria-label="Knowledge views" className="flex flex-wrap gap-2">
        <Button variant={view === "library" ? "secondary" : "ghost"} aria-pressed={view === "library"} onClick={() => setView("library")}><FolderOpen size={16} /> Document library</Button>
        <Button variant={view === "search" ? "secondary" : "ghost"} aria-pressed={view === "search"} onClick={() => setView("search")}><Search size={16} /> Semantic search</Button>
        <Button variant={view === "evaluation" ? "secondary" : "ghost"} aria-pressed={view === "evaluation"} onClick={() => setView("evaluation")}>Answer checks</Button>
      </div>
      <EmbeddingGuide status={embeddings.data} />
      <Dialog open={uploadOpen} onOpenChange={(open) => {
        if (upload.isPending) return;
        setUploadOpen(open);
        if (!open) setFile(null);
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Upload document</DialogTitle>
            <DialogDescription>Add a PDF or TXT file to the knowledge library for {organizationName}.</DialogDescription>
          </DialogHeader>
          <form className="grid gap-4" onSubmit={(event) => {
            event.preventDefault();
            if (file && !upload.isPending) upload.mutate(file);
          }}>
            <label className="grid gap-2 text-sm">
              Choose a PDF or TXT file
              <input
                type="file"
                accept=".pdf,.txt,application/pdf,text/plain"
                className="w-full min-w-0 rounded-md border border-border p-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-1.5"
                disabled={upload.isPending}
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>
            <label className="grid gap-2 text-sm">
              Document origin
              <select value={origin} disabled={upload.isPending} onChange={(event) => setOrigin(event.target.value as DocumentOrigin)} className="h-10 rounded-md border border-border bg-background px-3">
                {documentOrigins.map((value) => <option key={value} value={value}>{documentOriginLabel(value)}</option>)}
              </select>
            </label>
            {upload.isError ? <RequestError error={upload.error} /> : null}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" disabled={upload.isPending} onClick={() => { setFile(null); setUploadOpen(false); }}>Cancel</Button>
              <Button type="submit" disabled={!file || upload.isPending}>{upload.isPending ? "Uploading…" : "Upload and index"}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
      {upload.isSuccess ? <p role="status" className="text-sm text-success">Document uploaded. The library shows its indexing status.</p> : null}
      {view === "library" ? (
        <div className="grid min-w-0 items-start gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(18rem,0.6fr)]">
          <section aria-label="Document library" className="min-w-0 max-w-full overflow-hidden rounded-xl border border-border bg-card">
            <div className="flex w-full min-w-0 flex-wrap items-center gap-2 border-b border-border p-4 [&>select]:h-9 [&>select]:max-w-full [&>select]:rounded-md [&>select]:border [&>select]:border-border [&>select]:bg-background [&>select]:px-2 [&>select]:text-sm">
              <Input className="min-w-40 flex-1" aria-label="Search document library" placeholder="Search by document name" value={documentName} onChange={(event) => { setDocumentName(event.target.value); setPage(1); }} />
              <select aria-label="Filter by processing status" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value as DocumentStatus | ""); setPage(1); }}>
                <option value="">All statuses</option>
                <option value="ready">Ready</option>
                <option value="pending">Queued</option>
                <option value="processing">Processing</option>
                <option value="failed">Failed</option>
              </select>
              <select aria-label="Filter by file type" value={typeFilter} onChange={(event) => { setTypeFilter(event.target.value as typeof typeFilter); setPage(1); }}>
                <option value="">All file types</option>
                <option value="pdf">PDF</option>
                <option value="txt">TXT</option>
              </select>
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input type="checkbox" checked={includeArchived} onChange={(event) => { setIncludeArchived(event.target.checked); setPage(1); }} />
                Show archived
              </label>
            </div>
        {documents.isPending ? <div className="space-y-2 p-4"><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-full" /></div> : null}
        {documents.isError ? <div className="p-4"><RequestError error={documents.error} /></div> : null}
        {documents.data && documents.data.items.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
            <BookOpen className="text-muted-foreground" size={24} />
            <p className="font-medium">{documentName || statusFilter || typeFilter || includeArchived ? "No matching documents" : "No documents uploaded yet"}</p>
            {documentName || statusFilter || typeFilter || includeArchived ? <Button variant="outline" size="sm" onClick={() => { clearFilters(); setIncludeArchived(false); }}>Clear filters</Button> : null}
          </div>
        ) : null}
        {documents.data && documents.data.items.length > 0 ? (
          <div className="min-w-0 overflow-x-auto">
          <Table aria-label="Knowledge documents">
            <TableHeader>
              <TableRow>
                <TableHead>Document</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Origin</TableHead>
                <TableHead>Updated</TableHead>
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
                  isAdmin={isAdmin}
                  onSelect={() => { setHighlightId(null); setSelectedId(document.id); }}
                  onUpdated={(updated) => {
                    queryClient.setQueryData(["document", organizationId, updated.id], updated);
                    queryClient.setQueriesData<PageResult<KnowledgeDocument>>({ queryKey: ["documents", organizationId] }, (cached) =>
                      cached && { ...cached, items: cached.items.map((item) => item.id === updated.id ? updated : item) },
                    );
                    void queryClient.invalidateQueries({ queryKey: ["documents", organizationId] });
                    void queryClient.invalidateQueries({ queryKey: ["document-search", organizationId] });
                    void queryClient.invalidateQueries({ queryKey: ["document-preview", organizationId, updated.id] });
                    void queryClient.invalidateQueries({ queryKey: ["document-chunks", organizationId, updated.id] });
                  }}
                  onDeleted={() => {
                    if (document.id === selectedId) {
                      setSelectedId(null);
                    }
                    void queryClient.invalidateQueries({ queryKey: ["documents", organizationId] });
                    if (documents.data?.items.length === 1 && page > 1) setPage(page - 1);
                    void queryClient.invalidateQueries({ queryKey: ["document-search", organizationId] });
                  }}
                />
              ))}
            </TableBody>
          </Table>
          </div>
        ) : null}
            {documents.data && (documents.data.total > documents.data.page_size || page > 1) ? (
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-3 text-sm text-muted-foreground">
                <span>{documents.data.total} documents · Page {page}</span>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</Button>
                  <Button size="sm" variant="outline" disabled={page * documents.data.page_size >= documents.data.total} onClick={() => setPage(page + 1)}>Next</Button>
                </div>
              </div>
            ) : null}
          </section>
          {selected ? <ChunkList organizationId={organizationId} document={selected} highlightId={highlightId} /> : (
            <div className="rounded-xl border border-border bg-card p-6 text-sm text-muted-foreground">Select a document to review its details and extracted text.</div>
          )}
        </div>
      ) : null}
      {view === "search" ? (
      <section className="rounded-xl border border-border bg-card p-5">
        <h2 className="font-medium">Semantic search</h2>
        <p className="mt-1 text-sm text-muted-foreground">Find relevant passages in indexed workspace documents.</p>
        <form
          className="mt-3 flex flex-col gap-3 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            const next = search.trim();
            if (next === submitted && next.length >= 2) void hits.refetch();
            setSubmitted(next);
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
                <span className="ml-2 text-xs text-muted-foreground">score {hit.score.toFixed(4)}</span>
              </p>
              <p className="mt-2 whitespace-pre-wrap leading-6 text-muted-foreground">{hit.content}</p>
              <Button type="button" size="sm" variant="outline" className="mt-3" onClick={() => { setSelectedId(hit.document_id); setHighlightId(hit.id); setView("library"); }}>Open source</Button>
            </li>
          ))}
        </ul>
      </section>
      ) : null}
      {view === "evaluation" ? (
        <section className="rounded-xl border border-border bg-card p-5">
          <h2 className="font-medium">Answer checks</h2>
          <p className="mt-1 text-xs text-muted-foreground">Run an organization-scoped evidence check against indexed documents.</p>
          <div className="mt-3 grid gap-2">
            <select aria-label="Evaluation mode" value={evaluationMode} onChange={(event) => setEvaluationMode(event.target.value)} className="h-10 rounded-md border border-border bg-background px-3 text-sm">
              <option value="grounded">Retrieval / grounded</option>
              <option value="missing_knowledge">Missing knowledge</option>
              <option value="human_handoff">Human handoff</option>
              <option value="low_confidence">Low confidence</option>
            </select>
            <Input aria-label="Evaluation question" placeholder="Question to evaluate" value={evaluationQuestion} onChange={(event) => setEvaluationQuestion(event.target.value)} />
            <Input aria-label="Expected evidence" placeholder="Expected evidence terms, comma separated" value={evaluationEvidence} onChange={(event) => setEvaluationEvidence(event.target.value)} />
            <Button onClick={() => runEvaluation.mutate()} disabled={!evaluationQuestion.trim() || runEvaluation.isPending}>{runEvaluation.isPending ? "Evaluating…" : "Run evaluation"}</Button>
          </div>
          {runEvaluation.isError ? <div className="mt-3"><RequestError error={runEvaluation.error} /></div> : null}
          {evaluation ? <div className="mt-3 rounded-md bg-secondary p-3 text-sm"><p className={evaluation.answer_grounded ? "text-success" : "text-warning"}>{evaluation.answer_grounded ? "Evaluation passed." : evaluation.failure_reason ?? "Evaluation requires review."}</p><p className="mt-1 text-xs text-muted-foreground">Mode: {String(evaluation.case_result.scenario ?? evaluationMode)} · side effects: {String(evaluation.case_result.side_effects ?? "none")}</p>{evaluation.retrieved_sources.length ? <p className="mt-1 text-xs text-muted-foreground">Sources: {evaluation.retrieved_sources.map((source) => `${source.document_title} (${source.score.toFixed(4)})`).join(", ")}</p> : null}</div> : null}
          {comparison.data ? <p className="mt-3 text-xs text-muted-foreground">Historical comparison: {comparison.data.regressions.length} regressions, {comparison.data.improvements.length} improvements.</p> : null}
        </section>
      ) : null}
    </div>
  );
}

function DocumentRow({
  organizationId,
  document,
  selected,
  isAdmin,
  onSelect,
  onUpdated,
  onDeleted,
}: {
  organizationId: string;
  document: KnowledgeDocument;
  selected: boolean;
  isAdmin: boolean;
  onSelect: () => void;
  onUpdated: (document: KnowledgeDocument) => void;
  onDeleted: () => void;
}) {
  const replaceInput = useRef<HTMLInputElement>(null);
  const archived = Boolean(document.archived_at);
  const indexing = document.status === "pending" || document.status === "processing";
  const reindex = useMutation({
    mutationFn: () => document.status === "failed" && isAdmin
      ? retryDocumentJob(organizationId, document.id)
      : reindexDocument(organizationId, document.id),
    onSuccess: onUpdated,
  });
  const archive = useMutation({ mutationFn: () => archiveDocument(organizationId, document.id), onSuccess: onUpdated });
  const restore = useMutation({ mutationFn: () => restoreDocument(organizationId, document.id), onSuccess: onUpdated });
  const replace = useMutation({
    mutationFn: (file: File) => replaceDocument(organizationId, document.id, file),
    onSuccess: onUpdated,
  });
  const remove = useMutation({
    mutationFn: () => deleteDocument(organizationId, document.id),
    onSuccess: onDeleted,
  });
  const pending = reindex.isPending || archive.isPending || restore.isPending || replace.isPending || remove.isPending;
  return (
    <TableRow className={selected ? "bg-accent/40" : undefined}>
      <TableCell>
        <button type="button" aria-pressed={selected} className="flex min-w-0 items-start gap-2 break-words text-left font-medium hover:text-primary" onClick={onSelect}>
          <FileText className="mt-0.5 shrink-0 text-primary" size={16} /> {document.title}
        </button>
        <p className="mt-1 pl-6 text-xs text-muted-foreground">{Math.ceil(document.byte_size / 1024)} KB</p>
        {document.error_message ? <p className="mt-1 text-xs text-destructive">{document.error_message}</p> : null}
        {reindex.isError ? <RequestError error={reindex.error} /> : null}
        {archive.isError ? <RequestError error={archive.error} /> : null}
        {restore.isError ? <RequestError error={restore.error} /> : null}
        {replace.isError ? <RequestError error={replace.error} /> : null}
        {remove.isError ? <RequestError error={remove.error} /> : null}
      </TableCell>
      <TableCell>
        <Badge variant="secondary" className={statusClass(document.status)}>{archived ? "archived" : document.status}</Badge>
      </TableCell>
      <TableCell className={document.origin === "demo" ? "text-primary" : "text-muted-foreground"}>
        {documentOriginLabel(document.origin)}
      </TableCell>
      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{new Date(document.updated_at).toLocaleDateString()}</TableCell>
      <TableCell>
        <div className="flex flex-wrap gap-2 sm:flex-nowrap">
          {archived ? (
            <Button type="button" size="sm" variant="outline" disabled={pending} onClick={() => restore.mutate()}>{restore.isPending ? "Restoring…" : "Restore"}</Button>
          ) : (
            <Button type="button" size="sm" variant="outline" disabled={pending || indexing} onClick={() => reindex.mutate()}>
              {reindex.isPending ? "Queuing…" : document.status === "failed" ? "Retry indexing" : "Reindex"}
            </Button>
          )}
          {!archived ? (
            <>
              <input ref={replaceInput} type="file" accept=".pdf,.txt,application/pdf,text/plain" className="sr-only" aria-label={`Replace ${document.title}`} disabled={pending || indexing} onChange={(event) => {
                const next = event.target.files?.[0];
                event.target.value = "";
                if (next) replace.mutate(next);
              }} />
              <Button type="button" size="sm" variant="outline" disabled={pending || indexing} onClick={() => replaceInput.current?.click()}>{replace.isPending ? "Replacing…" : "Replace file"}</Button>
              <ConfirmButton label="Archive" confirmLabel="Confirm archive" pendingLabel="Archiving…" pending={archive.isPending} size="sm" onConfirm={() => { if (!pending && !indexing) archive.mutate(); }} />
            </>
          ) : null}
          <ConfirmButton label="Delete" confirmLabel="Confirm delete" pendingLabel="Deleting…" pending={remove.isPending} size="sm" onConfirm={() => { if (!pending) remove.mutate(); }} />
        </div>
      </TableCell>
    </TableRow>
  );
}

function ChunkList({
  organizationId,
  document,
  highlightId,
}: {
  organizationId: string;
  document: KnowledgeDocument;
  highlightId: string | null;
}) {
  const status = document.status;
  const archived = Boolean(document.archived_at);
  const chunks = useQuery({
    queryKey: ["document-chunks", organizationId, document.id, status, document.archived_at, document.updated_at],
    queryFn: () => documentChunks(organizationId, document.id),
    refetchInterval: status === "pending" || status === "processing" ? 2000 : false,
  });
  const preview = useQuery({
    queryKey: ["document-preview", organizationId, document.id, document.updated_at],
    queryFn: () => previewDocument(organizationId, document.id),
  });
  return (
    <section className="min-w-0 rounded-xl border border-border bg-card p-4">
      <h2 className="break-words text-base font-medium text-foreground">{document.title}</h2>
      <p className={`mt-2 text-xs uppercase tracking-[0.12em] ${statusClass(status)}`}>{archived ? "Archived. Search and assistant answers skip this document until it is restored." : statusCopy(status)}</p>
      <dl className="mt-4 space-y-2 text-xs text-muted-foreground">
        <div><dt className="text-subtle">File</dt><dd>{document.filename}</dd></div>
        <div><dt className="text-subtle">Type</dt><dd>{document.media_type}</dd></div>
        <div><dt className="text-subtle">Size</dt><dd>{Math.ceil(document.byte_size / 1024)} KB</dd></div>
        <div><dt className="text-subtle">Origin</dt><dd>{documentOriginLabel(document.origin)}</dd></div>
        <div><dt className="text-subtle">Updated</dt><dd>{new Date(document.updated_at).toLocaleString()}</dd></div>
      </dl>
      {document.error_message ? <p className="mt-4 text-sm leading-6 text-destructive">{document.error_message}</p> : null}
      <div className="mt-4">
        <h3 className="text-sm font-medium">File preview</h3>
        {preview.isPending ? <Skeleton className="mt-2 h-16 w-full" /> : null}
        {preview.isError ? <div className="mt-2"><RequestError error={preview.error} /></div> : null}
        {preview.data ? <p className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{preview.data.excerpt || "This file has no readable text."}{preview.data.truncated ? "…" : ""}</p> : null}
      </div>
      <h3 className="mt-4 text-sm font-medium">Extracted text</h3>
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
          <li key={chunk.id} className={`rounded-[10px] p-3 text-sm ${chunk.id === highlightId ? "bg-primary/10 ring-1 ring-primary" : "bg-secondary"}`}>
            <p className="text-xs text-muted-foreground">
              Section {chunk.chunk_index + 1}
              {chunk.page_number !== null ? ` · page ${chunk.page_number}` : ""}
            </p>
            <p className="mt-2 whitespace-pre-wrap">{chunk.content}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EmbeddingGuide({ status }: { status?: { embedding_ready: boolean; embedding_provider: string; embedding_model: string; embedding_detail: string; incompatible_documents: number } }) {
  return (
    <section className="rounded-xl border border-border bg-card p-4" aria-label="How document search works">
      <h2 className="text-sm font-medium">How search uses your documents</h2>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        A document is queued, then processed, then ready for search. A failed file stays in the library and can be retried. Replacing a file updates search. Archiving hides it from search and from assistant answers until you restore it.
      </p>
      {status ? (
        <p className="mt-2 text-sm leading-6">
          {status.embedding_provider === "double" || status.embedding_model === "demonstration"
            ? "Search uses the documents in this workspace. A paid search service is not called."
            : status.embedding_ready
              ? status.embedding_detail
              : `An administrator needs to finish document search setup before new files can be indexed. ${status.embedding_detail}`}
          {" "}
          <Link href="/integrations" className="font-medium text-primary underline">Open Integrations</Link>
        </p>
      ) : <p className="mt-2 text-sm text-muted-foreground">Checking document search…</p>}
      {status && status.incompatible_documents > 0 ? (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {status.incompatible_documents} ready {status.incompatible_documents === 1 ? "document was" : "documents were"} indexed with a different model. Reindex {status.incompatible_documents === 1 ? "it" : "them"} so search uses the current model. The files stay in place.
        </p>
      ) : null}
    </section>
  );
}
