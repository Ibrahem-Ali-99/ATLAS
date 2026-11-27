import { useEffect, useMemo, useRef, useState } from "react";
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
import { ApiError } from "@/data/client";
import { archiveCrm, createFollowUp, createLeadPrediction, failureMessage, getLeadPrediction, loadCrm, loadTeam, restoreCrm, saveCrm, type LeadPredictionResult } from "@/data/resources";
import { Avatar, Badge, Button, Modal, type Tone } from "./components";
import { appConfig, workspace } from "./appConfig";

export type CRMSection =
  | "Companies"
  | "Contacts"
  | "Leads"
  | "Customer inquiries"
  | "Opportunities"
  | "Tasks"
  | "Customer interactions";

type CRMRecord = {
  id: string;
  name: string;
  detail: string;
  status: string;
  owner: string;
  ownerId?: string;
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

const emptyCrm = (): Record<CRMSection, CRMRecord[]> => ({
  Companies: [],
  Contacts: [],
  Leads: [],
  "Customer inquiries": [],
  Opportunities: [],
  Tasks: [],
  "Customer interactions": [],
});

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
  focusQuery = "",
  onOpenInbox,
}: {
  section: CRMSection;
  onSectionChange: (section: CRMSection) => void;
  onToast: (message: string) => void;
  focusQuery?: string;
  onOpenInbox?: () => void;
}) {
  const [data, setData] = useState(emptyCrm);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All statuses");
  const [ownerFilter, setOwnerFilter] = useState("All owners");
  const pendingQuery = useRef("");
  const appliedFocus = useRef("");
  const [showArchived, setShowArchived] = useState(false);
  const [sort, setSort] = useState<"name" | "updated" | "status">("updated");
  const [sortAsc, setSortAsc] = useState(false);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [detail, setDetail] = useState<CRMRecord | null>(null);
  const [editing, setEditing] = useState<CRMRecord | null>(null);
  const [creating, setCreating] = useState(false);
  const [formName, setFormName] = useState("");
  const [formCompany, setFormCompany] = useState("");
  const [formStatus, setFormStatus] = useState("New");
  const [formOwner, setFormOwner] = useState("");
  const [members, setMembers] = useState<{ user_id: string; full_name: string }[]>([]);
  const [view, setView] = useState<"table" | "kanban">("table");
  const [loading, setLoading] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState<CRMRecord | null>(null);
  const pageSize = 4;
  useEffect(() => {
    loadTeam().then((rows) => setMembers(rows.map((member) => ({ user_id: member.user_id, full_name: member.full_name })))).catch(() => undefined);
  }, []);
  useEffect(() => {
    if (!filterOpen) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setFilterOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filterOpen]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const queued = pendingQuery.current;
    pendingQuery.current = "";
    if (queued) setSearch(queued);
    else if (focusQuery && focusQuery !== appliedFocus.current) {
      appliedFocus.current = focusQuery;
      setSearch(focusQuery);
    } else setSearch("");
    setStatusFilter("All statuses");
    setSelected([]);
    setPage(1);
    setDetail(null);
    loadCrm()
      .then((next) => {
        if (!cancelled) {
          setData(next);
          setLoadError(null);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) setLoadError(failureMessage(error));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [section, workspace.organizationId, focusQuery]);

  const records = data[section];
  const statuses = [...new Set(records.map((record) => record.status))];
  const visible = useMemo(() => {
    const filtered = records
      .filter((record) => (showArchived ? record.archived : !record.archived))
      .filter((record) => statusFilter === "All statuses" || record.status === statusFilter)
      .filter((record) => ownerFilter === "All owners" || record.owner === ownerFilter)
      .filter((record) => `${record.name} ${record.detail} ${record.company || ""} ${record.owner}`.toLowerCase().includes(search.toLowerCase()));
    return [...filtered].sort((a, b) => {
      const comparison = String(a[sort]).localeCompare(String(b[sort]));
      return sortAsc ? comparison : -comparison;
    });
  }, [records, showArchived, statusFilter, ownerFilter, search, sort, sortAsc]);
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
    setFormStatus(section === "Leads" || section === "Opportunities" ? "New" : section === "Tasks" ? "Open" : "");
    setFormOwner("");
    setCreating(true);
  };

  const openEdit = (record: CRMRecord) => {
    setEditing(record);
    setFormName(record.name);
    setFormCompany(record.company || "");
    setFormStatus(record.status);
    setFormOwner(record.ownerId || "");
    setCreating(true);
  };

  const refresh = () => loadCrm().then(setData).catch((error: unknown) => onToast(failureMessage(error)));

  const saveRecord = () => {
    void saveCrm(section, { id: editing?.id, name: formName, company: formCompany, status: formStatus, ownerId: formOwner }, data.Companies, data.Leads)
      .then(() => {
        setCreating(false);
        onToast(editing ? `${formName} was updated` : `${formName} was created`);
        return refresh();
      })
      .catch((error: unknown) => onToast(failureMessage(error)));
  };

  const archiveRecord = (record: CRMRecord) => {
    void archiveCrm(section, record.id)
      .then(() => {
        setDetail(null);
        setConfirmArchive(null);
        onToast(`${record.name} was archived`);
        return refresh();
      })
      .catch((error: unknown) => onToast(failureMessage(error)));
  };

  const restoreRecord = (record: CRMRecord) => {
    void restoreCrm(section, record.id)
      .then(() => {
        setDetail(null);
        onToast(`${record.name} was restored`);
        return refresh();
      })
      .catch((error: unknown) => onToast(failureMessage(error)));
  };

  const updateStage = (record: CRMRecord, stage: string) => {
    void saveCrm("Opportunities", { id: record.id, name: record.name, company: record.company, status: stage }, data.Companies, data.Leads)
      .then(() => {
        onToast(`${record.name} moved to ${stage}`);
        return refresh();
      })
      .catch((error: unknown) => onToast(failureMessage(error)));
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

      {loadError ? <div className="auth-error" role="alert">{loadError}</div> : null}
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
              <Button size="sm" variant={statusFilter !== "All statuses" || ownerFilter !== "All owners" || showArchived ? "primary" : "secondary"} onClick={() => setFilterOpen(true)}>
                <Filter size={14} /> Filters{statusFilter !== "All statuses" || ownerFilter !== "All owners" || showArchived ? " · 1" : ""}
              </Button>
              {selected.length > 0 && (
                <Button size="sm" variant="secondary" onClick={() => {
                  void Promise.all(selected.map((id) => archiveCrm(section, id)))
                    .then(() => {
                      setSelected([]);
                      onToast("Selected records were archived");
                      return loadCrm().then(setData);
                    })
                    .catch((error: unknown) => onToast(failureMessage(error)));
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
              <label className="field"><span>Owner</span><select value={ownerFilter} onChange={(event) => { setOwnerFilter(event.target.value); setPage(1); }}><option>All owners</option>{[...new Set(records.map((record) => record.owner).filter(Boolean))].map((owner) => <option key={owner}>{owner}</option>)}</select></label>
              <label className="toggle-row"><span><strong>Archived records</strong><small>Show archived records instead of active records.</small></span><input type="checkbox" checked={showArchived} onChange={(event) => { setShowArchived(event.target.checked); setPage(1); }} /></label>
            </div>
            <div className="drawer-footer"><Button variant="ghost" onClick={() => { setStatusFilter("All statuses"); setOwnerFilter("All owners"); setShowArchived(false); }}>Reset</Button><Button variant="primary" onClick={() => setFilterOpen(false)}>Apply filters</Button></div>
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
                  <div className="drawer-section-title"><h3>Inquiry</h3><Badge tone="blue">{detail.status}</Badge></div>
                  <p className="detail-copy">{detail.detail}</p>
                  <div className="inquiry-actions"><Button size="sm" onClick={() => { void createFollowUp(`Follow up: ${detail.name}`, detail.detail).then(() => onToast("Follow-up task created")).catch((error: unknown) => onToast(failureMessage(error))); }}><CalendarCheck size={14} /> Create follow-up</Button>{onOpenInbox && <Button size="sm" onClick={onOpenInbox}><Mail size={14} /> Open inbox</Button>}</div>
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
                <section className="drawer-section">
                  <div className="drawer-section-title"><h3>Related records</h3></div>
                  <RelatedRecords section={section} detail={detail} data={data} onOpen={(next, query) => { pendingQuery.current = query; setDetail(null); onSectionChange(next); }} />
                </section>
              )}
              <section className="drawer-section">
                <div className="drawer-section-title"><h3>Recent activity</h3></div>
                <div className="mini-timeline"><div><span /><p><strong>Record updated</strong><small>{detail.updated || "Stored record"}</small></p></div></div>
              </section>
              {detail.restricted && <div className="permission-state"><LockKeyhole size={18} /><span><strong>System-managed record</strong><small>You can view this interaction, but editing requires administrator permission.</small></span></div>}
            </div>
            <div className="drawer-footer">
              {detail.archived ? <Button variant="secondary" onClick={() => restoreRecord(detail)}><RotateCcw size={14} /> Restore</Button> : <Button variant="ghost" disabled={detail.restricted} title={detail.restricted ? "Administrator permission required" : undefined} onClick={() => setConfirmArchive(detail)}><Archive size={14} /> Archive</Button>}
              <Button variant="primary" disabled={detail.restricted || detail.archived || section === "Customer interactions"} onClick={() => openEdit(detail)}><Edit3 size={14} /> Edit record</Button>
            </div>
          </aside>
        </>
      )}

      <Modal open={creating} title={editing ? `Edit ${currentContent.singular}` : `New ${currentContent.singular}`} description={editing ? "Update this record in ATLAS." : `Create a connected ${currentContent.singular} record.`} onClose={() => setCreating(false)}>
        <form onSubmit={(event) => { event.preventDefault(); saveRecord(); }}>
          <div className="dialog-body">
            <label className="field"><span>Name</span><input autoFocus readOnly={section === "Tasks" && !!editing} value={formName} onChange={(event) => setFormName(event.target.value)} placeholder={`Enter ${currentContent.singular} name`} aria-invalid={formName.length > 0 && formName.trim().length < 2} /><small className="field-help">{section === "Tasks" && editing ? "Task edits store the status. Create a new task to change the title." : formName.length > 0 && formName.trim().length < 2 ? "Use at least two characters." : "Required"}</small></label>
            {section !== "Companies" && <label className="field"><span>{section === "Customer inquiries" ? "Message" : "Company"}</span><input value={formCompany} onChange={(event) => setFormCompany(event.target.value)} placeholder={section === "Customer inquiries" ? "Stored inquiry message" : "Link a company"} /></label>}
            {section === "Contacts" && <label className="field"><span>Title</span><input value={formStatus} onChange={(event) => setFormStatus(event.target.value)} placeholder="Role" /></label>}
            {(section === "Leads" || section === "Opportunities" || section === "Tasks") && <label className="field"><span>Status</span><select value={formStatus} onChange={(event) => setFormStatus(event.target.value)}>{section === "Opportunities" ? <><option>New</option><option>Contacted</option><option>Qualified</option><option>Won</option><option>Lost</option></> : section === "Tasks" ? <><option>Open</option><option>In progress</option><option>Complete</option></> : <><option>New</option><option>Contacted</option><option>Qualified</option><option>Unqualified</option><option>Won</option><option>Lost</option></>}</select></label>}
            {(section === "Leads" || section === "Opportunities") && <label className="field"><span>Owner</span><select aria-label="Record owner" value={formOwner} onChange={(event) => setFormOwner(event.target.value)}><option value="">Unassigned</option>{members.map((member) => <option key={member.user_id} value={member.user_id}>{member.full_name}</option>)}</select></label>}
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

function RelatedRecords({ section, detail, data, onOpen }: { section: CRMSection; detail: CRMRecord; data: Record<CRMSection, CRMRecord[]>; onOpen: (section: CRMSection, query: string) => void }) {
  const company = section === "Companies" ? detail.name : detail.company;
  const related = [
    ...data.Leads.filter((record) => record.company === company).map((record) => ({ record, section: "Leads" as CRMSection, icon: Target })),
    ...data.Opportunities.filter((record) => record.company === company).map((record) => ({ record, section: "Opportunities" as CRMSection, icon: Columns3 })),
    ...data.Contacts.filter((record) => record.company === company && record.id !== detail.id).map((record) => ({ record, section: "Contacts" as CRMSection, icon: Contact })),
  ].slice(0, 6);
  if (!related.length) return <p className="detail-copy">No related records are stored for this account.</p>;
  return <div className="related-list">{related.map(({ record, section: next, icon: Icon }) => <button key={`${next}-${record.id}`} onClick={() => onOpen(next, record.name)}><Icon size={14} /><span><strong>{record.name}</strong><small>{record.status}</small></span><ChevronRight size={14} /></button>)}</div>;
}

function TableLoading() {
  return (
    <div aria-label="Loading records" role="status">
      {[1, 2, 3, 4].map((item) => <div className="crm-table-row skeleton-row" key={item}><span /><i /><i /><i /><i /><i /></div>)}
    </div>
  );
}

function LeadPrediction({ record }: { record: CRMRecord }) {
  const [prediction, setPrediction] = useState<LeadPredictionResult | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let cancelled = false;
    setPrediction(null);
    setMissing(false);
    setError("");
    getLeadPrediction(record.id)
      .then((next) => { if (!cancelled) setPrediction(next); })
      .catch((cause: unknown) => {
        if (cancelled) return;
        if (cause instanceof ApiError && cause.status === 404) setMissing(true);
        else setError(failureMessage(cause));
      });
    return () => { cancelled = true; };
  }, [record.id]);
  function generate() {
    setBusy(true);
    setError("");
    createLeadPrediction(record.id)
      .then((next) => { setPrediction(next); setMissing(false); })
      .catch((cause: unknown) => setError(failureMessage(cause)))
      .finally(() => setBusy(false));
  }
  const percent = prediction ? Math.round(Math.min(1, Math.max(0, prediction.probability)) * 100) : 0;
  return (
    <section className="drawer-section prediction-section">
      <div className="drawer-section-title"><h3>Lead prediction</h3>{prediction && <Badge tone={percent >= 75 ? "green" : "amber"}>{percent}/100</Badge>}</div>
      {prediction ? (
        <>
          <div className="score-gauge"><span style={{ width: `${percent}%` }} /></div>
          <div className="prediction-grid"><div><span>Label</span><strong>{prediction.label}</strong></div><div><span>Confidence</span><strong>{prediction.confidence == null ? "Not stored" : prediction.confidence.toFixed(2)}</strong></div><div><span>Model</span><strong>{prediction.model_version}</strong></div></div>
          <div className="prediction-note"><Sparkles size={15} /><p><strong>{prediction.explanation}</strong><small>{prediction.notice}</small></p></div>
          <Button size="sm" disabled={busy} onClick={generate}>{busy ? "Generating" : "Generate prediction"}</Button>
        </>
      ) : (
        <div className="prediction-unavailable"><Zap size={18} /><strong>{error ? "Prediction failed" : "Prediction unavailable"}</strong><p>{error || (missing ? "No prediction is stored for this lead yet." : "Loading the stored prediction.")}</p><Button size="sm" disabled={busy || (!missing && !error)} onClick={generate}>{busy ? "Generating" : "Generate prediction"}</Button></div>
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
