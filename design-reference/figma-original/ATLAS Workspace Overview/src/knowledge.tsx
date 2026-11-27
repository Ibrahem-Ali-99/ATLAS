import { useMemo, useRef, useState } from "react";
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
import { appConfig } from "./appConfig";

type DocumentStatus = "Indexed" | "Processing" | "Failed";
type KnowledgeDocument = {
  id: number;
  name: string;
  type: "PDF" | "DOCX" | "TXT";
  size: string;
  status: DocumentStatus;
  owner: string;
  updated: string;
  progress?: number;
  restricted?: boolean;
};

const initialDocuments: KnowledgeDocument[] = [
  { id: 1, name: "Enterprise implementation guide", type: "PDF", size: "2.4 MB", status: "Indexed", owner: "Olivia Martin", updated: "Today" },
  { id: 2, name: "Security and compliance overview", type: "PDF", size: "1.8 MB", status: "Indexed", owner: "Maya Chen", updated: "Yesterday" },
  { id: 3, name: "Customer onboarding playbook", type: "DOCX", size: "860 KB", status: "Processing", owner: "Sam Rivera", updated: "4 min ago", progress: 64 },
  { id: 4, name: "Data residency policy", type: "PDF", size: "1.1 MB", status: "Failed", owner: "Olivia Martin", updated: "2 hr ago" },
  { id: 5, name: "Internal pricing notes", type: "TXT", size: "42 KB", status: "Indexed", owner: "Finance team", updated: "Feb 19", restricted: true },
];

const statusTone = (status: DocumentStatus): Tone => status === "Indexed" ? "green" : status === "Processing" ? "blue" : "red";

function useKnowledgeModel(onToast: (message: string) => void) {
  const [documents, setDocuments] = useState(initialDocuments);
  const [selectedId, setSelectedId] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All statuses");
  const [type, setType] = useState("All file types");
  const [mode, setMode] = useState<"library" | "search">("library");
  const [semanticQuery, setSemanticQuery] = useState("How is an enterprise workspace implemented?");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<KnowledgeDocument | null>(null);
  const selected = documents.find((document) => document.id === selectedId) || null;
  const filtered = useMemo(() => documents.filter((document) =>
    document.name.toLowerCase().includes(search.toLowerCase()) &&
    (status === "All statuses" || document.status === status) &&
    (type === "All file types" || document.type === type),
  ), [documents, search, status, type]);
  const addFile = (name: string) => {
    const document: KnowledgeDocument = { id: Date.now(), name, type: name.toLowerCase().endsWith(".txt") ? "TXT" : name.toLowerCase().endsWith(".docx") ? "DOCX" : "PDF", size: "New upload", status: "Processing", owner: "Olivia Martin", updated: "Just now", progress: 12 };
    setDocuments((current) => [document, ...current]);
    setSelectedId(document.id);
    setUploadOpen(false);
    onToast(`${name} added for processing`);
  };
  const retry = (id: number) => {
    setDocuments((current) => current.map((document) => document.id === id ? { ...document, status: "Processing", progress: 18, updated: "Just now" } : document));
    onToast("Document processing restarted");
  };
  const remove = () => {
    if (!removeTarget) return;
    setDocuments((current) => current.filter((document) => document.id !== removeTarget.id));
    if (selectedId === removeTarget.id) setSelectedId(0);
    onToast(`${removeTarget.name} removed`);
    setRemoveTarget(null);
  };
  return { documents, filtered, selected, selectedId, setSelectedId, search, setSearch, status, setStatus, type, setType, mode, setMode, semanticQuery, setSemanticQuery, uploadOpen, setUploadOpen, removeTarget, setRemoveTarget, addFile, retry, remove };
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
            {filtersOpen && <div className="knowledge-filters"><select value={model.status} onChange={(event) => model.setStatus(event.target.value)} aria-label="Filter by processing status"><option>All statuses</option><option>Indexed</option><option>Processing</option><option>Failed</option></select><select value={model.type} onChange={(event) => model.setType(event.target.value)} aria-label="Filter by file type"><option>All file types</option><option>PDF</option><option>DOCX</option><option>TXT</option></select></div>}
            <div className="knowledge-table" role="table" aria-label="Knowledge documents">
              <div className="knowledge-row head" role="row"><span>Document</span><span>Status</span><span>Owner</span><span>Updated</span><span /></div>
              {model.filtered.length ? model.filtered.map((document) => <button className={`knowledge-row ${model.selectedId === document.id ? "active" : ""}`} role="row" key={document.id} onClick={() => model.setSelectedId(document.id)}>
                <span className="document-cell"><span className="file-icon"><FileText size={16} /></span><span><strong>{document.name}</strong><small>{document.type} · {document.size}</small></span></span>
                <span className="document-status"><Badge tone={statusTone(document.status)}>{document.status}</Badge>{document.status === "Processing" && <i><span style={{ width: `${document.progress}%` }} /></i>}</span>
                <span className="document-owner"><Avatar initials={document.owner.split(" ").map((word) => word[0]).join("").slice(0, 2)} size="sm" />{document.owner}</span>
                <span>{document.updated}</span>
                <MoreHorizontal size={16} />
              </button>) : <div className="module-empty"><BookOpen size={25} /><strong>No documents found</strong><p>Change your search or filters, or upload a new document.</p><Button size="sm" onClick={() => { model.setSearch(""); model.setStatus("All statuses"); model.setType("All file types"); }}>Clear filters</Button></div>}
            </div>
          </section>
          <DocumentInspector document={model.selected} onRetry={model.retry} onRemove={model.setRemoveTarget} onToast={onToast} />
        </div>
      ) : <SemanticSearch query={model.semanticQuery} setQuery={model.setSemanticQuery} onOpen={(id) => { model.setSelectedId(id); model.setMode("library"); }} />}

      <UploadDialog open={model.uploadOpen} onClose={() => model.setUploadOpen(false)} onAdd={model.addFile} />
      <Modal open={!!model.removeTarget} title="Remove document?" description="The document and its indexed passages will be removed from knowledge search." onClose={() => model.setRemoveTarget(null)}>
        <div className="confirm-content"><Trash2 size={20} /><p><strong>{model.removeTarget?.name}</strong> will no longer be available as an Assistant source. This prototype action can’t be undone.</p></div>
        <div className="dialog-footer"><Button onClick={() => model.setRemoveTarget(null)}>Cancel</Button><Button variant="danger" onClick={model.remove}><Trash2 size={14} /> Remove document</Button></div>
      </Modal>
    </main>
  );
}

function DocumentInspector({ document, onRetry, onRemove, onToast }: { document: KnowledgeDocument | null; onRetry: (id: number) => void; onRemove: (document: KnowledgeDocument) => void; onToast: (message: string) => void }) {
  const [tab, setTab] = useState<"content" | "passages">("content");
  if (!document) return <aside className="panel document-inspector"><div className="module-empty"><File size={24} /><strong>Select a document</strong><p>Choose a document to inspect its content and indexing status.</p></div></aside>;
  return <aside className="panel document-inspector" aria-label={`${document.name} details`}>
    <header><div className="file-icon large"><FileText size={19} /></div><div><h2>{document.name}</h2><p>{document.type} · {document.size}</p></div><Button size="icon" variant="ghost" aria-label="Document actions"><MoreHorizontal size={16} /></Button></header>
    <div className="document-meta"><div><span>Status</span><Badge tone={statusTone(document.status)}>{document.status}</Badge></div><div><span>Owner</span><strong>{document.owner}</strong></div><div><span>Updated</span><strong>{document.updated}</strong></div></div>
    {document.status === "Failed" && <div className="state-banner error"><CircleAlert size={16} /><span><strong>Indexing failed</strong><small>The PDF text layer could not be read. Upload an accessible PDF or retry processing.</small></span><Button size="sm" onClick={() => onRetry(document.id)}><RefreshCw size={13} /> Retry</Button></div>}
    {document.status === "Processing" && <div className="indexing-card"><div><LoaderCircle size={16} /><span><strong>Indexing document</strong><small>Extracting text and preparing passages.</small></span><b>{document.progress}%</b></div><i><span style={{ width: `${document.progress}%` }} /></i></div>}
    {document.restricted && <div className="permission-state"><LockKeyhole size={17} /><span><strong>Restricted document</strong><small>You can inspect metadata, but extracted content requires Finance team access.</small></span></div>}
    <div className="inspector-tabs"><button className={tab === "content" ? "active" : ""} onClick={() => setTab("content")}>Extracted content</button><button className={tab === "passages" ? "active" : ""} onClick={() => setTab("passages")}>Indexed passages</button></div>
    <div className="inspector-content">{document.restricted ? <div className="module-empty compact"><LockKeyhole size={22} /><strong>Content restricted</strong><p>Request access from the document owner.</p><Button size="sm" disabled>Request access</Button></div> : document.status !== "Indexed" ? <div className="module-empty compact"><AlertTriangle size={22} /><strong>Content unavailable</strong><p>Extracted content will appear after indexing succeeds.</p></div> : tab === "content" ? <article><h3>Enterprise implementation</h3><p>Implementation begins with workspace planning, account configuration, and role mapping. Available setup options are confirmed with the customer during the implementation phase.</p><h3>Security review</h3><p>The account team coordinates security documentation and confirms data handling requirements before rollout.</p></article> : <div className="passage-list"><article><span>Passage 1 · Page 4</span><p>Workspace roles and available account options are confirmed during implementation planning.</p></article><article><span>Passage 2 · Page 7</span><p>Workspace administrators validate role mapping before inviting the broader team.</p></article></div>}</div>
    <footer><Button size="sm" onClick={() => onToast("Document download prepared")}><Download size={13} /> Download</Button><Button size="sm" variant="ghost" disabled={document.restricted} onClick={() => onRemove(document)}><Trash2 size={13} /> Remove</Button></footer>
  </aside>;
}

function UploadDialog({ open, onClose, onAdd }: { open: boolean; onClose: () => void; onAdd: (name: string) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");
  const [dragging, setDragging] = useState(false);
  return <Modal open={open} title="Upload document" description="Add a trusted source for knowledge search and Assistant citations." onClose={onClose}>
    <div className="dialog-body">
      <button className={`drop-zone ${dragging ? "dragging" : ""}`} onClick={() => inputRef.current?.click()} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); setFileName(event.dataTransfer.files[0]?.name || ""); }}>
        <UploadCloud size={25} /><strong>{fileName || "Drop a file here or choose a file"}</strong><span>PDF, DOCX, or TXT · Up to 20 MB</span>
      </button>
      <input ref={inputRef} className="sr-only" type="file" accept=".pdf,.docx,.txt" aria-label="Choose a knowledge document" onChange={(event) => setFileName(event.target.files?.[0]?.name || "")} />
      <div className="permission-state"><CheckCircle2 size={17} /><span><strong>Private to {appConfig.organization.name}</strong><small>Uploaded content remains scoped to this organization.</small></span></div>
    </div>
    <div className="dialog-footer"><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={!fileName} onClick={() => onAdd(fileName)}><UploadCloud size={14} /> Upload and index</Button></div>
  </Modal>;
}

function SemanticSearch({ query, setQuery, onOpen }: { query: string; setQuery: (query: string) => void; onOpen: (id: number) => void }) {
  const [searched, setSearched] = useState(true);
  const results = query.trim() ? [
    { id: 1, rank: 1, relevance: "High relevance", file: "Enterprise implementation guide", page: "Page 4", passage: "Workspace roles and available account options are confirmed during implementation planning." },
    { id: 2, rank: 2, relevance: "Relevant", file: "Security and compliance overview", page: "Page 11", passage: "Account configuration is validated before workspace rollout and broader user provisioning." },
  ] : [];
  return <section className="panel semantic-search">
    <div className="semantic-search-head"><span className="assistant-logo"><Sparkles size={20} /></span><h2>Semantic search</h2><p>Find relevant passages by meaning, not only exact keywords.</p><div className="semantic-query"><Search size={16} /><input value={query} onChange={(event) => { setQuery(event.target.value); setSearched(false); }} placeholder="Ask a question about your knowledge" aria-label="Semantic knowledge search" /><Button variant="primary" disabled={!query.trim()} onClick={() => setSearched(true)}>Search</Button></div></div>
    <div className="semantic-results">{!searched ? <div className="module-empty"><Search size={24} /><strong>Search is ready</strong><p>Run the query to rank matching passages.</p></div> : results.length ? <><div className="results-summary"><strong>{results.length} ranked passages</strong><span>Sorted by semantic relevance</span></div>{results.map((result) => <article key={result.id}><div className="rank">{result.rank}</div><div><div className="result-source"><FileText size={14} /><strong>{result.file}</strong><span>{result.page}</span><Badge tone="green">{result.relevance}</Badge></div><p>{result.passage}</p><button onClick={() => onOpen(result.id)}>Open source <ChevronRight size={13} /></button></div></article>)}</> : <div className="module-empty"><Search size={24} /><strong>No relevant passages</strong><p>Try a broader question or add more knowledge documents.</p></div>}</div>
  </section>;
}
