import { useEffect, useMemo, useState } from "react";
import {
  Archive,
  ArrowDown,
  ArrowUp,
  Building2,
  CalendarCheck,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Columns3,
  Contact,
  Edit3,
  Filter,
  Inbox,
  LayoutList,
  LockKeyhole,
  Mail,
  MessageSquareText,
  MoreHorizontal,
  Phone,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Sparkles,
  Target,
  Trash2,
  UserRound,
  Users,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { Avatar, Badge, Button, Modal, type Tone } from "./components";
import { appConfig } from "./appConfig";

export type CRMSection =
  | "Companies"
  | "Contacts"
  | "Leads"
  | "Customer inquiries"
  | "Opportunities"
  | "Tasks"
  | "Customer interactions";

type CRMRecord = {
  id: number;
  name: string;
  detail: string;
  status: string;
  owner: string;
  updated: string;
  company?: string;
  contact?: string;
  stage?: string;
  score?: number;
  archived?: boolean;
  restricted?: boolean;
};

const sections: { label: CRMSection; short: string; icon: LucideIcon }[] = [
  { label: "Companies", short: "Companies", icon: Building2 },
  { label: "Contacts", short: "Contacts", icon: Contact },
  { label: "Leads", short: "Leads", icon: Target },
  { label: "Customer inquiries", short: "Inquiries", icon: Inbox },
  { label: "Opportunities", short: "Opportunities", icon: Columns3 },
  { label: "Tasks", short: "Tasks", icon: CalendarCheck },
  { label: "Customer interactions", short: "Interactions", icon: MessageSquareText },
];

const sectionContent: Record<CRMSection, { singular: string; description: string }> = {
  Companies: { singular: "company", description: "Manage organizations, account ownership, and connected customer records." },
  Contacts: { singular: "contact", description: "Manage people, roles, communication details, and account relationships." },
  Leads: { singular: "lead", description: "Qualify prospective customers with engagement context and predictive scoring." },
  "Customer inquiries": { singular: "inquiry", description: "Review incoming questions, coordinate responses, and schedule follow-up." },
  Opportunities: { singular: "opportunity", description: "Track qualified customer work through each stage of the opportunity pipeline." },
  Tasks: { singular: "task", description: "Coordinate customer-related work, due dates, ownership, and completion." },
  "Customer interactions": { singular: "interaction", description: "Review calls, messages, meetings, and system-recorded customer activity." },
};

const initialData: Record<CRMSection, CRMRecord[]> = {
  Companies: [
    { id: 1, name: "Arcade", detail: "Software · 84 employees", status: "Customer", owner: "Olivia Martin", updated: "12 min ago" },
    { id: 2, name: "Layers", detail: "Design tools · 42 employees", status: "Prospect", owner: "Sam Rivera", updated: "46 min ago" },
    { id: 3, name: "Northstar", detail: "Financial services · 230 employees", status: "Customer", owner: "Olivia Martin", updated: "2 hr ago" },
    { id: 4, name: "Vertex", detail: "Infrastructure · 115 employees", status: "Prospect", owner: "Maya Chen", updated: "Yesterday" },
    { id: 5, name: "Mercury Labs", detail: "Research · 28 employees", status: "Archived", owner: "Sam Rivera", updated: "Feb 18", archived: true },
  ],
  Contacts: [
    { id: 11, name: "Mina Park", detail: "VP Operations · mina@arcade.example", status: "Decision maker", owner: "Olivia Martin", updated: "18 min ago", company: "Arcade" },
    { id: 12, name: "Theo Brooks", detail: "Head of Design · theo@layers.example", status: "Champion", owner: "Sam Rivera", updated: "1 hr ago", company: "Layers" },
    { id: 13, name: "Nadia Flores", detail: "General Counsel · nadia@northstar.example", status: "Stakeholder", owner: "Olivia Martin", updated: "3 hr ago", company: "Northstar" },
    { id: 14, name: "Jon Bell", detail: "Security Lead · jon@vertex.example", status: "Evaluator", owner: "Maya Chen", updated: "Yesterday", company: "Vertex" },
    { id: 15, name: "Priya Shah", detail: "COO · priya@arcade.example", status: "Champion", owner: "Olivia Martin", updated: "Feb 20", company: "Arcade" },
  ],
  Leads: [
    { id: 21, name: "Mina Park", detail: "Enterprise workspace inquiry", status: "Qualified", owner: "Olivia Martin", updated: "21 min ago", company: "Arcade", score: 88 },
    { id: 22, name: "Theo Brooks", detail: "Product collaboration evaluation", status: "Contacted", owner: "Sam Rivera", updated: "1 hr ago", company: "Layers", score: 72 },
    { id: 23, name: "Nadia Flores", detail: "Custom terms request", status: "Qualified", owner: "Olivia Martin", updated: "3 hr ago", company: "Northstar", score: 81 },
    { id: 24, name: "Jon Bell", detail: "Security questionnaire", status: "New", owner: "Maya Chen", updated: "Yesterday", company: "Vertex" },
    { id: 25, name: "Ellis Ward", detail: "Team workspace evaluation", status: "New", owner: "Sam Rivera", updated: "Feb 20", company: "Layers", score: 54 },
  ],
  "Customer inquiries": [
    { id: 31, name: "Enterprise plan requirements", detail: "Website form · Mina Park", status: "Open", owner: "Olivia Martin", updated: "8 min ago", company: "Arcade", contact: "Mina Park" },
    { id: 32, name: "Data residency options", detail: "Email · Nadia Flores", status: "In progress", owner: "Olivia Martin", updated: "52 min ago", company: "Northstar", contact: "Nadia Flores" },
    { id: 33, name: "Security questionnaire", detail: "Email · Jon Bell", status: "Waiting", owner: "Maya Chen", updated: "3 hr ago", company: "Vertex", contact: "Jon Bell" },
    { id: 34, name: "Workspace provisioning", detail: "Chat · Theo Brooks", status: "Resolved", owner: "Sam Rivera", updated: "Yesterday", company: "Layers", contact: "Theo Brooks" },
    { id: 35, name: "Support coverage", detail: "Website form · Priya Shah", status: "Open", owner: "Olivia Martin", updated: "Feb 20", company: "Arcade", contact: "Priya Shah" },
  ],
  Opportunities: [
    { id: 41, name: "Arcade enterprise rollout", detail: "Mina Park · Enterprise workspace", status: "Qualified", stage: "Qualified", owner: "Olivia Martin", updated: "42 min ago", company: "Arcade", contact: "Mina Park" },
    { id: 42, name: "Layers team expansion", detail: "Theo Brooks · Product evaluation", status: "Contacted", stage: "Contacted", owner: "Sam Rivera", updated: "2 hr ago", company: "Layers", contact: "Theo Brooks" },
    { id: 43, name: "Northstar agreement", detail: "Nadia Flores · Custom terms", status: "Qualified", stage: "Qualified", owner: "Olivia Martin", updated: "3 hr ago", company: "Northstar", contact: "Nadia Flores" },
    { id: 44, name: "Vertex security review", detail: "Jon Bell · Security evaluation", status: "New", stage: "New", owner: "Maya Chen", updated: "Yesterday", company: "Vertex", contact: "Jon Bell" },
    { id: 45, name: "Arcade pilot", detail: "Priya Shah · Pilot workspace", status: "Won", stage: "Won", owner: "Olivia Martin", updated: "Feb 19", company: "Arcade", contact: "Priya Shah" },
  ],
  Tasks: [
    { id: 51, name: "Reply to security questionnaire", detail: "Due today · Vertex", status: "In progress", owner: "Maya Chen", updated: "24 min ago", company: "Vertex" },
    { id: 52, name: "Review custom terms", detail: "Due today · Northstar", status: "Open", owner: "Olivia Martin", updated: "1 hr ago", company: "Northstar" },
    { id: 53, name: "Schedule product review", detail: "Due tomorrow · Layers", status: "Open", owner: "Sam Rivera", updated: "2 hr ago", company: "Layers" },
    { id: 54, name: "Confirm workspace requirements", detail: "Due Friday · Arcade", status: "Complete", owner: "Olivia Martin", updated: "Yesterday", company: "Arcade" },
    { id: 55, name: "Prepare onboarding outline", detail: "Due Friday · Arcade", status: "Open", owner: "Olivia Martin", updated: "Feb 20", company: "Arcade" },
  ],
  "Customer interactions": [
    { id: 61, name: "Email reply received", detail: "Re: Security questionnaire", status: "Email", owner: "Maya Chen", updated: "3 hr ago", company: "Vertex", contact: "Jon Bell" },
    { id: 62, name: "Discovery call completed", detail: "32 minutes · Meeting notes added", status: "Call", owner: "Olivia Martin", updated: "Yesterday", company: "Arcade", contact: "Mina Park" },
    { id: 63, name: "Product guide viewed", detail: "Enterprise workspace guide", status: "System", owner: "ATLAS", updated: "Yesterday", company: "Layers", restricted: true },
    { id: 64, name: "Terms document shared", detail: "Secure document link", status: "Email", owner: "Olivia Martin", updated: "Feb 20", company: "Northstar", contact: "Nadia Flores" },
    { id: 65, name: "Support chat completed", detail: "Workspace provisioning", status: "Chat", owner: "Sam Rivera", updated: "Feb 19", company: "Layers", contact: "Theo Brooks" },
  ],
};

const toneFor = (status: string): Tone => {
  if (["Customer", "Qualified", "Won", "Resolved", "Complete", "Champion"].includes(status)) return "green";
  if (["Open", "New", "Email", "Decision maker"].includes(status)) return "blue";
  if (["Waiting", "Contacted", "In progress", "Evaluator"].includes(status)) return "amber";
  if (["Archived", "Lost"].includes(status)) return "red";
  if (["Call", "Stakeholder"].includes(status)) return "purple";
  return "neutral";
};

const initials = (name: string) =>
  name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

export function CRMWorkspace({
  section,
  onSectionChange,
  onToast,
}: {
  section: CRMSection;
  onSectionChange: (section: CRMSection) => void;
  onToast: (message: string) => void;
}) {
  const [data, setData] = useState(initialData);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All statuses");
  const [showArchived, setShowArchived] = useState(false);
  const [sort, setSort] = useState<"name" | "updated" | "status">("updated");
  const [sortAsc, setSortAsc] = useState(false);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number[]>([]);
  const [detail, setDetail] = useState<CRMRecord | null>(null);
  const [editing, setEditing] = useState<CRMRecord | null>(null);
  const [creating, setCreating] = useState(false);
  const [formName, setFormName] = useState("");
  const [formCompany, setFormCompany] = useState("");
  const [formStatus, setFormStatus] = useState("New");
  const [view, setView] = useState<"table" | "kanban">("table");
  const [loading, setLoading] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [enrichmentError, setEnrichmentError] = useState(true);
  const [confirmArchive, setConfirmArchive] = useState<CRMRecord | null>(null);
  const pageSize = 4;

  useEffect(() => {
    setLoading(true);
    setSearch("");
    setStatusFilter("All statuses");
    setSelected([]);
    setPage(1);
    setDetail(null);
    const timer = window.setTimeout(() => setLoading(false), 280);
    return () => window.clearTimeout(timer);
  }, [section]);

  const records = data[section];
  const statuses = [...new Set(records.map((record) => record.status))];
  const visible = useMemo(() => {
    const filtered = records
      .filter((record) => (showArchived ? record.archived : !record.archived))
      .filter((record) => statusFilter === "All statuses" || record.status === statusFilter)
      .filter((record) => `${record.name} ${record.detail} ${record.company || ""} ${record.owner}`.toLowerCase().includes(search.toLowerCase()));
    return [...filtered].sort((a, b) => {
      const comparison = String(a[sort]).localeCompare(String(b[sort]));
      return sortAsc ? comparison : -comparison;
    });
  }, [records, showArchived, statusFilter, search, sort, sortAsc]);
  const pageCount = Math.max(1, Math.ceil(visible.length / pageSize));
  const pageRows = visible.slice((page - 1) * pageSize, page * pageSize);

  const changeSort = (next: typeof sort) => {
    if (sort === next) setSortAsc(!sortAsc);
    else {
      setSort(next);
      setSortAsc(true);
    }
  };

  const openCreate = () => {
    setEditing(null);
    setFormName("");
    setFormCompany("");
    setFormStatus(section === "Companies" ? "Prospect" : section === "Customer inquiries" ? "Open" : "New");
    setCreating(true);
  };

  const openEdit = (record: CRMRecord) => {
    setEditing(record);
    setFormName(record.name);
    setFormCompany(record.company || "");
    setFormStatus(record.status);
    setCreating(true);
  };

  const saveRecord = () => {
    if (editing) {
      setData((current) => ({
        ...current,
        [section]: current[section].map((record) =>
          record.id === editing.id ? { ...record, name: formName, company: formCompany || record.company, status: formStatus, updated: "Just now" } : record,
        ),
      }));
      setDetail((current) => current && { ...current, name: formName, company: formCompany || current.company, status: formStatus, updated: "Just now" });
      onToast(`${formName} was updated`);
    } else {
      const newRecord: CRMRecord = {
        id: Date.now(),
        name: formName,
        detail: formCompany ? `${formCompany} · Created in ATLAS` : "Created in ATLAS",
        status: formStatus,
        owner: appConfig.user.name,
        updated: "Just now",
        company: formCompany || undefined,
        stage: section === "Opportunities" ? formStatus : undefined,
      };
      setData((current) => ({ ...current, [section]: [newRecord, ...current[section]] }));
      onToast(`${formName} was created`);
    }
    setCreating(false);
  };

  const archiveRecord = (record: CRMRecord) => {
    setData((current) => ({
      ...current,
      [section]: current[section].map((item) =>
        item.id === record.id ? { ...item, archived: true, status: "Archived", updated: "Just now" } : item,
      ),
    }));
    setDetail(null);
    setConfirmArchive(null);
    onToast(`${record.name} was archived`);
  };

  const restoreRecord = (record: CRMRecord) => {
    setData((current) => ({
      ...current,
      [section]: current[section].map((item) =>
        item.id === record.id ? { ...item, archived: false, status: section === "Companies" ? "Prospect" : "New", updated: "Just now" } : item,
      ),
    }));
    setDetail(null);
    onToast(`${record.name} was restored`);
  };

  const updateStage = (record: CRMRecord, stage: string) => {
    setData((current) => ({
      ...current,
      Opportunities: current.Opportunities.map((item) =>
        item.id === record.id ? { ...item, stage, status: stage, updated: "Just now" } : item,
      ),
    }));
    onToast(`${record.name} moved to ${stage}`);
  };

  const currentMeta = sections.find((item) => item.label === section)!;
  const currentContent = sectionContent[section];
  const CurrentIcon = currentMeta.icon;

  return (
    <main className="crm-main">
      <div className="page-heading crm-heading">
        <div>
          <div className="eyebrow"><span className="live-dot" /> {appConfig.organization.name} · CRM</div>
          <h1>{section}</h1>
          <p>{currentContent.description}</p>
        </div>
        <div className="page-actions">
          {section === "Opportunities" && (
            <div className="view-switch" aria-label="Opportunity view">
              <button className={view === "table" ? "active" : ""} onClick={() => setView("table")} aria-label="Table view"><LayoutList size={15} /></button>
              <button className={view === "kanban" ? "active" : ""} onClick={() => setView("kanban")} aria-label="Kanban view"><Columns3 size={15} /></button>
            </div>
          )}
          <Button variant="primary" onClick={openCreate}><Plus size={16} /> New {currentContent.singular}</Button>
        </div>
      </div>

      <nav className="crm-tabs" aria-label="CRM sections">
        {sections.map(({ label, short, icon: Icon }) => (
          <button className={section === label ? "active" : ""} aria-current={section === label ? "page" : undefined} key={label} onClick={() => onSectionChange(label)}>
            <Icon size={15} /><span>{short}</span>
          </button>
        ))}
      </nav>

      {section === "Opportunities" && view === "kanban" ? (
        <OpportunityKanban records={records.filter((record) => !record.archived)} onOpen={setDetail} onStageChange={updateStage} />
      ) : (
        <section className="panel crm-table-panel">
          <div className="crm-toolbar">
            <label className="crm-search">
              <Search size={15} />
              <input
                value={search}
                onChange={(event) => { setSearch(event.target.value); setPage(1); }}
                placeholder={`Search ${currentMeta.short.toLowerCase()}`}
                aria-label={`Search ${currentMeta.short.toLowerCase()}`}
              />
              {search && <button aria-label="Clear search" onClick={() => setSearch("")}><X size={14} /></button>}
            </label>
            <div className="crm-toolbar-actions">
              <Button size="sm" variant={statusFilter !== "All statuses" || showArchived ? "primary" : "secondary"} onClick={() => setFilterOpen(true)}>
                <Filter size={14} /> Filters{statusFilter !== "All statuses" || showArchived ? " · 1" : ""}
              </Button>
              {selected.length > 0 && (
                <Button size="sm" variant="secondary" onClick={() => {
                  setData((current) => ({ ...current, [section]: current[section].map((record) => selected.includes(record.id) ? { ...record, archived: true, status: "Archived" } : record) }));
                  setSelected([]);
                  onToast("Selected records were archived");
                }}><Archive size={14} /> Archive {selected.length}</Button>
              )}
            </div>
          </div>

          <div className="crm-table-scroll">
            <div className="crm-table" role="table" aria-label={`${section} records`}>
              <div className="crm-table-row crm-table-head" role="row">
                <span><input type="checkbox" aria-label="Select all visible records" checked={pageRows.length > 0 && pageRows.every((record) => selected.includes(record.id))} onChange={(event) => setSelected(event.target.checked ? [...new Set([...selected, ...pageRows.map((record) => record.id)])] : selected.filter((id) => !pageRows.some((record) => record.id === id)))} /></span>
                <button onClick={() => changeSort("name")}>Name {sort === "name" && (sortAsc ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}</button>
                <span>{section === "Companies" ? "Account detail" : section === "Contacts" ? "Company" : "Context"}</span>
                <button onClick={() => changeSort("status")}>Status {sort === "status" && (sortAsc ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}</button>
                <span>Owner</span>
                <button onClick={() => changeSort("updated")}>Updated {sort === "updated" && (sortAsc ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}</button>
                <span />
              </div>
              {loading ? (
                <TableLoading />
              ) : pageRows.length ? (
                pageRows.map((record) => (
                  <div className="crm-table-row" role="row" key={record.id}>
                    <span><input type="checkbox" aria-label={`Select ${record.name}`} checked={selected.includes(record.id)} onChange={(event) => setSelected(event.target.checked ? [...selected, record.id] : selected.filter((id) => id !== record.id))} /></span>
                    <button className="crm-primary-cell" onClick={() => setDetail(record)}>
                      <Avatar initials={initials(record.name)} tone={toneFor(record.status)} size="sm" />
                      <span><strong>{record.name}</strong>{record.archived && <small>Archived record</small>}</span>
                    </button>
                    <span className="crm-secondary-cell">{record.company || record.detail}</span>
                    <span><Badge tone={toneFor(record.status)}>{record.status}</Badge></span>
                    <span className="crm-owner"><Avatar initials={initials(record.owner)} size="sm" />{record.owner}</span>
                    <span className="crm-updated">{record.updated}</span>
                    <button className="crm-more" aria-label={`Open ${record.name}`} onClick={() => setDetail(record)}><MoreHorizontal size={16} /></button>
                  </div>
                ))
              ) : (
                <div className="crm-empty">
                  <CurrentIcon size={24} />
                  <strong>{search || statusFilter !== "All statuses" ? "No matching records" : `No ${currentMeta.short.toLowerCase()} yet`}</strong>
                  <p>{search || statusFilter !== "All statuses" ? "Change your search or filters and try again." : "Create the first record to begin building this workspace."}</p>
                  {(search || statusFilter !== "All statuses") ? <Button size="sm" onClick={() => { setSearch(""); setStatusFilter("All statuses"); }}>Clear filters</Button> : <Button size="sm" variant="primary" onClick={openCreate}><Plus size={14} /> Create record</Button>}
                </div>
              )}
            </div>
          </div>
          <div className="crm-pagination">
            <span>{visible.length ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, visible.length)} of ${visible.length}` : "0 records"}</span>
            <div><Button size="icon" variant="ghost" disabled={page === 1} aria-label="Previous page" onClick={() => setPage(page - 1)}><ChevronLeft size={15} /></Button><span>Page {page} of {pageCount}</span><Button size="icon" variant="ghost" disabled={page === pageCount} aria-label="Next page" onClick={() => setPage(page + 1)}><ChevronRight size={15} /></Button></div>
          </div>
        </section>
      )}

      {filterOpen && (
        <>
          <button className="drawer-backdrop" aria-label="Close filters" onClick={() => setFilterOpen(false)} />
          <aside className="drawer" aria-label={`${section} filters`}>
            <div className="drawer-header"><div><h2>Filter {currentMeta.short.toLowerCase()}</h2><p>Refine the records shown in this view.</p></div><Button size="icon" variant="ghost" aria-label="Close filters" onClick={() => setFilterOpen(false)}><X size={17} /></Button></div>
            <div className="drawer-content">
              <label className="field"><span>Status</span><select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}><option>All statuses</option>{statuses.map((status) => <option key={status}>{status}</option>)}</select></label>
              <label className="field"><span>Owner</span><select><option>All owners</option><option>Olivia Martin</option><option>Sam Rivera</option><option>Maya Chen</option></select></label>
              <label className="toggle-row"><span><strong>Archived records</strong><small>Show archived records instead of active records.</small></span><input type="checkbox" checked={showArchived} onChange={(event) => { setShowArchived(event.target.checked); setPage(1); }} /></label>
            </div>
            <div className="drawer-footer"><Button variant="ghost" onClick={() => { setStatusFilter("All statuses"); setShowArchived(false); }}>Reset</Button><Button variant="primary" onClick={() => setFilterOpen(false)}>Apply filters</Button></div>
          </aside>
        </>
      )}

      {detail && (
        <>
          <button className="drawer-backdrop" aria-label="Close record details" onClick={() => setDetail(null)} />
          <aside className="drawer crm-detail-drawer" aria-label={`${detail.name} details`}>
            <div className="drawer-header">
              <div className="drawer-title-with-avatar"><Avatar initials={initials(detail.name)} tone={toneFor(detail.status)} /><div><h2>{detail.name}</h2><p>{section.replace("Customer ", "")} record</p></div></div>
              <Button size="icon" variant="ghost" aria-label="Close record details" onClick={() => setDetail(null)}><X size={17} /></Button>
            </div>
            <div className="drawer-content">
              <div className="detail-status"><Badge tone={toneFor(detail.status)}>{detail.status}</Badge><span>Updated {detail.updated}</span></div>
              <div className="record-properties">
                <div><span>Owner</span><strong><Avatar initials={initials(detail.owner)} size="sm" />{detail.owner}</strong></div>
                {detail.company && <div><span>Company</span><strong><Building2 size={14} />{detail.company}</strong></div>}
                {detail.contact && <div><span>Contact</span><strong><UserRound size={14} />{detail.contact}</strong></div>}
                <div><span>Record ID</span><strong>AT-{detail.id}</strong></div>
              </div>

              {section === "Leads" && <LeadPrediction record={detail} />}
              {section === "Customer inquiries" && (
                <section className="drawer-section">
                  <div className="drawer-section-title"><h3>Inquiry management</h3><Badge tone="blue">Follow-up</Badge></div>
                  <label className="field"><span>Status</span><select value={detail.status} onChange={(event) => {
                    const status = event.target.value;
                    setDetail({ ...detail, status });
                    setData((current) => ({ ...current, [section]: current[section].map((record) => record.id === detail.id ? { ...record, status } : record) }));
                  }}><option>Open</option><option>In progress</option><option>Waiting</option><option>Resolved</option></select></label>
                  <div className="inquiry-actions"><Button size="sm" onClick={() => onToast("Follow-up task created")}><CalendarCheck size={14} /> Create follow-up</Button><Button size="sm" onClick={() => onToast("Reply composer opened")}><Mail size={14} /> Reply</Button></div>
                </section>
              )}
              {section === "Opportunities" && (
                <section className="drawer-section">
                  <h3>Opportunity stage</h3>
                  <label className="field"><span>Current stage</span><select value={detail.stage} onChange={(event) => { updateStage(detail, event.target.value); setDetail({ ...detail, stage: event.target.value, status: event.target.value }); }}><option>New</option><option>Contacted</option><option>Qualified</option><option>Won</option><option>Lost</option></select></label>
                  <div className="linked-records"><span>Linked records</span><button><Target size={14} /> Lead · {detail.contact || "Unassigned"}<ChevronRight size={14} /></button><button><Building2 size={14} /> Company · {detail.company}<ChevronRight size={14} /></button></div>
                </section>
              )}
              {(section === "Companies" || section === "Contacts") && (
                <>
                  <section className="drawer-section">
                    <div className="drawer-section-title"><h3>Related records</h3><span>3 records</span></div>
                    <div className="related-list"><button><Target size={14} /><span><strong>Enterprise evaluation</strong><small>Qualified lead</small></span><ChevronRight size={14} /></button><button><Columns3 size={14} /><span><strong>Workspace rollout</strong><small>Open opportunity</small></span><ChevronRight size={14} /></button></div>
                  </section>
                  <section className="drawer-section">
                    <div className="drawer-section-title"><h3>Company enrichment</h3></div>
                    {enrichmentError ? <div className="inline-error"><CircleAlert size={16} /><span><strong>Enrichment unavailable</strong><small>The enrichment provider did not return data.</small></span><Button size="sm" onClick={() => setEnrichmentError(false)}><RefreshCw size={13} /> Retry</Button></div> : <div className="inline-success"><Check size={15} /> Enrichment checked · No new fields</div>}
                  </section>
                </>
              )}
              <section className="drawer-section">
                <div className="drawer-section-title"><h3>Recent activity</h3><button>View all</button></div>
                <div className="mini-timeline"><div><span /><p><strong>Record updated</strong><small>Olivia Martin · {detail.updated}</small></p></div><div><span /><p><strong>Customer interaction logged</strong><small>Email · Yesterday</small></p></div></div>
              </section>
              {detail.restricted && <div className="permission-state"><LockKeyhole size={18} /><span><strong>System-managed record</strong><small>You can view this interaction, but editing requires administrator permission.</small></span></div>}
            </div>
            <div className="drawer-footer">
              {detail.archived ? <Button variant="secondary" onClick={() => restoreRecord(detail)}><RotateCcw size={14} /> Restore</Button> : <Button variant="ghost" disabled={detail.restricted} title={detail.restricted ? "Administrator permission required" : undefined} onClick={() => setConfirmArchive(detail)}><Archive size={14} /> Archive</Button>}
              <Button variant="primary" disabled={detail.restricted || detail.archived} onClick={() => openEdit(detail)}><Edit3 size={14} /> Edit record</Button>
            </div>
          </aside>
        </>
      )}

      <Modal open={creating} title={editing ? `Edit ${currentContent.singular}` : `New ${currentContent.singular}`} description={editing ? "Update this record in ATLAS." : `Create a connected ${currentContent.singular} record.`} onClose={() => setCreating(false)}>
        <form onSubmit={(event) => { event.preventDefault(); saveRecord(); }}>
          <div className="dialog-body">
            <label className="field"><span>Name</span><input autoFocus value={formName} onChange={(event) => setFormName(event.target.value)} placeholder={`Enter ${currentContent.singular} name`} aria-invalid={formName.length > 0 && formName.trim().length < 2} /><small className="field-help">{formName.length > 0 && formName.trim().length < 2 ? "Use at least two characters." : "Required"}</small></label>
            {section !== "Companies" && <label className="field"><span>Company</span><input value={formCompany} onChange={(event) => setFormCompany(event.target.value)} placeholder="Link a company" /></label>}
            <label className="field"><span>Status</span><select value={formStatus} onChange={(event) => setFormStatus(event.target.value)}>{section === "Companies" ? <><option>Prospect</option><option>Customer</option></> : section === "Customer inquiries" ? <><option>Open</option><option>In progress</option><option>Waiting</option><option>Resolved</option></> : section === "Opportunities" ? <><option>New</option><option>Contacted</option><option>Qualified</option><option>Won</option><option>Lost</option></> : <><option>New</option><option>In progress</option><option>Complete</option></>}</select></label>
          </div>
          <div className="dialog-footer"><Button type="button" onClick={() => setCreating(false)}>Cancel</Button><Button type="submit" variant="primary" disabled={formName.trim().length < 2}>{editing ? "Save changes" : "Create record"}</Button></div>
        </form>
      </Modal>

      <Modal open={!!confirmArchive} title="Archive record?" description="Archived records are hidden from active views but can be restored later." onClose={() => setConfirmArchive(null)}>
        <div className="confirm-content"><Archive size={20} /><p><strong>{confirmArchive?.name}</strong> and its history will remain available in archived records.</p></div>
        <div className="dialog-footer"><Button onClick={() => setConfirmArchive(null)}>Cancel</Button><Button variant="danger" onClick={() => confirmArchive && archiveRecord(confirmArchive)}><Trash2 size={14} /> Archive record</Button></div>
      </Modal>
    </main>
  );
}

function TableLoading() {
  return (
    <div aria-label="Loading records" role="status">
      {[1, 2, 3, 4].map((item) => <div className="crm-table-row skeleton-row" key={item}><span /><i /><i /><i /><i /><i /></div>)}
    </div>
  );
}

function LeadPrediction({ record }: { record: CRMRecord }) {
  return (
    <section className="drawer-section prediction-section">
      <div className="drawer-section-title"><h3>Lead prediction</h3>{record.score && <Badge tone={record.score > 75 ? "green" : "amber"}>{record.score}/100</Badge>}</div>
      {record.score ? (
        <>
          <div className="score-gauge"><span style={{ width: `${record.score}%` }} /></div>
          <div className="prediction-grid"><div><span>Fit</span><strong>{record.score > 75 ? "Strong" : "Moderate"}</strong></div><div><span>Intent</span><strong>{record.score > 80 ? "High" : "Medium"}</strong></div><div><span>Data quality</span><strong>{record.score > 75 ? "Complete" : "Partial"}</strong></div></div>
          <div className="prediction-note"><Sparkles size={15} /><p><strong>Likely to progress</strong><small>Based on profile completeness and recent engagement in the available customer records.</small></p></div>
        </>
      ) : (
        <div className="prediction-unavailable"><Zap size={18} /><strong>Prediction unavailable</strong><p>There is not enough activity to calculate a reliable score. Add an interaction or complete the lead profile.</p><Button size="sm" disabled>Generate prediction</Button></div>
      )}
    </section>
  );
}

function OpportunityKanban({
  records,
  onOpen,
  onStageChange,
}: {
  records: CRMRecord[];
  onOpen: (record: CRMRecord) => void;
  onStageChange: (record: CRMRecord, stage: string) => void;
}) {
  const stages = ["New", "Contacted", "Qualified", "Won", "Lost"];
  return (
    <div className="kanban-board" aria-label="Opportunity pipeline">
      {stages.map((stage) => {
        const stageRecords = records.filter((record) => record.stage === stage);
        return (
          <section className="kanban-column" key={stage}>
            <header><span className={`status-dot dot-${toneFor(stage)}`} /><strong>{stage}</strong><Badge>{stageRecords.length}</Badge></header>
            <div className="kanban-stack">
              {stageRecords.map((record) => (
                <article className="kanban-card" key={record.id}>
                  <button className="kanban-card-title" onClick={() => onOpen(record)}><strong>{record.name}</strong><MoreHorizontal size={15} /></button>
                  <p>{record.company} · {record.contact}</p>
                  <div><Avatar initials={initials(record.owner)} size="sm" /><select value={record.stage} aria-label={`Move ${record.name}`} onChange={(event) => onStageChange(record, event.target.value)}>{stages.map((nextStage) => <option key={nextStage}>{nextStage}</option>)}</select></div>
                </article>
              ))}
              {!stageRecords.length && <div className="kanban-empty">No opportunities</div>}
            </div>
          </section>
        );
      })}
    </div>
  );
}
