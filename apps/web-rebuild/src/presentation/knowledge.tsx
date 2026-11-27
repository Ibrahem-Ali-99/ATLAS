import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Archive,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Download,
  File,
  FileText,
  Filter,
  FolderOpen,
  LoaderCircle,
  LockKeyhole,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import { Avatar, Badge, Button, Modal, type Tone } from "./components";
import { archiveKnowledge, chunksKnowledge, failureMessage, listKnowledge, previewKnowledge, reindexKnowledge, replaceKnowledge, restoreKnowledge, retryKnowledge, searchKnowledge, uploadKnowledge } from "@/data/resources";
import { appConfig } from "./appConfig";

type DocumentStatus = "Indexed" | "Processing" | "Failed";
type KnowledgeDocument = {
  id: string;
  name: string;
  type: string;
  size: string;
  status: DocumentStatus;
  owner: string;
  updated: string;
  error?: string | null;
  archived?: boolean;
};

const statusTone = (status: DocumentStatus): Tone => status === "Indexed" ? "green" : status === "Processing" ? "blue" : "red";

function mapDocument(item: { id: string; title: string; filename: string; status: string; byte_size: number; error_message: string | null; updated_at: string; media_type: string; archived_at?: string | null }): KnowledgeDocument {
  const status: DocumentStatus = item.status === "ready" ? "Indexed" : item.status === "failed" ? "Failed" : "Processing";
  const extension = item.filename.split(".").pop()?.toUpperCase() || "FILE";
  return { id: item.id, name: item.title || item.filename, type: extension, size: `${Math.max(1, Math.round(item.byte_size / 1024))} KB`, status, owner: "Workspace", updated: item.updated_at.slice(0, 10), error: item.error_message, archived: Boolean(item.archived_at) };
}

function useKnowledgeModel(onToast: (message: string) => void) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All statuses");
  const [type, setType] = useState("All file types");
  const [mode, setMode] = useState<"library" | "search">("library");
  const [semanticQuery, setSemanticQuery] = useState("How is an enterprise workspace implemented?");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<KnowledgeDocument | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const selected = documents.find((document) => document.id === selectedId) || null;
  const filtered = useMemo(() => documents.filter((document) =>
    document.name.toLowerCase().includes(search.toLowerCase()) &&
    (status === "All statuses" || document.status === status) &&
    (type === "All file types" || document.type === type) &&
    (showArchived ? document.archived : !document.archived),
  ), [documents, search, status, type, showArchived]);
  const refresh = () => listKnowledge(showArchived).then((rows) => {
    const next = rows.map(mapDocument);
    setDocuments(next);
    setSelectedId((current) => current || next[0]?.id || "");
  });
  useEffect(() => { refresh().catch((error: unknown) => onToast(failureMessage(error))); }, [onToast, showArchived]);
  const addFile = (file: File) => {
    void uploadKnowledge(file).then(() => { setUploadOpen(false); onToast(`${file.name} added for processing`); return refresh(); }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const retry = (id: string) => {
    void retryKnowledge(id).then(() => { onToast("Document processing restarted"); return refresh(); }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const remove = () => {
    if (!removeTarget) return;
    void archiveKnowledge(removeTarget.id).then(() => { onToast(`${removeTarget.name} archived`); setRemoveTarget(null); return refresh(); }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const restore = (id: string) => {
    void restoreKnowledge(id).then(() => { onToast("Document restored"); return refresh(); }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const replace = (id: string, file: File) => {
    void replaceKnowledge(id, file).then(() => { onToast(`${file.name} replaced the stored file`); return refresh(); }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  const reindex = (id: string) => {
    void reindexKnowledge(id).then(() => { onToast("Reindex queued"); return refresh(); }).catch((error: unknown) => onToast(failureMessage(error)));
  };
  return { documents, filtered, selected, selectedId, setSelectedId, search, setSearch, status, setStatus, type, setType, showArchived, setShowArchived, mode, setMode, semanticQuery, setSemanticQuery, uploadOpen, setUploadOpen, removeTarget, setRemoveTarget, addFile, retry, remove, restore, replace, reindex };
}

export function KnowledgeWorkspace({ onToast }: { onToast: (message: string) => void }) {
  const model = useKnowledgeModel(onToast);
  const [filtersOpen, setFiltersOpen] = useState(false);
  return (
    <main className="module-main knowledge-main">
      <div className="module-heading">
        <div><div className="eyebrow"><span className="live-dot" /> Trusted workspace sources</div><h1>Knowledge</h1><p>Manage indexed documents and inspect the passages used by ATLAS.</p></div>
        <Button variant="primary" onClick={() => model.setUploadOpen(true)}><Plus size={15} /> Upload document</Button>
      </div>
      <div className="knowledge-view-switch"><button className={model.mode === "library" ? "active" : ""} onClick={() => model.setMode("library")}><FolderOpen size={15} /> Document library</button><button className={model.mode === "search" ? "active" : ""} onClick={() => model.setMode("search")}><Sparkles size={15} /> Semantic search</button></div>
      {model.mode === "library" ? (
        <div className="knowledge-layout">
          <section className="panel knowledge-library">
            <div className="knowledge-toolbar">
              <label className="module-search"><Search size={15} /><input value={model.search} onChange={(event) => model.setSearch(event.target.value)} placeholder="Search documents" aria-label="Search knowledge documents" />{model.search && <button onClick={() => model.setSearch("")} aria-label="Clear search"><X size={14} /></button>}</label>
              <Button size="sm" variant={model.status !== "All statuses" || model.type !== "All file types" ? "primary" : "secondary"} onClick={() => setFiltersOpen(!filtersOpen)}><Filter size={14} /> Filters</Button>
            </div>
            {filtersOpen && <div className="knowledge-filters"><select value={model.status} onChange={(event) => model.setStatus(event.target.value)} aria-label="Filter by processing status"><option>All statuses</option><option>Indexed</option><option>Processing</option><option>Failed</option></select><select value={model.type} onChange={(event) => model.setType(event.target.value)} aria-label="Filter by file type"><option>All file types</option><option>PDF</option><option>DOCX</option><option>TXT</option></select><label className="toggle-row"><span>Archived</span><input type="checkbox" checked={model.showArchived} onChange={(event) => model.setShowArchived(event.target.checked)} /></label></div>}
            <div className="knowledge-table" role="table" aria-label="Knowledge documents">
              <div className="knowledge-row head" role="row"><span>Document</span><span>Status</span><span>Owner</span><span>Updated</span><span /></div>
              {model.filtered.length ? model.filtered.map((document) => <button className={`knowledge-row ${model.selectedId === document.id ? "active" : ""}`} role="row" key={document.id} onClick={() => model.setSelectedId(document.id)}>
                <span className="document-cell"><span className="file-icon"><FileText size={16} /></span><span><strong>{document.name}</strong><small>{document.type} · {document.size}</small></span></span>
                <span className="document-status"><Badge tone={statusTone(document.status)}>{document.status}</Badge>{document.status === "Processing" && <i><span style={{ width: "40%" }} /></i>}</span>
                <span className="document-owner"><Avatar initials={document.owner.split(" ").map((word) => word[0]).join("").slice(0, 2)} size="sm" />{document.owner}</span>
                <span>{document.updated}</span>
                <MoreHorizontal size={16} />
              </button>) : <div className="module-empty"><BookOpen size={25} /><strong>No documents found</strong><p>Change your search or filters, or upload a new document.</p><Button size="sm" onClick={() => { model.setSearch(""); model.setStatus("All statuses"); model.setType("All file types"); }}>Clear filters</Button></div>}
            </div>
          </section>
          <DocumentInspector document={model.selected} onRetry={model.retry} onRemove={model.setRemoveTarget} onRestore={model.restore} onReplace={model.replace} onReindex={model.reindex} />
        </div>
      ) : <SemanticSearch query={model.semanticQuery} setQuery={model.setSemanticQuery} onOpen={(id) => { model.setSelectedId(id); model.setMode("library"); }} />}

      <UploadDialog open={model.uploadOpen} onClose={() => model.setUploadOpen(false)} onAdd={model.addFile} />
      <Modal open={!!model.removeTarget} title="Remove document?" description="The document and its indexed passages will be removed from knowledge search." onClose={() => model.setRemoveTarget(null)}>
        <div className="confirm-content"><Trash2 size={20} /><p><strong>{model.removeTarget?.name}</strong> will be hidden from knowledge search until it is restored.</p></div>
        <div className="dialog-footer"><Button onClick={() => model.setRemoveTarget(null)}>Cancel</Button><Button variant="danger" onClick={model.remove}><Trash2 size={14} /> Remove document</Button></div>
      </Modal>
    </main>
  );
}

function DocumentInspector({ document, onRetry, onRemove, onRestore, onReplace, onReindex }: { document: KnowledgeDocument | null; onRetry: (id: string) => void; onRemove: (document: KnowledgeDocument) => void; onRestore: (id: string) => void; onReplace: (id: string, file: File) => void; onReindex: (id: string) => void }) {
  const replaceRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<"content" | "passages">("content");
  const [excerpt, setExcerpt] = useState("");
  const [passages, setPassages] = useState<{ content: string; page_number: number | null; chunk_index: number }[]>([]);
  useEffect(() => {
    if (!document || document.status !== "Indexed") { setExcerpt(""); setPassages([]); return; }
    previewKnowledge(document.id).then((preview) => setExcerpt(preview.excerpt)).catch(() => setExcerpt(""));
    chunksKnowledge(document.id).then((page) => setPassages(page.items)).catch(() => setPassages([]));
  }, [document]);
  if (!document) return <aside className="panel document-inspector"><div className="module-empty"><File size={24} /><strong>Select a document</strong><p>Choose a document to inspect its content and indexing status.</p></div></aside>;
  return <aside className="panel document-inspector" aria-label={`${document.name} details`}>
    <header><div className="file-icon large"><FileText size={19} /></div><div><h2>{document.name}</h2><p>{document.type} · {document.size}</p></div></header>
    <div className="document-meta"><div><span>Status</span><Badge tone={statusTone(document.status)}>{document.status}</Badge></div><div><span>Owner</span><strong>{document.owner}</strong></div><div><span>Updated</span><strong>{document.updated}</strong></div></div>
    {document.status === "Failed" && <div className="state-banner error"><CircleAlert size={16} /><span><strong>Indexing failed</strong><small>{document.error || "Processing did not finish."}</small></span><Button size="sm" onClick={() => onRetry(document.id)}><RefreshCw size={13} /> Retry</Button></div>}
    {document.status === "Processing" && <div className="indexing-card"><div><LoaderCircle size={16} /><span><strong>Indexing document</strong><small>Extracting text and preparing passages.</small></span></div><i><span style={{ width: "40%" }} /></i></div>}
    <div className="inspector-tabs"><button className={tab === "content" ? "active" : ""} onClick={() => setTab("content")}>Extracted content</button><button className={tab === "passages" ? "active" : ""} onClick={() => setTab("passages")}>Indexed passages</button></div>
    <div className="inspector-content">{document.status !== "Indexed" ? <div className="module-empty compact"><AlertTriangle size={22} /><strong>Content unavailable</strong><p>Extracted content will appear after indexing succeeds.</p></div> : tab === "content" ? <article><p>{excerpt || "No extracted preview is stored for this document."}</p></article> : <div className="passage-list">{passages.map((passage) => <article key={passage.chunk_index}><span>Passage {passage.chunk_index + 1}{passage.page_number ? ` · Page ${passage.page_number}` : ""}</span><p>{passage.content}</p></article>)}</div>}</div>
    <footer>{document.archived ? <Button size="sm" onClick={() => onRestore(document.id)}><RefreshCw size={13} /> Restore</Button> : <><input ref={replaceRef} className="sr-only" type="file" accept=".pdf,.txt,application/pdf,text/plain" aria-label={`Replace ${document.name}`} onChange={(event) => { const next = event.target.files?.[0]; event.target.value = ""; if (next) onReplace(document.id, next); }} /><Button size="sm" onClick={() => replaceRef.current?.click()}>Replace file</Button><Button size="sm" disabled={document.status === "Processing"} onClick={() => onReindex(document.id)}>Reindex</Button><Button size="sm" variant="ghost" onClick={() => onRemove(document)}><Trash2 size={13} /> Archive</Button></>}</footer>
  </aside>;
}

function UploadDialog({ open, onClose, onAdd }: { open: boolean; onClose: () => void; onAdd: (file: File) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  return <Modal open={open} title="Upload document" description="Add a trusted source for knowledge search and Assistant citations." onClose={onClose}>
    <div className="dialog-body">
      <button className={`drop-zone ${dragging ? "dragging" : ""}`} onClick={() => inputRef.current?.click()} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); setFile(event.dataTransfer.files[0] || null); }}>
        <UploadCloud size={25} /><strong>{file?.name || "Drop a file here or choose a file"}</strong><span>PDF or TXT</span>
      </button>
      <input ref={inputRef} className="sr-only" type="file" accept=".pdf,.txt" aria-label="Choose a knowledge document" onChange={(event) => setFile(event.target.files?.[0] || null)} />
      <div className="permission-state"><CheckCircle2 size={17} /><span><strong>Private to {appConfig.organization.name}</strong><small>Uploaded content remains scoped to this organization.</small></span></div>
    </div>
    <div className="dialog-footer"><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={!file} onClick={() => file && onAdd(file)}><UploadCloud size={14} /> Upload and index</Button></div>
  </Modal>;
}

function SemanticSearch({ query, setQuery, onOpen }: { query: string; setQuery: (query: string) => void; onOpen: (id: string) => void }) {
  const [searched, setSearched] = useState(false);
  const [pending, setPending] = useState(false);
  const [results, setResults] = useState<{ document_id: string; document_title: string; page_number: number | null; content: string; score: number }[]>([]);
  const [error, setError] = useState("");
  const run = () => {
    setSearched(true);
    setPending(true);
    setError("");
    searchKnowledge(query).then((page) => setResults(page.items)).catch((reason: unknown) => setError(failureMessage(reason))).finally(() => setPending(false));
  };
  return <section className="panel semantic-search">
    <div className="semantic-search-head"><span className="assistant-logo"><Sparkles size={20} /></span><h2>Semantic search</h2><p>Find relevant passages by meaning, not only exact keywords.</p><div className="semantic-query"><Search size={16} /><input value={query} onChange={(event) => { setQuery(event.target.value); setSearched(false); }} placeholder="Ask a question about your knowledge" aria-label="Semantic knowledge search" /><Button variant="primary" disabled={!query.trim() || pending} onClick={run}>Search</Button></div></div>
    <div className="semantic-results">{error ? <div className="module-empty"><Search size={24} /><strong>Search failed</strong><p>{error}</p></div> : pending || !searched ? <div className="module-empty"><Search size={24} /><strong>{pending ? "Searching knowledge" : "Search is ready"}</strong><p>{pending ? "Ranking matching passages." : "Run the query to rank matching passages."}</p></div> : results.length ? <><div className="results-summary"><strong>{results.length} ranked passages</strong><span>Sorted by semantic relevance</span></div>{results.map((result, index) => <article key={`${result.document_id}-${index}`}><div className="rank">{index + 1}</div><div><div className="result-source"><FileText size={14} /><strong>{result.document_title}</strong><span>{result.page_number ? `Page ${result.page_number}` : "Passage"}</span><Badge tone="green">{result.score.toFixed(2)}</Badge></div><p>{result.content}</p><button onClick={() => onOpen(result.document_id)}>Open source <ChevronRight size={13} /></button></div></article>)}</> : <div className="module-empty"><Search size={24} /><strong>No relevant passages</strong><p>Try a broader question or add more knowledge documents.</p></div>}</div>
  </section>;
}
